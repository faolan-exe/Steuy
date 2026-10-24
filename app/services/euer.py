"""EÜR je Kalenderjahr nach Zahlungsdatum (docs/domain/euer.md)."""

from sqlalchemy import extract, func, select

from app.domain.buchung import betrieblicher_anteil
from app.domain.euer import OHNE_ZUORDNUNG, Ergebnis, Posten, Summenzeilen, verteile
from app.extensions import db
from app.models import EuerSummen, EuerZeile, EuerZuordnung, Zahlung


def vordruck_jahr(jahr: int) -> int | None:
    passend = db.session.execute(
        select(func.max(EuerZeile.steuerjahr)).where(EuerZeile.steuerjahr <= jahr)
    ).scalar()
    if passend is not None:
        return passend
    return db.session.execute(select(func.min(EuerZeile.steuerjahr))).scalar()


def berechne(jahr: int) -> Ergebnis:
    vordruck = vordruck_jahr(jahr)
    zeilen = [
        z.als_zeile()
        for z in db.session.execute(
            select(EuerZeile).where(EuerZeile.steuerjahr == vordruck)
        ).scalars()
    ]
    zuordnung = {
        z.kategorie_id: z.zeile
        for z in db.session.execute(
            select(EuerZuordnung).where(EuerZuordnung.steuerjahr == vordruck)
        ).scalars()
    }

    from datetime import date

    from app.services.anlagen import buchungen_mit_anlagegut, verzeichnis

    # Zahlungen für Anlagegüter zählen nicht direkt, sondern über die AfA (unten)
    anlagen = buchungen_mit_anlagegut()
    zeile_je_kennzahl = {z.kennzahl: z.nummer for z in zeilen if z.kennzahl}

    from app.services.jahreswechsel import zuordnungen

    # Am Jahreswechsel bestätigte Zahlungen zählen im zugeordneten Jahr (§ 11 EStG)
    jahr_von = zuordnungen()

    def eur_jahr(z: Zahlung) -> int:
        return jahr_von.get(z.id) or jahr_von.get(z.storno_von_id) or z.datum.year

    posten = []
    zahlungen = db.session.execute(
        select(Zahlung)
        .where(extract("year", Zahlung.datum).between(jahr - 1, jahr + 1))
        .order_by(Zahlung.datum)
    ).scalars()
    for z in zahlungen:
        if eur_jahr(z) != jahr:
            continue
        if z.rechnung_id is not None:
            r = z.rechnung
            text = f"{r.nummer} {r.empfaenger_name or ''}".strip()
            if z.storno_von_id:
                text += " (Rückbuchung)"
            posten.append(
                Posten(
                    zuordnung.get(None, OHNE_ZUORDNUNG["einnahme"]),
                    "einnahme",
                    z.datum,
                    text,
                    z.betrag_cent,
                )
            )
            continue
        b = z.buchung
        if b.id in anlagen or b.storno_von_id in anlagen:
            continue
        text = " · ".join(t for t in (b.partner, b.belegnummer) if t) or b.kategorie.name
        if b.betrieblich_prozent != 100:
            text += f" ({b.betrieblich_prozent} % betrieblich)"
        if z.storno_von_id:
            text += " (Storno)"
        if z.datum.year != jahr:
            text += f" (gezahlt {z.datum:%d.%m.%Y}, Jahreswechsel)"
        posten.append(
            Posten(
                zuordnung.get(b.kategorie_id, OHNE_ZUORDNUNG[b.art]),
                b.art,
                z.datum,
                text,
                betrieblicher_anteil(z.betrag_cent, b.betrieblich_prozent),
            )
        )
    for eintrag in verzeichnis(jahr):
        if not eintrag.afa_cent:
            continue
        gut = eintrag.anlagegut
        dauer = (
            "voll im Anschaffungsjahr"
            if gut.nutzungsdauer_jahre == 1
            else (f"{gut.nutzungsdauer_jahre} Jahre")
        )
        posten.append(
            Posten(
                zeile_je_kennzahl.get(eintrag.kennzahl, OHNE_ZUORDNUNG["ausgabe"]),
                "ausgabe",
                max(gut.anschaffungsdatum, date(jahr, 1, 1)),
                f"AfA {gut.bezeichnung} ({dauer})",
                eintrag.afa_cent,
            )
        )
    summen = db.session.get(EuerSummen, vordruck) if vordruck is not None else None
    return verteile(
        jahr,
        vordruck,
        zeilen,
        posten,
        Summenzeilen(
            summen.einnahmen_zeile,
            summen.einnahmen_kz,
            summen.ausgaben_zeile,
            summen.ausgaben_kz,
            summen.gewinn_einnahmen_zeile,
            summen.gewinn_ausgaben_zeile,
        )
        if summen
        else None,
    )


def jahre_mit_daten() -> list[int]:
    jahre = db.session.execute(
        select(extract("year", Zahlung.datum)).distinct().order_by(extract("year", Zahlung.datum))
    ).scalars()
    ergebnis = {int(j) for j in jahre}
    # Jahre, in denen nur noch abgeschrieben wird
    from app.models import Anlagegut
    from app.services.anlagen import afa_plan

    for gut in db.session.execute(select(Anlagegut)).scalars():
        if gut.aktiv:
            ergebnis |= set(afa_plan(gut))
    return sorted(ergebnis)
