"""Konfiguration aus Umgebungsvariablen."""

import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "postgresql+psycopg://localhost/steuy")
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Hinter HTTPS (Reverse Proxy) auf 1 setzen, damit das Cookie nur verschlüsselt geht.
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE") == "1"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    # Anzahl vorgeschalteter Reverse Proxys (z. B. 1 für Caddy/nginx), sonst 0
    PROXY_ANZAHL = int(os.environ.get("PROXY_ANZAHL", "0"))
    # Unveränderliche Dateien (Rechnungs-PDFs, später Belege). Gehört ins Backup.
    ABLAGE_VERZEICHNIS = os.environ.get("ABLAGE_VERZEICHNIS", "instance/ablage")
    # Update-Prüfung: GitHub-Repository, optional ein Token (nur nötig bei privatem Repository)
    UPDATE_REPO = os.environ.get("UPDATE_REPO", "faolan-exe/Steuy")
    UPDATE_TOKEN = os.environ.get("UPDATE_TOKEN", "")
    # Gemeinsamer Ordner mit dem Update-Dienst des Servers (im LXC-Setup eingebunden)
    UPDATE_VERZEICHNIS = os.environ.get("UPDATE_VERZEICHNIS", "")
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # mehrere Belege à max. 20 MB auf einmal
    # Texterkennung für Fotos und Scans (braucht Tesseract), mit TEXTERKENNUNG=0 abschalten
    TEXTERKENNUNG = os.environ.get("TEXTERKENNUNG", "1") != "0"
    # Ordner, in den der Scanner speichert (Scan-Eingang). Im Docker-Betrieb /daten/scan-eingang.
    SCAN_VERZEICHNIS = os.environ.get("SCAN_VERZEICHNIS", "instance/scan-eingang")
    # Steuerdatei für die Samba-Freigabe und deren Adresse im Docker-Netz (Anzeige "läuft")
    FREIGABE_VERZEICHNIS = os.environ.get("FREIGABE_VERZEICHNIS", "instance/freigabe")
    SCAN_FREIGABE_HOST = os.environ.get("SCAN_FREIGABE_HOST", "scanfreigabe")
    # Öffentliche Adresse, z. B. https://buchhaltung.example.de, für Links in E-Mails
    BASIS_URL = os.environ.get("BASIS_URL", "")


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "nur-fuer-tests"
    WTF_CSRF_ENABLED = False
    MAIL_TESTBETRIEB = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", "postgresql+psycopg://localhost/steuy_test"
    )
