"""Regeln für Zahlungseingänge (docs/domain/zahlungen-und-pruefung.md)."""

from datetime import date

ZAHLUNGSARTEN = {
    "ueberweisung": "Überweisung",
    "paypal": "PayPal",
    "karte": "Kartenzahlung",
    "bar": "Bar",
    "sonstige": "Sonstige",
}


class ZahlungUngueltig(ValueError):
    pass


def status_nach_zahlungen(summe_cent: int, bezahlt_cent: int) -> str:
    if bezahlt_cent <= 0:
        return "offen"
    return "bezahlt" if bezahlt_cent >= summe_cent else "teilbezahlt"


def pruefe_zahlung(
    *,
    betrag_cent: int,
    offen_cent: int,
    angekommen_cent: int | None,
    datum: date,
    rechnungsdatum: date,
) -> None:
    if betrag_cent <= 0:
        raise ZahlungUngueltig("Der Betrag muss größer als 0 sein.")
    if betrag_cent > offen_cent:
        raise ZahlungUngueltig("Der Betrag ist höher als der offene Rest der Rechnung.")
    if angekommen_cent is not None and not 0 <= angekommen_cent <= betrag_cent:
        raise ZahlungUngueltig(
            "Angekommen kann nicht mehr als der gezahlte Betrag sein. Gebühren mindern ihn."
        )
    if datum > date.today():
        raise ZahlungUngueltig("Das Zahlungsdatum liegt in der Zukunft.")
    if datum < rechnungsdatum.replace(year=rechnungsdatum.year - 1):
        raise ZahlungUngueltig("Das Zahlungsdatum liegt mehr als ein Jahr vor der Rechnung.")


def offene_gebuehr(betrag_cent: int, angekommen_cent: int | None) -> int:
    """Differenz zwischen gezahltem und angekommenem Betrag, z. B. PayPal-Gebühr."""
    return 0 if angekommen_cent is None else betrag_cent - angekommen_cent


def ist_ueberfaellig(faellig_am: date | None, status: str, heute: date) -> bool:
    return status in {"offen", "teilbezahlt"} and faellig_am is not None and faellig_am < heute
