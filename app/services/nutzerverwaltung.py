"""Nutzer anlegen und ändern. Nutzer werden nie gelöscht, nur deaktiviert."""

from datetime import date

from sqlalchemy import func, select

from app.domain.passwort import hash_passwort, normalisiere_email
from app.domain.rollen import Rolle
from app.extensions import db
from app.models import Nutzer
from app.services.protokoll import protokolliere

_UNVERAENDERT = object()


class EmailVergeben(ValueError):
    pass


class LetzterAdmin(ValueError):
    pass


def alle_nutzer() -> list[Nutzer]:
    return list(db.session.execute(select(Nutzer).order_by(Nutzer.name)).scalars())


def _email_frei(email: str, ausser_id: int | None = None) -> None:
    abfrage = select(Nutzer.id).where(Nutzer.email == email)
    if ausser_id is not None:
        abfrage = abfrage.where(Nutzer.id != ausser_id)
    if db.session.execute(abfrage).first():
        raise EmailVergeben("Diese E-Mail-Adresse ist bereits vergeben.")


def _ist_aktiver_admin(rolle: str, aktiv: bool, zugang_bis: date | None) -> bool:
    return rolle == Rolle.ADMIN and aktiv and (zugang_bis is None or zugang_bis >= date.today())


def lege_nutzer_an(
    name: str,
    email: str,
    rolle: str,
    passwort: str,
    zugang_bis: date | None,
    admin_id: int,
) -> Nutzer:
    email = normalisiere_email(email)
    _email_frei(email)
    nutzer = Nutzer(
        name=name.strip(),
        email=email,
        rolle=Rolle(rolle).value,
        passwort_hash=hash_passwort(passwort),
        zugang_bis=zugang_bis,
    )
    db.session.add(nutzer)
    db.session.flush()
    protokolliere(
        "nutzer_angelegt",
        nutzer_id=admin_id,
        objekt_typ="nutzer",
        objekt_id=nutzer.id,
        details={"email": email, "rolle": nutzer.rolle, "zugang_bis": _datum(zugang_bis)},
    )
    db.session.commit()
    return nutzer


def aendere_nutzer(
    nutzer: Nutzer,
    *,
    admin_id: int,
    name=_UNVERAENDERT,
    email=_UNVERAENDERT,
    rolle=_UNVERAENDERT,
    aktiv=_UNVERAENDERT,
    zugang_bis=_UNVERAENDERT,
    neues_passwort: str | None = None,
) -> dict:
    neu = {
        "name": nutzer.name if name is _UNVERAENDERT else name.strip(),
        "email": nutzer.email if email is _UNVERAENDERT else normalisiere_email(email),
        "rolle": nutzer.rolle if rolle is _UNVERAENDERT else Rolle(rolle).value,
        "aktiv": nutzer.aktiv if aktiv is _UNVERAENDERT else bool(aktiv),
        "zugang_bis": nutzer.zugang_bis if zugang_bis is _UNVERAENDERT else zugang_bis,
    }

    if _ist_aktiver_admin(nutzer.rolle, nutzer.aktiv, nutzer.zugang_bis) and not (
        _ist_aktiver_admin(neu["rolle"], neu["aktiv"], neu["zugang_bis"])
    ):
        andere_admins = db.session.execute(
            select(func.count())
            .select_from(Nutzer)
            .where(
                Nutzer.id != nutzer.id,
                Nutzer.rolle == Rolle.ADMIN.value,
                Nutzer.aktiv.is_(True),
                (Nutzer.zugang_bis.is_(None)) | (Nutzer.zugang_bis >= date.today()),
            )
        ).scalar_one()
        if andere_admins == 0:
            raise LetzterAdmin("Es muss immer mindestens einen aktiven Admin geben.")

    if neu["email"] != nutzer.email:
        _email_frei(neu["email"], ausser_id=nutzer.id)

    aenderungen: dict = {}
    for feld, wert in neu.items():
        alt = getattr(nutzer, feld)
        if alt != wert:
            darstellung = _datum if feld == "zugang_bis" else (lambda w: w)
            aenderungen[feld] = {"alt": darstellung(alt), "neu": darstellung(wert)}
            setattr(nutzer, feld, wert)

    if neues_passwort:
        nutzer.passwort_hash = hash_passwort(neues_passwort)
        aenderungen["passwort"] = "neu gesetzt"

    if aenderungen:
        protokolliere(
            "nutzer_geaendert",
            nutzer_id=admin_id,
            objekt_typ="nutzer",
            objekt_id=nutzer.id,
            details=aenderungen,
        )
        db.session.commit()
    return aenderungen


def _datum(wert: date | None) -> str | None:
    return wert.isoformat() if wert else None
