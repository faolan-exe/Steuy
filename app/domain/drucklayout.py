"""Drucklayout: Auswahl, Grenzen und Prüfung der Einstellungen für Rechnungen, Angebote usw."""

import re
from dataclasses import dataclass, fields

LAYOUTS = {
    1: ("Klassisch", "Logo rechts, schlichte Linien"),
    2: ("Modern", "Logo links, Titel und Tabellenlinie in Akzentfarbe"),
    3: ("Elegant", "Alles mittig, feine Linien"),
    4: ("Farbband", "Farbiges Band oben, gefüllter Tabellenkopf"),
    5: ("Seitenleiste", "Farbiger Streifen am linken Rand"),
}

# Nur Schriften, die im Container vorhanden sind (Liberation ersetzt Arial und Times, DejaVu)
SCHRIFTEN = {
    "sans": (
        "Sans-Serif (Arial-ähnlich)",
        '"Liberation Sans", "Helvetica Neue", Helvetica, Arial, "DejaVu Sans", sans-serif',
    ),
    "serif": (
        "Serif (Times-ähnlich)",
        '"Liberation Serif", "Times New Roman", Times, "DejaVu Serif", serif',
    ),
    "dejavu": ("DejaVu Sans (breit)", '"DejaVu Sans", Verdana, sans-serif'),
    "dejavuserif": ("DejaVu Serif (breit)", '"DejaVu Serif", Georgia, serif'),
}

LOGO_POSITIONEN = {
    "auto": "Wie im Layout",
    "links": "Links",
    "mitte": "Mitte",
    "rechts": "Rechts",
}
# Standardplatz des Logos je Layout, wenn „Wie im Layout“ gewählt ist
LOGO_STANDARD = {1: "rechts", 2: "links", 3: "mitte", 4: "links", 5: "links"}

FARBVORSCHLAEGE = ("#2e7d4f", "#1f5fa8", "#b23a48", "#c9772b", "#5b4b8a", "#333333")
FARBE = re.compile(r"^#[0-9a-fA-F]{6}$")

LOGO_PROZENT = (30, 250)
TEXT_PT = (8, 12)
TITEL_PT = (12, 22)


class LayoutUngueltig(ValueError):
    pass


@dataclass
class Layout:
    layout: int = 1
    akzent: str = "#2e7d4f"
    schrift: str = "sans"
    schrift_text: int = 10
    schrift_titel: int = 15
    logo_prozent: int = 100
    logo_position: str = "auto"
    zeige_firmenname: bool = True
    zeige_absenderzeile: bool = True
    zeige_pos: bool = True
    gesamt_grau: bool = False
    zeige_fusszeile: bool = True
    zeige_bank: bool = True
    zeige_steuer: bool = True

    @property
    def schriftfamilie(self) -> str:
        return SCHRIFTEN[self.schrift][1]

    @property
    def logo_platz(self) -> str:
        """Wo Logo und Firmenname stehen: links, mitte oder rechts."""
        return LOGO_STANDARD[self.layout] if self.logo_position == "auto" else self.logo_position

    @property
    def akzent_text(self) -> str:
        """Schriftfarbe auf einer Akzentfläche: weiß oder schwarz je nach Helligkeit."""
        return kontrastfarbe(self.akzent)

    @property
    def akzent_hell(self) -> str:
        return mische(self.akzent, 0.88)


def kontrastfarbe(hexfarbe: str) -> str:
    r, g, b = (int(hexfarbe[i : i + 2], 16) for i in (1, 3, 5))
    # Wahrgenommene Helligkeit (ITU-R BT.601)
    return "#111111" if (299 * r + 587 * g + 114 * b) / 1000 > 150 else "#ffffff"


def mische(hexfarbe: str, anteil_weiss: float) -> str:
    """Hellt eine Farbe auf (für Tabellenköpfe und Flächen)."""
    r, g, b = (int(hexfarbe[i : i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(c + (255 - c) * anteil_weiss):02x}" for c in (r, g, b))


def _zahl(wert, grenzen: tuple[int, int], name: str) -> int:
    try:
        zahl = int(str(wert).strip())
    except (TypeError, ValueError) as fehler:
        raise LayoutUngueltig(f"{name}: Bitte eine ganze Zahl eingeben.") from fehler
    if not grenzen[0] <= zahl <= grenzen[1]:
        raise LayoutUngueltig(f"{name}: Zwischen {grenzen[0]} und {grenzen[1]}.")
    return zahl


def pruefe(werte: dict) -> Layout:
    """Baut ein geprüftes Layout aus Eingabewerten (Formular oder Vorschau-Adresse)."""
    standard = Layout()
    layout = _zahl(werte.get("layout", standard.layout), (1, len(LAYOUTS)), "Layout")
    akzent = str(werte.get("akzent", standard.akzent)).strip().lower()
    if not FARBE.match(akzent):
        raise LayoutUngueltig("Akzentfarbe: Bitte eine Farbe wie #2e7d4f wählen.")
    schrift = werte.get("schrift", standard.schrift)
    if schrift not in SCHRIFTEN:
        raise LayoutUngueltig("Schriftart: Bitte aus der Liste wählen.")

    position = werte.get("logo_position", standard.logo_position)
    if position not in LOGO_POSITIONEN:
        raise LayoutUngueltig("Logo-Platz: Bitte links, Mitte, rechts oder „Wie im Layout“ wählen.")

    def haken(name: str) -> bool:
        wert = werte.get(name)
        return wert in (True, "y", "1", "on", "true", "ja")

    return Layout(
        layout=layout,
        akzent=akzent,
        schrift=schrift,
        schrift_text=_zahl(werte.get("schrift_text", standard.schrift_text), TEXT_PT, "Fließtext"),
        schrift_titel=_zahl(
            werte.get("schrift_titel", standard.schrift_titel), TITEL_PT, "Überschrift"
        ),
        logo_prozent=_zahl(
            werte.get("logo_prozent", standard.logo_prozent), LOGO_PROZENT, "Logo-Größe"
        ),
        logo_position=position,
        zeige_firmenname=haken("zeige_firmenname"),
        zeige_absenderzeile=haken("zeige_absenderzeile"),
        zeige_pos=haken("zeige_pos"),
        gesamt_grau=haken("gesamt_grau"),
        zeige_fusszeile=haken("zeige_fusszeile"),
        zeige_bank=haken("zeige_bank"),
        zeige_steuer=haken("zeige_steuer"),
    )


def feldnamen() -> list[str]:
    return [f.name for f in fields(Layout)]
