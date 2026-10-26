"""Software-Authenticator für Tests: erzeugt echte WebAuthn-Antworten (ES256, ohne Attestation)."""

import hashlib
import json
import os
import struct

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

UP, UV, AT = 0x01, 0x04, 0x40


class Authenticator:
    def __init__(self, ursprung: str = "http://localhost", rp_id: str = "localhost") -> None:
        self.ursprung = ursprung
        self.rp_id = rp_id
        self.schluessel = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.zaehler = 0
        self.user_handle: bytes = b""

    def _client_data(self, art: str, herausforderung: str, ursprung: str | None = None) -> bytes:
        return json.dumps(
            {
                "type": art,
                "challenge": herausforderung,
                "origin": ursprung or self.ursprung,
                "crossOrigin": False,
            }
        ).encode()

    def _cose(self) -> bytes:
        zahlen = self.schluessel.public_key().public_numbers()
        return cbor2.dumps(
            {1: 2, 3: -7, -1: 1, -2: zahlen.x.to_bytes(32, "big"), -3: zahlen.y.to_bytes(32, "big")}
        )

    def registrieren(self, optionen: dict, *, flags: int = UP | UV, ursprung: str | None = None):
        self.user_handle = base64url_to_bytes(optionen["user"]["id"])
        client = self._client_data("webauthn.create", optionen["challenge"], ursprung)
        daten = (
            hashlib.sha256(self.rp_id.encode()).digest()
            + bytes([flags | AT])
            + struct.pack(">I", self.zaehler)
            + bytes(16)
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + self._cose()
        )
        objekt = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": daten})
        kennung = bytes_to_base64url(self.credential_id)
        return {
            "id": kennung,
            "rawId": kennung,
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client),
                "attestationObject": bytes_to_base64url(objekt),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
        }

    def anmelden(
        self,
        optionen: dict,
        *,
        flags: int = UP | UV,
        zaehler: int | None = None,
        schluessel=None,
        handle: bytes | None = None,
        ursprung: str | None = None,
    ):
        self.zaehler = zaehler if zaehler is not None else self.zaehler + 1
        client = self._client_data("webauthn.get", optionen["challenge"], ursprung)
        daten = (
            hashlib.sha256(self.rp_id.encode()).digest()
            + bytes([flags])
            + struct.pack(">I", self.zaehler)
        )
        signatur = (schluessel or self.schluessel).sign(
            daten + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256())
        )
        kennung = bytes_to_base64url(self.credential_id)
        return {
            "id": kennung,
            "rawId": kennung,
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client),
                "authenticatorData": bytes_to_base64url(daten),
                "signature": bytes_to_base64url(signatur),
                "userHandle": bytes_to_base64url(
                    handle if handle is not None else self.user_handle
                ),
            },
            "clientExtensionResults": {},
        }
