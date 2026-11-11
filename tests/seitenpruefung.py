"""Prüft gerenderte Seiten auf Fehler, die nicht abstürzen, sondern still falsch aussehen.

Hintergrund: Ein Makro gab Attribute maskiert aus (autocomplete=&#34;off&#34;). Nichts stürzte
ab, kein Test sah es, der Browser ignorierte das kaputte Attribut. Diese Prüfungen suchen genau
solche Fehlerklassen auf jeder Seite.
"""

import re
from collections import Counter
from html.parser import HTMLParser

from jinja2 import Undefined
from jinja2.exceptions import UndefinedError

# Ein Attribut, dessen Wert maskierte Anführungszeichen enthält: name=&#34;wert&#34;
MASKIERTES_ATTRIBUT = re.compile(r"<[a-zA-Z][^<>]*?\s[\w:-]+=&(?:#34|#39|quot|apos);")
# HTML, das als Text erscheint (&lt;div ... statt <div ...)
HTML_ALS_TEXT = re.compile(
    r"&lt;/?(?:div|span|a|p|br|strong|em|input|label|ul|li|table|tr|td|svg|button|select)\b"
)
NONE_AUSGABE = re.compile(r'(?:value|content|title|aria-label|alt)="None"|>\s*None\s*<')
JINJA_RESTE = re.compile(r"\{\{|\{%|%\}|\}\}")


class MeldendesUndefined(Undefined):
    """Wie Jinjas Standard, aber eine nicht definierte Variable auszugeben ist ein Fehler.
    Abfragen wie {% if x %} bleiben erlaubt."""

    def __str__(self):  # noqa: D105
        self._fail_with_undefined_error()

    __html__ = __str__

    def __iter__(self):
        self._fail_with_undefined_error()


class _Leser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids: Counter = Counter()
        self.label_fuer: list[str] = []
        self.namen: set[str] = set()
        self.links: list[str] = []
        # Formulare: (Methode, Ziel, Anzahl sichtbarer Eingabefelder)
        self.formulare: list[list] = []
        self.probleme: list[str] = []
        self._in_template = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "template":
            self._in_template += 1
        # Inhalte von <template> sind Vorlagen mit Platzhaltern, sie zählen nicht als Seite
        if not self._in_template:
            if a.get("id"):
                self.ids[a["id"]] += 1
            if tag == "label" and a.get("for"):
                self.label_fuer.append(a["for"])
        if a.get("name"):
            self.namen.add(a["name"])
        for name, wert in attrs:
            if name.startswith("on"):
                self.probleme.append(f"Inline-Handler {name} an <{tag}> (CSP blockiert ihn)")
            if (
                name in ("href", "src", "action")
                and wert
                and wert.strip().lower().startswith("javascript:")
            ):
                self.probleme.append(f"javascript:-Adresse an <{tag}>")
        daten_skript = (a.get("type") or "").lower() in ("application/json", "application/ld+json")
        if tag == "script" and not a.get("src") and "nonce" not in a and not daten_skript:
            self.probleme.append("Inline-<script> ohne Nonce (CSP blockiert es)")
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if not self._in_template:
            if tag == "form":
                self.formulare.append([(a.get("method") or "get").lower(), a.get("action"), 0])
            elif self.formulare and (
                tag in ("textarea", "select")
                or (tag == "input" and a.get("type", "text") not in ("hidden", "submit", "button"))
            ):
                self.formulare[-1][2] += 1

    def handle_endtag(self, tag):
        if tag == "template" and self._in_template:
            self._in_template -= 1


def pruefe_html(html: str, formulare=()) -> list[str]:
    """Alle Funde einer Seite als Text (leer = in Ordnung)."""
    funde = []
    for treffer in MASKIERTES_ATTRIBUT.finditer(html):
        funde.append(f"Maskiertes Attribut: {treffer.group(0)[-80:]}")
    for treffer in HTML_ALS_TEXT.finditer(html):
        umgebung = html[max(0, treffer.start() - 40) : treffer.end() + 40]
        funde.append(f"HTML als Text: …{umgebung}…")
    for treffer in NONE_AUSGABE.finditer(html):
        funde.append(f"None ausgegeben: {html[max(0, treffer.start() - 60) : treffer.end()]}")
    ohne_skripte = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    for treffer in JINJA_RESTE.finditer(ohne_skripte):
        funde.append(
            f"Jinja-Rest: …{ohne_skripte[max(0, treffer.start() - 40) : treffer.end() + 40]}…"
        )
    leser = _Leser()
    leser.feed(html)
    funde += leser.probleme
    funde += [f"ID doppelt: {i} ({n}×)" for i, n in leser.ids.items() if n > 1]
    funde += [f"Label ohne Feld: for={f}" for f in leser.label_fuer if f not in leser.ids]
    for formular in formulare:
        felder = [f for f in formular if f.type != "CSRFTokenField" and f.name != "csrf_token"]
        # Ein Formular, von dem gar nichts auf der Seite steht, wird bewusst nicht gezeigt
        if not any(f.name in leser.namen for f in felder):
            continue
        for feld in felder:
            if feld.name not in leser.namen:
                funde.append(
                    f"Formularfeld fehlt auf der Seite: {type(formular).__name__}.{feld.name} "
                    "(würde beim Speichern still zurückgesetzt)"
                )
    return funde


def links_von(html: str) -> list[str]:
    leser = _Leser()
    leser.feed(html)
    return leser.links


def ids_von(html: str) -> set[str]:
    leser = _Leser()
    leser.feed(html)
    return set(leser.ids)


def formulare_von(html: str) -> list[tuple[str, str | None, int]]:
    leser = _Leser()
    leser.feed(html)
    return [tuple(f) for f in leser.formulare]


__all__ = [
    "MeldendesUndefined",
    "UndefinedError",
    "formulare_von",
    "ids_von",
    "links_von",
    "pruefe_html",
]
