"""WooCommerce: Bestellungen abrufen, Rechnungen anlegen, Zahlungen übernehmen.

Ablauf und Regeln: docs/domain/woocommerce.md. Rechnungen entstehen als Entwurf und warten
unter „Zu prüfen“ auf Freigabe, außer der Auto-Modus ist an.
"""

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import func, select

from app.domain.woocommerce import Bestellung, BestellungUngueltig, lies_bestellung
from app.extensions import db
from app.models import Kontakt, Rechnung, ShopBestellung
from app.services.einrichtung import aktuelles_gewerbe
from app.services.geheimnis import entschluessele
from app.services.protokoll import protokolliere

ZEITLIMIT = 30
SEITENGROESSE = 50
UEBERLAPPUNG = timedelta(hours=1)  # Uhren von Shop und Server gehen nicht gleich


class ShopFehler(RuntimeError):
    pass


@dataclass
class Ergebnis:
    abgerufen: int = 0
    neue_rechnungen: int = 0
    freigegeben: int = 0
    zahlungen: int = 0
    hinweise: int = 0
    fehler: list[str] = field(default_factory=list)

    def text(self) -> str:
        teile = [f"{self.abgerufen} Bestellungen abgerufen"]
        if self.neue_rechnungen:
            teile.append(f"{self.neue_rechnungen} neue Rechnungen")
        if self.freigegeben:
            teile.append(f"{self.freigegeben} automatisch freigegeben")
        if self.zahlungen:
            teile.append(f"{self.zahlungen} Zahlungen übernommen")
        if self.hinweise:
            teile.append(f"{self.hinweise} Hinweise unter „Zu prüfen“")
        return ", ".join(teile) + "."


def eingerichtet() -> bool:
    gewerbe = aktuelles_gewerbe()
    return bool(gewerbe and gewerbe.shop_url and gewerbe.shop_schluessel and gewerbe.shop_geheimnis)


def pruefe_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    teile = urllib.parse.urlsplit(url)
    lokal = teile.hostname in {"localhost", "127.0.0.1"}
    if teile.scheme != "https" and not (teile.scheme == "http" and lokal):
        raise ShopFehler("Die Shop-Adresse muss mit https:// beginnen.")
    if not teile.hostname:
        raise ShopFehler("Bitte die Adresse des Shops angeben, z. B. https://mein-shop.de")
    return url


def _anfrage(pfad: str, parameter: dict) -> tuple[list | dict, dict]:
    gewerbe = aktuelles_gewerbe()
    if not eingerichtet():
        raise ShopFehler("Der Shop ist noch nicht verbunden (Einstellungen → Shop).")
    schluessel = entschluessele(gewerbe.shop_schluessel) or ""
    geheimnis = entschluessele(gewerbe.shop_geheimnis) or ""
    url = f"{pruefe_url(gewerbe.shop_url)}/wp-json/wc/v3/{pfad}?{urllib.parse.urlencode(parameter)}"
    zugang = base64.b64encode(f"{schluessel}:{geheimnis}".encode()).decode()
    anfrage = urllib.request.Request(
        url, headers={"Authorization": f"Basic {zugang}", "User-Agent": "steuy"}
    )
    try:
        with urllib.request.urlopen(anfrage, timeout=ZEITLIMIT) as antwort:  # noqa: S310
            return json.loads(antwort.read().decode()), dict(antwort.headers)
    except urllib.error.HTTPError as fehler:
        if fehler.code in (401, 403):
            raise ShopFehler(
                "Der Shop lehnt die Schlüssel ab. Bitte Consumer Key und Secret prüfen "
                "(WooCommerce → Einstellungen → Erweitert → REST-API)."
            ) from fehler
        if fehler.code == 404:
            raise ShopFehler(
                "Unter dieser Adresse gibt es keine WooCommerce-REST-API. Adresse und "
                "Permalinks im Shop prüfen."
            ) from fehler
        raise ShopFehler(f"Der Shop antwortet mit Fehler {fehler.code}.") from fehler
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as fehler:
        current_app.logger.warning("Shop nicht erreichbar", exc_info=True)
        raise ShopFehler(
            "Der Shop ist nicht erreichbar. Adresse und Internetverbindung prüfen."
        ) from fehler


def teste_verbindung() -> None:
    _anfrage("orders", {"per_page": 1})


def hole_bestellungen(geaendert_seit: datetime | None) -> Iterable[dict]:
    """Alle seit dem letzten Abruf geänderten Bestellungen, älteste zuerst."""
    parameter = {"per_page": SEITENGROESSE, "orderby": "modified", "order": "asc"}
    if geaendert_seit:
        parameter["modified_after"] = (
            (geaendert_seit - UEBERLAPPUNG).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        )
    seite = 1
    while True:
        daten, kopf = _anfrage("orders", {**parameter, "page": seite})
        yield from daten
        seiten = int(kopf.get("X-WP-TotalPages") or kopf.get("x-wp-totalpages") or 1)
        if seite >= seiten or not daten:
            return
        seite += 1


# ---------- Verarbeitung ----------


def _finde_oder_lege_kontakt(kunde: dict, nutzer_id: int) -> Kontakt:
    from app.services.kontakte import _vergib_nummern, lege_kontakt_an

    if kunde.get("email"):
        vorhanden = (
            db.session.execute(
                select(Kontakt)
                .where(func.lower(Kontakt.email) == kunde["email"], Kontakt.archiviert.is_(False))
                .order_by(Kontakt.ist_kunde.desc(), Kontakt.id)
            )
            .scalars()
            .first()
        )
        if vorhanden:
            if not vorhanden.ist_kunde:
                vorhanden.ist_kunde = True
                _vergib_nummern(vorhanden)
            return vorhanden
    daten = dict(kunde)
    if daten["art"] == "person" and not daten.get("nachname"):
        daten["nachname"] = daten.get("email") or "Shop-Kunde"
    return lege_kontakt_an(daten, nutzer_id)


def _lege_rechnung_an(bestellung: Bestellung, kontakt: Kontakt, nutzer_id: int) -> Rechnung:
    from app.services.rechnungen import (
        Kopfdaten,
        Positionsdaten,
        neuer_entwurf,
        speichere_entwurf,
    )

    gewerbe = aktuelles_gewerbe()
    rechnung = neuer_entwurf(nutzer_id, kontakt=kontakt)
    datum = bestellung.erstellt_am.strftime("%d.%m.%Y")
    kopf = Kopfdaten(
        kontakt_id=kontakt.id,
        empfaenger_name=rechnung.empfaenger_name,
        empfaenger_zusatz=rechnung.empfaenger_zusatz,
        empfaenger_strasse=rechnung.empfaenger_strasse,
        empfaenger_plz=rechnung.empfaenger_plz,
        empfaenger_ort=rechnung.empfaenger_ort,
        empfaenger_land=rechnung.empfaenger_land,
        rechnungsdatum=bestellung.erstellt_am,
        # Annahme: Lieferung am Bestelltag. Vor der Freigabe anpassbar (offene Frage in der Doku)
        leistung_art="lieferdatum",
        leistung_von=bestellung.erstellt_am,
        leistung_bis=None,
        titel="Rechnung",
        einleitung=f"Vielen Dank für Ihre Bestellung {bestellung.nummer} vom {datum}.",
        nachbemerkung=rechnung.nachbemerkung,
        hinweis_steuerbefreiung=rechnung.hinweis_steuerbefreiung,
        zahlungsziel_tage=rechnung.zahlungsziel_tage,
        # Bereits bezahlt: kein QR-Code zum Überweisen
        qr_ueberweisung=bool(gewerbe.iban) and not bestellung.bezahlt,
    )
    positionen = [
        Positionsdaten(
            typ="artikel",
            bezeichnung=p.bezeichnung[:200],
            beschreibung=p.beschreibung,
            menge_tausendstel=p.menge_tausendstel,
            einheit="Stück",
            einzelpreis_cent=p.einzelpreis_cent,
        )
        for p in bestellung.positionen
    ]
    speichere_entwurf(rechnung, kopf, positionen)
    db.session.commit()
    return rechnung


def uebernehme_zahlung(eintrag: ShopBestellung, nutzer_id: int) -> bool:
    """Zahlung aus dem Shop an die finalisierte Rechnung, mit dem Zahlungsdatum aus dem Shop."""
    from app.domain.woocommerce import ZAHLUNGSARTEN
    from app.services.zahlungen import erfasse_zahlung

    rechnung = eintrag.rechnung
    if not (eintrag.bezahlt_am and rechnung and not rechnung.ist_entwurf) or eintrag.zahlung_id:
        return False
    if rechnung.offen_cent <= 0:
        return False
    zahlung = erfasse_zahlung(
        rechnung,
        datum=eintrag.bezahlt_am,
        betrag_cent=min(eintrag.summe_cent, rechnung.offen_cent),
        zahlungsart=ZAHLUNGSARTEN.get(eintrag.zahlungsart_shop, "sonstige"),
        angekommen_cent=None,
        notiz=f"Shop-Bestellung {eintrag.nummer}",
        nutzer_id=nutzer_id,
        referenz=(eintrag.rohdaten or {}).get("transaction_id") or None,
    )
    eintrag.zahlung_id = zahlung.id
    db.session.commit()
    return True


def freigeben(eintrag: ShopBestellung, nutzer_id: int) -> list[str]:
    """Finalisiert die Shop-Rechnung, verschickt sie (falls möglich) und übernimmt die Zahlung."""
    from app.services.mail import MailFehler
    from app.services.mail import eingerichtet as mail_eingerichtet
    from app.services.rechnungen import NichtFinalisierbar, finalisiere
    from app.services.versand import sende_beleg, vorschlag

    rechnung = eintrag.rechnung
    if not rechnung:
        raise ShopFehler("Zu dieser Bestellung gibt es noch keine Rechnung.")
    meldungen = []
    if rechnung.ist_entwurf:
        try:
            finalisiere(rechnung, nutzer_id)
        except NichtFinalisierbar as fehler:
            db.session.rollback()
            raise ShopFehler(f"Rechnung zu Bestellung {eintrag.nummer}: {fehler}") from fehler
        meldungen.append(f"Rechnung {rechnung.nummer} erstellt.")
    if uebernehme_zahlung(eintrag, nutzer_id):
        meldungen.append("Zahlung aus dem Shop übernommen.")
    if mail_eingerichtet() and rechnung.kontakt and rechnung.kontakt.email and not rechnung.versand:
        vorlage = vorschlag(rechnung)
        try:
            sende_beleg(
                rechnung,
                an=vorlage["an"],
                betreff=vorlage["betreff"],
                text=vorlage["text"],
                nutzer_id=nutzer_id,
            )
        except MailFehler as fehler:
            meldungen.append(f"Nicht verschickt: {fehler}")
        else:
            meldungen.append(f"An {vorlage['an']} verschickt.")
    return meldungen


def _aktualisiere(eintrag: ShopBestellung, bestellung: Bestellung, daten: dict) -> int:
    """Übernimmt den neuen Stand. Gibt 1 zurück, wenn ein neuer Hinweis entstanden ist."""
    neuer_hinweis = 0
    hinweis = " ".join(bestellung.hinweise) or None
    if hinweis and (
        hinweis != eintrag.hinweis or bestellung.erstattet_cent > eintrag.erstattet_cent
    ):
        eintrag.hinweis = hinweis
        eintrag.hinweis_erledigt_von = None
        neuer_hinweis = 1
    eintrag.status = bestellung.status
    eintrag.bezahlt_am = bestellung.bezahlt_am if bestellung.bezahlt else None
    eintrag.erstattet_cent = bestellung.erstattet_cent
    eintrag.summe_cent = bestellung.summe_cent
    eintrag.rohdaten = daten
    eintrag.aktualisiert_am = datetime.now(UTC)
    return neuer_hinweis


def verarbeite(daten: dict, nutzer_id: int, ergebnis: Ergebnis) -> None:
    try:
        bestellung = lies_bestellung(daten)
    except BestellungUngueltig as fehler:
        ergebnis.fehler.append(f"Bestellung {daten.get('number') or daten.get('id')}: {fehler}")
        return
    eintrag = db.session.execute(
        select(ShopBestellung).where(ShopBestellung.externe_id == bestellung.externe_id)
    ).scalar_one_or_none()
    if eintrag is None:
        if not bestellung.braucht_rechnung:
            return  # z. B. offen, storniert oder fehlgeschlagen: (noch) nichts zu tun
        eintrag = ShopBestellung(
            externe_id=bestellung.externe_id,
            nummer=bestellung.nummer,
            status=bestellung.status,
            zahlungsart_shop=bestellung.zahlungsart_shop,
            summe_cent=bestellung.summe_cent,
            rohdaten=daten,
        )
        db.session.add(eintrag)
    else:
        eintrag.abrufe += 1
    ergebnis.hinweise += _aktualisiere(eintrag, bestellung, daten)
    db.session.flush()

    if bestellung.braucht_rechnung and eintrag.rechnung_id is None:
        kontakt = _finde_oder_lege_kontakt(bestellung.kunde, nutzer_id)
        eintrag.kontakt_id = kontakt.id
        rechnung = _lege_rechnung_an(bestellung, kontakt, nutzer_id)
        eintrag.rechnung_id = rechnung.id
        db.session.commit()
        ergebnis.neue_rechnungen += 1
        if aktuelles_gewerbe().shop_auto_versand and not eintrag.hinweis:
            try:
                freigeben(eintrag, nutzer_id)
            except ShopFehler as fehler:
                ergebnis.fehler.append(str(fehler))
            else:
                ergebnis.freigegeben += 1
    if uebernehme_zahlung(eintrag, nutzer_id):
        ergebnis.zahlungen += 1
    db.session.commit()


def synchronisiere(
    nutzer_id: int,
    holer: Callable[[datetime | None], Iterable[dict]] | None = None,
    jetzt: datetime | None = None,
) -> Ergebnis:
    gewerbe = aktuelles_gewerbe()
    jetzt = jetzt or datetime.now(UTC)
    ergebnis = Ergebnis()
    for daten in (holer or hole_bestellungen)(gewerbe.shop_letzter_abruf):
        ergebnis.abgerufen += 1
        verarbeite(daten, nutzer_id, ergebnis)
    gewerbe.shop_letzter_abruf = jetzt
    protokolliere(
        "shop_abruf",
        nutzer_id=nutzer_id,
        details={
            "abgerufen": ergebnis.abgerufen,
            "neue_rechnungen": ergebnis.neue_rechnungen,
            "zahlungen": ergebnis.zahlungen,
            "fehler": len(ergebnis.fehler),
        },
    )
    db.session.commit()
    return ergebnis


def zur_freigabe() -> list[ShopBestellung]:
    return list(
        db.session.execute(
            select(ShopBestellung)
            .join(Rechnung, ShopBestellung.rechnung_id == Rechnung.id)
            .where(Rechnung.status == "entwurf")
            .order_by(ShopBestellung.externe_id)
        ).scalars()
    )


def offene_hinweise() -> list[ShopBestellung]:
    return list(
        db.session.execute(
            select(ShopBestellung)
            .where(
                ShopBestellung.hinweis.is_not(None), ShopBestellung.hinweis_erledigt_von.is_(None)
            )
            .order_by(ShopBestellung.externe_id)
        ).scalars()
    )


def speichere_einstellungen(gewerbe, daten: dict, nutzer_id: int) -> list[str]:
    """Leere Schlüsselfelder behalten die gespeicherten Werte."""
    from app.services.geheimnis import verschluessele

    geaendert = []
    url = (daten.get("shop_url") or "").strip()
    url = pruefe_url(url) if url else None
    if url != gewerbe.shop_url:
        gewerbe.shop_url = url
        gewerbe.shop_letzter_abruf = None  # anderer Shop: alles neu abrufen
        geaendert.append("shop_url")
    for feld in ("shop_schluessel", "shop_geheimnis"):
        if daten.get(feld):
            setattr(gewerbe, feld, verschluessele(daten[feld].strip()))
            geaendert.append(feld)
    if daten.get("trennen"):
        gewerbe.shop_url = gewerbe.shop_schluessel = gewerbe.shop_geheimnis = None
        geaendert.append("getrennt")
    if bool(daten.get("shop_auto_versand")) != gewerbe.shop_auto_versand:
        gewerbe.shop_auto_versand = bool(daten.get("shop_auto_versand"))
        geaendert.append("shop_auto_versand")
    if geaendert:
        protokolliere("shop_einstellungen", nutzer_id=nutzer_id, details={"felder": geaendert})
    db.session.commit()
    return geaendert
