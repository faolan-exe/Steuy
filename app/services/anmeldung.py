import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import delete, func, select

from app.domain.passwort import normalisiere_email, pruefe_passwort
from app.domain.sperre import FENSTER, gesperrt
from app.extensions import db
from app.models import Anmeldeversuch, Nutzer
from app.services.protokoll import protokolliere


class ZuVieleVersuche(RuntimeError):
    pass


def _hash(wert: str) -> str:
    schluessel = current_app.config["SECRET_KEY"].encode()
    return hmac.new(schluessel, wert.encode(), hashlib.sha256).hexdigest()


def _fehlversuche(spalte, wert: str, jetzt: datetime) -> list[datetime]:
    letzter_erfolg = db.session.execute(
        select(func.max(Anmeldeversuch.zeitpunkt)).where(spalte == wert, Anmeldeversuch.erfolgreich)
    ).scalar()
    abfrage = select(Anmeldeversuch.zeitpunkt).where(
        spalte == wert,
        Anmeldeversuch.erfolgreich.is_(False),
        Anmeldeversuch.zeitpunkt >= jetzt - FENSTER,
    )
    if letzter_erfolg:
        abfrage = abfrage.where(Anmeldeversuch.zeitpunkt > letzter_erfolg)
    return list(db.session.execute(abfrage).scalars())


def _merke(email_hash: str, ip_hash: str, erfolgreich: bool, jetzt: datetime) -> None:
    db.session.execute(
        delete(Anmeldeversuch).where(Anmeldeversuch.zeitpunkt < jetzt - timedelta(days=1))
    )
    db.session.add(
        Anmeldeversuch(
            zeitpunkt=jetzt, email_hash=email_hash, ip_hash=ip_hash, erfolgreich=erfolgreich
        )
    )


def pruefe_anmeldung(email: str, passwort: str, ip: str = "unbekannt") -> Nutzer | None:
    """Gibt den Nutzer zurück, wenn E-Mail und Passwort stimmen und das Konto aktiv ist.

    Nach zu vielen Fehlversuchen je Konto oder je Adresse wird für 15 Minuten gesperrt
    (ZuVieleVersuche), ohne zu verraten, ob es das Konto gibt. Erfolg und Fehlschlag werden
    protokolliert, bei Fehlschlag ohne die eingegebene E-Mail.
    """
    jetzt = datetime.now(UTC)
    email_hash = _hash(normalisiere_email(email))
    ip_hash = _hash(ip)
    _pruefe_sperre(email_hash, ip_hash, jetzt)

    nutzer = db.session.execute(
        select(Nutzer).where(Nutzer.email == normalisiere_email(email))
    ).scalar_one_or_none()

    passt = pruefe_passwort(nutzer.passwort_hash if nutzer else None, passwort)
    if nutzer and passt and nutzer.is_active:
        if nutzer.totp_aktiv:
            # Erst nach dem zweiten Faktor zählt die Anmeldung als erfolgreich. Sonst könnte
            # jemand mit dem Passwort den Fehlerzähler zurücksetzen und Codes durchprobieren.
            protokolliere("anmeldung_passwort_ok", nutzer_id=nutzer.id)
        else:
            _merke(email_hash, ip_hash, True, jetzt)
            protokolliere("anmeldung", nutzer_id=nutzer.id)
        db.session.commit()
        return nutzer

    _merke(email_hash, ip_hash, False, jetzt)
    protokolliere("anmeldung_fehlgeschlagen", nutzer_id=nutzer.id if nutzer else None)
    db.session.commit()
    return None


def _pruefe_sperre(email_hash: str, ip_hash: str, jetzt: datetime) -> None:
    if gesperrt(
        _fehlversuche(Anmeldeversuch.email_hash, email_hash, jetzt),
        _fehlversuche(Anmeldeversuch.ip_hash, ip_hash, jetzt),
        jetzt,
    ):
        raise ZuVieleVersuche("Zu viele Anmeldeversuche. Bitte in 15 Minuten erneut versuchen.")


def pruefe_zweiten_faktor(nutzer: Nutzer, code: str, ip: str = "unbekannt") -> bool:
    """Zweiter Schritt der Anmeldung. Fehlversuche zählen zur selben Sperre wie Passwörter."""
    from app.services.zwei_faktor import pruefe_code_fuer

    jetzt = datetime.now(UTC)
    email_hash = _hash(nutzer.email)
    ip_hash = _hash(ip)
    _pruefe_sperre(email_hash, ip_hash, jetzt)
    if pruefe_code_fuer(nutzer, code):
        _merke(email_hash, ip_hash, True, jetzt)
        protokolliere("anmeldung", nutzer_id=nutzer.id, details={"zwei_faktor": True})
        db.session.commit()
        return True
    _merke(email_hash, ip_hash, False, jetzt)
    protokolliere("zweiter_faktor_falsch", nutzer_id=nutzer.id)
    db.session.commit()
    return False


def protokolliere_abmeldung(nutzer_id: int) -> None:
    protokolliere("abmeldung", nutzer_id=nutzer_id)
    db.session.commit()
