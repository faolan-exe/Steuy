"""Fehlerseiten auf Deutsch, mit einem Weg zurück. Die Standardseiten sind englisch und enden
in einer Sackgasse (z. B. nach dem Neuladen einer abgeschickten Seite)."""

from flask import Flask, render_template, request
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

TEXTE = {
    400: (
        "Das hat nicht geklappt",
        "Die Anfrage war unvollständig. Bitte gehe zurück und versuche es noch einmal.",
    ),
    403: (
        "Dafür fehlt dir die Berechtigung",
        "Diese Seite ist für deine Rolle nicht freigegeben. Ein Admin kann dir die Rechte unter "
        "Einstellungen → Rechte geben.",
    ),
    404: (
        "Seite nicht gefunden",
        "Diese Seite gibt es nicht (mehr). Vielleicht wurde der Eintrag gelöscht oder der Link "
        "ist veraltet.",
    ),
    405: (
        "Diese Seite lässt sich so nicht öffnen",
        "Das passiert zum Beispiel, wenn man eine Seite neu lädt, nachdem man ein Formular "
        "abgeschickt hat. Gehe zurück zur Übersicht und öffne sie von dort aus neu.",
    ),
    413: (
        "Die Datei ist zu groß",
        "Auf einmal sind bis zu 100 MB erlaubt, je Datei höchstens 20 MB. Bitte lade weniger "
        "oder kleinere Dateien hoch.",
    ),
}
CSRF_TEXT = (
    "Die Seite war zu lange geöffnet",
    "Aus Sicherheitsgründen läuft ein geöffnetes Formular nach einiger Zeit ab, oder es wurde "
    "schon abgeschickt. Bitte lade die Seite neu und versuche es noch einmal.",
)

# Minimale Seite für interne Fehler: Sie darf nichts aus der Datenbank brauchen, weil die
# vielleicht gerade das Problem ist.
SEITE_500 = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Fehler – steuy</title>
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:34rem;margin:15vh auto;padding:0 1rem;
color:#222}a{color:#2f6f4e}</style></head><body><h1>Da ist etwas schiefgelaufen</h1>
<p>Das liegt an steuy, nicht an dir. Deine Daten sind sicher: Es wurde nichts halb gespeichert.
Bitte versuche es in einem Moment noch einmal. Hilft das nicht, schau in die Protokolle
(<code>docker compose logs app</code>) oder frag deine Betreuung.</p>
<p><a href="/">Zur Startseite</a></p></body></html>"""


def _seite(status: int, titel: str, text: str):
    # JSON-Aufrufer (z. B. /gesund) bekommen keine HTML-Seite
    return render_template("fehler.html", status=status, titel=titel, text=text), status


def registriere(app: Flask) -> None:
    @app.errorhandler(CSRFError)
    def csrf(_fehler):
        return _seite(400, *CSRF_TEXT)

    @app.errorhandler(HTTPException)
    def http(fehler: HTTPException):
        status = fehler.code or 500
        if status in TEXTE:
            return _seite(status, *TEXTE[status])
        return fehler

    @app.errorhandler(500)
    def intern(_fehler):
        app.logger.exception("Interner Fehler bei %s %s", request.method, request.path)
        return SEITE_500, 500
