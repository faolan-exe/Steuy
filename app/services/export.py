"""Exporte: ZIP für die Steuerberatung, Wechsel-Export (DATEV) und Gesamtexport."""

import csv
import hashlib
import io
import tempfile
import zipfile
from datetime import date, datetime

from sqlalchemy import extract, inspect, or_, select

from app.domain.buchung import betrieblicher_anteil
from app.domain.datev import Kopf, buchungsstapel, pruefe_kopf
from app.domain.datev import Posten as DatevPosten
from app.domain.geld import cent_zu_euro
from app.extensions import db
from app.models import Artikel, Beleg, Buchung, Kontakt, Rechnung, Zahlung
from app.services import ablage
from app.services.einrichtung import aktuelles_gewerbe
from app.services.euer import berechne
from app.services.protokoll import protokolliere
from app.version import VERSION

# Gesamtexport: alle fachlichen Tabellen
TABELLEN = (
    "gewerbe",
    "nutzer",
    "kontakt",
    "artikel",
    "kategorie",
    "rechnung",
    "rechnungsposition",
    "mahnung",
    "zahlung",
    "beleg",
    "buchung",
    "buchung_gebuehr",
    "euer_zeile",
    "euer_zuordnung",
    "nummernkreis",
    "protokoll",
)
OHNE_SPALTEN = {"nutzer": {"passwort_hash"}}


PRUEFSUMMEN_DATEI = "SHA256SUMS"
PRUEFEN_TEXT = """So prüfst du, dass nichts verändert wurde
==========================================

Die Datei SHA256SUMS enthält zu jeder Datei dieses Archivs eine SHA-256-Prüfsumme (ein
digitaler Fingerabdruck). Stimmt eine Summe nicht mehr, wurde die Datei nach dem Export
geändert oder ist beschädigt. Hebe das Archiv samt dieser Datei auf (Aufbewahrungsfristen
bitte mit der Steuerberatung klären).

1. Archiv entpacken.
2. Prüfen:
   - Linux:    sha256sum -c SHA256SUMS
   - macOS:    shasum -a 256 -c SHA256SUMS
   - Windows:  in PowerShell: Get-FileHash -Algorithm SHA256 <Datei>
               und mit der Zeile in SHA256SUMS vergleichen
   - steuy:    flask export-pruefen <Archiv>.zip

Erstellt mit steuy {version}.
"""


class _Archiv:
    """ZIP, das beim Schließen eine Prüfsummenliste (SHA256SUMS) und eine Anleitung anhängt."""

    def __init__(self, datei) -> None:
        self._zip = zipfile.ZipFile(datei, "w", zipfile.ZIP_DEFLATED)
        self._summen: dict[str, str] = {}

    def writestr(self, name: str, inhalt: bytes | str) -> None:
        daten = inhalt.encode() if isinstance(inhalt, str) else inhalt
        self._zip.writestr(name, daten)
        self._summen[name] = hashlib.sha256(daten).hexdigest()

    def __enter__(self) -> "_Archiv":
        return self

    def __exit__(self, art, wert, spur) -> None:
        if art is None:
            self.writestr("PRUEFEN.txt", PRUEFEN_TEXT.format(version=VERSION))
            zeilen = "".join(f"{summe}  {name}\n" for name, summe in sorted(self._summen.items()))
            self._zip.writestr(PRUEFSUMMEN_DATEI, zeilen)
        self._zip.close()


def pruefe_archiv(inhalt: bytes) -> list[str]:
    """Prüft ein steuy-Archiv gegen seine SHA256SUMS. Leere Liste heißt: alles in Ordnung."""
    probleme: list[str] = []
    try:
        archiv = zipfile.ZipFile(io.BytesIO(inhalt))
    except zipfile.BadZipFile:
        return ["Das ist keine ZIP-Datei."]
    with archiv:
        if PRUEFSUMMEN_DATEI not in archiv.namelist():
            return [f"{PRUEFSUMMEN_DATEI} fehlt im Archiv."]
        erwartet: dict[str, str] = {}
        for zeile in archiv.read(PRUEFSUMMEN_DATEI).decode().splitlines():
            summe, _, name = zeile.partition("  ")
            if summe and name:
                erwartet[name] = summe
        vorhanden = {n for n in archiv.namelist() if n != PRUEFSUMMEN_DATEI and not n.endswith("/")}
        for name in sorted(vorhanden - erwartet.keys()):
            probleme.append(f"{name}: steht nicht in {PRUEFSUMMEN_DATEI} (hinzugefügt?)")
        for name, summe in sorted(erwartet.items()):
            if name not in vorhanden:
                probleme.append(f"{name}: fehlt im Archiv")
            elif hashlib.sha256(archiv.read(name)).hexdigest() != summe:
                probleme.append(f"{name}: Prüfsumme stimmt nicht (verändert oder beschädigt)")
    return probleme


def _betrag(cent: int) -> str:
    return cent_zu_euro(cent)[:-2].replace(".", "")


def _csv(zeilen: list[list]) -> bytes:
    puffer = io.StringIO()
    csv.writer(puffer, delimiter=";").writerows(zeilen)
    return ("﻿" + puffer.getvalue()).encode()


def _dateiname(text: str) -> str:
    return "".join(z if z.isalnum() or z in "-_." else "_" for z in text)[:80]


def _endung(beleg: Beleg) -> str:
    return {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}.get(
        beleg.mime, ".xml"
    )


def steuerberater_zip(jahr: int, nutzer_id: int) -> tempfile.SpooledTemporaryFile:
    """ZIP mit EÜR, Zahlungen, Rechnungs-PDFs und Belegen eines Jahres."""
    from app.services.auswertung_pdf import euer_pdf

    # Wird an send_file übergeben und dort geschlossen
    datei = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024)  # noqa: SIM115
    ergebnis = berechne(jahr)
    with _Archiv(datei) as zip_:
        zip_.writestr(f"EUER-{jahr}.pdf", euer_pdf(ergebnis))

        zeilen = [["Zeile", "Kennzahl", "Bezeichnung", "Betrag EUR"]]
        for zeile, betrag, _ in ergebnis.einnahmen + ergebnis.ausgaben:
            nummer = zeile.nummer if zeile.nummer > 0 else ""
            zeilen.append([nummer, zeile.kennzahl or "", zeile.bezeichnung, _betrag(betrag)])
        zeilen += [
            ["", "", "Summe Betriebseinnahmen", _betrag(ergebnis.summe_einnahmen)],
            ["", "", "Summe Betriebsausgaben", _betrag(ergebnis.summe_ausgaben)],
            ["", "", "Gewinn/Verlust", _betrag(ergebnis.gewinn)],
        ]
        zip_.writestr(f"EUER-{jahr}.csv", _csv(zeilen))

        # Alle Zahlungen des Jahres (Zufluss/Abfluss) mit Bezug
        zahlungen = db.session.execute(
            select(Zahlung).where(extract("year", Zahlung.datum) == jahr).order_by(Zahlung.datum)
        ).scalars()
        zeilen = [
            [
                "Datum",
                "Art",
                "Bezug",
                "Partner",
                "Kategorie",
                "Betrag EUR",
                "Betrieblich %",
                "Betrieblich EUR",
                "Zahlungsart",
                "Belegdatei",
            ]
        ]
        belege: dict[int, Beleg] = {}
        for z in zahlungen:
            if z.rechnung_id:
                r = z.rechnung
                zeilen.append(
                    [
                        z.datum.strftime("%d.%m.%Y"),
                        "Einnahme",
                        r.nummer,
                        r.empfaenger_name or "",
                        "Rechnung",
                        _betrag(z.betrag_cent),
                        "100",
                        _betrag(z.betrag_cent),
                        z.zahlungsart,
                        f"rechnungen/{r.nummer}.pdf",
                    ]
                )
                continue
            b = z.buchung
            datei_name = ""
            if b.beleg:
                belege[b.beleg.id] = b.beleg
                datei_name = f"belege/{b.beleg.id:05d}{_endung(b.beleg)}"
            zeilen.append(
                [
                    z.datum.strftime("%d.%m.%Y"),
                    "Einnahme" if b.art == "einnahme" else "Ausgabe",
                    b.belegnummer or f"Buchung {b.id}",
                    b.partner or "",
                    b.kategorie.name if b.kategorie else "",
                    _betrag(z.betrag_cent),
                    str(b.betrieblich_prozent),
                    _betrag(betrieblicher_anteil(z.betrag_cent, b.betrieblich_prozent)),
                    z.zahlungsart,
                    datei_name,
                ]
            )
        zip_.writestr(f"Zahlungen-{jahr}.csv", _csv(zeilen))

        # Belege von Buchungen mit Belegdatum im Jahr kommen ebenfalls mit
        weitere = db.session.execute(
            select(Buchung).where(
                extract("year", Buchung.belegdatum) == jahr, Buchung.beleg_id.is_not(None)
            )
        ).scalars()
        for b in weitere:
            belege[b.beleg.id] = b.beleg
        index = [["Datei", "Originalname", "Hochgeladen", "SHA-256"]]
        for beleg in sorted(belege.values(), key=lambda x: x.id):
            name = f"belege/{beleg.id:05d}{_endung(beleg)}"
            zip_.writestr(name, ablage.lies(beleg.sha256))
            index.append(
                [name, beleg.dateiname, beleg.hochgeladen_am.strftime("%d.%m.%Y"), beleg.sha256]
            )
        zip_.writestr("belege/Index.csv", _csv(index))

        rechnungen = db.session.execute(
            select(Rechnung).where(
                Rechnung.belegart.in_(["rechnung", "korrektur"]),
                Rechnung.finalisiert_am.is_not(None),
                or_(
                    extract("year", Rechnung.rechnungsdatum) == jahr,
                    Rechnung.id.in_(
                        select(Zahlung.rechnung_id).where(extract("year", Zahlung.datum) == jahr)
                    ),
                ),
            )
        ).scalars()
        uebersicht = [
            [
                "Nummer",
                "Art",
                "Datum",
                "Kunde",
                "Betrag EUR",
                "Status",
                "Fällig am",
                "SHA-256 (PDF)",
            ]
        ]
        for r in sorted(rechnungen, key=lambda x: (x.rechnungsdatum, x.nummer)):
            zip_.writestr(f"rechnungen/{_dateiname(r.nummer)}.pdf", ablage.lies(r.pdf_sha256))
            if r.xml_sha256:
                zip_.writestr(f"rechnungen/{_dateiname(r.nummer)}.xml", ablage.lies(r.xml_sha256))
            uebersicht.append(
                [
                    r.nummer,
                    "Rechnungskorrektur" if r.belegart == "korrektur" else "Rechnung",
                    r.rechnungsdatum.strftime("%d.%m.%Y"),
                    r.empfaenger_name or "",
                    _betrag(r.summe_cent),
                    r.status,
                    r.faellig_am.strftime("%d.%m.%Y") if r.faellig_am else "",
                    r.pdf_sha256,
                ]
            )
        zip_.writestr(f"Rechnungen-{jahr}.csv", _csv(uebersicht))

        zip_.writestr(
            "LIESMICH.txt",
            f"Export steuy für {aktuelles_gewerbe().name}, Jahr {jahr}, erstellt am "
            f"{date.today():%d.%m.%Y}.\n\n"
            "EUER-*.pdf/csv: Werte für die Anlage EÜR (nach Zahlungsdatum)\n"
            "Zahlungen-*.csv: alle Zahlungseingänge und -ausgänge des Jahres\n"
            "Rechnungen-*.csv: Übersicht der Ausgangsrechnungen mit Prüfsumme des PDFs\n"
            "rechnungen/: Ausgangsrechnungen und Rechnungskorrekturen (PDF/A, Original)\n"
            "belege/: Eingangsbelege im Original, Index.csv mit SHA-256-Prüfsummen\n"
            "SHA256SUMS: Prüfsumme jeder Datei dieses Archivs, Anleitung in PRUEFEN.txt\n",
        )
    protokolliere("export_steuerberater", nutzer_id=nutzer_id, details={"jahr": jahr})
    db.session.commit()
    datei.seek(0)
    return datei


def _wert(wert) -> str:
    if wert is None:
        return ""
    if isinstance(wert, datetime | date):
        return wert.isoformat()
    return str(wert)


def gesamt_zip(nutzer_id: int) -> tempfile.SpooledTemporaryFile:
    """Alle Tabellen als CSV und alle Dateien der Ablage (ohne Passwort-Hashes)."""
    # Wird an send_file übergeben und dort geschlossen
    datei = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024)  # noqa: SIM115
    verbindung = db.session.connection()
    vorhandene = set(inspect(verbindung).get_table_names())
    with _Archiv(datei) as zip_:
        for tabelle in TABELLEN:
            if tabelle not in vorhandene:
                continue
            ergebnis = verbindung.exec_driver_sql(f'SELECT * FROM "{tabelle}" ORDER BY 1')
            alle_spalten = list(ergebnis.keys())
            spalten = [s for s in alle_spalten if s not in OHNE_SPALTEN.get(tabelle, set())]
            zeilen = [spalten]
            for zeile in ergebnis.mappings():
                zeilen.append([_wert(zeile[s]) for s in spalten])
            zip_.writestr(f"daten/{tabelle}.csv", _csv(zeilen))
        hashes = set(db.session.execute(select(Beleg.sha256)).scalars())
        hashes |= set(
            db.session.execute(
                select(Rechnung.pdf_sha256).where(Rechnung.pdf_sha256.is_not(None))
            ).scalars()
        )
        from app.models import Mahnung

        hashes |= set(db.session.execute(select(Mahnung.pdf_sha256)).scalars())
        hashes |= set(
            db.session.execute(
                select(Rechnung.xml_sha256).where(Rechnung.xml_sha256.is_not(None))
            ).scalars()
        )
        hashes |= set(
            db.session.execute(
                select(Zahlung.nachweis_sha256).where(Zahlung.nachweis_sha256.is_not(None))
            ).scalars()
        )
        for sha in sorted(hashes):
            zip_.writestr(f"ablage/{sha[:2]}/{sha}", ablage.lies(sha))
    protokolliere("export_gesamt", nutzer_id=nutzer_id)
    db.session.commit()
    datei.seek(0)
    return datei


def _datev_posten(zahlung: Zahlung) -> DatevPosten:
    if zahlung.rechnung_id:
        r = zahlung.rechnung
        return DatevPosten(
            art="einnahme",
            datum=zahlung.datum,
            betrag_cent=zahlung.betrag_cent,
            kategorie="Rechnung",
            zahlungsart=zahlung.zahlungsart,
            belegfeld=r.nummer or "",
            text=r.empfaenger_name or f"Rechnung {r.nummer}",
        )
    b = zahlung.buchung
    return DatevPosten(
        art=b.art,
        datum=zahlung.datum,
        betrag_cent=zahlung.betrag_cent,
        kategorie=b.kategorie.name if b.kategorie else None,
        zahlungsart=zahlung.zahlungsart,
        belegfeld=b.belegnummer or f"B{b.id}",
        text=b.partner or b.beschreibung or (b.kategorie.name if b.kategorie else "Buchung"),
        betrieblich_prozent=b.betrieblich_prozent,
    )


def _ja(wert: bool) -> str:
    return "ja" if wert else "nein"


def _kontakte_csv(lieferanten: bool) -> bytes:
    nummer = Kontakt.lieferantennummer if lieferanten else Kontakt.kundennummer
    kontakte = db.session.execute(
        select(Kontakt).where(nummer.is_not(None)).order_by(nummer)
    ).scalars()
    zeilen = [
        [
            "Lieferantennummer" if lieferanten else "Kundennummer",
            "Firmenname",
            "Anrede",
            "Vorname",
            "Nachname",
            "Adresszusatz",
            "Straße",
            "PLZ",
            "Ort",
            "Land",
            "E-Mail",
            "Telefon",
            "Steuernummer",
            "USt-IdNr.",
            "Notiz",
            "Archiviert",
        ]
    ]
    for k in kontakte:
        zeilen.append(
            [
                k.lieferantennummer if lieferanten else k.kundennummer,
                k.firmenname or "",
                k.anrede or "",
                k.vorname or "",
                k.nachname or "",
                k.adresszusatz or "",
                k.strasse or "",
                k.plz or "",
                k.ort or "",
                k.land or "",
                k.email or "",
                k.telefon or "",
                k.steuernummer or "",
                k.ust_idnr or "",
                k.notiz or "",
                _ja(k.archiviert),
            ]
        )
    return _csv(zeilen)


def _artikel_csv() -> bytes:
    zeilen = [
        [
            "Artikelnummer",
            "Typ",
            "Bezeichnung",
            "Beschreibung",
            "Einheit",
            "Preis EUR",
            "GTIN",
            "Notiz",
            "Archiviert",
        ]
    ]
    for a in db.session.execute(select(Artikel).order_by(Artikel.id)).scalars():
        zeilen.append(
            [
                a.artikelnummer or "",
                "Dienstleistung" if a.typ == "service" else "Produkt",
                a.bezeichnung,
                a.beschreibung or "",
                a.einheit,
                _betrag(a.preis_cent),
                a.gtin or "",
                a.notiz or "",
                _ja(a.archiviert),
            ]
        )
    return _csv(zeilen)


def wechsel_zip(
    kontenrahmen: str, beraternummer: int, mandantennummer: int, nutzer_id: int
) -> tempfile.SpooledTemporaryFile:
    """Daten für den Umzug in andere Software: DATEV-Buchungsstapel je Jahr und Stammdaten."""
    pruefe_kopf(kontenrahmen, beraternummer, mandantennummer)
    # Wird an send_file übergeben und dort geschlossen
    datei = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024)  # noqa: SIM115
    jahre: dict[int, list[DatevPosten]] = {}
    for z in db.session.execute(select(Zahlung).order_by(Zahlung.datum, Zahlung.id)).scalars():
        jahre.setdefault(z.datum.year, []).append(_datev_posten(z))
    jetzt = datetime.now()
    with _Archiv(datei) as zip_:
        for jahr, posten in sorted(jahre.items()):
            kopf = Kopf(jahr, kontenrahmen, beraternummer, mandantennummer, jetzt)
            zip_.writestr(f"DATEV/EXTF_Buchungsstapel_{jahr}.csv", buchungsstapel(kopf, posten))
        zip_.writestr("Stammdaten/Kunden.csv", _kontakte_csv(lieferanten=False))
        zip_.writestr("Stammdaten/Lieferanten.csv", _kontakte_csv(lieferanten=True))
        zip_.writestr("Stammdaten/Artikel.csv", _artikel_csv())
        zip_.writestr(
            "LIESMICH.txt",
            f"Wechsel-Export steuy für {aktuelles_gewerbe().name}, erstellt am "
            f"{date.today():%d.%m.%Y}.\n\n"
            f"DATEV/: Buchungsstapel (EXTF 700) je Jahr, Kontenrahmen {kontenrahmen}. Jede "
            "Zahlung ist eine Buchung, Bank bzw. Kasse gegen Erlös- oder Aufwandskonto.\n"
            "Die Konten sind Vorschläge und müssen vor dem Import geprüft werden.\n"
            "Lexware Office, sevDesk und andere Programme lesen dieses Format ebenfalls ein.\n\n"
            "Stammdaten/: Kunden, Lieferanten und Artikel als CSV (UTF-8, Semikolon). Beim "
            "Import die Spalten im Importdialog der neuen Software zuordnen.\n\n"
            "Rechnungs-PDFs und Belege enthält der Export für die Steuerberatung (je Jahr).\n",
        )
    protokolliere(
        "export_wechsel",
        nutzer_id=nutzer_id,
        details={"kontenrahmen": kontenrahmen, "jahre": sorted(jahre)},
    )
    db.session.commit()
    datei.seek(0)
    return datei
