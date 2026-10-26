# Roadmap: was steuy kann und was als Nächstes kommt

steuy ist in der **Beta**. Es wird aktiv weiterentwickelt, Datenmodell und Abläufe können sich ändern. Beim Update per Klick macht steuy vorher eine Sicherung. Trotzdem gilt: Lege Sicherungen auf ein zweites Gerät und prüfe die Werte der Anlage EÜR vor der Abgabe selbst oder mit deiner Steuerberatung. Die Reihenfolge unten ist ein Plan, keine Zusage.

## Schon da (Version 0.6)

- Angebote, Rechnungen, Lieferscheine, Rechnungskorrekturen und Storno, PDF/A, E-Mail-Versand, QR-Code für die Überweisung, eigenes Drucklayout
- Zahlungen und Teilzahlungen, Mahnwesen von Hand oder automatisch
- Belege mit Texterkennung, Scan-Eingang vom Scanner mit eingebauter Netzwerkfreigabe
- EÜR nach Zuflussprinzip, Dashboard, Anlagegüter mit Abschreibung
- Umzug von Lexware (DATEV-Archiv und Zahlungslisten), WooCommerce-Import
- Rollen und Rechte, Zwei-Faktor-Anmeldung, unveränderliche Buchungen (GoBD)
- Updates per Klick, Sicherungsskript, Exporte (Jahresexport mit Prüfsummen, Wechsel-Export, Gesamtexport)

## Als Nächstes (in dieser Reihenfolge)

1. **Wiederkehrende Rechnungen** für Abos und Dauerkunden
2. **Anmeldung per Passkey** (WebAuthn) zusätzlich zu Passwort und Zwei-Faktor
3. **E-Rechnung erzeugen** (ZUGFeRD und XRechnung) für eigene Rechnungen
4. **Dokumentations-Website mit Suche** auf GitHub Pages
5. **Fertiges Docker-Image** (amd64 und arm64), damit die Installation nicht mehr 30 Minuten baut
6. **Bankabgleich:** Kontoumsätze importieren (CAMT.053, CSV) und Zahlungen automatisch zuordnen

## Danach (Ideen, noch nicht geplant)

- Pauschalen wie Homeoffice, Fahrten mit dem Privat-Pkw und Verpflegungsmehraufwand (die fachlichen Regeln zuerst mit der Steuerberatung klären)
- Kassenbuch für Barzahlungen
- Belege per E-Mail einliefern, Teilen vom Handy, installierbare Web-App (PWA)
- Automatisches HTTPS und tägliche Sicherung als eigener Container
- Fristen-Übersicht mit Kalender-Feed
- Live-Vorschau der Rechnung neben dem Editor
- Teilmengen beim Lieferschein, Teilrechnung und Teilstorno

## Nicht geplant

steuy bleibt eine Buchhaltung für **Kleinunternehmer nach § 19 UStG mit EÜR**. Deshalb gibt es keine Umsatzsteuer-Voranmeldung, keine ELSTER-Übermittlung, keine doppelte Buchführung mit Kontenrahmen (SKR03/SKR04) und kein Reverse Charge. Wer das braucht, ist mit anderer Software besser bedient.

## Wünsche und Fehler

Wünsche und Fehler bitte als [Issue auf GitHub](https://github.com/faolan-exe/Steuy/issues) melden. Sicherheitslücken bitte vertraulich, siehe [SECURITY.md](../SECURITY.md).
