"""WooCommerce-Bestellungen lesen und in Rechnungsdaten übersetzen (docs/domain/woocommerce.md).

Nur reine Funktionen auf dem JSON der WooCommerce REST API (v3), ohne Netzwerk.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.domain.geld import cent_zu_euro

# Rechnung sofort bei Bestellung (Vorkasse), sonst erst wenn bezahlt
VORKASSE = {"bacs"}
ZAHLUNGSARTEN = {
    "bacs": "ueberweisung",
    "paypal": "paypal",
    "ppcp-gateway": "paypal",
    "ppec_paypal": "paypal",
    "stripe": "karte",
    "woocommerce_payments": "karte",
    "cod": "bar",
}
BEZAHLT = {"processing", "completed"}
LAENDER = {
    "DE": "Deutschland",
    "AT": "Österreich",
    "CH": "Schweiz",
    "NL": "Niederlande",
    "BE": "Belgien",
    "FR": "Frankreich",
    "IT": "Italien",
    "ES": "Spanien",
    "PL": "Polen",
    "DK": "Dänemark",
    "LU": "Luxemburg",
}


class BestellungUngueltig(ValueError):
    pass


@dataclass(frozen=True)
class Position:
    bezeichnung: str
    menge_tausendstel: int
    einzelpreis_cent: int
    beschreibung: str | None = None


@dataclass
class Bestellung:
    externe_id: int
    nummer: str
    status: str
    erstellt_am: date
    bezahlt_am: date | None
    zahlungsart_shop: str
    zahlungsart: str
    transaktion: str | None
    summe_cent: int
    erstattet_cent: int
    kunde: dict
    positionen: list[Position] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)

    @property
    def bezahlt(self) -> bool:
        return self.bezahlt_am is not None and self.status in BEZAHLT

    @property
    def braucht_rechnung(self) -> bool:
        """Vorkasse sofort (auch „in Wartestellung“), sonst erst nach der Zahlung."""
        if self.bezahlt:
            return True
        return self.zahlungsart_shop in VORKASSE and self.status in {"on-hold", *BEZAHLT}


def _cent(wert) -> int:
    """WooCommerce liefert Beträge als Text mit Punkt, z. B. "152.20" (nie float rechnen)."""
    try:
        betrag = Decimal(str(wert or "0")) * 100
    except InvalidOperation as fehler:
        raise BestellungUngueltig(f"Ungültiger Betrag: {wert!r}") from fehler
    if betrag != betrag.to_integral_value():
        raise BestellungUngueltig(f"Betrag mit mehr als zwei Nachkommastellen: {wert!r}")
    return int(betrag)


def _datum(wert: str | None) -> date | None:
    if not wert:
        return None
    return datetime.fromisoformat(wert.replace("Z", "+00:00")).date()


def _position(name: str, menge, gesamt_cent: int, beschreibung: str | None = None) -> Position:
    """Positionsbetrag muss exakt stimmen. Geht der Preis je Stück nicht in Cent auf,
    wird die Position als Pauschale mit Mengenangabe in der Beschreibung geführt."""
    try:
        stueck = int(Decimal(str(menge)))
    except (InvalidOperation, ValueError):
        stueck = 1
    if stueck > 0 and gesamt_cent % stueck == 0:
        return Position(name, stueck * 1000, gesamt_cent // stueck, beschreibung)
    zusatz = f"Menge: {menge}"
    return Position(
        name, 1000, gesamt_cent, f"{beschreibung}\n{zusatz}" if beschreibung else zusatz
    )


def _sichtbar(merkmal: dict) -> bool:
    """Variationen wie „Größe: M“, keine internen Felder (beginnen mit _)."""
    return (
        not str(merkmal.get("key", "")).startswith("_") and merkmal.get("display_value") is not None
    )


def _merkmal(merkmal: dict) -> str:
    name = merkmal.get("display_key") or merkmal.get("key")
    return f"{name}: {merkmal.get('display_value')}"


def kunde(daten: dict) -> dict:
    """Rechnungsanschrift als Kontaktdaten (Format von services/kontakte.py)."""
    rechnung = daten.get("billing") or {}
    firma = (rechnung.get("company") or "").strip()
    strasse = " ".join(
        t
        for t in (
            (rechnung.get("address_1") or "").strip(),
            (rechnung.get("address_2") or "").strip(),
        )
        if t
    )
    land = (rechnung.get("country") or "DE").upper()
    return {
        "art": "firma" if firma else "person",
        "firmenname": firma or None,
        "vorname": (rechnung.get("first_name") or "").strip() or None,
        "nachname": (rechnung.get("last_name") or "").strip() or None,
        "strasse": strasse or None,
        "plz": (rechnung.get("postcode") or "").strip() or None,
        "ort": (rechnung.get("city") or "").strip() or None,
        "land": LAENDER.get(land, land),
        "email": (rechnung.get("email") or "").strip().lower() or None,
        "telefon": (rechnung.get("phone") or "").strip() or None,
        "typ": "kunde",
    }


def lies_bestellung(daten: dict) -> Bestellung:
    try:
        externe_id = int(daten["id"])
    except (KeyError, TypeError, ValueError) as fehler:
        raise BestellungUngueltig("Bestellung ohne ID") from fehler
    methode = daten.get("payment_method") or ""
    erstellt = _datum(daten.get("date_created")) or date.today()
    bestellung = Bestellung(
        externe_id=externe_id,
        nummer=str(daten.get("number") or externe_id),
        status=daten.get("status") or "",
        erstellt_am=erstellt,
        bezahlt_am=_datum(daten.get("date_paid")),
        zahlungsart_shop=methode,
        zahlungsart=ZAHLUNGSARTEN.get(methode, "sonstige"),
        transaktion=(daten.get("transaction_id") or "").strip() or None,
        summe_cent=_cent(daten.get("total")),
        erstattet_cent=sum(-_cent(r.get("total")) for r in daten.get("refunds") or []),
        kunde=kunde(daten),
    )
    for zeile in daten.get("line_items") or []:
        beschreibung = ", ".join(_merkmal(m) for m in zeile.get("meta_data") or [] if _sichtbar(m))
        beschreibung = beschreibung or None
        name = (zeile.get("name") or "Artikel").strip()
        if zeile.get("sku"):
            beschreibung = f"Art.-Nr. {zeile['sku']}" + (
                f"\n{beschreibung}" if beschreibung else ""
            )
        bestellung.positionen.append(
            _position(name, zeile.get("quantity") or 1, _cent(zeile.get("total")), beschreibung)
        )
    for versand in daten.get("shipping_lines") or []:
        betrag = _cent(versand.get("total"))
        if betrag:
            titel = (versand.get("method_title") or "").strip()
            bestellung.positionen.append(
                Position(f"Versand ({titel})" if titel else "Versand", 1000, betrag)
            )
    for gebuehr in daten.get("fee_lines") or []:
        betrag = _cent(gebuehr.get("total"))
        if betrag:
            bestellung.positionen.append(
                Position((gebuehr.get("name") or "Gebühr").strip(), 1000, betrag)
            )

    steuer = _cent(daten.get("total_tax"))
    if steuer:
        bestellung.hinweise.append(
            f"Der Shop hat {cent_zu_euro(steuer)} Umsatzsteuer berechnet. Als Kleinunternehmer "
            "darfst du keine Umsatzsteuer ausweisen. Bitte die Steuereinstellungen im Shop prüfen."
        )
        bestellung.positionen.append(Position("Im Shop berechnete Steuer", 1000, steuer))
    if sum(p.menge_tausendstel // 1000 * p.einzelpreis_cent for p in bestellung.positionen) != (
        bestellung.summe_cent
    ):
        bestellung.hinweise.append(
            "Die Positionen ergeben nicht den Bestellbetrag aus dem Shop. "
            "Bitte vor der Freigabe prüfen."
        )
    if bestellung.erstattet_cent:
        bestellung.hinweise.append(
            f"Im Shop wurden {cent_zu_euro(bestellung.erstattet_cent)} erstattet. Bitte eine "
            "Rechnungskorrektur prüfen."
        )
    return bestellung
