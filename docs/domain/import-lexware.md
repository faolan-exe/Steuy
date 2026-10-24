# Import des Belegarchivs aus Lexware (DATEV-Format)

Seite: `/import/archiv`. Eingelesen wird das ZIP „DATEV-Export Belegbilder mit Belegdaten“: `document.xml`, je Beleg eine XML-Datei (Buchungsdaten) und das PDF.

## Was übernommen wird

| Lexware | steuy |
|---|---|
| Ausgangsrechnung | Buchung „Einnahme“ mit dem PDF als Beleg (keine Rechnung mit Positionen) |
| Eingangsrechnung | Buchung „Ausgabe“ mit dem PDF als Beleg |
| Kunde / Lieferant (Name, Ort, USt-IdNr., Nummer) | Kontakt; vorhandene Kontakte werden über den Namen gefunden |

## Entscheidungen

- **Zahlungen stehen nicht im Export.** Alle Buchungen kommen offen herein. Für die EÜR zählt das Zahlungsdatum (Zuflussprinzip), das erfasst der Nutzer danach selbst.
- **Kategorie** nach Kontonummer (`KATEGORIE_NACH_KONTO` in `app/domain/datev_archiv.py`). Ohne eindeutige Zuordnung entsteht ein Entwurf unter „Zu prüfen“, damit nichts Falsches festgeschrieben wird.
- **Stornos:** Lexware bucht einen Storno mit derselben Rechnungsnummer und negativem Betrag. Steuy übernimmt die Rechnung und storniert sie (Gegenbuchung). War die Rechnung nur ein Entwurf, werden beide übersprungen. Andere negative Beträge werden nicht übernommen und aufgelistet.
- **Offene Einnahmen** erscheinen unter „Zu prüfen“ und im Dashboard (offene Forderungen), damit die Zahlungen erfasst werden können.
- **Doppelte** (gleiche Datei, oder gleiche Art, Datum, Nummer, Betrag und Partner) werden übersprungen. So lassen sich Jahres- und Monatsexport gefahrlos kombinieren und ein Import wiederholen.
- **Bewirtung** (Konten 6640 und 6644) ist in Lexware zweigeteilt. Geht der abzugsfähige Anteil ganzzahlig auf, wird er als betrieblicher Anteil vorbelegt. Es bleibt ein Entwurf.

## Offene Fachfragen (Steuerberatung)

- Passen die Kategorien je Konto? Besonders 6845 „Werkzeuge und Kleingeräte“, 135 „EDV-Software“ und 690 „Betriebsausstattung“ (GWG-Grenze, AfA) sowie 6430 „Sonstige Abgaben“ bleiben bewusst Entwürfe.
- Wie sollen Bewirtungskosten in der EÜR erscheinen (eigene Zeile, 70/30)?
- Gutschriften: Gegenbuchung zu welchem Beleg?
