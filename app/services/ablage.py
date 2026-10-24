"""Unveränderliche Dateiablage. Dateiname = SHA-256 des Inhalts (docs/architektur.md)."""

import hashlib
import os
from pathlib import Path

from flask import current_app


class AblageBeschaedigt(RuntimeError):
    """Der Inhalt passt nicht mehr zum gespeicherten Hash."""


def _verzeichnis() -> Path:
    return Path(current_app.config["ABLAGE_VERZEICHNIS"])


def _pfad(sha256: str) -> Path:
    return _verzeichnis() / sha256[:2] / sha256


def speichere(inhalt: bytes) -> str:
    sha256 = hashlib.sha256(inhalt).hexdigest()
    pfad = _pfad(sha256)
    if not pfad.exists():
        pfad.parent.mkdir(parents=True, exist_ok=True)
        temp = pfad.with_suffix(".tmp")
        temp.write_bytes(inhalt)
        os.chmod(temp, 0o444)
        temp.replace(pfad)
    return sha256


def lies(sha256: str) -> bytes:
    inhalt = _pfad(sha256).read_bytes()
    if hashlib.sha256(inhalt).hexdigest() != sha256:
        raise AblageBeschaedigt(f"Datei {sha256} wurde verändert.")
    return inhalt
