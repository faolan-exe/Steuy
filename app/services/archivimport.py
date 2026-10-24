"""Belegarchiv aus Lexware (DATEV-Format) übernehmen: Kontakte, Belege und Buchungen.

Zahlungen stehen im Archiv nicht drin. Alle Buchungen kommen deshalb als offen herein; für die
EÜR zählt erst die Zahlung (Zuflussprinzip), die erfasst der Nutzer danach selbst.
"""

import io
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import func, select

from app.domain.csvimport import CsvUngueltig, lies
from app.domain.datev_archiv import (
    KATEGORIE_NACH_KONTO,
    ArchivUngueltig,
    Eintrag,
    bewirtung_prozent,
    ist_bewirtung,
    lies_archiv,
)
from app.domain.geld import GeldFormatFehler, euro_zu_cent
from app.domain.zahlung import ZahlungUngueltig
from app.extensions import db
from app.models import Beleg, Buchung, Kategorie, Kontakt
from app.services.belege import BelegUngueltig, BelegVorhanden, lade_hoch
from app.services.buchungen import (
    Buchungsdaten,
    BuchungUngueltig,
    erfasse_zahlung,
    festschreiben,
    lege_entwurf_an,
    storniere,
)
from app.services.kontakte import _bereinige, _vergib_nummern
from app.services.protokoll import protokolliere


@dataclass
class Ergebnis:
    art: str = "archiv"
    festgeschrieben: int = 0
    entwuerfe: int = 0
    kontakte_neu: int = 0
    storniert: int = 0
    uebersprungen: list[str] = field(default_factory=list)
    gutschriften: list[str] = field(default_factory=list)
    probleme: list[str] = field(default_factory=list)
    entwurf_gruende: dict[str, int] = field(default_factory=dict)

    @property
    def neu(self) -> int:
        return self.festgeschrieben + self.entwuerfe


def _bezeichnung(e: Eintrag) -> str:
    return f"{e.datum:%d.%m.%Y} {e.rechnungsnr or 'ohne Nummer'} ({e.partner or 'ohne Name'})"


def _kategorien() -> dict[str, Kategorie]:
    return {k.name: k for k in db.session.execute(select(Kategorie)).scalars()}


def _finde_kontakt(e: Eintrag) -> Kontakt | None:
    if not e.partner:
        return None
    name = e.partner.lower()
    treffer = db.session.execute(
        select(Kontakt).where(
            (func.lower(func.coalesce(Kontakt.firmenname, "")) == name)
            | (func.lower(func.coalesce(Kontakt.nachname, "")) == name)
        )
    ).scalars()
    return next(iter(treffer), None)


def _lege_kontakt_an(e: Eintrag) -> Kontakt:
    ist_kunde = e.art == "einnahme"
    daten = {
        "art": "firma",
        "firmenname": e.partner,
        "ort": e.ort,
        "ust_idnr": e.ust_idnr,
    }
    kontakt = Kontakt(**_bereinige(daten), ist_kunde=ist_kunde, ist_lieferant=not ist_kunde)
    spalte = Kontakt.kundennummer if ist_kunde else Kontakt.lieferantennummer
    if (
        e.partner_nr
        and not db.session.execute(select(spalte).where(spalte == e.partner_nr)).first()
    ):
        if ist_kunde:
            kontakt.kundennummer = e.partner_nr
        else:
            kontakt.lieferantennummer = e.partner_nr
    _vergib_nummern(kontakt)
    db.session.add(kontakt)
    db.session.flush()
    return kontakt


def _rolle_ergaenzen(kontakt: Kontakt, e: Eintrag) -> None:
    if e.art == "einnahme" and not kontakt.ist_kunde:
        kontakt.ist_kunde = True
    elif e.art == "ausgabe" and not kontakt.ist_lieferant:
        kontakt.ist_lieferant = True
    _vergib_nummern(kontakt)


def _schon_gebucht(e: Eintrag) -> bool:
    abfrage = select(Buchung.id).where(
        Buchung.art == e.art,
        Buchung.belegdatum == e.datum,
        Buchung.betrag_cent == e.gesamt_cent,
        Buchung.belegnummer.is_not_distinct_from(e.rechnungsnr),
        Buchung.storno_von_id.is_(None),
    )
    return db.session.execute(abfrage).first() is not None


def _buchung_zum_storno(e: Eintrag) -> tuple[Buchung | None, bool]:
    """Lexware bucht einen Storno mit derselben Rechnungsnummer und negativem Betrag.
    Gibt (offene Buchung, gab es schon eine stornierte) zurück."""
    kandidaten = db.session.execute(
        select(Buchung).where(
            Buchung.art == e.art,
            Buchung.belegnummer.is_not_distinct_from(e.rechnungsnr),
            Buchung.partner.is_not_distinct_from(e.partner),
            Buchung.betrag_cent == -e.gesamt_cent,
            Buchung.storno_von_id.is_(None),
        )
    ).scalars()
    offen, schon = None, False
    for b in kandidaten:
        if b.storniert:
            schon = True
        elif not b.ist_entwurf and offen is None:
            offen = b
    return offen, schon


def importiere_archiv(
    inhalt: bytes, nutzer_id: int, pruefen: bool = False, bekannt: set | None = None
) -> Ergebnis:
    """Mit pruefen=True wird nichts gespeichert, nur gezählt (Vorschau).

    `bekannt` sammelt die Schlüssel schon gelesener Belege über mehrere Dateien hinweg
    (überlappende Zeiträume, z. B. Jahres- und Monatsexport)."""
    ergebnis = Ergebnis()
    try:
        eintraege, probleme = lies_archiv(inhalt)
    except ArchivUngueltig as fehler:
        ergebnis.probleme.append(str(fehler))
        return ergebnis
    ergebnis.probleme.extend(probleme)
    bekannt = bekannt if bekannt is not None else set()
    kategorien = _kategorien()

    stornos = {
        ("positiv", e.art, e.rechnungsnr, e.partner, -e.gesamt_cent)
        for e in eintraege
        if e.gesamt_cent < 0
    }
    # Erst die Rechnungen, dann ihre Stornos: so findet jeder Storno sein Original.
    for e in sorted(eintraege, key=lambda x: x.gesamt_cent < 0):
        if e.schluessel in bekannt:
            ergebnis.uebersprungen.append(f"{_bezeichnung(e)}: kommt in den Dateien doppelt vor")
            continue
        bekannt.add(e.schluessel)
        if e.gesamt_cent < 0:
            gegen = ("positiv", e.art, e.rechnungsnr, e.partner, -e.gesamt_cent)
            if ("ausgeglichen", *gegen) in bekannt:
                ergebnis.uebersprungen.append(
                    f"{_bezeichnung(e)}: Storno und Rechnung gleichen sich aus, nicht übernommen"
                )
                continue
            original, schon_storniert = _buchung_zum_storno(e)
            if pruefen and (original is not None or gegen in bekannt):
                ergebnis.storniert += 1
            elif original is not None:
                try:
                    storniere(original, nutzer_id)
                    ergebnis.storniert += 1
                except BuchungUngueltig as fehler:
                    db.session.rollback()
                    ergebnis.probleme.append(f"{_bezeichnung(e)}: {fehler}")
            elif schon_storniert:
                ergebnis.uebersprungen.append(f"{_bezeichnung(e)}: Storno ist schon gebucht")
            else:
                ergebnis.gutschriften.append(_bezeichnung(e))
            continue
        if e.gesamt_cent == 0:
            ergebnis.gutschriften.append(_bezeichnung(e))
            continue
        if e.pdf:
            datei = ("datei", _sha(e.pdf))
            schon = (
                datei in bekannt
                or db.session.execute(select(Beleg.id).where(Beleg.sha256 == datei[1])).first()
            )
            if schon:
                ergebnis.uebersprungen.append(f"{_bezeichnung(e)}: dieselbe Datei gibt es schon")
                continue
        if _schon_gebucht(e):
            ergebnis.uebersprungen.append(f"{_bezeichnung(e)}: ist schon gebucht")
            continue

        kategorie, grund = _kategorie_fuer(e, kategorien)
        schluessel = ("positiv", e.art, e.rechnungsnr, e.partner, e.gesamt_cent)
        if kategorie is None and schluessel in stornos:
            # Ein Entwurf lässt sich nicht stornieren; beide wären nur Ballast.
            bekannt.add(("ausgeglichen", *schluessel))
            ergebnis.uebersprungen.append(
                f"{_bezeichnung(e)}: wurde in Lexware storniert, nicht übernommen"
            )
            continue
        prozent = 100
        if ist_bewirtung(e):
            prozent = bewirtung_prozent(e) or 100
        if grund:
            ergebnis.entwurf_gruende[grund] = ergebnis.entwurf_gruende.get(grund, 0) + 1

        if e.pdf:
            bekannt.add(("datei", _sha(e.pdf)))

        if pruefen:
            if (
                e.partner
                and not _finde_kontakt(e)
                and ("kontakt", e.partner.lower()) not in bekannt
            ):
                bekannt.add(("kontakt", e.partner.lower()))
                ergebnis.kontakte_neu += 1
            if kategorie:
                ergebnis.festgeschrieben += 1
                bekannt.add(("positiv", e.art, e.rechnungsnr, e.partner, e.gesamt_cent))
                bekannt.add(("eintrag", e.art, e.rechnungsnr, e.datum, e.gesamt_cent))
            else:
                ergebnis.entwuerfe += 1
            continue

        try:
            kontakt = _finde_kontakt(e)
            if e.partner and kontakt is None:
                kontakt = _lege_kontakt_an(e)
                ergebnis.kontakte_neu += 1
            elif kontakt is not None:
                _rolle_ergaenzen(kontakt, e)
            beleg_id = None
            if e.pdf:
                try:
                    beleg_id = lade_hoch(e.pdf_name or "beleg.pdf", e.pdf, nutzer_id).id
                except BelegVorhanden:
                    db.session.rollback()
                    ergebnis.uebersprungen.append(f"{_bezeichnung(e)}: ist schon in steuy")
                    continue
                except BelegUngueltig as fehler:
                    db.session.rollback()
                    ergebnis.probleme.append(f"{_bezeichnung(e)}: {fehler}")
                    continue
            daten = Buchungsdaten(
                art=e.art,
                belegdatum=e.datum,
                betrag_cent=e.gesamt_cent,
                kategorie_id=kategorie.id if kategorie else None,
                betrieblich_prozent=prozent,
                kontakt_id=kontakt.id if kontakt else None,
                partner=e.partner,
                belegnummer=e.rechnungsnr,
                beschreibung=e.info,
                beleg_id=beleg_id,
            )
            buchung = lege_entwurf_an(daten, nutzer_id)
            if kategorie:
                festschreiben(buchung, nutzer_id)
                ergebnis.festgeschrieben += 1
            else:
                ergebnis.entwuerfe += 1
        except (BuchungUngueltig, ValueError) as fehler:
            db.session.rollback()
            ergebnis.probleme.append(f"{_bezeichnung(e)}: {fehler}")

    if not pruefen:
        protokolliere(
            "archiv_import",
            nutzer_id=nutzer_id,
            objekt_typ="import",
            details={
                "festgeschrieben": ergebnis.festgeschrieben,
                "entwuerfe": ergebnis.entwuerfe,
                "kontakte_neu": ergebnis.kontakte_neu,
                "storniert": ergebnis.storniert,
                "uebersprungen": len(ergebnis.uebersprungen),
            },
        )
        db.session.commit()
    return ergebnis


def _sha(inhalt: bytes) -> str:
    import hashlib

    return hashlib.sha256(inhalt).hexdigest()


def _kategorie_fuer(e: Eintrag, kategorien: dict[str, Kategorie]) -> tuple[Kategorie | None, str]:
    """Kategorie und, falls keine gefunden wird, der Grund für den Entwurf."""
    if ist_bewirtung(e):
        return None, "Bewirtung (bitte Kategorie und Anteil prüfen)"
    if len(e.posten) > 1:
        return None, "Mehrere Konten in einem Beleg"
    name = KATEGORIE_NACH_KONTO.get(e.konto)
    kategorie = kategorien.get(name) if name else None
    if kategorie is None or kategorie.art != e.art:
        return None, f"Konto {e.konto} {e.kontoname}".strip()
    return kategorie, ""


# ---------- Zahlungsdaten aus den Lexware-Listen (CSV) ----------


@dataclass
class ZahlungsErgebnis:
    art: str = "zahlungen"
    liste: str = "Ausgaben"
    erfasst: int = 0
    schon_bezahlt: int = 0
    ohne_treffer: list[str] = field(default_factory=list)
    entwuerfe: list[str] = field(default_factory=list)
    mehrdeutig: list[str] = field(default_factory=list)
    probleme: list[str] = field(default_factory=list)


SPALTEN = ("RG-Datum", "RG-Nr.", "Gesamtbetrag", "bezahlt am")


def _tag(wert: str) -> date | None:
    try:
        return datetime.strptime(wert.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def ist_zahlungsliste(inhalt: bytes) -> bool:
    try:
        kopf, _ = lies(inhalt)
    except CsvUngueltig:
        return False
    return all(spalte in kopf for spalte in SPALTEN)


def zahlungslisten_im_zip(inhalt: bytes) -> list[bytes]:
    """Alle Zahlungslisten (Eingangs- und Ausgangsrechnungen) aus dem Lexware-ZIP."""
    gefunden = []
    try:
        with zipfile.ZipFile(io.BytesIO(inhalt)) as archiv:
            for info in archiv.infolist():
                if info.filename.lower().endswith(".csv") and info.file_size <= 2 * 1024 * 1024:
                    daten = archiv.read(info.filename)
                    if ist_zahlungsliste(daten):
                        gefunden.append(daten)
    except zipfile.BadZipFile:
        return []
    return gefunden


def _art_der_liste(kopf: list[str]) -> str:
    """Die Liste der Ausgangsrechnungen hat eine Kundennummer, die der Eingangsrechnungen eine
    Lieferantennummer."""
    return "einnahme" if any(k.lower().startswith("kunde") for k in kopf) else "ausgabe"


def _offene_buchungen(art: str) -> dict[tuple, list]:
    gefunden: dict[tuple, list] = defaultdict(list)
    abfrage = select(Buchung).where(
        Buchung.art == art,
        Buchung.status == "festgeschrieben",
        Buchung.storno_von_id.is_(None),
    )
    for b in db.session.execute(abfrage).scalars():
        if b.zahlstatus == "offen":
            gefunden[(b.belegnummer, b.belegdatum, b.betrag_cent)].append(b)
    return gefunden


def _entwurfs_schluessel(art: str) -> set[tuple]:
    abfrage = select(Buchung).where(Buchung.art == art, Buchung.status == "entwurf")
    return {
        (b.belegnummer, b.belegdatum, b.betrag_cent) for b in db.session.execute(abfrage).scalars()
    }


def uebernehme_zahlungen(
    inhalt: bytes, nutzer_id: int, pruefen: bool = False, bekannt: set | None = None
) -> ZahlungsErgebnis:
    """Trägt „bezahlt am“ aus der Lexware-Liste bei den importierten Ausgaben oder Einnahmen ein.

    Zuerst mit Rechnungsnummer, Datum und Betrag, sonst mit Datum und Betrag, wenn das
    eindeutig ist. In der Vorschau zählen auch die Belege, die der Archivimport im selben Lauf
    erst anlegen würde."""
    ergebnis = ZahlungsErgebnis()
    try:
        kopf, zeilen = lies(inhalt)
    except CsvUngueltig as fehler:
        ergebnis.probleme.append(str(fehler))
        return ergebnis
    if not all(spalte in kopf for spalte in SPALTEN):
        ergebnis.probleme.append("Das ist keine Lexware-Liste mit „bezahlt am“.")
        return ergebnis
    spalte = {name: kopf.index(name) for name in SPALTEN}
    art = _art_der_liste(kopf)
    ergebnis.liste = "Einnahmen" if art == "einnahme" else "Ausgaben"
    kandidaten = _offene_buchungen(art)
    if pruefen:
        for merker in bekannt or ():
            if merker[0] == "eintrag" and merker[1] == art:
                kandidaten[(merker[2], merker[3], merker[4])].append(None)

    # Zeilen nach Schlüssel bündeln
    nach_schluessel: dict[tuple, list[tuple[str, date | None]]] = defaultdict(list)
    for zeile in zeilen:
        if not any(f.strip() for f in zeile):
            continue
        try:
            datum = _tag(zeile[spalte["RG-Datum"]])
            cent = euro_zu_cent(zeile[spalte["Gesamtbetrag"]])
        except (GeldFormatFehler, IndexError):
            ergebnis.probleme.append(f"Zeile ohne lesbaren Betrag: {zeile[:2]}")
            continue
        bezeichnung = f"{zeile[spalte['RG-Datum']]} {zeile[spalte['RG-Nr.']] or 'ohne Nummer'}"
        nach_schluessel[(zeile[spalte["RG-Nr."]] or None, datum, cent)].append(
            (bezeichnung, _tag(zeile[spalte["bezahlt am"]]))
        )

    entwuerfe = _entwurfs_schluessel(art)
    unerledigt: dict[tuple, list] = {}
    for schluessel, zeilen_dazu in nach_schluessel.items():
        if schluessel in entwuerfe and schluessel not in kandidaten:
            ergebnis.entwuerfe.extend(bezeichnung for bezeichnung, _ in zeilen_dazu)
            continue
        passende = kandidaten.get(schluessel, [])
        if not passende:
            unerledigt[schluessel] = zeilen_dazu
            continue
        _verbuche(schluessel, zeilen_dazu, passende, ergebnis, nutzer_id, pruefen)

    # Zweiter Versuch ohne Rechnungsnummer (Sonderzeichen werden von Lexware unterschiedlich
    # exportiert), nur wenn Datum und Betrag genau einen offenen Beleg treffen.
    for (_nr, datum, cent), zeilen_dazu in unerledigt.items():
        passende = [
            b
            for (_n, d, c), liste in kandidaten.items()
            if (d, c) == (datum, cent)
            for b in liste
            if b is None or b.zahlstatus == "offen"
        ]
        if len(passende) == 1 and len(zeilen_dazu) == 1:
            _verbuche(("", datum, cent), zeilen_dazu, passende, ergebnis, nutzer_id, pruefen)
        else:
            for bezeichnung, _ in zeilen_dazu:
                ergebnis.ohne_treffer.append(bezeichnung)

    if not pruefen:
        protokolliere(
            "zahlungen_aus_liste",
            nutzer_id=nutzer_id,
            objekt_typ="import",
            details={"erfasst": ergebnis.erfasst, "ohne_treffer": len(ergebnis.ohne_treffer)},
        )
        db.session.commit()
    return ergebnis


def _verbuche(schluessel, zeilen_dazu, passende, ergebnis, nutzer_id, pruefen) -> None:
    daten = {tag for _, tag in zeilen_dazu}
    if len(zeilen_dazu) > len(passende) or (len(zeilen_dazu) > 1 and len(daten) > 1):
        for bezeichnung, _ in zeilen_dazu:
            ergebnis.mehrdeutig.append(bezeichnung)
        return
    for (bezeichnung, tag), buchung in zip(zeilen_dazu, passende, strict=False):
        if tag is None:
            ergebnis.ohne_treffer.append(f"{bezeichnung} (ohne Zahlungsdatum)")
        elif pruefen or buchung is None:
            ergebnis.erfasst += 1
        else:
            try:
                erfasse_zahlung(
                    buchung,
                    datum=tag,
                    betrag_cent=buchung.betrag_cent,
                    zahlungsart="sonstige",
                    notiz="Zahlungsdatum aus Lexware-Liste",
                    nutzer_id=nutzer_id,
                )
                ergebnis.erfasst += 1
            except (ZahlungUngueltig, ValueError) as fehler:
                db.session.rollback()
                ergebnis.probleme.append(f"{bezeichnung}: {fehler}")
