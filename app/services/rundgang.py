"""Rundgang: Stufe merken, starten, weitergehen, beenden (je Person)."""

from app.domain.rollen import Recht
from app.domain.rundgang import ANFAENGER, ERFAHREN, EXPERTE, Schritt, schritte_fuer
from app.extensions import db
from app.models import Nutzer
from app.services.protokoll import protokolliere
from app.services.rechte import darf

STUFEN = (ANFAENGER, ERFAHREN, EXPERTE)


def schritte(nutzer: Nutzer) -> list[Schritt]:
    return schritte_fuer(nutzer.erfahrung, lambda recht: darf(nutzer, Recht(recht)))


def aktiv(nutzer: Nutzer) -> bool:
    return nutzer.rundgang_schritt is not None


def aktueller_schritt(nutzer: Nutzer) -> tuple[Schritt, int, int] | None:
    """(Schritt, Nummer ab 1, Anzahl) oder None, wenn kein Rundgang läuft."""
    if nutzer.rundgang_schritt is None:
        return None
    liste = schritte(nutzer)
    index = min(max(nutzer.rundgang_schritt, 0), len(liste) - 1)
    return liste[index], index + 1, len(liste)


def stelle_ein(nutzer: Nutzer, erfahrung: str, kennt_steuy: bool) -> None:
    if erfahrung not in STUFEN:
        raise ValueError("Unbekannte Stufe")
    nutzer.erfahrung = erfahrung
    nutzer.kennt_steuy = kennt_steuy
    db.session.commit()


def starte(nutzer: Nutzer) -> None:
    nutzer.rundgang_schritt = 0
    nutzer.rundgang_fertig = False
    protokolliere("rundgang_gestartet", nutzer_id=nutzer.id, details={"stufe": nutzer.erfahrung})
    db.session.commit()


def weiter(nutzer: Nutzer) -> bool:
    """Zum nächsten Schritt. False, wenn der Rundgang damit zu Ende ist."""
    if nutzer.rundgang_schritt is None:
        return False
    if nutzer.rundgang_schritt >= len(schritte(nutzer)) - 1:
        beende(nutzer, fertig=True)
        return False
    nutzer.rundgang_schritt += 1
    db.session.commit()
    return True


def zurueck(nutzer: Nutzer) -> None:
    if nutzer.rundgang_schritt:
        nutzer.rundgang_schritt -= 1
        db.session.commit()


def beende(nutzer: Nutzer, fertig: bool = False) -> None:
    nutzer.rundgang_schritt = None
    nutzer.rundgang_fertig = fertig or nutzer.rundgang_fertig
    protokolliere("rundgang_beendet" if fertig else "rundgang_abgebrochen", nutzer_id=nutzer.id)
    db.session.commit()


def ueberspringe(nutzer: Nutzer) -> None:
    """Rundgang bewusst nicht machen (zählt als erledigt, damit nicht mehr gefragt wird)."""
    nutzer.rundgang_schritt = None
    nutzer.rundgang_fertig = True
    protokolliere("rundgang_uebersprungen", nutzer_id=nutzer.id)
    db.session.commit()
