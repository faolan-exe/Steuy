"""Rollen und Rechte nach docs/domain/rollen.md."""

from enum import StrEnum


class Rolle(StrEnum):
    ADMIN = "admin"
    BUCHHALTER = "buchhalter"
    MITARBEITER = "mitarbeiter"
    STEUERBERATER = "steuerberater"


ROLLEN_NAMEN = {
    Rolle.ADMIN: "Admin",
    Rolle.BUCHHALTER: "Buchhalter",
    Rolle.MITARBEITER: "Mitarbeiter",
    Rolle.STEUERBERATER: "Steuerberater",
}


class Recht(StrEnum):
    ANSEHEN = "ansehen"
    BELEGE = "belege"
    STAMMDATEN = "stammdaten"
    ENTWUERFE = "entwuerfe"
    RECHNUNGEN_VERSENDEN = "rechnungen_versenden"
    ZAHLUNGEN = "zahlungen"
    BUCHEN = "buchen"
    AUSWERTUNGEN = "auswertungen"
    EXPORT = "export"
    PROTOKOLL = "protokoll"
    EINSTELLUNGEN = "einstellungen"
    NUTZER_VERWALTEN = "nutzer_verwalten"
    JAHR_ABSCHLIESSEN = "jahr_abschliessen"


RECHTE_NAMEN = {
    Recht.ANSEHEN: "Dashboard, Listen und Belege ansehen",
    Recht.BELEGE: "Belege hochladen, unverbuchte Belege löschen",
    Recht.STAMMDATEN: "Kontakte und Artikel bearbeiten",
    Recht.ENTWUERFE: "Angebote und Rechnungen als Entwurf anlegen",
    Recht.RECHNUNGEN_VERSENDEN: "Rechnungen finalisieren und versenden",
    Recht.ZAHLUNGEN: "Zahlungen erfassen, Gebühren zuordnen",
    Recht.BUCHEN: "Buchungen festschreiben und stornieren",
    Recht.AUSWERTUNGEN: "EÜR und Auswertungen ansehen",
    Recht.EXPORT: "Export (ZIP für Steuerberater, CSV)",
    Recht.PROTOKOLL: "Änderungsprotokoll ansehen",
    Recht.EINSTELLUNGEN: "Einstellungen (Firmendaten, Nummernkreise, Shop, Mahnstufen)",
    Recht.NUTZER_VERWALTEN: "Nutzer verwalten und Rechte ändern",
    Recht.JAHR_ABSCHLIESSEN: "Geschäftsjahr abschließen",
}

# Hat jeder aktive Nutzer, nicht abwählbar.
IMMER = frozenset({Recht.ANSEHEN})

# Nur Admins. Nicht an andere Rollen vergebbar, sonst könnte sich jemand selbst zum Admin machen.
NUR_ADMIN = frozenset({Recht.EINSTELLUNGEN, Recht.NUTZER_VERWALTEN, Recht.JAHR_ABSCHLIESSEN})

# Diese Rechte kann der Admin je Rolle (außer Admin) ein- und ausschalten.
EINSTELLBAR = tuple(r for r in Recht if r not in IMMER and r not in NUR_ADMIN)

EINSTELLBARE_ROLLEN = (Rolle.BUCHHALTER, Rolle.MITARBEITER, Rolle.STEUERBERATER)

STANDARDRECHTE: dict[Rolle, frozenset[Recht]] = {
    Rolle.BUCHHALTER: frozenset(
        {
            Recht.BELEGE,
            Recht.STAMMDATEN,
            Recht.ENTWUERFE,
            Recht.RECHNUNGEN_VERSENDEN,
            Recht.ZAHLUNGEN,
            Recht.BUCHEN,
            Recht.AUSWERTUNGEN,
            Recht.EXPORT,
            Recht.PROTOKOLL,
        }
    ),
    Rolle.MITARBEITER: frozenset({Recht.BELEGE, Recht.STAMMDATEN, Recht.ENTWUERFE}),
    Rolle.STEUERBERATER: frozenset({Recht.AUSWERTUNGEN, Recht.EXPORT, Recht.PROTOKOLL}),
}


def hat_recht(rolle: Rolle, recht: Recht, vergeben: set[Recht]) -> bool:
    """Ob eine Rolle ein Recht hat. `vergeben` sind die eingestellten Rechte dieser Rolle."""
    if rolle == Rolle.ADMIN or recht in IMMER:
        return True
    if recht in NUR_ADMIN:
        return False
    return recht in vergeben
