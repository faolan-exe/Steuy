# Ziel und Umfang

## Wofür

Ein kostenloses, öffentliches, quelloffenes Tool, mit dem Kleinunternehmer nach § 19 UStG ihre Buchhaltung selbst führen: Belege ablegen, Rechnungen und Angebote schreiben, Zahlungen verfolgen, eine EÜR erstellen. Die Werte der Anlage EÜR werden von Hand in ELSTER übertragen. → ADR 0005

**Für wen:** Einzelunternehmen und Freiberufler mit Kleinunternehmerregelung, die ihren Gewinn per EÜR ermitteln. Vor allem Einsteiger ohne Buchhaltungskenntnisse. Das Tool muss ohne Fachwissen bedienbar sein und Begriffe erklären.

**Betrieb:** Self-Hosting per Docker Compose. Eine Installation enthält genau ein Gewerbe. Wer mehrere Gewerbe hat, betreibt mehrere Installationen. → ADR 0007. Unsere eigenen zwei Gewerbe sind die ersten Nutzer, mit je einer Installation.

**Haftung:** Nutzung auf eigene Gefahr, keine Steuerberatung.

## Version 1 (MVP)

1. **Einrichtung:** Einrichtungsassistent beim ersten Start (Gewerbe, Kleinunternehmer-Prüfung, Bankverbindung für Rechnungen, Rechnungslayout). Login und Nutzerverwaltung mit den Rollen Admin, Buchhalter, Mitarbeiter und Steuerberater, deren Rechte der Admin einstellen kann (siehe `domain/rollen.md`).
2. **Kontakte:** Kunden und Lieferanten mit Adresse, Kontaktdaten, Kunden- bzw. Lieferantennummer.
3. **Buchungen:** Einnahmen und Ausgaben erfassen, Kategorie zuordnen, als Entwurf speichern, festschreiben, stornieren.
4. **Belege:** PDF, Bild oder E-Rechnung (XRechnung/ZUGFeRD) hochladen, an Buchung hängen, unveränderlich ablegen. **Texterkennung direkt beim Erfassen:** Das Tool liest Lieferant, Belegdatum, Rechnungsnummer und Betrag aus und füllt die Felder vor. Bei E-Rechnungen kommen die Werte direkt aus dem XML. Der Nutzer prüft und bestätigt, bis dahin liegt der Beleg in „Zu prüfen“. Die Erkennung läuft lokal, Belege verlassen den Server nicht.
5. **Ausgangsrechnungen:** Rechnung mit fortlaufender Nummer, § 19-Hinweis, PDF-Export mit **QR-Code für Überweisungen** (GiroCode/EPC). Rechnungskorrektur bzw. Storno statt Ändern.
6. **Angebote:** Angebot schreiben, als PDF ausgeben und mit einem Klick in eine Rechnung umwandeln.
7. **Zahlungen:** Rechnungen und Ausgaben als bezahlt markieren mit **Zahlungsdatum**, Betrag und Zahlungsart. Teilzahlungen. Der Zahlungseingang erzeugt die Einnahme-Buchung.
8. **Mahnwesen:** Überfällige Rechnungen werden angezeigt. Das Tool erinnert an fällige Zahlungserinnerungen und Mahnungen (Stufen und Abstände einstellbar) und erzeugt sie mit erneutem QR-Code über den offenen Betrag. Mahnsperre je Rechnung oder Kontakt.
9. **WooCommerce-Import:** bezahlte Bestellungen und Erstattungen eines Shops als Buchungsentwürfe importieren, ohne Duplikate (siehe `domain/woocommerce.md`). Optional: Wer keinen Shop hat, schreibt seine Rechnungen nur im Tool.
10. **EÜR-Auswertung:** Summen je Kategorie für ein Kalenderjahr, zugeordnet zu den Zeilen der Anlage EÜR, als Bildschirmansicht, PDF und CSV.
11. **Umsatzgrenze:** Anzeige des Jahresumsatzes gegen die Kleinunternehmergrenzen, Warnung vor Erreichen.
12. **Änderungsprotokoll:** wer hat wann was angelegt, festgeschrieben, storniert.
13. **Datensicherung:** Export aller Daten und Belege, dokumentierte Sicherung und Wiederherstellung.

## Später (Version 2 und folgende)

Reihenfolge noch offen.

- **Kontoauszüge importieren:** CSV, CAMT.053, MT940, mit Vorschlägen zur Zuordnung von Umsätzen zu Rechnungen und Belegen
- **Kontoabruf per FinTS** für deutsche Banken (Produktregistrierung bei der Deutschen Kreditwirtschaft klären). PSD2-Anbieter für Neobanken höchstens als optionale Erweiterung.
- Belegfoto vom Handy, Kategorie-Vorschlag aus früheren Belegen desselben Lieferanten
- Wiederkehrende Rechnungen und Ausgaben
- Verzugszinsen und Pauschale bei Mahnungen an Firmen
- Anlagegüter und Abschreibungen (siehe `domain/euer.md`)
- Leistungen aus dem Ausland nach § 13b UStG erkennen und darauf hinweisen
- Export für Steuerberater (DATEV), GoBD-Datenexport
- Eigene Rechnungen zusätzlich als E-Rechnung (ZUGFeRD/XRechnung)
- Auftragsbestätigungen, Lieferscheine

## Ausdrücklich nicht geplant

- Regelbesteuerung: Umsatzsteuer, Vorsteuer, UStVA. Wer die Grenze überschreitet, bekommt eine Warnung und einen vollständigen Export.
- Gesellschaften (GbR, UG, GmbH), Bilanzierung, Lohnbuchhaltung
- Lager und Warenwirtschaft, Zeiterfassung
- ELSTER-Übermittlung (ERiC)
- Gehosteter Dienst für Dritte, Mobile App

Neue Funktionen kommen erst ins Tool, wenn sie hier unter Version 1 oder „Später“ stehen.

## Offene Fragen

- [ ] Anlagegüter und AfA schon in Version 1 oder erst später? (Siehe `domain/euer.md`.)
- [ ] Wo läuft unsere eigene Installation produktiv (Homelab), wie werden DB und Belege gesichert?
- [ ] Welche Zahlungsanbieter laufen über WooCommerce (Stripe, PayPal, …)? Davon hängt der Gebühren-Import ab.
- [x] Lizenz: PolyForm Shield 1.0.0 (Nutzung im Gewerbe erlaubt, kein Verkauf als Konkurrenzprodukt)
- [ ] Ab wann wird das Repository öffentlich? (Voraussetzungen siehe ADR 0005, „Folgen“)
- [ ] Wer prüft die Fachregeln vor dem ersten Release (Steuerberatung)?
