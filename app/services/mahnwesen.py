"""Mahnstufen, fällige Mahnungen, Mahnung erstellen (docs/domain/mahnwesen.md)."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.domain.geld import cent_zu_euro
from app.domain.mahnung import (
    PAUSCHALE_AB_STUFE,
    PAUSCHALE_SATZ,
    TEXT_MAX,
    VERZUGSPAUSCHALE_CENT,
    LetzteMahnung,
    Stufe,
    faellig_ab,
    faellige_stufe,
    fuelle_platzhalter,
    naechste_stufe,
    pauschale_vorschlagen,
)
from app.extensions import db
from app.models import Mahnstufe, Mahnung, Mahnvorlage, Rechnung
from app.services import ablage
from app.services.einrichtung import aktuelles_gewerbe
from app.services.protokoll import protokolliere


class MahnungNichtMoeglich(ValueError):
    pass


def stufen() -> list[Stufe]:
    zeilen = db.session.execute(select(Mahnstufe).order_by(Mahnstufe.nummer)).scalars()
    return [z.als_stufe() for z in zeilen]


def _letzte(rechnung: Rechnung) -> LetzteMahnung | None:
    if not rechnung.mahnungen:
        return None
    letzte = max(rechnung.mahnungen, key=lambda m: m.stufe)
    return LetzteMahnung(letzte.stufe, letzte.datum)


def naechste_fuer(rechnung: Rechnung) -> Stufe | None:
    return naechste_stufe(stufen(), _letzte(rechnung))


def naechste_faellig_ab(rechnung: Rechnung) -> date | None:
    """Datum, ab dem die nächste Mahnstufe laut Zeitplan fällig ist (sonst None)."""
    stufe = naechste_fuer(rechnung)
    if stufe is None:
        return None
    return faellig_ab(faellig_am=rechnung.faellig_am, letzte=_letzte(rechnung), stufe=stufe)


def faellige_mahnungen(heute: date | None = None) -> list[tuple[Rechnung, Stufe]]:
    heute = heute or date.today()
    alle = stufen()
    offene = db.session.execute(
        select(Rechnung)
        .where(Rechnung.status.in_(["offen", "teilbezahlt"]), Rechnung.belegart == "rechnung")
        .order_by(Rechnung.faellig_am)
    ).scalars()
    ergebnis = []
    for rechnung in offene:
        if rechnung.gesperrt_fuer_mahnungen:
            continue
        stufe = faellige_stufe(
            faellig_am=rechnung.faellig_am, letzte=_letzte(rechnung), stufen=alle, heute=heute
        )
        if stufe:
            ergebnis.append((rechnung, stufe))
    return ergebnis


MAX_VORLAGEN = 30


def pruefe_mahnbar(rechnung: Rechnung) -> Stufe:
    """Die nächste Stufe, wenn die Rechnung gerade gemahnt werden darf."""
    if not rechnung.ist_rechnung or rechnung.ist_entwurf or rechnung.status == "storniert":
        raise MahnungNichtMoeglich("Nur offene, finalisierte Rechnungen können gemahnt werden.")
    if rechnung.offen_cent <= 0:
        raise MahnungNichtMoeglich("Für diese Rechnung ist nichts mehr offen.")
    if rechnung.gesperrt_fuer_mahnungen:
        raise MahnungNichtMoeglich("Für diese Rechnung oder diesen Kontakt gilt eine Mahnsperre.")
    stufe = naechste_fuer(rechnung)
    if stufe is None:
        raise MahnungNichtMoeglich("Alle Mahnstufen sind bereits erstellt.")
    return stufe


def stufentext(nummer: int) -> str:
    return db.session.get(Mahnstufe, nummer).text


def pauschale_vorschlag(rechnung: Rechnung, stufe: int) -> bool:
    frueher = [m for m in rechnung.mahnungen if m.stufe >= PAUSCHALE_AB_STUFE]
    vorherige = max(frueher, key=lambda m: m.stufe).pauschale_cent > 0 if frueher else None
    return pauschale_vorschlagen(stufe, vorherige)


def _pruefe_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        raise MahnungNichtMoeglich("Bitte gib einen Text für die Mahnung ein.")
    if len(text) > TEXT_MAX:
        raise MahnungNichtMoeglich(f"Der Text darf höchstens {TEXT_MAX} Zeichen lang sein.")
    return text


def entwurf(
    rechnung: Rechnung,
    *,
    text: str | None = None,
    pauschale: bool | None = None,
    heute: date | None = None,
) -> tuple[Mahnung, str]:
    """Die nächste Mahnung samt fertigem Brieftext, noch nicht gespeichert (auch für die
    Vorschau). Ohne `text` gilt der Text der Stufe, ohne `pauschale` der Vorschlag."""
    heute = heute or date.today()
    stufe = pruefe_mahnbar(rechnung)
    if pauschale is None:
        pauschale = pauschale_vorschlag(rechnung, stufe.nummer)
    elif pauschale and stufe.nummer < PAUSCHALE_AB_STUFE:
        raise MahnungNichtMoeglich("Die Verzugspauschale gibt es erst ab der zweiten Stufe.")
    text = _pruefe_text(stufentext(stufe.nummer) if text is None else text)
    mahnung = Mahnung(
        rechnung_id=rechnung.id,
        stufe=stufe.nummer,
        bezeichnung=stufe.bezeichnung,
        datum=heute,
        offen_cent=rechnung.offen_cent,
        frist_bis=heute + timedelta(days=stufe.frist_tage),
        pauschale_cent=VERZUGSPAUSCHALE_CENT if pauschale else 0,
    )
    werte = {
        "nummer": rechnung.nummer,
        "rechnungsdatum": f"{rechnung.rechnungsdatum:%d.%m.%Y}",
        "faellig": f"{rechnung.faellig_am:%d.%m.%Y}" if rechnung.faellig_am else "",
        "frist": f"{mahnung.frist_bis:%d.%m.%Y}",
        "betrag": cent_zu_euro(mahnung.offen_cent),
        "gesamt": cent_zu_euro(mahnung.gesamt_cent),
        "pauschale": PAUSCHALE_SATZ if mahnung.pauschale_cent else "",
    }
    return mahnung, fuelle_platzhalter(text, werte)


def erstelle_mahnung(
    rechnung: Rechnung,
    nutzer_id: int,
    heute: date | None = None,
    automatisch: bool = False,
    text: str | None = None,
    pauschale: bool | None = None,
) -> Mahnung:
    """Erstellt die nächste Stufe, auch wenn sie laut Zeitplan noch nicht fällig ist."""
    from app.services.pdf import rendere_mahnung

    mahnung, brieftext = entwurf(rechnung, text=text, pauschale=pauschale, heute=heute)
    mahnung.erstellt_von = nutzer_id
    mahnung.automatisch = automatisch
    mahnung.pdf_sha256 = ablage.speichere(rendere_mahnung(rechnung, mahnung, brieftext))
    db.session.add(mahnung)
    db.session.flush()
    protokolliere(
        "mahnung_erstellt",
        nutzer_id=nutzer_id,
        objekt_typ="rechnung",
        objekt_id=rechnung.id,
        details={
            "stufe": mahnung.stufe,
            "offen_cent": mahnung.offen_cent,
            "pauschale_cent": mahnung.pauschale_cent,
            "pdf_sha256": mahnung.pdf_sha256,
            "automatisch": automatisch,
        },
    )
    db.session.commit()
    db.session.refresh(rechnung, ["mahnungen"])
    return mahnung


def vorlagen() -> list[Mahnvorlage]:
    return list(db.session.execute(select(Mahnvorlage).order_by(Mahnvorlage.name)).scalars())


def speichere_vorlage(name: str, text: str, nutzer_id: int) -> Mahnvorlage:
    """Legt eine eigene Textvorlage an oder ersetzt die gleichnamige."""
    name = (name or "").strip()[:60]
    if not name:
        raise MahnungNichtMoeglich("Bitte gib der Vorlage einen Namen.")
    text = _pruefe_text(text)
    vorlage = db.session.execute(
        select(Mahnvorlage).where(Mahnvorlage.name == name)
    ).scalar_one_or_none()
    if vorlage is None:
        if len(vorlagen()) >= MAX_VORLAGEN:
            raise MahnungNichtMoeglich(f"Mehr als {MAX_VORLAGEN} Vorlagen sind nicht möglich.")
        vorlage = Mahnvorlage(name=name)
        db.session.add(vorlage)
    vorlage.text = text
    protokolliere("mahnvorlage_gespeichert", nutzer_id=nutzer_id, details={"name": name})
    db.session.commit()
    return vorlage


def loesche_vorlage(vorlage_id: int, nutzer_id: int) -> None:
    vorlage = db.session.get(Mahnvorlage, vorlage_id)
    if vorlage is None:
        return
    protokolliere("mahnvorlage_geloescht", nutzer_id=nutzer_id, details={"name": vorlage.name})
    db.session.delete(vorlage)
    db.session.commit()


def setze_mahnsperre(rechnung: Rechnung, sperre: bool, grund: str | None, nutzer_id: int) -> None:
    grund = (grund or "").strip()[:200] or None if sperre else None
    if rechnung.mahnsperre == sperre and rechnung.mahnsperre_grund == grund:
        return
    rechnung.mahnsperre = sperre
    rechnung.mahnsperre_grund = grund
    protokolliere(
        "mahnsperre_gesetzt" if sperre else "mahnsperre_aufgehoben",
        nutzer_id=nutzer_id,
        objekt_typ="rechnung",
        objekt_id=rechnung.id,
        details={"grund": grund} if grund else None,
    )
    db.session.commit()


def aendere_stufen(daten: dict[int, dict], nutzer_id: int) -> dict:
    aenderungen = {}
    for nummer, werte in daten.items():
        zeile = db.session.get(Mahnstufe, nummer)
        for feld, neu in werte.items():
            alt = getattr(zeile, feld)
            if alt != neu:
                aenderungen[f"{nummer}.{feld}"] = {"alt": alt, "neu": neu}
                setattr(zeile, feld, neu)
    if aenderungen:
        protokolliere("mahnstufen_geaendert", nutzer_id=nutzer_id, details=aenderungen)
        db.session.commit()
    return aenderungen


def setze_automatik(an: bool, nutzer_id: int) -> None:
    gewerbe = aktuelles_gewerbe()
    if gewerbe.auto_mahnen == an:
        return
    gewerbe.auto_mahnen = an
    protokolliere("auto_mahnen_geaendert", nutzer_id=nutzer_id, details={"an": an})
    db.session.commit()


@dataclass
class Mahnlauf:
    erstellt: int = 0
    verschickt: int = 0
    nicht_verschickt: list[str] = field(default_factory=list)


def automatischer_mahnlauf(nutzer_id: int, heute: date | None = None) -> Mahnlauf:
    """Erstellt fällige Mahnungen von selbst und schickt sie per E-Mail, wenn das möglich ist.

    Nur wenn der Schalter in den Einstellungen eingeschaltet ist (Standard: aus). Rechnungen mit
    Mahnsperre bleiben außen vor. Ohne E-Mail-Adresse oder ohne eingerichteten Versand liegt die
    Mahnung fertig bereit und erscheint in der Rechnung zum Verschicken von Hand."""
    ergebnis = Mahnlauf()
    gewerbe = aktuelles_gewerbe()
    if not gewerbe or not gewerbe.auto_mahnen:
        return ergebnis
    # Erst nachholen, was bei einem früheren Lauf nicht rausging (Mailserver war nicht erreichbar)
    for mahnung in _unversendete_automatische(heute):
        _verschicke(mahnung.rechnung, mahnung, nutzer_id, ergebnis, nachgeholt=True)
    for rechnung, _stufe in faellige_mahnungen(heute):
        try:
            mahnung = erstelle_mahnung(rechnung, nutzer_id, heute=heute, automatisch=True)
        except MahnungNichtMoeglich:
            db.session.rollback()
            continue
        ergebnis.erstellt += 1
        _verschicke(rechnung, mahnung, nutzer_id, ergebnis)
    return ergebnis


def _jetzt() -> datetime:
    return datetime.now(UTC)


def _unversendete_automatische(heute: date | None) -> list[Mahnung]:
    """Automatisch erstellte Mahnungen ohne erfolgreichen Versand, solange die Rechnung offen ist
    und die Mahnfrist noch läuft."""
    from app.models import Versand

    jetzt = _jetzt()
    heute = heute or date.today()
    kandidaten = db.session.execute(
        select(Mahnung).where(Mahnung.automatisch.is_(True), Mahnung.frist_bis >= heute)
    ).scalars()
    offene = []
    for m in kandidaten:
        if m.rechnung.offen_cent <= 0 or m.rechnung.gesperrt_fuer_mahnungen:
            continue
        versuche = list(
            db.session.execute(select(Versand).where(Versand.mahnung_id == m.id)).scalars()
        )
        if any(v.erfolgreich for v in versuche):
            continue
        # Nicht stündlich neu versuchen: nach einem Fehlversuch erst nach sechs Stunden wieder
        if any(v.gesendet_am > jetzt - timedelta(hours=6) for v in versuche):
            continue
        offene.append(m)
    return offene


def _verschicke(rechnung, mahnung, nutzer_id, ergebnis, nachgeholt: bool = False) -> None:
    from app.services.mail import MailFehler, eingerichtet
    from app.services.versand import sende_beleg, vorschlag

    vorlage = vorschlag(rechnung, mahnung)
    if not (eingerichtet() and vorlage["an"]):
        if not nachgeholt:
            ergebnis.nicht_verschickt.append(
                f"{rechnung.nummer}: keine E-Mail-Adresse oder Versand nicht eingerichtet"
            )
        return
    try:
        sende_beleg(
            rechnung,
            mahnung=mahnung,
            an=vorlage["an"],
            betreff=vorlage["betreff"],
            text=vorlage["text"],
            nutzer_id=nutzer_id,
        )
    except MailFehler as fehler:
        db.session.rollback()
        ergebnis.nicht_verschickt.append(f"{rechnung.nummer}: {fehler}")
    else:
        ergebnis.verschickt += 1
