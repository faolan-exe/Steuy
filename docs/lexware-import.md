# Von Lexware nach steuy umziehen: Buchhaltungsdaten importieren

Diese Anleitung sagt, welche Dateien du in Lexware exportierst und was steuy daraus macht. Alles läuft in deiner eigenen Installation. Die Exporte enthalten Geschäftsdaten: Lade sie nur dort hoch, nie in ein öffentliches Forum oder Issue.

In Lexware: **Export** (Menü links). Wähle oben **Individueller Zeitraum** und exportiere **ein Jahr nach dem anderen** (01.01. bis 31.12.). Exportiere nur abgeschlossene Monate.

## Was du exportierst

| Reihenfolge | Export in Lexware | Dateiname (Beispiel) | In steuy |
|---|---|---|---|
| 1 | **Anwenderdaten**: Kontakte (Link unten auf der Export-Seite) | Kontakte als CSV | *Importieren → Kontakte*: Kunden und Lieferanten mit Adresse, E-Mail, Nummer |
| 2 | **Belege/Belegbilder mit Buchungsvorschlag (DATEV-Format)** | `DATEV-Export_Belegbilder_mit_Belegdaten_von_…zip` | *Importieren → Belegarchiv*: alle Rechnungen und Eingangsbelege mit PDF als Buchungen, Stornos erkannt |
| 3 | **Listen im CSV-Format exportieren** | `CSV-Export_Belege_von_…zip` (mit `Export_RE` und `Export_RA`) | Zahlungsdaten („bezahlt am“) von Ausgaben und Einnahmen, zusammen mit Schritt 2 hochladen |
| 4 | **Kontoumsätze der Geschäftskonten** (Girokonten, PayPal) | Kontoumsätze je Konto | Zahlungsdatum je Rechnung, siehe unten |
| 5 | **Anwenderdaten**: Produkte/Services | Artikel als CSV | *Importieren → Artikel* |

Nicht nötig: „Belege (alle Belege zum Archivieren)“ (die PDFs stecken schon in Export 2), die Betriebsprüfungs-Exporte (Z3, euBP) und der Anlagenspiegel. Der Anlagenspiegel hilft nur, wenn du Anschaffungen über mehrere Jahre abschreibst: Dann zusätzlich mit exportieren, steuy legt Anlagegüter bisher von Hand an.

## Wer wurde schon bezahlt?

Der DATEV-Export der Belege (2) enthält **kein Zahlungsdatum**, nur Rechnungsdatum und Fälligkeit. Alle Buchungen kommen deshalb als **offen** herein und erscheinen unter „Zu prüfen“. Für die EÜR zählt aber das Zahlungsdatum (Zuflussprinzip), steuy rät es nicht.

Wo Lexware das Zahlungsdatum liefert:

- **Listen im CSV-Format** (3): Das ZIP enthält `Export_RE…csv` (Eingangsrechnungen) und `Export_RA…csv` (Ausgangsrechnungen), jeweils mit „bezahlt am“. Steuy trägt daraus die Zahlungen ein (Abgleich über Rechnungsnummer, Datum und Betrag, notfalls nur Datum und Betrag). Wichtig: Das ZIP muss beide Dateien enthalten, sonst fehlen die Einnahmen.
- **Kontoumsätze** (4): Auf dem Konto steht, wann Geld geflossen ist.

Zahlungsart ist „Sonstige“. Die Liste der Ausgangsrechnungen führt nur bezahlte Rechnungen: Was fehlt, bleibt offen. Der Abgleich mit den **Kontoumsätzen** ist nicht eingebaut und nur nötig, wenn Rechnungen in den Listen fehlen.

## Ablauf in steuy

1. Kontakte importieren (optional, sonst legt der Belegimport sie mit Name, Ort und USt-IdNr. an).
2. *Importieren → Belegarchiv importieren*, ZIP-Dateien wählen, **Vorschau** ansehen, dann **Jetzt importieren**. Doppelte Belege (z. B. Jahres- und Monatsexport) überspringt steuy.
3. Unter „Zu prüfen“: Entwürfe kategorisieren (steuy rät bei Bewirtung, Werkzeugen, Software und Anschaffungen nicht), Zahlungen erfassen.
4. Rechnungsnummern: Unter *Einstellungen → Rechnungen* die nächste freie Nummer eintragen, z. B. 131 für RE0131.

Was steuy beim Belegimport entscheidet, steht in [domain/import-lexware.md](domain/import-lexware.md).
