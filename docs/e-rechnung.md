# E-Rechnung erzeugen: ZUGFeRD und XRechnung

steuy kann jede Rechnung als **E-Rechnung** festschreiben: Das PDF enthält die Rechnungsdaten zusätzlich maschinenlesbar (Format **ZUGFeRD / Factur-X**, Profil EN 16931). Dein Kunde kann sie ohne Abtippen in seine Buchhaltung einlesen, und ein Mensch liest weiter das ganz normale PDF. Für Behörden entsteht daraus eine **XRechnung**.

> Hinweis: Als Kleinunternehmer musst du nach unserem Kenntnisstand E-Rechnungen nicht ausstellen, nur empfangen können. Ob und wann das für dich anders ist, klärst du mit deiner Steuerberatung. steuy bietet die Funktion für alle, die ihren Kunden trotzdem eine E-Rechnung schicken möchten oder müssen.

## Einschalten

*Einstellungen → Rechnungen → E-Rechnung:* Haken setzen und speichern. Ab dann wird **jede neue Rechnung und jede Rechnungskorrektur** beim Festschreiben als E-Rechnung erzeugt. Bereits festgeschriebene Rechnungen bleiben, wie sie sind.

Dafür braucht steuy von dir:

- Steuernummer (oder USt-IdNr.), E-Mail und Telefon in den **Firmendaten**
- eine **Bankverbindung** (IBAN) in den Rechnungseinstellungen
- beim Kunden Name und Anschrift

Fehlt etwas, nennt dir die Vorschau vor dem Festschreiben genau, was.

## Was in der E-Rechnung steht

- Rechnungsnummer, Datum, Fälligkeit, Leistungsdatum oder Leistungszeitraum
- deine Daten mit Ansprechstelle und Steuernummer, die Anschrift des Kunden
- alle Positionen mit Menge, Einheit, Einzelpreis und Rabatt
- Zahlung per SEPA-Überweisung mit IBAN und Verwendungszweck
- **Steuerkategorie „befreit“** mit 0 Prozent und dem Hinweistext nach § 19 UStG (so wie auf der Rechnung)
- bei einer **Rechnungskorrektur** (Storno) eine Gutschrift mit Verweis auf die ursprüngliche Rechnung

Textpositionen (Freitext zwischen den Positionen) erscheinen nur im PDF, nicht in den Daten.

## Wo du die E-Rechnung findest

- Das **PDF** ist die ZUGFeRD-Rechnung: Du verschickst es wie bisher.
- Auf der Rechnungsseite lädst du das **XML** zusätzlich über „E-Rechnung (XML)“ herunter.
- Im **Jahresexport** liegt das XML neben dem PDF.

Beides ist wie die Rechnung selbst unveränderlich abgelegt.

## XRechnung für Behörden

Trägst du beim Kunden eine **Leitweg-ID** ein (Kontakt bearbeiten), kennzeichnet steuy die Rechnung als XRechnung und trägt die Leitweg-ID als Käuferreferenz ein. Die Daten sind dann in der Rechnung selbst. Viele Behörden verlangen die XRechnung als reine XML-Datei: Lade sie über „E-Rechnung (XML)“ herunter und reiche sie über das Portal der Behörde ein.

## Prüfen und Grenzen

- steuy prüft die erzeugten Daten gegen das offizielle **Schema** (XSD) von Factur-X / EN 16931. Die fachlichen **Schematron-Regeln** der KoSIT-Prüfstelle sind dagegen nicht eingebaut. Prüfe wichtige E-Rechnungen, besonders XRechnungen für Behörden, vor dem Versand mit einem Validator, zum Beispiel dem [KoSIT-Prüftool](https://github.com/itplr-kosit/validator) oder einem Online-Prüfdienst.
- Es gibt keine Zertifizierung. Du bleibst für die Richtigkeit deiner Rechnung verantwortlich.
- Eigene Bildschirmausgaben von Empfängern („Rechnung ansehen“) zeigen oft nur das PDF, das ist normal.
