"""Versand der wöchentlichen Zusammenfassung, aufgerufen per `flask erinnerungen`."""

from datetime import UTC, datetime

from flask import current_app
from sqlalchemy import select

from app.domain import erinnerung
from app.domain.geld import cent_zu_euro
from app.domain.rollen import Recht
from app.extensions import db
from app.models import Nutzer
from app.services.einrichtung import aktuelles_gewerbe
from app.services.mail import MailFehler, eingerichtet, sende
from app.services.protokoll import protokolliere
from app.services.rechte import darf
from app.services.zahlungen import zu_pruefen

# Wer eines dieser Rechte hat, kann etwas an „Zu prüfen“ erledigen
ARBEITSRECHTE = (Recht.ZAHLUNGEN, Recht.BUCHEN, Recht.BELEGE, Recht.RECHNUNGEN_VERSENDEN)


def punkte(daten: dict) -> list[str]:
    ueberfaellig = sum(r.offen_cent for r in daten["ueberfaellig"])
    liste = erinnerung.zeilen(
        [
            (len(daten["ueberfaellig"]), "überfällige Rechnung", "überfällige Rechnungen"),
            (
                len(daten["shop_freigabe"]),
                "Shop-Rechnung zur Freigabe",
                "Shop-Rechnungen zur Freigabe",
            ),
            (len(daten["shop_hinweise"]), "Hinweis aus dem Shop", "Hinweise aus dem Shop"),
            (
                len(daten["jahreswechsel"]),
                "Zahlung am Jahreswechsel zum Zuordnen",
                "Zahlungen am Jahreswechsel zum Zuordnen",
            ),
            (len(daten["mahnungen"]), "fällige Mahnung", "fällige Mahnungen"),
            (len(daten["belege"]), "neuer Beleg", "neue Belege"),
            (len(daten["buchungsentwuerfe"]), "Buchungsentwurf", "Buchungsentwürfe"),
            (len(daten["offene_ausgaben"]), "unbezahlte Ausgabe", "unbezahlte Ausgaben"),
            (len(daten["offene_einnahmen"]), "unbezahlte Einnahme", "unbezahlte Einnahmen"),
            (len(daten["gebuehren"]), "Zahlungsgebühr zum Buchen", "Zahlungsgebühren zum Buchen"),
            (len(daten["angebote"]), "Angebot ohne Antwort", "Angebote ohne Antwort"),
            (len(daten["entwuerfe"]), "Entwurf", "Entwürfe"),
            (len(daten["offen"]), "offene Rechnung", "offene Rechnungen"),
        ]
    )
    if ueberfaellig and liste:
        # Die überfälligen Rechnungen stehen immer als erster Punkt
        liste[0] += f" (zusammen {cent_zu_euro(ueberfaellig)})"
    return liste


def empfaenger() -> list[Nutzer]:
    nutzer = db.session.execute(
        select(Nutzer).where(Nutzer.wochenmail.is_(True)).order_by(Nutzer.id)
    ).scalars()
    return [n for n in nutzer if n.is_active and any(darf(n, r) for r in ARBEITSRECHTE)]


def sende_wochenmails(jetzt: datetime | None = None) -> int:
    """Gibt die Zahl der verschickten Mails zurück. Ohne Mail-Einrichtung passiert nichts."""
    jetzt = jetzt or datetime.now(UTC)
    if not eingerichtet():
        return 0
    liste = punkte(zu_pruefen(heute=jetzt.date()))
    if not liste:
        return 0
    gewerbe = aktuelles_gewerbe()
    basis = (current_app.config.get("BASIS_URL") or "").rstrip("/")
    link = f"{basis}/zu-pruefen" if basis else None
    gesendet = 0
    for nutzer in empfaenger():
        if not erinnerung.faellig(nutzer.wochenmail_gesendet_am, jetzt):
            continue
        try:
            sende(
                an=nutzer.email,
                betreff=f"steuy: {len(liste)} {'Punkt' if len(liste) == 1 else 'Punkte'} "
                f"zu prüfen für {gewerbe.name}",
                text=erinnerung.text(nutzer.name, gewerbe.name, liste, link),
            )
        except MailFehler:
            current_app.logger.warning(
                "Wochenmail an %s fehlgeschlagen", nutzer.email, exc_info=True
            )
            continue
        nutzer.wochenmail_gesendet_am = jetzt
        protokolliere("wochenmail_gesendet", nutzer_id=nutzer.id, details={"punkte": len(liste)})
        db.session.commit()
        gesendet += 1
    return gesendet
