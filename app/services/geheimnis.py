"""Verschlüsselung kleiner Geheimnisse (z. B. TOTP-Schlüssel) mit einem aus SECRET_KEY
abgeleiteten Schlüssel. Ändert sich SECRET_KEY, müssen Nutzer 2FA neu einrichten."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


def _fernet() -> Fernet:
    # „taxcraft“ ist der frühere Projektname. Nicht ändern: Sonst lassen sich die
    # gespeicherten 2FA-Geheimnisse bestehender Installationen nicht mehr entschlüsseln.
    roh = hashlib.sha256(("taxcraft-geheimnis:" + current_app.config["SECRET_KEY"]).encode())
    return Fernet(base64.urlsafe_b64encode(roh.digest()))


def verschluessele(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def entschluessele(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
