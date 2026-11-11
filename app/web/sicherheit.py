"""Sicherheits-Kopfzeilen für jede Antwort (nicht nur in der Demo).

- Content-Security-Policy: Skripte nur von steuy selbst oder mit dem Nonce dieser Antwort.
  Eingeschleustes HTML kann so kein JavaScript ausführen.
- Keine Einbettung in fremde Seiten (Clickjacking), kein MIME-Raten, keine Referrer nach außen.
- Seiten mit Daten werden nie zwischengespeichert (Cache-Control: no-store). Das gilt auch für
  Formulare, die bei einem Fehler das eingegebene Passwort stehen lassen.
"""

import secrets

from flask import Flask, g, request


def nonce() -> str:
    if "csp_nonce" not in g:
        g.csp_nonce = secrets.token_urlsafe(16)
    return g.csp_nonce


def csp(skript_nonce: str) -> str:
    return (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{skript_nonce}'; "
        # HTMX und einzelne Vorlagen setzen Stile inline, Stile führen keinen Code aus
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-src 'self' blob:; "
        "object-src 'self'; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )


def registriere(app: Flask) -> None:
    app.jinja_env.globals["csp_nonce"] = nonce

    @app.after_request
    def kopfzeilen(antwort):
        k = antwort.headers
        k.setdefault("X-Content-Type-Options", "nosniff")
        k.setdefault("X-Frame-Options", "SAMEORIGIN")
        k.setdefault("Referrer-Policy", "same-origin")
        k.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        k.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        k.setdefault("Content-Security-Policy", csp(nonce()))
        if request.endpoint != "static":
            k.setdefault("Cache-Control", "no-store")
        if request.is_secure:
            k.setdefault("Strict-Transport-Security", "max-age=31536000")
        return antwort
