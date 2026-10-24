# 0005: Öffentliches Open-Source-Projekt für alle Kleinunternehmer

- Status: angenommen
- Datum: 2026-10-21

## Kontext

Bisher war das Tool für genau zwei Gewerbe gedacht, ausdrücklich „kein Produkt für Dritte“ (`docs/ziel.md`, Stand 2026-10-19).

Viele Gründer und Kleinunternehmer nach § 19 UStG zahlen für Buchhaltungssoftware, obwohl sie nur wenige Funktionen brauchen. Dazu gehören Belege ablegen, Rechnungen schreiben, Zahlungen verfolgen und eine EÜR erstellen. Freie Alternativen sind entweder international ausgerichtet und kennen keine EÜR, oder sie sind für Einsteiger zu komplex.

Die bisherigen Grundsatzentscheidungen eignen sich für ein öffentliches Projekt genauso: Integer-Cent (0001), append-only Buchungen (0002) und Jinja/HTMX ohne Build-Schritt (0004). Die getrennten Buchungskreise (0003) werden durch ein Gewerbe pro Installation ersetzt (0007).

## Entscheidung

- Das Tool wird von Anfang an als **öffentliches, kostenloses, quelloffenes Projekt** entwickelt. Das Repository wird öffentlich, sobald die Punkte unter „Folgen“ erledigt sind.
- **Zielgruppe:** Einzelunternehmen und Freiberufler mit Kleinunternehmerregelung nach § 19 UStG, die ihren Gewinn per EÜR ermitteln. Besonders Einsteiger ohne Buchhaltungskenntnisse.
- **Bewusst nicht abgedeckt:** Regelbesteuerung (Umsatzsteuer, Vorsteuer, UStVA), Gesellschaften (GbR, UG, GmbH), Bilanzierung, Lohn, Warenwirtschaft. Wer die Kleinunternehmergrenze überschreitet, bekommt eine Warnung und einen vollständigen Export, aber keine Regelbesteuerung im Tool.
- **Betrieb:** Self-Hosting. Jedes Gewerbe bekommt eine eigene Installation (ADR 0007). Mehrere Personen arbeiten über Nutzerrollen im selben System. Ein gehosteter Mehrmandanten-Dienst ist nicht geplant.
- **Unsere eigenen Gewerbe** sind die ersten Nutzer, mit je einer eigenen Installation. Einnahmen kommen auf zwei Wegen ins Tool: über selbst geschriebene Rechnungen und über den WooCommerce-Import. Beides gehört zu Version 1. Der Import ist optional, denn nicht jedes Gewerbe hat einen Shop.
- **Haftung:** Nutzung auf eigene Gefahr. Das Tool ersetzt keine Steuerberatung. Der Hinweis steht in README, Lizenz und Einrichtungsassistent.

## Verworfene Alternativen

- **Privat bleiben, später veröffentlichen:** Spätere Veröffentlichung heißt, Doku, Commit-Historie, Konfiguration und Testdaten nachträglich auf persönliche Daten zu prüfen. Annahmen über „genau zwei Nutzer“ wandern unbemerkt in den Code.
- **Bestehendes Projekt forken** (Invoice Ninja, Akaunting, ERPNext): Keines bringt EÜR, deutsche Belegbuchhaltung und Einsteigerfreundlichkeit zusammen. Teils passt die Lizenz nicht, teils ist der Umfang viel zu groß.
- **Gehosteter Dienst für alle:** Betrieb, Haftung, Datenschutz und Kosten sind für ein Hobbyprojekt nicht tragbar.

## Folgen

- **Lizenz:** PolyForm Shield 1.0.0. Sie erlaubt die Nutzung im eigenen Gewerbe sowie Änderungen und verbietet, steuy als konkurrierendes Produkt oder Dienst anzubieten. Es ist keine Open-Source-Lizenz im Sinn der OSI.
- **Keine persönlichen Daten im Repo:** keine echten Kunden, Belege, Shop-Zugänge oder Screenshots mit Kundendaten, auch nicht in Tests oder Issues. Testdaten nur erfunden.
- **Einrichtung für Laien:** Docker Compose mit einem Befehl, Einrichtungsassistent beim ersten Start, verständliche Doku auf Deutsch.
- **Fachregeln mit Jahresbezug** (Umsatzgrenzen, Zeilen der Anlage EÜR, Basiszinssatz) liegen versioniert als Daten vor, damit Gesetzesänderungen ohne Codeänderung nachgezogen werden können. Das gilt laut `docs/domain/euer.md` schon jetzt.
- **Umfang wächst:** Angebote und Mahnwesen rücken in Version 1, da fast jedes Kleinunternehmen sie braucht (siehe `docs/ziel.md`). Das MVP wird dadurch größer.
- **Mitarbeit Dritter:** `CONTRIBUTING.md`, Issue-Vorlagen und CI werden vor der Veröffentlichung für externe Beitragende fertig gemacht.
- **Sicherheit:** Da Fremde das Tool betreiben, braucht es eine `SECURITY.md` mit Meldeweg sowie sichere Standardeinstellungen (Login, Backups, keine offenen Ports außer der App).
- **Fachliche Prüfung:** Vor dem ersten Release sollte eine Steuerberaterin oder ein Steuerberater die Fachregeln in `docs/domain/` gegenlesen.
