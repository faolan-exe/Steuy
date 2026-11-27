"""Versionen vergleichen und Release-Texte von GitHub lesbar aufbereiten (ohne Netzwerk)."""

import re

VERSION_MUSTER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


# Schritte des Updates, in derselben Reihenfolge wie in scripts/update-ausfuehren.sh
UPDATE_SCHRITTE = (
    "Sicherung anlegen",
    "Neue Version laden",
    "Version prüfen",
    "Programm ersetzen",
    "Neu bauen und starten",
    "Neue Version prüfen",
)
# So lange darf eine Anfrage liegen, bis der Dienst auf dem Server sie aufgreift
DIENST_WARTET_HOECHSTENS = 90  # Sekunden
# Ohne neues Lebenszeichen gilt ein laufendes Update als hängen geblieben
LAUF_STILL_HOECHSTENS = 20 * 60  # Sekunden


def update_lage(status: dict, jetzt: float) -> str:
    """Was die Seite zeigen soll: „bereit“, „wartet“, „laeuft“, „haengt“, „dienst_fehlt“,
    „fertig“ oder „fehlgeschlagen“."""
    zustand = status.get("zustand")
    zeit = status.get("zeit")
    alter = jetzt - zeit if isinstance(zeit, int | float) else None
    if zustand == "angefragt":
        return (
            "dienst_fehlt" if alter is not None and alter > DIENST_WARTET_HOECHSTENS else "wartet"
        )
    if zustand == "laeuft":
        return "haengt" if alter is not None and alter > LAUF_STILL_HOECHSTENS else "laeuft"
    if zustand == "fertig":
        # Die Erfolgsmeldung nur einen Tag lang zeigen, danach ist die Seite wieder normal
        return "bereit" if alter > 24 * 3600 else "fertig"
    if zustand == "fehlgeschlagen":
        return zustand
    return "bereit"


class VersionUngueltig(ValueError):
    pass


def lies_version(text: str) -> tuple[int, int, int]:
    """„v0.2.1“ oder „0.2.1“ → (0, 2, 1)."""
    treffer = VERSION_MUSTER.match((text or "").strip())
    if not treffer:
        raise VersionUngueltig(f"Keine Version: {text!r}")
    return tuple(int(teil) for teil in treffer.groups())


def ist_neuer(kandidat: str, installiert: str) -> bool:
    return lies_version(kandidat) > lies_version(installiert)


def tag_fuer(version: str) -> str:
    return "v" + ".".join(str(teil) for teil in lies_version(version))


ABSCHNITTE = {
    "neu": "Neu",
    "neues": "Neu",
    "features": "Neu",
    "hinzugefügt": "Neu",
    "added": "Neu",
    "was ist neu": "Neu",
    "behoben": "Behoben",
    "fixes": "Behoben",
    "bugfixes": "Behoben",
    "fixed": "Behoben",
    "korrigiert": "Behoben",
    "was wurde behoben": "Behoben",
    "geändert": "Geändert",
    "changed": "Geändert",
    "verbessert": "Geändert",
}


def release_notizen(text: str) -> list[tuple[str, list[str]]]:
    """Gliedert den Release-Text in Abschnitte („Neu“, „Behoben“, „Geändert“, sonst „Hinweise“).

    Überschriften wie „## Neu“ oder „## Behoben“ werden erkannt, Aufzählungspunkte
    („- ...“ oder „* ...“) werden zu Einträgen. Text ohne Aufzählung bleibt Zeile für Zeile
    erhalten."""
    abschnitte: dict[str, list[str]] = {}
    aktuell = "Hinweise"
    for zeile in (text or "").replace("\r", "").split("\n"):
        zeile = zeile.strip()
        if not zeile:
            continue
        kopf = re.match(r"^#{1,6}\s*(.+?)\s*:?$", zeile)
        if kopf:
            aktuell = ABSCHNITTE.get(kopf.group(1).strip().lower(), kopf.group(1).strip())
            abschnitte.setdefault(aktuell, [])
            continue
        punkt = re.match(r"^[-*+]\s+(.*)$", zeile)
        eintrag = (punkt.group(1) if punkt else zeile).strip()
        # Markdown-Zeichen für Fett, Code und Links entfernen
        eintrag = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", eintrag)
        eintrag = re.sub(r"[*_`]{1,3}", "", eintrag)
        if eintrag:
            abschnitte.setdefault(aktuell, []).append(eintrag)
    reihenfolge = {"Neu": 0, "Behoben": 1, "Geändert": 2}
    return sorted(
        ((name, eintraege) for name, eintraege in abschnitte.items() if eintraege),
        key=lambda a: (reihenfolge.get(a[0], 9),),
    )
