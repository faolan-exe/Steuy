# Exporte und Wechsel zu anderer Software

steuy soll niemanden festhalten. Drei Exporte, alle im Menü *Auswertung* bzw. unter *Einstellungen → Firmendaten*:

| Export | Inhalt | Für wen |
|---|---|---|
| Export für Steuerberatung (je Jahr) | EÜR als PDF/CSV, alle Zahlungen, Rechnungs-PDFs, Belege mit SHA-256 | Steuerberatung, Betriebsprüfung |
| Wechsel-Export | DATEV-Buchungsstapel je Jahr, Kunden, Lieferanten, Artikel als CSV | Umzug zu Lexware Office, sevDesk, DATEV u. a. |
| Gesamtexport | Alle Tabellen als CSV und alle Dateien der Ablage | Vollständige Sicherung, eigene Auswertungen |

## DATEV-Buchungsstapel

Format „EXTF“ Version 700, Datenkategorie 21 (Buchungsstapel), Formatversion 13. Windows-1252, Semikolon, CRLF, Beträge mit Dezimalkomma ohne Vorzeichen plus Soll/Haben-Kennzeichen, Belegdatum als TTMM. Ein Stapel enthält genau ein Wirtschaftsjahr (Kalenderjahr).

- Jede **Zahlung** wird eine Buchung (Zuflussprinzip, wie die EÜR). Datum = Zahlungsdatum.
- Einnahme: Soll Geldkonto an Erlöskonto. Ausgabe: Soll Aufwandskonto an Geldkonto.
- Gegenbuchungen (Storno) haben dieselben Konten mit umgekehrtem Soll/Haben.
- Geldkonto: Kasse bei Zahlungsart „bar“, sonst Bank (auch PayPal und Karte).
- Privatanteil einer Ausgabe geht als eigene Buchung auf das Privatkonto, damit das Geldkonto zum tatsächlichen Abfluss passt. Der betriebliche Teil wird wie in der EÜR abgerundet, der Rest ist privat.
- Zahlungsgebühren sind eigene Ausgaben (Kategorie „Gebühren“), der Zahlungseingang einer Rechnung bleibt in voller Höhe.

### Kontenvorschläge

**Vorschläge, nicht geprüft.** Sie folgen den üblichen DATEV-Standardkontenrahmen und müssen vor dem Import von der Steuerberatung oder in der Zielsoftware geprüft werden. Die Tabelle steht in `app/domain/datev.py`.

| Kategorie | SKR03 | SKR04 |
|---|---|---|
| Rechnungen, Umsatzerlöse (Kleinunternehmer § 19) | 8195 | 4185 |
| Sonstige Einnahmen | 2700 | 4830 |
| Waren und Material | 3200 | 5200 |
| Fremdleistungen | 3100 | 5900 |
| Büromaterial | 4930 | 6815 |
| Software und Abos | 4964 | 6837 |
| Telefon und Internet | 4920 | 6805 |
| Werbung | 4600 | 6600 |
| Reisekosten | 4670 | 6670 |
| Fahrzeugkosten | 4500 | 6500 |
| Fortbildung | 4945 | 6821 |
| Miete und Raumkosten | 4210 | 6310 |
| Versicherungen und Beiträge | 4360 | 6400 |
| Gebühren | 4970 | 6855 |
| Geringwertige Anschaffungen | 4855 | 6260 |
| Sonstige Ausgaben, eigene Kategorien | 4900 | 6300 |
| Bank / Kasse / Privatentnahmen | 1200 / 1000 / 1800 | 1800 / 1600 / 2100 |

## Stammdaten (Kunden, Lieferanten, Artikel)

CSV in UTF-8 mit BOM, Semikolon, deutsche Spaltennamen. Kunden und Lieferanten getrennt, weil z. B. Lexware Office sie getrennt importiert. Die Zuordnung der Spalten erfolgt im Importdialog der Zielsoftware. Archivierte Einträge sind enthalten und markiert.

## Offene Fragen (Steuerberatung)

- Passen die Kontenvorschläge, insbesondere „Software und Abos“ (Lizenzen vs. EDV-Kosten) und „Geringwertige Anschaffungen“?
- Soll PayPal ein eigenes Geldkonto (z. B. Geldtransit) bekommen statt der Bank?
- Reicht ein Buchungsstapel ohne Debitoren/Kreditoren (Personenkonten), oder werden Personenkonten erwartet?
