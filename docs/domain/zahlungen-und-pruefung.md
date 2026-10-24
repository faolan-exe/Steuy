# Zahlungen, „Zu prüfen“ und Erinnerungen

Fachlich geklärt mit Philipp am 2026-10-21. Gilt allgemein, nicht nur für unsere eigenen Gewerbe.

## Zahlungen erfassen

- Version 1 hat **keine Bankanbindung**. Geld geht auf dem Konto ein, danach wird der Beleg von Hand als bezahlt markiert.
- Pflichtangaben beim Markieren: **bezahlt am** (Datum), **Betrag**, **Zahlungsart**.
- Zahlungsarten: Überweisung, PayPal, Kartenzahlung, Bar, Sonstige. Die Liste ist erweiterbar.
- Teilzahlungen: mehrere Zahlungen je Beleg. Bis zum vollen Betrag ist der Status „teilbezahlt“.
- Das Zahlungsdatum bestimmt das EÜR-Jahr (siehe `euer.md`).

## Bargeld

- Kein Kassenbuch in Version 1. „Bar“ ist nur eine Zahlungsart.
- Begründung: Barzahlungen sind bei der Zielgruppe selten. Werden sie häufiger, kommt ein Kassenbuch als eigenes Feature.

## Zahlungsgebühren (PayPal, Karte, Stripe, …)

- Die Einnahme wird immer in voller Rechnungshöhe gebucht, die Gebühr als eigene Ausgabe. Nie nur den angekommenen Betrag buchen.
- Beim Markieren als bezahlt kann der **tatsächlich angekommene Betrag** angegeben werden. Ist er kleiner als der Rechnungsbetrag, landet der Beleg in „Zu prüfen“ mit dem Hinweis „Gebühr noch nicht erfasst“.
- Gebühren werden **gesammelt** eingetragen, z. B. einmal im Monat aus der Abrechnung des Zahlungsanbieters, und mit den offenen Fällen verknüpft. Danach verschwinden sie aus „Zu prüfen“.

## Ordner „Zu prüfen“

Eine Sammelansicht für alles, was noch eine Entscheidung braucht:

| Was | Verschwindet, wenn |
|---|---|
| Ausgangsrechnung nicht bezahlt | als bezahlt markiert oder storniert |
| Angebot offen | angenommen oder abgelehnt |
| Ausgabe-Beleg nicht bezahlt | als bezahlt markiert oder storniert |
| Zahlung mit offener Gebühr | Gebühr erfasst und verknüpft |
| Shop-Rechnung wartet auf Freigabe | freigegeben und verschickt (siehe `woocommerce.md`) |
| Zahlung rund um den Jahreswechsel | Jahr bestätigt (siehe `euer.md`) |
| Hochgeladener Beleg ohne Buchung | verbucht oder gelöscht (siehe ADR 0006) |

## Erinnerungen

- **Wöchentlich** (montags) eine E-Mail mit dem Inhalt von „Zu prüfen“, wenn dort etwas liegt. Geht an alle mit Arbeitsrechten (Zahlungen, Buchen, Belege oder Rechnungen versenden), pro Person im Profil abschaltbar.
- Dieselbe Übersicht erscheint im Dashboard.

## Gemeinsame Ausgaben mehrerer Gewerbe

- Jedes Gewerbe hat eine eigene Installation (ADR 0007). Eine Ausgabe wird nie aufgeteilt.
- Wer sich Kosten mit einem anderen Gewerbe teilt, regelt das untereinander und bucht die Ausgabe nur in einem Gewerbe.

## Steuerberater

- Version 1: **Export als ZIP** je Jahr mit EÜR (PDF und CSV), allen Buchungen (CSV) und allen Belegen im Original.
- Zusätzlich kann ein Nutzer mit der Rolle **Steuerberater** angelegt werden (siehe `rollen.md`).

## Datenübernahme

- Version 1 soll Daten aus **Lexware Office (lexoffice)** und allgemein per **CSV** übernehmen können: Kontakte, Artikel, offene Rechnungen.
- Der Rechnungsnummernkreis muss an einer bestehenden Nummer weitermachen können (z. B. nächste Nummer `RE0131`).

## Offen / zu prüfen

- [ ] Welche Exportformate bietet Lexware Office genau (Kontakte, Artikel, Belege, Belegdateien)? Vor Umsetzung an einem echten Export prüfen, Testdaten anonymisieren.
- [ ] Sollen abgeschlossene Rechnungen aus dem Altsystem nur als PDF-Archiv übernommen werden oder auch als Buchungen?
- [x] Sichtbarkeit zwischen Nutzern: geregelt über Rollen mit einstellbaren Rechten, siehe `rollen.md`.
