"""CSV-Dateien anderer Programme (z. B. Lexware Office) für den Import lesen und zuordnen.

Die Spalten heißen je Programm anders. Deshalb wird nur vorgeschlagen, welche Spalte
wohin gehört. Die endgültige Zuordnung bestätigt der Nutzer vor dem Import.
"""

import csv
import io
import re

from app.domain.geld import GeldFormatFehler, euro_zu_cent

MAX_ZEILEN = 5000
MAX_GROESSE = 2 * 1024 * 1024

# Zielfeld → Beschriftung und bekannte Spaltennamen (klein, ohne Sonderzeichen verglichen)
FELDER = {
    "kontakte": {
        "firmenname": (
            "Firmenname",
            ["firmenname", "firma", "unternehmen", "company", "organisation"],
        ),
        "anrede": ("Anrede", ["anrede", "salutation"]),
        "vorname": ("Vorname", ["vorname", "firstname", "first name"]),
        "nachname": ("Nachname", ["nachname", "name", "lastname", "last name", "familienname"]),
        "adresszusatz": ("Adresszusatz", ["adresszusatz", "zusatz", "addresszusatz", "co"]),
        "strasse": (
            "Straße und Hausnummer",
            [
                "strasse",
                "straße",
                "strasse und hausnummer",
                "straße und hausnummer",
                "adresse",
                "anschrift",
                "street",
                "address",
            ],
        ),
        "plz": ("PLZ", ["plz", "postleitzahl", "zip", "postcode", "zip code"]),
        "ort": ("Ort", ["ort", "stadt", "city"]),
        "land": ("Land", ["land", "country", "staat"]),
        "email": ("E-Mail", ["email", "e-mail", "mail", "emailadresse", "e-mail-adresse"]),
        "telefon": ("Telefon", ["telefon", "telefonnummer", "tel", "phone", "mobil"]),
        "steuernummer": ("Steuernummer", ["steuernummer", "steuer-nr", "steuernr"]),
        "ust_idnr": ("USt-IdNr.", ["ust-idnr", "ustidnr", "umsatzsteuer-id", "ust-id", "vat id"]),
        "notiz": ("Notiz", ["notiz", "notizen", "bemerkung", "anmerkung", "kommentar"]),
        "kundennummer": ("Kundennummer", ["kundennummer", "kunden-nr", "kundennr", "kunden nr"]),
        "lieferantennummer": (
            "Lieferantennummer",
            ["lieferantennummer", "lieferanten-nr", "lieferantennr", "lieferanten nr"],
        ),
    },
    "artikel": {
        "bezeichnung": (
            "Bezeichnung",
            ["bezeichnung", "name", "titel", "artikelname", "produktname"],
        ),
        "artikelnummer": (
            "Artikelnummer",
            ["artikelnummer", "artikel-nr", "artikelnr", "sku", "nummer"],
        ),
        "beschreibung": ("Beschreibung", ["beschreibung", "langtext", "description"]),
        "einheit": ("Einheit", ["einheit", "mengeneinheit", "unit"]),
        "preis": ("Preis EUR", ["preis", "preis eur", "verkaufspreis", "price"]),
        "typ": ("Typ (Produkt/Dienstleistung)", ["typ", "art", "artikeltyp", "type"]),
        "gtin": ("GTIN/EAN", ["gtin", "ean", "barcode"]),
        "notiz": ("Notiz", ["notiz", "bemerkung", "anmerkung"]),
    },
}
PFLICHT = {"kontakte": [], "artikel": ["bezeichnung", "preis"]}


class CsvUngueltig(ValueError):
    pass


def _normal(text: str) -> str:
    text = (text or "").strip().lower().replace("ß", "ss")
    text = re.sub(r"[.:()\[\]/]", "", text)
    return re.sub(r"\s+", " ", text)


def lies(inhalt: bytes) -> tuple[list[str], list[list[str]]]:
    """Spaltennamen und Zeilen. Erkennt UTF-8 (mit/ohne BOM) und Windows-1252,
    Semikolon, Komma oder Tabulator."""
    if not inhalt:
        raise CsvUngueltig("Die Datei ist leer.")
    if len(inhalt) > MAX_GROESSE:
        raise CsvUngueltig("Die Datei ist größer als 2 MB. Bitte in mehrere Dateien aufteilen.")
    try:
        text = inhalt.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = inhalt.decode("cp1252", errors="replace")
    erste = text.split("\n", 1)[0]
    trenner = max(";,\t", key=erste.count)
    if not erste.count(trenner):
        raise CsvUngueltig("Keine Spalten erkannt. Ist das eine CSV-Datei?")
    try:
        zeilen = list(csv.reader(io.StringIO(text), delimiter=trenner))
    except csv.Error as fehler:
        raise CsvUngueltig("Die Datei ist keine lesbare CSV-Datei.") from fehler
    kopf = [s.strip() for s in zeilen[0]]
    # Leere Zeilen bleiben drin, damit die Zeilennummern zur Datei passen
    daten = zeilen[1:]
    while daten and leer(daten[-1]):
        daten.pop()
    if not any(not leer(z) for z in daten):
        raise CsvUngueltig("Die Datei enthält keine Datenzeilen.")
    if len(daten) > MAX_ZEILEN:
        raise CsvUngueltig(f"Höchstens {MAX_ZEILEN} Zeilen auf einmal.")
    return kopf, daten


def leer(zeile: list[str]) -> bool:
    """True, wenn die Zeile keinen Inhalt hat."""
    return not any(feld.strip() for feld in zeile)


def vorschlag(art: str, spalten: list[str]) -> dict[str, int | None]:
    """Zielfeld → Spaltenindex. Genaue Treffer vor Teiltreffern, jede Spalte höchstens einmal."""
    normal = [_normal(s) for s in spalten]
    zuordnung: dict[str, int | None] = {}
    vergeben: set[int] = set()
    for feld, (_, namen) in FELDER[art].items():
        kandidaten = [_normal(n) for n in namen]
        treffer = next(
            (i for i, s in enumerate(normal) if s in kandidaten and i not in vergeben), None
        )
        zuordnung[feld] = treffer
        if treffer is not None:
            vergeben.add(treffer)
    return zuordnung


def _wert(zeile: list[str], index: int | None) -> str | None:
    if index is None or index >= len(zeile):
        return None
    return zeile[index].strip() or None


def kontakt_aus(zeile: list[str], zuordnung: dict[str, int | None], typ: str) -> dict:
    daten = {feld: _wert(zeile, index) for feld, index in zuordnung.items()}
    if not daten.get("firmenname") and not daten.get("nachname"):
        raise CsvUngueltig("Weder Firmenname noch Nachname.")
    daten["art"] = "firma" if daten.get("firmenname") else "person"
    for feld in ("kundennummer", "lieferantennummer"):
        nummer = daten.get(feld)
        daten[feld] = int(nummer) if nummer and nummer.isdigit() else None
    if daten.get("email") and "@" not in daten["email"]:
        raise CsvUngueltig(f"Ungültige E-Mail-Adresse: {daten['email']}")
    daten["typ"] = typ
    return daten


def artikel_aus(zeile: list[str], zuordnung: dict[str, int | None]) -> dict:
    daten = {feld: _wert(zeile, index) for feld, index in zuordnung.items()}
    if not daten.get("bezeichnung"):
        raise CsvUngueltig("Bezeichnung fehlt.")
    try:
        daten["preis_cent"] = euro_zu_cent(daten.pop("preis") or "")
    except GeldFormatFehler as fehler:
        raise CsvUngueltig(f"Preis nicht lesbar: {fehler}") from fehler
    typ = _normal(daten.get("typ") or "")
    daten["typ"] = "service" if typ.startswith(("dienst", "leistung", "service")) else "produkt"
    daten["einheit"] = daten.get("einheit") or ("Stunde" if daten["typ"] == "service" else "Stück")
    return daten
