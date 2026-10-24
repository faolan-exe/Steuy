"""Zwei-Faktor-Anmeldung mit Einmalcodes (TOTP, RFC 6238) und Wiederherstellungscodes."""

import secrets
import time

import pyotp

AUSSTELLER = "steuy"
ANZAHL_WIEDERHERSTELLUNGSCODES = 10
MAIL_CODE_GUELTIG_SEKUNDEN = 600
MAIL_CODE_NEU_FRUEHESTENS_SEKUNDEN = 60
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # ohne leicht verwechselbare Zeichen


def neuer_mail_code() -> str:
    """Sechs Ziffern, kryptografisch zufällig, mit führenden Nullen."""
    return f"{secrets.randbelow(1_000_000):06d}"


def nur_ziffern(code: str | None) -> str:
    return "".join(z for z in (code or "") if z.isdigit())


def neues_geheimnis() -> str:
    return pyotp.random_base32()


def einrichtungs_uri(geheimnis: str, konto: str) -> str:
    return pyotp.TOTP(geheimnis).provisioning_uri(name=konto, issuer_name=AUSSTELLER)


def zeitschritt(zeitpunkt: float | None = None) -> int:
    return int((time.time() if zeitpunkt is None else zeitpunkt) // 30)


def pruefe_code(
    geheimnis: str, code: str, letzter_schritt: int | None, zeitpunkt: float | None = None
) -> int | None:
    """Gibt den verwendeten Zeitschritt zurück oder None.

    Erlaubt einen Schritt Abweichung (Uhren gehen ungenau) und lehnt bereits verwendete
    oder ältere Schritte ab, damit ein mitgelesener Code nicht erneut funktioniert.
    """
    code = "".join(z for z in (code or "") if z.isdigit())
    if len(code) != 6:
        return None
    totp = pyotp.TOTP(geheimnis)
    jetzt = zeitschritt(zeitpunkt)
    for schritt in (jetzt - 1, jetzt, jetzt + 1):
        if letzter_schritt is not None and schritt <= letzter_schritt:
            continue
        if secrets.compare_digest(totp.at(schritt * 30), code):
            return schritt
    return None


def neue_wiederherstellungscodes() -> list[str]:
    def code() -> str:
        teile = ["".join(secrets.choice(_ALPHABET) for _ in range(5)) for _ in range(2)]
        return "-".join(teile)

    return [code() for _ in range(ANZAHL_WIEDERHERSTELLUNGSCODES)]


def normalisiere_wiederherstellungscode(code: str) -> str:
    roh = "".join(z for z in (code or "").lower() if z.isalnum())
    return f"{roh[:5]}-{roh[5:]}" if len(roh) == 10 else roh
