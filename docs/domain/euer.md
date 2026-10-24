# EÜR-Regeln

## Zuflussprinzip (§ 11 EStG)

- Einnahmen zählen in dem Jahr, in dem das Geld eingeht. Ausgaben in dem Jahr, in dem sie bezahlt werden.
- Maßgeblich ist `buchung.zahlungsdatum`. Bestell- und Rechnungsdatum sind nur Information.
- **Ausnahme zum Jahreswechsel:** regelmäßig wiederkehrende Zahlungen (z. B. Miete, Abos), die bis zu 10 Tage vor oder nach dem 31.12. fällig und gezahlt werden, gehören in das Jahr, zu dem sie wirtschaftlich gehören. → Feld `wirtschaftliches_jahr` oder Kennzeichen „wiederkehrend“ nötig. Details vor Umsetzung prüfen.
- **Verhalten im Tool** (geklärt mit Philipp, 2026-10-21): Das Tool erkennt mögliche Fälle selbst, z. B. eine Zahlung zwischen 22.12. und 10.01. bei einem Kontakt mit regelmäßigen Zahlungen. Der Fall landet in „Zu prüfen“ mit der Frage „Gehört diese Zahlung noch zu <Jahr>?“. Erst die Bestätigung setzt das wirtschaftliche Jahr.
- **Umsetzung:** Kandidat ist eine Zahlung zu einer Buchung zwischen 22.12. und 10.01., wenn es beim selben Kontakt (ohne Kontakt: gleicher Partnername) mindestens zwei frühere festgeschriebene Buchungen gleicher Art in den 400 Tagen davor gibt. Die Kriterien sind bewusst großzügig, weil jeder Fall bestätigt wird. Die Entscheidung steht unveränderlich in `jahreszuordnung`, die Zahlung selbst bleibt unverändert. Ein Storno folgt der Zuordnung der ursprünglichen Zahlung. Ausgangsrechnungen sind nicht betroffen.

## Kleinunternehmer (§ 19 UStG), Stand ab 2025

- Grenzen: Gesamtumsatz im **Vorjahr höchstens 25.000 €** und im **laufenden Jahr höchstens 100.000 €**.
- Wird die 100.000 € im laufenden Jahr überschritten, endet der Status **sofort** mit dem überschreitenden Umsatz, nicht erst zum Jahresende.
- Folge fürs Tool: Umsatz laufend summieren, Warnstufen vor 25.000 € (wirkt aufs Folgejahr) und vor 100.000 € (wirkt sofort). Die Grenzwerte als Konfiguration je Jahr, nicht als Konstante im Code.
- Rechnungen ohne Umsatzsteuer und mit Hinweis, etwa: „Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.“ Wer trotzdem Umsatzsteuer ausweist, schuldet sie (§ 14c UStG).
- Ausgaben werden brutto gebucht, da kein Vorsteuerabzug.

## E-Rechnung

- Seit 2025 müssen auch Kleinunternehmer E-Rechnungen **empfangen** können.
- Eigene Rechnungen als E-Rechnung **ausstellen** müssen Kleinunternehmer nicht.
- Fürs Tool: Upload von XRechnung/ZUGFeRD als Beleg, XML im Original speichern, Lesbarkeit (Betrag, Datum, Absender) ist ein späteres Komfortfeature.

## Anlage EÜR

- Kategorien werden Zeilen der Anlage EÜR zugeordnet. Die Zeilennummern ändern sich von Jahr zu Jahr, deshalb Zuordnung **je Steuerjahr** in einer Tabelle, nicht im Code.
- Zeilennummern jedes Jahr aus dem aktuellen Formular übernehmen, nicht aus dem Gedächtnis.
- Für Jahre ohne geprüfte Zuordnung nutzt die Auswertung den nächstälteren Vordruck und zeigt einen deutlichen Hinweis.

### Zuordnung 2025

Quelle: amtlicher Vordruck Anlage EÜR 2025 (BMF-Schreiben vom 29.08.2025, IV C 6 - S 2142/00023/010/001). Gegengeprüft mit der ELSTER-Anleitung zur EÜR 2025 (Zeilen 12, 29, 30, 36, 44, 55–60) und Haufe (Zeile 45 Fortbildung, Zeile 46 Rechts- und Steuerberatung).

| Kategorie in steuy | Zeile | Kz | Bezeichnung im Vordruck |
|---|---|---|---|
| Zahlungen zu Ausgangsrechnungen, Umsatzerlöse, Sonstige Einnahmen | 12 | 111 | Betriebseinnahmen als umsatzsteuerlicher Kleinunternehmer |
| Waren und Material | 27 | 100 | Waren, Rohstoffe und Hilfsstoffe |
| Fremdleistungen | 29 | 110 | Bezogene Fremdleistungen |
| Geringwertige Anschaffungen | 36 | 132 | Aufwendungen für geringwertige Wirtschaftsgüter |
| Miete und Raumkosten | 39 | 150 | Miete/Pacht für Geschäftsräume |
| Telefon und Internet | 43 | 280 | Aufwendungen für Telekommunikation |
| Reisekosten | 44 | 221 | Übernachtungs- und Reisenebenkosten bei Geschäftsreisen |
| Fortbildung | 45 | 281 | Fortbildungskosten (ohne Reisekosten) |
| Versicherungen und Beiträge | 49 | 223 | Beiträge, Gebühren, Abgaben und Versicherungen |
| Software und Abos | 50 | 228 | Laufende EDV-Kosten |
| Büromaterial | 51 | 229 | Arbeitsmittel (z. B. Bürobedarf, Porto, Fachliteratur) |
| Werbung | 54 | 224 | Werbekosten |
| Gebühren (Bank, PayPal, Karte), Sonstige Ausgaben | 60 | 183 | Übrige unbeschränkt abziehbare Betriebsausgaben |
| Fahrzeugkosten | 70 | 146 | Sonstige tatsächliche Fahrtkosten (betriebliches Fahrzeug) |

Summen: Zeile 23 (Kz 159) Betriebseinnahmen, Zeile 75 (Kz 199) Betriebsausgaben, Gewinn aus Zeile 76 abzüglich 77.

AfA (seit Anlagegütern): Zeile 32 (Kz 131) immaterielle, Zeile 33 (Kz 130) bewegliche Wirtschaftsgüter.

### Zuordnung 2026

Quelle: amtlicher Vordruck Anlage EÜR 2026 (BMF-Schreiben vom 01.09.2026), Formularseiten im Layout ausgelesen und mit den Zeilenverweisen der Anleitung abgeglichen.

Neu ist Zeile 27 „Bildung Rücklage Tierbewertung bei Land- und Forstwirten“. Dadurch liegen alle Ausgabenzeilen ab „Waren“ **eine Zeile tiefer** als 2025. Die Kennzahlen sind gleich geblieben, die Einnahmenseite (Zeile 12) auch.

| Kategorie in steuy | Zeile | Kz |
|---|---|---|
| Zahlungen zu Ausgangsrechnungen, Umsatzerlöse, Sonstige Einnahmen | 12 | 111 |
| Waren und Material | 29 | 100 |
| Fremdleistungen | 30 | 110 |
| AfA immaterielle / bewegliche Wirtschaftsgüter | 33 / 34 | 131 / 130 |
| Geringwertige Anschaffungen | 37 | 132 |
| Miete und Raumkosten | 40 | 150 |
| Telefon und Internet | 44 | 280 |
| Reisekosten | 45 | 221 |
| Fortbildung | 46 | 281 |
| Versicherungen und Beiträge | 50 | 223 |
| Software und Abos | 51 | 228 |
| Büromaterial | 52 | 229 |
| Werbung | 55 | 224 |
| Gebühren, Sonstige Ausgaben | 61 | 183 |
| Fahrzeugkosten | 71 | 146 |

Summen: Zeile 23 (Kz 159) Betriebseinnahmen, Zeile 76 (Kz 199) Betriebsausgaben, Gewinn aus Zeile 77 abzüglich 78.

## Anschaffungen und Abschreibung (Version 1)

Geklärt mit Philipp am 2026-10-21. Die Kleinunternehmerregelung betrifft nur die Umsatzsteuer, für Abschreibungen gelten die allgemeinen Regeln.

- **Geringwertige Wirtschaftsgüter:** bis 800 € netto sofort voll als Ausgabe. Nach unserem Kenntnisstand (R 6.13 EStR) wird auch bei Kleinunternehmern gegen den Nettobetrag geprüft, also bis 952 € brutto bei 19 %. Gebucht wird der Bruttobetrag.
- **Computerhardware und Software:** Nutzungsdauer 1 Jahr (BMF-Schreiben vom 22.02.2022). Dadurch fällt der volle Betrag im Anschaffungsjahr an, auch über der GWG-Grenze.
- **Alle anderen Anschaffungen über der GWG-Grenze:** lineare Abschreibung über die Nutzungsdauer laut amtlicher AfA-Tabelle, im Anschaffungsjahr zeitanteilig nach Monaten.
- **Ablauf im Tool:** Bei einer Ausgabe über der Grenze fragt das Tool „Ist das ein Computer oder Software?“. Bei Ja wird sofort voll gebucht. Bei Nein wird ein Anlagegut mit Nutzungsdauer angelegt (Vorschlag aus Tabelle, änderbar) und der Abschreibungsplan erzeugt.
- Grenzwerte und Nutzungsdauern als Daten je Jahr, nicht im Code.

### Umsetzung

- Tabellen `afa_vorgabe` (GWG-Grenze netto je Steuerjahr, 800 € seit 2018), `nutzungsdauer` (Vorschläge aus der AfA-Tabelle AV, änderbar) und `anlagegut` (unveränderlich, Korrektur über Storno der Buchung).
- Nachfrage nach dem Festschreiben, wenn eine „Geringwertige Anschaffung“ mehr als 952 € (800 € + 19 %) kostet. Jede festgeschriebene Ausgabe lässt sich auch nachträglich als Anlagegut abschreiben.
- EÜR: Die Zahlung für ein Anlagegut zählt nicht in ihrer Kategorie. Stattdessen erscheint die AfA des Jahres in **Zeile 33, Kz 130** (bewegliche Wirtschaftsgüter inkl. Computerhardware) bzw. **Zeile 32, Kz 131** (immaterielle Wirtschaftsgüter inkl. Software). Maßgeblich ist das Anschaffungsdatum, nicht das Zahlungsdatum.
- Lineare AfA in ganzen Cent: kumuliert je Monat abgerundet, die Summe ergibt exakt die Anschaffungskosten. Der Anschaffungsmonat zählt voll.
- Anlagenverzeichnis je Jahr (Auswertung → Anlagen) mit AfA und Restwert als Grundlage für die Anlage AVEÜR.

## Privatanteil (Version 1)

Geklärt mit Philipp am 2026-10-21.

- Auch bei Kleinunternehmern muss die EÜR Betriebliches und Privates trennen.
- Jede Ausgabe hat das Feld **„betrieblicher Anteil“** in Prozent, Standard 100 %. In der EÜR zählt nur der betriebliche Anteil. Der Beleg bleibt in voller Höhe gespeichert.
- Private Kfz-Nutzung und Warenentnahmen für den Eigenbedarf sind **nicht** in Version 1.

## Gemeinsame Ausgaben

Eine Ausgabe gehört immer genau einem Gewerbe, es gibt kein Aufteilen. Siehe `zahlungen-und-pruefung.md`.

## Offen / zu prüfen

- [ ] Sammelposten (250 € bis 1.000 €) als Alternative zur GWG-Regel anbieten? Erst nach Rücksprache mit Steuerberatung.
- [ ] Anlagegüter mit privater Mitnutzung (z. B. Laptop 70 % betrieblich): Betriebsvermögen oder nicht, wie AfA und Privatanteil? Bis zur Klärung lässt steuy das nicht zu.
- [ ] Verkauf oder Entnahme eines Anlageguts (Erlös Zeile 19, Restbuchwert Kz 135): spätere Version.
- [ ] Nutzungsdauern in der Tabelle `nutzungsdauer` gegen die aktuelle AfA-Tabelle prüfen lassen.
- [ ] Regeln zu GWG-Grenze (netto/brutto bei Kleinunternehmern), Nutzungsdauern und zeitanteiliger AfA vor dem Release von Steuerberatung prüfen lassen.
- [ ] Private Kfz-Nutzung (1-%-Regelung, Fahrtenbuch) und Sachentnahmen: spätere Version
- [ ] Zuordnung 2025 von Steuerberatung prüfen lassen, besonders: Software-Abos in Zeile 50 (EDV-Kosten), Bank- und PayPal-Gebühren in Zeile 60, Fahrzeugkosten in Zeile 70 (nur für Fahrzeuge im Betriebsvermögen; Privatfahrzeug → Zeile 71), Reisekosten in Zeile 44 (Fahrtkosten mit öffentlichen Verkehrsmitteln gehören in Zeile 70, Verpflegung in Zeile 64)
- [x] Zuordnung für 2026 aus dem Vordruck 2026 (BMF 01.09.2026) als Daten ergänzt
- [ ] Zuordnung 2026 zusammen mit 2025 von Steuerberatung prüfen lassen
- [ ] Kleinunternehmergrenze: Das Dashboard misst den Umsatz vorerst an den Zahlungseingängen des Jahres. Prüfen, ob für § 19 die vereinnahmten oder die vereinbarten Entgelte maßgeblich sind, und ob im Gründungsjahr eine eigene Grenze gilt.
- [x] Erkennung „regelmäßig wiederkehrend“ zum Jahreswechsel: großzügige Kriterien, Entscheidung durch den Nutzer (siehe oben)
- [ ] Jahreswechsel: Sollen auch Zahlungen zu Ausgangsrechnungen (z. B. monatliche Wartungsverträge) erkannt werden?
