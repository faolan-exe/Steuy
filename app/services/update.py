"""Nach einer neuen Version auf GitHub suchen und das Update anstoßen.

Geprüft wird das jüngste GitHub-Release des Repositories. Installiert wird nicht von der App
selbst: Sie legt eine Anfrage in den gemeinsamen Ordner, der Dienst auf dem Server
(scripts/update-ausfuehren.sh, eingerichtet vom LXC-Skript) holt die Version und startet neu."""

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from flask import Flask, current_app

from app.domain.update import VersionUngueltig, ist_neuer, release_notizen, tag_fuer
from app.extensions import db
from app.services.einrichtung import aktuelles_gewerbe
from app.services.protokoll import protokolliere
from app.version import VERSION

STANDARD_REPO = "faolan-exe/Steuy"
CACHE_SEKUNDEN = 600
_cache: dict = {"zeit": 0.0, "ergebnis": None}


SUCHE_ALLE = timedelta(hours=24)
_suche_laeuft = threading.Lock()


@dataclass
class Pruefung:
    zustand: str  # "neu", "aktuell", "uebersprungen", "fehler", "nicht_gesucht"
    installiert: str = VERSION
    neueste: str | None = None
    titel: str | None = None
    notizen: list[tuple[str, list[str]]] = field(default_factory=list)
    link: str | None = None
    meldung: str | None = None


def _repo() -> str:
    repo = current_app.config.get("UPDATE_REPO") or STANDARD_REPO
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("UPDATE_REPO ist ungültig.")
    return repo


def _hole_release() -> dict:
    anfrage = urllib.request.Request(
        f"https://api.github.com/repos/{_repo()}/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"steuy/{VERSION}",
        },
    )
    token = current_app.config.get("UPDATE_TOKEN")
    if token:
        anfrage.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(anfrage, timeout=8) as antwort:  # noqa: S310
        return json.loads(antwort.read().decode("utf-8"))


def pruefe(frisch: bool = False) -> Pruefung:
    """Prüft auf eine neue Version. Das Ergebnis wird zehn Minuten gemerkt (GitHub drosselt)."""
    if not frisch and _cache["ergebnis"] and time.time() - _cache["zeit"] < CACHE_SEKUNDEN:
        _merke_ergebnis(_cache["ergebnis"], nur_wenn_anders=True)
        return _mit_ueberspringen(_cache["ergebnis"])
    try:
        release = _hole_release()
        neueste = tag_fuer(release.get("tag_name", ""))
        ergebnis = Pruefung(
            zustand="neu" if ist_neuer(neueste, VERSION) else "aktuell",
            neueste=neueste,
            titel=release.get("name") or neueste,
            notizen=release_notizen(release.get("body") or ""),
            link=release.get("html_url"),
        )
    except urllib.error.HTTPError as fehler:
        text = (
            "Es gibt noch keine veröffentlichte Version, oder das Repository ist nicht öffentlich."
            if fehler.code == 404
            else f"GitHub antwortet mit Fehler {fehler.code}."
        )
        ergebnis = Pruefung(zustand="fehler", meldung=text)
    except (urllib.error.URLError, TimeoutError, OSError):
        ergebnis = Pruefung(
            zustand="fehler",
            meldung="GitHub ist gerade nicht erreichbar. Bitte später erneut versuchen.",
        )
    except (VersionUngueltig, ValueError, KeyError):
        ergebnis = Pruefung(zustand="fehler", meldung="Die Antwort von GitHub war nicht lesbar.")
    _cache.update(zeit=time.time(), ergebnis=ergebnis)
    _merke_ergebnis(ergebnis)
    return _mit_ueberspringen(ergebnis)


def _merke_ergebnis(ergebnis: Pruefung, nur_wenn_anders: bool = False) -> None:
    """Ergebnis jeder Suche (von Hand oder automatisch) für den Hinweis in der Oberfläche.
    So zeigen Dashboard und Update-Seite immer denselben Stand."""
    gewerbe = aktuelles_gewerbe()
    if gewerbe is None or ergebnis.zustand == "fehler":
        return
    verfuegbar = ergebnis.neueste if ergebnis.zustand == "neu" else None
    if nur_wenn_anders and gewerbe.update_verfuegbar == verfuegbar:
        return
    if not nur_wenn_anders:
        gewerbe.update_gesucht_am = datetime.now(UTC)
    gewerbe.update_verfuegbar = verfuegbar
    db.session.commit()


def seite(frisch: bool = False) -> Pruefung:
    """Für die Update-Seite. Ist die automatische Suche aus, fragt steuy GitHub nur, wenn
    jemand ausdrücklich auf „Nach Updates suchen“ klickt."""
    gewerbe = aktuelles_gewerbe()
    if frisch or (gewerbe and gewerbe.update_auto_suchen):
        return pruefe(frisch=frisch)
    if _cache["ergebnis"] and time.time() - _cache["zeit"] < CACHE_SEKUNDEN:
        return _mit_ueberspringen(_cache["ergebnis"])
    return Pruefung(zustand="nicht_gesucht")


def hinweis() -> str | None:
    """Neue Version, auf die die Oberfläche hinweisen soll (nicht übersprungen, nicht alt)."""
    gewerbe = aktuelles_gewerbe()
    if not gewerbe or not gewerbe.update_verfuegbar:
        return None
    try:
        if not ist_neuer(gewerbe.update_verfuegbar, VERSION):
            return None
    except VersionUngueltig:
        return None
    if gewerbe.update_uebersprungen == gewerbe.update_verfuegbar:
        return None
    return gewerbe.update_verfuegbar


def suche_faellig(jetzt: datetime | None = None) -> bool:
    gewerbe = aktuelles_gewerbe()
    if not gewerbe or not gewerbe.update_auto_suchen:
        return False
    jetzt = jetzt or datetime.now(UTC)
    return gewerbe.update_gesucht_am is None or jetzt - gewerbe.update_gesucht_am >= SUCHE_ALLE


def suche_im_hintergrund(app: Flask) -> bool:
    """Startet die tägliche Suche in einem eigenen Thread, damit keine Seite wartet.
    Installiert nie etwas. Gibt zurück, ob eine Suche gestartet wurde."""
    if not _suche_laeuft.acquire(blocking=False):
        return False

    def lauf():
        try:
            with app.app_context():
                if suche_faellig():
                    pruefe(frisch=True)
        except Exception:  # noqa: BLE001  Hintergrund: nie die App stören
            app.logger.exception("Automatische Update-Suche fehlgeschlagen")
        finally:
            with app.app_context():
                db.session.remove()
            _suche_laeuft.release()

    threading.Thread(target=lauf, name="update-suche", daemon=True).start()
    return True


def schalte_automatik(an: bool, nutzer_id: int) -> None:
    gewerbe = aktuelles_gewerbe()
    gewerbe.update_auto_suchen = an
    if not an:
        gewerbe.update_verfuegbar = None
    protokolliere("update_automatik", nutzer_id=nutzer_id, details={"an": an})
    db.session.commit()


def _mit_ueberspringen(ergebnis: Pruefung) -> Pruefung:
    gewerbe = aktuelles_gewerbe()
    if (
        ergebnis.zustand == "neu"
        and gewerbe
        and gewerbe.update_uebersprungen
        and gewerbe.update_uebersprungen == ergebnis.neueste
    ):
        kopie = Pruefung(**{**ergebnis.__dict__, "zustand": "uebersprungen"})
        return kopie
    return ergebnis


def ueberspringe(version: str, nutzer_id: int) -> None:
    tag = tag_fuer(version)
    aktuelles_gewerbe().update_uebersprungen = tag
    protokolliere("update_uebersprungen", nutzer_id=nutzer_id, details={"version": tag})
    db.session.commit()


def vergiss_ueberspringen(nutzer_id: int) -> None:
    aktuelles_gewerbe().update_uebersprungen = None
    db.session.commit()


# ---------- Anstoßen und Fortschritt ----------


def update_ordner() -> Path | None:
    ordner = current_app.config.get("UPDATE_VERZEICHNIS")
    if not ordner:
        return None
    pfad = Path(ordner)
    return pfad if pfad.is_dir() and os.access(pfad, os.W_OK) else None


def automatisch_moeglich() -> bool:
    return update_ordner() is not None


def starte_update(version: str, nutzer_id: int) -> None:
    """Legt die Anfrage ab. Der Dienst auf dem Server erledigt den Rest."""
    ordner = update_ordner()
    if ordner is None:
        raise RuntimeError(
            "Das automatische Update ist auf dieser Installation nicht eingerichtet."
        )
    tag = tag_fuer(version)
    if status().get("zustand") == "laeuft":
        raise RuntimeError("Es läuft bereits ein Update.")
    (ordner / "status.json").write_text(
        json.dumps({"zustand": "angefragt", "version": tag, "von": VERSION}), encoding="utf-8"
    )
    temp = ordner / "anfrage.tmp"
    temp.write_text(json.dumps({"version": tag, "zeit": int(time.time())}), encoding="utf-8")
    temp.replace(ordner / "anfrage")
    protokolliere("update_angefragt", nutzer_id=nutzer_id, details={"version": tag, "von": VERSION})
    db.session.commit()


def status() -> dict:
    """Stand des Updates aus dem gemeinsamen Ordner, sonst leer."""
    ordner = update_ordner()
    if ordner is None:
        return {}
    try:
        return json.loads((ordner / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
