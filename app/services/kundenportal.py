"""Kundenportal: persönliche Links zu Belegen.

Ein Link enthält einen zufälligen Schlüssel (192 Bit). Wer ihn kennt, sieht genau diesen einen
Beleg: Status, Positionen, PDF, E-Rechnung und Zahlungsdaten, bei Angeboten zusätzlich
„Annehmen“ und „Ablehnen“. Optional fragt steuy vorher die Postleitzahl des Empfängers ab, falls
eine Mail weitergeleitet wird. Links lassen sich jederzeit sperren und neu erzeugen.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from flask import current_app, request
from sqlalchemy import select

from app.extensions import db
from app.models import Kundenlink, Mahnung, Rechnung
from app.services.einrichtung import aktuelles_gewerbe
from app.services.geheimnis import entschluessele, verschluessele
from app.services.protokoll import protokolliere

PORTAL_BELEGARTEN = ("rechnung", "angebot", "korrektur", "lieferschein")
MAX_PLZ_VERSUCHE = 5
PLZ_SPERRE = timedelta(minutes=15)


class PortalFehler(ValueError):
    pass


def _hash(schluessel: str) -> str:
    return hashlib.sha256(schluessel.encode()).hexdigest()


# ---------- Einstellungen ----------


def oeffentliche_adresse() -> str:
    """Adresse, unter der Kunden steuy erreichen (Einstellung, sonst BASIS_URL)."""
    gewerbe = aktuelles_gewerbe()
    adresse = (gewerbe.oeffentliche_adresse if gewerbe else None) or current_app.config.get(
        "BASIS_URL", ""
    )
    return (adresse or "").strip().rstrip("/")


def aktiv() -> bool:
    gewerbe = aktuelles_gewerbe()
    return bool(gewerbe and gewerbe.kundenportal and oeffentliche_adresse())


# ---------- Links verwalten ----------


def _passt(rechnung: Rechnung) -> bool:
    return rechnung.belegart in PORTAL_BELEGARTEN and not rechnung.ist_entwurf


def aktueller_link(rechnung: Rechnung) -> Kundenlink | None:
    return (
        db.session.execute(
            select(Kundenlink)
            .where(Kundenlink.rechnung_id == rechnung.id, Kundenlink.gesperrt_am.is_(None))
            .order_by(Kundenlink.id.desc())
        )
        .scalars()
        .first()
    )


def erzeuge_link(rechnung: Rechnung, nutzer_id: int | None = None) -> Kundenlink:
    if not _passt(rechnung):
        raise PortalFehler("Nur festgeschriebene Belege lassen sich freigeben.")
    schluessel = secrets.token_urlsafe(24)
    link = Kundenlink(
        rechnung_id=rechnung.id,
        schluessel_hash=_hash(schluessel),
        schluessel_geheim=verschluessele(schluessel),
    )
    db.session.add(link)
    db.session.flush()
    protokolliere(
        "kundenlink_erzeugt", nutzer_id=nutzer_id, objekt_typ="rechnung", objekt_id=rechnung.id
    )
    # Sofort sichern: Der Link steht gleich im Mailtext, auch wenn die Anfrage danach abbricht
    db.session.commit()
    return link


def link_fuer(rechnung: Rechnung, nutzer_id: int | None = None) -> Kundenlink:
    """Vorhandenen aktiven Link nehmen oder einen neuen anlegen."""
    return aktueller_link(rechnung) or erzeuge_link(rechnung, nutzer_id)


def url(link: Kundenlink) -> str | None:
    schluessel = entschluessele(link.schluessel_geheim)
    basis = oeffentliche_adresse()
    if not schluessel or not basis:
        return None
    return f"{basis}/k/{schluessel}"


def url_fuer(rechnung: Rechnung, nutzer_id: int | None = None) -> str | None:
    """Link für E-Mails. None, wenn das Portal aus ist oder der Beleg nicht passt."""
    if not aktiv() or not _passt(rechnung):
        return None
    return url(link_fuer(rechnung, nutzer_id))


def sperre(link: Kundenlink, nutzer_id: int) -> None:
    link.gesperrt_am = datetime.now(UTC)
    protokolliere(
        "kundenlink_gesperrt",
        nutzer_id=nutzer_id,
        objekt_typ="rechnung",
        objekt_id=link.rechnung_id,
    )


def neuer_link(rechnung: Rechnung, nutzer_id: int) -> Kundenlink:
    """Alten Link sperren (z. B. an die falsche Adresse geschickt) und einen neuen erzeugen."""
    alt = aktueller_link(rechnung)
    if alt:
        sperre(alt, nutzer_id)
    return erzeuge_link(rechnung, nutzer_id)


# ---------- Zugriff des Kunden ----------


def finde(schluessel: str) -> Kundenlink | None:
    """Nur aktive Links zu festgeschriebenen Belegen. Unbekannt und gesperrt sehen gleich aus."""
    if not schluessel or len(schluessel) > 100:
        return None
    link = db.session.execute(
        select(Kundenlink).where(Kundenlink.schluessel_hash == _hash(schluessel))
    ).scalar_one_or_none()
    if not link or not link.aktiv or not _passt(link.rechnung):
        return None
    return link


def plz_noetig(link: Kundenlink) -> bool:
    gewerbe = aktuelles_gewerbe()
    return bool(gewerbe.kundenportal_plz and (link.rechnung.empfaenger_plz or "").strip())


def _plz(text: str | None) -> str:
    return "".join((text or "").split()).upper()


def pruefe_plz(link: Kundenlink, eingabe: str) -> bool:
    """Vergleicht in konstanter Zeit, sperrt nach zu vielen Fehlversuchen für 15 Minuten."""
    jetzt = datetime.now(UTC)
    if link.gesperrt_bis and link.gesperrt_bis > jetzt:
        raise PortalFehler("Zu viele Versuche. Bitte in 15 Minuten erneut versuchen.")
    richtig = hmac.compare_digest(_plz(eingabe), _plz(link.rechnung.empfaenger_plz))
    if richtig:
        link.fehlversuche = 0
        link.gesperrt_bis = None
    else:
        link.fehlversuche += 1
        if link.fehlversuche >= MAX_PLZ_VERSUCHE:
            link.fehlversuche = 0
            link.gesperrt_bis = jetzt + PLZ_SPERRE
            protokolliere(
                "kundenlink_plz_gesperrt", objekt_typ="rechnung", objekt_id=link.rechnung_id
            )
    db.session.commit()
    return richtig


def merke_abruf(link: Kundenlink) -> None:
    link.abrufe += 1
    link.zuletzt_abgerufen = datetime.now(UTC)
    db.session.commit()


# ---------- Anzeige ----------


@dataclass(frozen=True)
class Status:
    text: str
    art: str  # offen, ok, warnung, fehler, neutral


def status(rechnung: Rechnung, heute: date | None = None) -> Status:
    heute = heute or date.today()
    if rechnung.belegart == "angebot":
        if rechnung.status == "angenommen":
            return Status("Angenommen", "ok")
        if rechnung.status == "abgelehnt":
            return Status("Abgelehnt", "neutral")
        if rechnung.gueltig_bis and rechnung.gueltig_bis < heute:
            return Status("Abgelaufen", "neutral")
        return Status("Offen", "offen")
    if rechnung.belegart == "korrektur":
        return Status("Rechnungskorrektur", "neutral")
    if rechnung.belegart == "lieferschein":
        return Status("Lieferschein", "neutral")
    if rechnung.status == "storniert":
        return Status("Storniert", "neutral")
    if rechnung.status == "bezahlt":
        return Status("Bezahlt", "ok")
    if rechnung.faellig_am and rechnung.faellig_am < heute and rechnung.offen_cent > 0:
        return Status("Überfällig", "fehler")
    if rechnung.status == "teilbezahlt":
        return Status("Teilweise bezahlt", "warnung")
    return Status("Offen", "offen")


def mahnungen(rechnung: Rechnung) -> list[Mahnung]:
    return [m for m in rechnung.mahnungen if m.pdf_sha256]


def kann_entscheiden(rechnung: Rechnung, heute: date | None = None) -> bool:
    heute = heute or date.today()
    return (
        rechnung.belegart == "angebot"
        and rechnung.status == "offen"
        and not (rechnung.gueltig_bis and rechnung.gueltig_bis < heute)
    )


def entscheide(link: Kundenlink, angenommen: bool, name: str, kommentar: str) -> None:
    """Der Kunde nimmt ein Angebot an oder lehnt es ab. Danach ist es nicht mehr änderbar."""
    angebot = link.rechnung
    if not kann_entscheiden(angebot):
        raise PortalFehler("Dieses Angebot kann nicht mehr online angenommen werden.")
    name = " ".join((name or "").split())[:200]
    if angenommen and not name:
        raise PortalFehler("Bitte geben Sie Ihren Namen an.")
    angebot.status = "angenommen" if angenommen else "abgelehnt"
    link.entschieden_am = datetime.now(UTC)
    link.entschieden_von = name or None
    link.kommentar = (kommentar or "").strip()[:2000] or None
    protokolliere(
        f"angebot_{angebot.status}_online",
        objekt_typ="rechnung",
        objekt_id=angebot.id,
        details={
            "name": link.entschieden_von,
            "kommentar": link.kommentar,
            "ip": request.remote_addr if request else None,
        },
    )
    db.session.commit()
    _benachrichtige(angebot, link)


def _benachrichtige(angebot: Rechnung, link: Kundenlink) -> None:
    """Kurze Mail an das eigene Postfach. Fehlt der Mailversand, steht es trotzdem im Beleg."""
    from app.services.mail import MailFehler, eingerichtet, sende

    gewerbe = aktuelles_gewerbe()
    if not (eingerichtet() and gewerbe.email):
        return
    ergebnis = "angenommen" if angebot.status == "angenommen" else "abgelehnt"
    text = (
        f"{angebot.empfaenger_name or 'Dein Kunde'} hat das Angebot {angebot.nummer} "
        f"online {ergebnis}.\n\n"
        f"Name: {link.entschieden_von or '–'}\n"
        f"Nachricht: {link.kommentar or '–'}\n"
    )
    if angebot.status == "angenommen":
        text += "\nIn steuy kannst du daraus jetzt mit einem Klick die Rechnung erstellen.\n"
    try:
        sende(an=gewerbe.email, betreff=f"Angebot {angebot.nummer} {ergebnis}", text=text)
    except MailFehler:
        current_app.logger.warning("Benachrichtigung zum Angebot %s nicht versendet", angebot.id)
