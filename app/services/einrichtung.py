"""Erste Einrichtung: Gewerbe und Admin-Konto (ADR 0007)."""

from sqlalchemy import select

from app.domain.kleinunternehmer import Grenze, grenze_fuer_jahr
from app.domain.passwort import hash_passwort, normalisiere_email
from app.domain.rollen import Rolle
from app.extensions import db
from app.models import Gewerbe, Kleinunternehmergrenze, Nutzer
from app.services.protokoll import protokolliere


class BereitsEingerichtet(RuntimeError):
    pass


def aktuelles_gewerbe() -> Gewerbe | None:
    return db.session.get(Gewerbe, 1)


def ist_eingerichtet() -> bool:
    return aktuelles_gewerbe() is not None


def grenze(jahr: int) -> Grenze:
    zeilen = db.session.execute(select(Kleinunternehmergrenze)).scalars()
    return grenze_fuer_jahr([z.als_grenze() for z in zeilen], jahr)


def bereinige_firmendaten(daten: dict) -> dict:
    """Nur bekannte Felder, Leerzeichen entfernt, leere optionale Felder als None."""
    sauber = {}
    for feld in Gewerbe.FELDER:
        wert = (daten.get(feld) or "").strip()
        sauber[feld] = wert or None
    if sauber["email"]:
        sauber["email"] = normalisiere_email(sauber["email"])
    return sauber


def richte_ein(
    firmendaten: dict,
    admin_name: str,
    admin_email: str,
    passwort: str,
    erfahrung: str | None = None,
    kennt_steuy: bool | None = None,
) -> Nutzer:
    if ist_eingerichtet():
        raise BereitsEingerichtet("Das Gewerbe ist bereits eingerichtet.")

    gewerbe = Gewerbe(id=1, **bereinige_firmendaten(firmendaten))
    admin = Nutzer(
        name=admin_name.strip(),
        email=normalisiere_email(admin_email),
        passwort_hash=hash_passwort(passwort),
        rolle=Rolle.ADMIN,
        erfahrung=erfahrung,
        kennt_steuy=kennt_steuy,
    )
    db.session.add_all([gewerbe, admin])
    db.session.flush()
    protokolliere(
        "einrichtung",
        nutzer_id=admin.id,
        objekt_typ="gewerbe",
        objekt_id=gewerbe.id,
        details={"gewerbe": gewerbe.name, "admin": admin.email},
    )
    db.session.commit()
    return admin


def setze_ziel(art: str | None, wert: int | None, nutzer_id: int) -> None:
    """Dashboard-Ziel setzen oder (art=None) entfernen."""
    gewerbe = aktuelles_gewerbe()
    gewerbe.ziel_art = art
    gewerbe.ziel_wert = wert if art else None
    protokolliere(
        "ziel_gesetzt",
        nutzer_id=nutzer_id,
        objekt_typ="gewerbe",
        objekt_id=gewerbe.id,
        details={"art": art, "wert": wert},
    )
    db.session.commit()
