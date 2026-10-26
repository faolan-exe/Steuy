"""Passkeys (WebAuthn): Anmelden mit Fingerabdruck, Gesicht, Geräte-PIN oder Sicherheitsschlüssel.

Der private Schlüssel verlässt das Gerät nie, steuy speichert nur den öffentlichen. Ein Passkey
mit Nutzerprüfung (PIN oder Biometrie) ersetzt Passwort und zweiten Faktor zugleich.
Passkeys brauchen HTTPS und einen Domainnamen, im Heimnetz zum Beispiel hinter einem Reverse
Proxy. Auf http://localhost geht es zum Testen.
"""

import ipaddress
import json
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit

from flask import current_app, request, session
from sqlalchemy import select
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.extensions import db
from app.models import Nutzer, Passkey
from app.services.protokoll import protokolliere

HERAUSFORDERUNG_GUELTIG = 300  # Sekunden
MAX_PASSKEYS = 10
SCHLUESSEL_REG = "passkey_registrierung"
SCHLUESSEL_ANM = "passkey_anmeldung"


class PasskeyFehler(ValueError):
    """Fehler mit einer Meldung, die man der Person zeigen darf."""


def _host() -> str:
    return urlsplit("//" + request.host).hostname or request.host


def rp_id() -> str:
    return current_app.config.get("PASSKEY_RP_ID") or _host()


def erwarteter_ursprung() -> str:
    konfig = current_app.config.get("PASSKEY_URSPRUNG")
    return konfig or f"{request.scheme}://{request.host}"


def moeglich() -> tuple[bool, str]:
    """Ob Passkeys unter dieser Adresse funktionieren, sonst mit Erklärung."""
    host = rp_id()
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    else:
        return False, (
            "Passkeys brauchen einen Domainnamen statt einer IP-Adresse "
            "(z. B. buchhaltung.example.de über einen Reverse Proxy mit HTTPS)."
        )
    lokal = host == "localhost" or host.endswith(".localhost")
    if request.scheme != "https" and not lokal:
        return (
            False,
            "Passkeys brauchen eine verschlüsselte Verbindung (HTTPS), siehe docs/passkeys.md.",
        )
    return True, ""


def _nutzer_handle(nutzer: Nutzer) -> bytes:
    return f"steuy-{nutzer.id}".encode()


def _merke(schluessel: str, challenge: bytes, nutzer_id: int | None = None) -> None:
    session[schluessel] = {
        "challenge": bytes_to_base64url(challenge),
        "bis": time.time() + HERAUSFORDERUNG_GUELTIG,
        "nutzer": nutzer_id,
    }


def _hole(schluessel: str) -> dict:
    """Die Herausforderung gilt nur einmal und nur kurz."""
    gespeichert = session.pop(schluessel, None)
    if not gespeichert or gespeichert.get("bis", 0) < time.time():
        raise PasskeyFehler("Die Anfrage ist abgelaufen. Bitte noch einmal versuchen.")
    return gespeichert


def liste(nutzer: Nutzer) -> list[Passkey]:
    return list(
        db.session.execute(
            select(Passkey).where(Passkey.nutzer_id == nutzer.id).order_by(Passkey.id)
        ).scalars()
    )


def registrierung_optionen(nutzer: Nutzer) -> str:
    ok, grund = moeglich()
    if not ok:
        raise PasskeyFehler(grund)
    vorhandene = liste(nutzer)
    if len(vorhandene) >= MAX_PASSKEYS:
        raise PasskeyFehler(f"Mehr als {MAX_PASSKEYS} Passkeys sind nicht möglich.")
    optionen = generate_registration_options(
        rp_id=rp_id(),
        rp_name="steuy",
        user_id=_nutzer_handle(nutzer),
        user_name=nutzer.email,
        user_display_name=nutzer.name,
        exclude_credentials=[PublicKeyCredentialDescriptor(id=p.credential_id) for p in vorhandene],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    _merke(SCHLUESSEL_REG, optionen.challenge, nutzer.id)
    return options_to_json(optionen)


def registrierung_abschliessen(nutzer: Nutzer, antwort: dict | str, name: str) -> Passkey:
    gemerkt = _hole(SCHLUESSEL_REG)
    if not isinstance(antwort, dict | str):
        raise PasskeyFehler("Die Antwort des Passkeys ist unvollständig.")
    if gemerkt.get("nutzer") != nutzer.id:
        raise PasskeyFehler("Die Anfrage gehört zu einer anderen Anmeldung.")
    try:
        geprueft = verify_registration_response(
            credential=antwort,
            expected_challenge=base64url_to_bytes(gemerkt["challenge"]),
            expected_rp_id=rp_id(),
            expected_origin=erwarteter_ursprung(),
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, KeyError, TypeError, AttributeError) as fehler:
        current_app.logger.info("Passkey-Registrierung abgelehnt: %s", fehler)
        raise PasskeyFehler("Der Passkey konnte nicht bestätigt werden.") from fehler
    vorhanden = db.session.execute(
        select(Passkey.id).where(Passkey.credential_id == geprueft.credential_id)
    ).first()
    if vorhanden:
        raise PasskeyFehler("Dieser Passkey ist schon eingerichtet.")
    transports = None
    try:
        daten = json.loads(antwort) if isinstance(antwort, str) else antwort
        transports = [str(t)[:20] for t in (daten.get("response", {}).get("transports") or [])]
    except (ValueError, AttributeError):
        pass
    passkey = Passkey(
        nutzer_id=nutzer.id,
        credential_id=geprueft.credential_id,
        public_key=geprueft.credential_public_key,
        sign_count=geprueft.sign_count,
        name=(name or "").strip()[:80] or "Passkey",
        transports=transports or None,
        geraetetyp=str(getattr(geprueft.credential_device_type, "value", "single_device")),
        gesichert=bool(geprueft.credential_backed_up),
    )
    db.session.add(passkey)
    db.session.flush()
    protokolliere(
        "passkey_eingerichtet",
        nutzer_id=nutzer.id,
        objekt_typ="passkey",
        objekt_id=passkey.id,
        details={"name": passkey.name},
    )
    db.session.commit()
    return passkey


def anmeldung_optionen() -> str:
    """Optionen für die Anmeldung ohne Eingabe (der Passkey verrät, wer es ist)."""
    ok, grund = moeglich()
    if not ok:
        raise PasskeyFehler(grund)
    optionen = generate_authentication_options(
        rp_id=rp_id(), user_verification=UserVerificationRequirement.REQUIRED
    )
    _merke(SCHLUESSEL_ANM, optionen.challenge)
    return options_to_json(optionen)


def anmeldung_pruefen(antwort: dict | str) -> Nutzer:
    gemerkt = _hole(SCHLUESSEL_ANM)
    if not isinstance(antwort, dict | str):
        raise PasskeyFehler("Die Antwort des Passkeys ist unvollständig.")
    try:
        daten = json.loads(antwort) if isinstance(antwort, str) else antwort
        roh_id = base64url_to_bytes(daten["rawId"])
    except (ValueError, KeyError, TypeError) as fehler:
        raise PasskeyFehler("Die Antwort des Passkeys ist unvollständig.") from fehler
    passkey = db.session.execute(
        select(Passkey).where(Passkey.credential_id == roh_id)
    ).scalar_one_or_none()
    # Gleiche Meldung für „unbekannt“ und „falsch“: Es wird nichts über Konten verraten
    allgemein = PasskeyFehler("Anmeldung mit Passkey fehlgeschlagen.")
    if passkey is None:
        raise allgemein
    nutzer = passkey.nutzer
    if not nutzer.is_active:
        raise allgemein
    handle = (daten.get("response") or {}).get("userHandle")
    if handle and base64url_to_bytes(handle) != _nutzer_handle(nutzer):
        raise allgemein
    try:
        geprueft = verify_authentication_response(
            credential=daten,
            expected_challenge=base64url_to_bytes(gemerkt["challenge"]),
            expected_rp_id=rp_id(),
            expected_origin=erwarteter_ursprung(),
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, KeyError, TypeError, AttributeError) as fehler:
        current_app.logger.info("Passkey-Anmeldung abgelehnt: %s", fehler)
        raise allgemein from fehler
    passkey.sign_count = geprueft.new_sign_count
    passkey.zuletzt_benutzt_am = datetime.now(UTC)
    protokolliere(
        "anmeldung_passkey",
        nutzer_id=nutzer.id,
        objekt_typ="passkey",
        objekt_id=passkey.id,
    )
    db.session.commit()
    return nutzer


def loesche(nutzer: Nutzer, passkey_id: int) -> None:
    passkey = db.session.get(Passkey, passkey_id)
    if passkey is None or passkey.nutzer_id != nutzer.id:
        raise PasskeyFehler("Diesen Passkey gibt es nicht.")
    protokolliere(
        "passkey_entfernt",
        nutzer_id=nutzer.id,
        objekt_typ="passkey",
        objekt_id=passkey.id,
        details={"name": passkey.name},
    )
    db.session.delete(passkey)
    db.session.commit()
