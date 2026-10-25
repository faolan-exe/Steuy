"""Scan-Eingang: Belege aus einem Ordner übernehmen, in den der Scanner speichert.

Der Scanner (z. B. Brother ADS-1800W) legt PDF-, JPG- oder PNG-Dateien in einem Netzwerkordner
ab. steuy schaut regelmäßig nach, übernimmt jede fertige Datei als Beleg (wie ein Upload,
mit Texterkennung) und verschiebt das Original nach `verarbeitet/`. Belege in der Ablage
bleiben unverändert (harte Regel 5), im Ordner liegt nur die Arbeitskopie.
"""

import os
import secrets
import shutil
import socket
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from flask import current_app
from sqlalchemy import select, text

from app.extensions import db
from app.models import Nutzer, Protokoll
from app.services import belege
from app.services.einrichtung import aktuelles_gewerbe
from app.services.geheimnis import entschluessele, verschluessele
from app.services.protokoll import protokolliere

ENDUNGEN = {".pdf", ".jpg", ".jpeg", ".png"}
# Eine Datei gilt erst als fertig, wenn sie so lange unverändert ist (der Scanner schreibt noch)
RUHEZEIT_SEKUNDEN = 10
VERARBEITET = "verarbeitet"
DOPPELT = "doppelt"
FEHLER = "fehler"
RESERVIERT = {VERARBEITET, DOPPELT, FEHLER}
SPERRE_SCHLUESSEL = 734_001


@dataclass
class Ergebnis:
    importiert: list[str] = field(default_factory=list)
    doppelt: list[str] = field(default_factory=list)
    fehler: list[tuple[str, str]] = field(default_factory=list)
    uebersprungen: bool = False

    @property
    def leer(self) -> bool:
        return not (self.importiert or self.doppelt or self.fehler)

    def text(self) -> str:
        if self.uebersprungen:
            return "Der Scan-Eingang ist ausgeschaltet."
        if self.leer:
            return "Keine neuen Scans gefunden."
        teile = []
        if self.importiert:
            teile.append(f"{len(self.importiert)} Beleg(e) übernommen")
        if self.doppelt:
            teile.append(f"{len(self.doppelt)} schon vorhanden")
        if self.fehler:
            teile.append(f"{len(self.fehler)} nicht lesbar")
        return ", ".join(teile) + "."


def eingangsordner() -> Path:
    return Path(current_app.config["SCAN_VERZEICHNIS"])


def ist_aktiv() -> bool:
    gewerbe = aktuelles_gewerbe()
    return bool(gewerbe and gewerbe.scan_aktiv)


PASSWORT_ZEICHEN = "abcdefghjkmnpqrstuvwxyz23456789"  # ohne l, i, o, 0, 1: leichter abzutippen
PASSWORT_LAENGE = 12


def neues_passwort() -> str:
    return "".join(secrets.choice(PASSWORT_ZEICHEN) for _ in range(PASSWORT_LAENGE))


def passwort() -> str | None:
    """Das Passwort der Freigabe für den Benutzer "scanner" (lesbar für die Einstellungsseite)."""
    gewerbe = aktuelles_gewerbe()
    return entschluessele(gewerbe.scan_passwort) if gewerbe and gewerbe.scan_passwort else None


def freigabe_ordner() -> Path:
    return Path(current_app.config["FREIGABE_VERZEICHNIS"])


def freigabe_an() -> bool:
    gewerbe = aktuelles_gewerbe()
    return bool(gewerbe and gewerbe.scan_aktiv and gewerbe.scan_freigabe)


def schreibe_freigabe() -> bool:
    """Schreibt die Steuerdatei für den Samba-Container (nur bei Änderung). True, wenn es klappt."""
    gewerbe = aktuelles_gewerbe()
    zeilen = [
        f"aktiv={1 if freigabe_an() else 0}",
        f"kompatibel={1 if gewerbe.scan_kompatibel else 0}",
        f"passwort={passwort() or ''}",
    ]
    inhalt = "\n".join(zeilen) + "\n"
    datei = freigabe_ordner() / "status"
    try:
        if datei.exists() and datei.read_text() == inhalt:
            return True
        freigabe_ordner().mkdir(parents=True, exist_ok=True)
        temp = datei.with_suffix(".neu")
        temp.write_text(inhalt)
        os.chmod(temp, 0o600)
        temp.replace(datei)
    except OSError:
        current_app.logger.warning("Freigabe-Steuerdatei nicht beschreibbar", exc_info=True)
        return False
    return True


def freigabe_laeuft() -> bool:
    """Antwortet der Samba-Container auf Port 445? Dann ist die Freigabe wirklich an."""
    try:
        with socket.create_connection((current_app.config["SCAN_FREIGABE_HOST"], 445), timeout=1.0):
            return True
    except OSError:
        return False


def setze_aktiv(
    aktiv: bool,
    nutzer_id: int,
    freigabe: bool | None = None,
    kompatibel: bool | None = None,
) -> None:
    """Scan-Eingang an oder aus. Beim ersten Einschalten entsteht das Passwort der Freigabe."""
    gewerbe = aktuelles_gewerbe()
    if aktiv:
        bereite_ordner_vor()
        if not gewerbe.scan_passwort:
            gewerbe.scan_passwort = verschluessele(neues_passwort())
    gewerbe.scan_aktiv = aktiv
    if freigabe is not None:
        gewerbe.scan_freigabe = freigabe
    if kompatibel is not None:
        gewerbe.scan_kompatibel = kompatibel
    protokolliere(
        "scan_eingang_ein" if aktiv else "scan_eingang_aus",
        nutzer_id=nutzer_id,
        objekt_typ="gewerbe",
        objekt_id=gewerbe.id,
        details={"freigabe": gewerbe.scan_freigabe, "kompatibel": gewerbe.scan_kompatibel},
    )
    db.session.commit()
    schreibe_freigabe()


def erneuere_passwort(nutzer_id: int) -> None:
    gewerbe = aktuelles_gewerbe()
    gewerbe.scan_passwort = verschluessele(neues_passwort())
    protokolliere("scan_passwort_erneuert", nutzer_id=nutzer_id, objekt_typ="gewerbe", objekt_id=1)
    db.session.commit()
    schreibe_freigabe()


def bereite_ordner_vor() -> Path:
    ordner = eingangsordner()
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def _admin_id() -> int | None:
    nutzer = db.session.execute(
        select(Nutzer).where(Nutzer.rolle == "admin", Nutzer.aktiv).order_by(Nutzer.id)
    ).scalars()
    for kandidat in nutzer:
        if kandidat.is_active:
            return kandidat.id
    return None


def _kandidaten(ordner: Path) -> list[Path]:
    """Dateien im Ordner und eine Ebene darunter, ohne unsere eigenen Ablageordner."""
    gefunden: list[Path] = []
    try:
        eintraege = sorted(os.scandir(ordner), key=lambda e: e.name)
    except OSError:
        return gefunden
    for eintrag in eintraege:
        if eintrag.name.startswith(".") or eintrag.is_symlink():
            continue
        if eintrag.is_dir(follow_symlinks=False):
            if eintrag.name in RESERVIERT:
                continue
            try:
                unter = sorted(os.scandir(eintrag.path), key=lambda e: e.name)
            except OSError:
                continue
            gefunden.extend(Path(e.path) for e in unter if _ist_datei(e))
        elif _ist_datei(eintrag):
            gefunden.append(Path(eintrag.path))
    return gefunden


def _ist_datei(eintrag: os.DirEntry) -> bool:
    return (
        not eintrag.name.startswith(".")
        and not eintrag.is_symlink()
        and eintrag.is_file(follow_symlinks=False)
        and Path(eintrag.name).suffix.lower() in ENDUNGEN
    )


def _fertig(datei: Path, ruhezeit: float) -> bool:
    try:
        return time.time() - datei.stat().st_mtime >= ruhezeit
    except OSError:
        return False


def _wegsortieren(datei: Path, ordner: Path, unterordner: str) -> None:
    """Verschiebt die Datei, ohne etwas zu überschreiben."""
    monat = date.today().strftime("%Y-%m")
    ziel_ordner = (
        ordner / unterordner / monat if unterordner == VERARBEITET else ordner / unterordner
    )
    ziel_ordner.mkdir(parents=True, exist_ok=True)
    ziel = ziel_ordner / datei.name
    zaehler = 1
    while ziel.exists():
        ziel = ziel_ordner / f"{datei.stem}-{zaehler}{datei.suffix}"
        zaehler += 1
    shutil.move(str(datei), str(ziel))


AUFBEWAHREN_TAGE = 30


def raeume_auf(tage: int = AUFBEWAHREN_TAGE) -> int:
    """Löscht Arbeitskopien in verarbeitet/ und doppelt/ nach 30 Tagen. Belege bleiben in steuy."""
    grenze = time.time() - tage * 86400
    ordner = eingangsordner()
    geloescht = 0
    for name in (VERARBEITET, DOPPELT):
        for datei in (ordner / name).rglob("*") if (ordner / name).is_dir() else []:
            try:
                if datei.is_file() and not datei.is_symlink() and datei.stat().st_mtime < grenze:
                    datei.unlink()
                    geloescht += 1
            except OSError:
                continue
    return geloescht


def pruefe_ordner(ruhezeit: float = RUHEZEIT_SEKUNDEN, erzwinge: bool = False) -> Ergebnis:
    """Übernimmt alle fertigen Scans. Läuft nur, wenn der Scan-Eingang eingeschaltet ist."""
    ergebnis = Ergebnis()
    if not (erzwinge or ist_aktiv()):
        ergebnis.uebersprungen = True
        return ergebnis
    ordner = eingangsordner()
    if not ordner.is_dir():
        return ergebnis
    nutzer_id = _admin_id()
    if nutzer_id is None:
        return ergebnis
    gesperrt = db.session.execute(
        text("SELECT pg_try_advisory_lock(:k)"), {"k": SPERRE_SCHLUESSEL}
    ).scalar()
    if not gesperrt:
        return ergebnis  # ein anderer Lauf ist gerade dabei
    try:
        for datei in _kandidaten(ordner):
            if not _fertig(datei, ruhezeit):
                continue
            _uebernimm(datei, ordner, nutzer_id, ergebnis)
        gewerbe = aktuelles_gewerbe()
        gewerbe.scan_letzter_lauf = datetime.now(UTC)
        db.session.commit()
    finally:
        db.session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SPERRE_SCHLUESSEL})
        db.session.commit()
    return ergebnis


def _uebernimm(datei: Path, ordner: Path, nutzer_id: int, ergebnis: Ergebnis) -> None:
    name = datei.name
    try:
        if datei.stat().st_size > belege.MAX_GROESSE:
            raise belege.BelegUngueltig(f"{name}: Die Datei ist größer als 20 MB.")
        inhalt = datei.read_bytes()
        beleg = belege.lade_hoch(name, inhalt, nutzer_id)
    except belege.BelegVorhanden as doppelt:
        _wegsortieren(datei, ordner, DOPPELT)
        ergebnis.doppelt.append(name)
        protokolliere(
            "scan_doppelt",
            nutzer_id=nutzer_id,
            objekt_typ="beleg",
            objekt_id=doppelt.beleg.id,
            details={"datei": name},
        )
        db.session.commit()
    except (belege.BelegUngueltig, OSError) as fehler:
        db.session.rollback()
        _versuche_wegsortieren(datei, ordner, FEHLER)
        grund = str(fehler)
        ergebnis.fehler.append((name, grund))
        protokolliere(
            "scan_fehler", nutzer_id=nutzer_id, details={"datei": name, "grund": grund[:200]}
        )
        db.session.commit()
    else:
        _versuche_wegsortieren(datei, ordner, VERARBEITET)
        ergebnis.importiert.append(name)
        protokolliere(
            "scan_import",
            nutzer_id=nutzer_id,
            objekt_typ="beleg",
            objekt_id=beleg.id,
            details={"datei": name},
        )
        db.session.commit()


def _versuche_wegsortieren(datei: Path, ordner: Path, unterordner: str) -> None:
    try:
        _wegsortieren(datei, ordner, unterordner)
    except OSError:
        current_app.logger.warning("Scan konnte nicht verschoben werden: %s", datei, exc_info=True)


def status() -> dict:
    """Für die Einstellungsseite: Ordner, wartende Dateien, letzte Ereignisse."""
    ordner = eingangsordner()
    vorhanden = ordner.is_dir()
    beschreibbar = vorhanden and os.access(ordner, os.W_OK)
    wartend = len(_kandidaten(ordner)) if vorhanden else 0
    letzte = db.session.execute(
        select(Protokoll)
        .where(Protokoll.aktion.in_(["scan_import", "scan_doppelt", "scan_fehler"]))
        .order_by(Protokoll.id.desc())
        .limit(10)
    ).scalars()
    gewerbe = aktuelles_gewerbe()
    return {
        "freigabe_an": freigabe_an(),
        "freigabe_laeuft": freigabe_an() and freigabe_laeuft(),
        "passwort": passwort(),
        "kompatibel": gewerbe.scan_kompatibel,
        "ordner": str(ordner),
        "vorhanden": vorhanden,
        "beschreibbar": beschreibbar,
        "wartend": wartend,
        "letzter_lauf": gewerbe.scan_letzter_lauf,
        "letzte": list(letzte),
    }


def dienst(intervall: float = 30.0) -> None:
    """Endlosschleife für den Zeitplan-Container: alle 30 Sekunden nach neuen Scans sehen."""
    letztes_aufraeumen = 0.0
    while True:
        try:
            if aktuelles_gewerbe() is not None:
                schreibe_freigabe()  # hält die Steuerdatei auch nach neuem Volume aktuell
            if ist_aktiv():
                ergebnis = pruefe_ordner()
                if not ergebnis.leer:
                    current_app.logger.info("Scan-Eingang: %s", ergebnis.text())
                if time.time() - letztes_aufraeumen > 86400:
                    raeume_auf()
                    letztes_aufraeumen = time.time()
        except Exception:  # noqa: BLE001  der Dienst darf nie sterben
            current_app.logger.exception("Scan-Eingang: Fehler im Lauf")
            db.session.rollback()
        db.session.remove()
        time.sleep(intervall)
