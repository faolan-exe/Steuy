"""Zwei-Faktor-Anmeldung einrichten, prüfen und zurücksetzen."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.domain.passwort import hash_einmalcode, hash_passwort, pruefe_passwort
from app.domain.zwei_faktor import (  # noqa: F401  einrichtungs_uri wird weitergereicht
    MAIL_CODE_GUELTIG_SEKUNDEN,
    MAIL_CODE_NEU_FRUEHESTENS_SEKUNDEN,
    einrichtungs_uri,
    neue_wiederherstellungscodes,
    neuer_mail_code,
    neues_geheimnis,
    normalisiere_wiederherstellungscode,
    nur_ziffern,
    pruefe_code,
)
from app.extensions import db
from app.models import Nutzer, Wiederherstellungscode
from app.services.geheimnis import entschluessele, verschluessele
from app.services.protokoll import protokolliere


class ZweiFaktorFehler(ValueError):
    pass


def starte_einrichtung(nutzer: Nutzer) -> tuple[str, str]:
    """Neuer Schlüssel (noch nicht aktiv). Gibt Schlüssel und otpauth-URI zurück."""
    if nutzer.totp_aktiv:
        raise ZweiFaktorFehler("Die Zwei-Faktor-Anmeldung ist bereits eingerichtet.")
    geheimnis = neues_geheimnis()
    nutzer.totp_geheimnis = verschluessele(geheimnis)
    db.session.commit()
    return geheimnis, einrichtungs_uri(geheimnis, nutzer.email)


def offenes_geheimnis(nutzer: Nutzer) -> str | None:
    return entschluessele(nutzer.totp_geheimnis) if nutzer.totp_geheimnis else None


def _neue_codes(nutzer: Nutzer) -> list[str]:
    db.session.execute(
        delete(Wiederherstellungscode).where(Wiederherstellungscode.nutzer_id == nutzer.id)
    )
    codes = neue_wiederherstellungscodes()
    db.session.add_all(
        Wiederherstellungscode(nutzer_id=nutzer.id, code_hash=hash_passwort(c)) for c in codes
    )
    return codes


def bestaetige_einrichtung(nutzer: Nutzer, code: str) -> list[str]:
    """Aktiviert 2FA, wenn der Code aus der App stimmt. Gibt die Wiederherstellungscodes zurück."""
    geheimnis = offenes_geheimnis(nutzer)
    if not geheimnis:
        raise ZweiFaktorFehler("Bitte die Einrichtung neu starten.")
    schritt = pruefe_code(geheimnis, code, None)
    if schritt is None:
        raise ZweiFaktorFehler("Der Code stimmt nicht. Bitte die Uhrzeit des Handys prüfen.")
    nutzer.totp_aktiv = True
    nutzer.totp_letzter_schritt = schritt
    codes = _neue_codes(nutzer)
    protokolliere(
        "zwei_faktor_aktiviert", nutzer_id=nutzer.id, objekt_typ="nutzer", objekt_id=nutzer.id
    )
    db.session.commit()
    return codes


def pruefe_code_fuer(nutzer: Nutzer, code: str) -> bool:
    """Code aus der App bzw. per Mail oder ein unbenutzter Wiederherstellungscode."""
    if nutzer.zwei_faktor_art == "mail" and _pruefe_mail_code(nutzer, code):
        return True
    geheimnis = offenes_geheimnis(nutzer) if nutzer.zwei_faktor_art == "app" else None
    if geheimnis:
        schritt = pruefe_code(geheimnis, code, nutzer.totp_letzter_schritt)
        if schritt is not None:
            nutzer.totp_letzter_schritt = schritt
            return True
    normal = normalisiere_wiederherstellungscode(code)
    if len(normal) != 11:
        return False
    offene = db.session.execute(
        select(Wiederherstellungscode).where(
            Wiederherstellungscode.nutzer_id == nutzer.id,
            Wiederherstellungscode.benutzt_am.is_(None),
        )
    ).scalars()
    for eintrag in offene:
        if pruefe_passwort(eintrag.code_hash, normal):
            eintrag.benutzt_am = datetime.now(UTC)
            protokolliere(
                "wiederherstellungscode_benutzt",
                nutzer_id=nutzer.id,
                objekt_typ="nutzer",
                objekt_id=nutzer.id,
            )
            return True
    return False


def neue_codes(nutzer: Nutzer, passwort: str) -> list[str]:
    if not nutzer.totp_aktiv:
        raise ZweiFaktorFehler("Die Zwei-Faktor-Anmeldung ist nicht eingerichtet.")
    if not pruefe_passwort(nutzer.passwort_hash, passwort):
        raise ZweiFaktorFehler("Das Passwort stimmt nicht.")
    codes = _neue_codes(nutzer)
    protokolliere(
        "wiederherstellungscodes_neu", nutzer_id=nutzer.id, objekt_typ="nutzer", objekt_id=nutzer.id
    )
    db.session.commit()
    return codes


def offene_codes(nutzer: Nutzer) -> int:
    return len(
        db.session.execute(
            select(Wiederherstellungscode.id).where(
                Wiederherstellungscode.nutzer_id == nutzer.id,
                Wiederherstellungscode.benutzt_am.is_(None),
            )
        ).all()
    )


def deaktiviere(nutzer: Nutzer, handelnd_id: int, passwort: str | None = None) -> None:
    """Selbst (mit Passwort) oder durch einen Admin (ohne Passwort, z. B. Handy verloren)."""
    if passwort is not None and not pruefe_passwort(nutzer.passwort_hash, passwort):
        raise ZweiFaktorFehler("Das Passwort stimmt nicht.")
    nutzer.totp_aktiv = False
    nutzer.totp_geheimnis = None
    nutzer.totp_letzter_schritt = None
    nutzer.zwei_faktor_art = "app"
    nutzer.mail_code_hash = None
    nutzer.mail_code_bis = None
    db.session.execute(
        delete(Wiederherstellungscode).where(Wiederherstellungscode.nutzer_id == nutzer.id)
    )
    protokolliere(
        "zwei_faktor_deaktiviert",
        nutzer_id=handelnd_id,
        objekt_typ="nutzer",
        objekt_id=nutzer.id,
        details={"durch_admin": handelnd_id != nutzer.id},
    )
    db.session.commit()


def aendere_passwort(nutzer: Nutzer, alt: str, neu: str) -> None:
    if not pruefe_passwort(nutzer.passwort_hash, alt):
        raise ZweiFaktorFehler("Das bisherige Passwort stimmt nicht.")
    nutzer.passwort_hash = hash_passwort(neu)
    protokolliere(
        "passwort_geaendert", nutzer_id=nutzer.id, objekt_typ="nutzer", objekt_id=nutzer.id
    )
    db.session.commit()


# ---------- Code per E-Mail ----------


def sende_mail_code(nutzer: Nutzer, jetzt: datetime | None = None) -> None:
    """Neuer Einmalcode per Mail. Ersetzt einen älteren, höchstens einer pro Minute."""
    from app.services.mail import MailFehler, sende

    jetzt = jetzt or datetime.now(UTC)
    # Bremse nur, solange ein unbenutzter Code unterwegs ist
    if (
        nutzer.mail_code_hash
        and nutzer.mail_code_gesendet_am
        and jetzt - nutzer.mail_code_gesendet_am
        < timedelta(seconds=MAIL_CODE_NEU_FRUEHESTENS_SEKUNDEN)
    ):
        raise ZweiFaktorFehler(
            "Ein Code ist gerade unterwegs. Bitte kurz warten und ins Postfach schauen."
        )
    code = neuer_mail_code()
    try:
        sende(
            an=nutzer.email,
            betreff="Dein Anmeldecode für steuy",
            text=(
                f"Hallo {nutzer.name},\n\n"
                f"dein Code lautet: {code[:3]} {code[3:]}\n\n"
                f"Er gilt {MAIL_CODE_GUELTIG_SEKUNDEN // 60} Minuten und nur einmal.\n"
                "Hast du dich nicht gerade angemeldet? Dann kennt jemand dein Passwort: "
                "Bitte ändere es sofort.\n"
            ),
        )
    except MailFehler as fehler:
        raise ZweiFaktorFehler(
            "Der Code konnte nicht verschickt werden. Nutze einen Wiederherstellungscode "
            "oder bitte einen Admin, die Zwei-Faktor-Anmeldung zurückzusetzen."
        ) from fehler
    nutzer.mail_code_hash = hash_einmalcode(code)
    nutzer.mail_code_bis = jetzt + timedelta(seconds=MAIL_CODE_GUELTIG_SEKUNDEN)
    nutzer.mail_code_gesendet_am = jetzt
    protokolliere(
        "mail_code_gesendet", nutzer_id=nutzer.id, objekt_typ="nutzer", objekt_id=nutzer.id
    )
    db.session.commit()


def _pruefe_mail_code(nutzer: Nutzer, code: str, jetzt: datetime | None = None) -> bool:
    jetzt = jetzt or datetime.now(UTC)
    ziffern = nur_ziffern(code)
    if not nutzer.mail_code_hash or len(ziffern) != 6:
        return False
    if not nutzer.mail_code_bis or nutzer.mail_code_bis < jetzt:
        return False
    if not pruefe_passwort(nutzer.mail_code_hash, ziffern):
        return False
    # Nur einmal gültig
    nutzer.mail_code_hash = None
    nutzer.mail_code_bis = None
    return True


def starte_mail_einrichtung(nutzer: Nutzer) -> None:
    from app.services.mail import eingerichtet

    if nutzer.totp_aktiv:
        raise ZweiFaktorFehler("Die Zwei-Faktor-Anmeldung ist bereits eingerichtet.")
    if not eingerichtet():
        raise ZweiFaktorFehler(
            "Dafür muss zuerst der E-Mail-Versand eingerichtet sein (Einstellungen → E-Mail)."
        )
    sende_mail_code(nutzer)


def bestaetige_mail_einrichtung(nutzer: Nutzer, code: str) -> list[str]:
    if nutzer.totp_aktiv:
        raise ZweiFaktorFehler("Die Zwei-Faktor-Anmeldung ist bereits eingerichtet.")
    if not _pruefe_mail_code(nutzer, code):
        raise ZweiFaktorFehler("Der Code stimmt nicht oder ist abgelaufen. Bitte neu anfordern.")
    nutzer.totp_aktiv = True
    nutzer.zwei_faktor_art = "mail"
    nutzer.totp_geheimnis = None
    nutzer.totp_letzter_schritt = None
    codes = _neue_codes(nutzer)
    protokolliere(
        "zwei_faktor_aktiviert",
        nutzer_id=nutzer.id,
        objekt_typ="nutzer",
        objekt_id=nutzer.id,
        details={"art": "mail"},
    )
    db.session.commit()
    return codes
