# Häufige Fragen zu steuy

Antworten auf die Fragen, die Kleinunternehmer und Selbstständige am häufigsten stellen, bevor sie eine Buchhaltungssoftware zum Selbst-Hosten einsetzen. Keine Steuerberatung: Bei steuerlichen Fragen hilft deine Steuerberatung.

## Was ist steuy?

steuy ist eine kostenlose, selbst gehostete Buchhaltungssoftware für Kleinunternehmer und Kleingewerbe nach § 19 UStG. Du schreibst Angebote, Rechnungen und Lieferscheine, verwaltest Belege und Zahlungen, mahnst offene Rechnungen und bekommst am Jahresende die Werte für die Anlage EÜR. Die Software läuft auf deinem eigenen Rechner oder Server, deine Daten verlassen ihn nicht.

## Für wen ist steuy gedacht?

Für Kleinunternehmer, Kleingewerbetreibende, Freiberufler und Selbstständige, die die **Kleinunternehmerregelung (§ 19 UStG)** nutzen und ihren Gewinn per **Einnahmen-Überschuss-Rechnung (EÜR)** ermitteln. Beispiele: Fotografen, Handwerker, Berater, Designer, Entwickler, kleine Online-Shops.

## Für wen ist steuy nicht geeignet?

Wer Umsatzsteuer ausweist (Regelbesteuerung), eine doppelte Buchführung oder Bilanz braucht oder Umsatzsteuer-Voranmeldungen direkt an das Finanzamt senden will. steuy rechnet **keine Umsatzsteuer** und hat **keine ELSTER-Schnittstelle**: Die Werte der Anlage EÜR trägst du selbst in ELSTER ein.

## Was kostet steuy?

Nichts. steuy ist kostenlos und ohne Abo. Du brauchst nur einen kleinen Rechner, auf dem es dauerhaft läuft, zum Beispiel einen gebrauchten Thin Client oder Mini-PC.

## Ist steuy Open Source?

steuy ist **quelloffen** (Source-available): Du kannst den gesamten Quellcode lesen, ändern und im eigenen Gewerbe nutzen. Die Lizenz ist die [PolyForm Shield License 1.0.0](../LICENSE). Sie verbietet nur, steuy oder eine Abwandlung als konkurrierendes Produkt oder Dienst anzubieten. Eine Open-Source-Lizenz im Sinne der OSI ist das deshalb nicht.

## Was heißt „selbst gehostet“?

steuy läuft auf einem Rechner, den du selbst betreibst, zum Beispiel zu Hause im Heimnetz. Es gibt keine Cloud, kein Kundenkonto bei uns und keine Weitergabe deiner Buchhaltungsdaten. Du bist selbst für Betrieb und Sicherung verantwortlich, dafür gehören die Daten dir.

## Brauche ich Linux-Kenntnisse?

Nein. Die [Anleitung für Einsteiger](thinclient.md) führt Schritt für Schritt vom leeren Thin Client oder Mini-PC bis zum laufenden steuy. Wer schon einen Proxmox- oder Docker-Server hat, installiert mit einem Befehl ([Proxmox-Container](lxc.md), [Docker](betrieb.md)).

## Welche Hardware brauche ich?

Ein 64-Bit-Rechner (x86_64) mit 1 GB RAM und 10 GB Speicher reicht, empfohlen sind 2 GB RAM und eine SSD. Ein gebrauchter Dell Wyse 5070 ist ideal. Details stehen unter [Mindestanforderungen](../README.md#mindestanforderungen). Auf ARM-Geräten (z. B. Raspberry Pi) ist steuy nicht getestet.

## Kann ich steuy vor der Installation ausprobieren?

Ja, in der [Live-Demo](https://steuy.philsit.de). Sie läuft ohne Anmeldung mit einer erfundenen Musterfirma, ein Rundgang erklärt alle Bereiche. Alle Änderungen werden alle 15 Minuten zurückgesetzt.

## Welche Funktionen hat steuy?

- Angebote, Rechnungen, Lieferscheine und Rechnungskorrekturen mit PDF/A und E-Mail-Versand, auf Wunsch mit QR-Code für die Überweisung
- Eigenes Drucklayout mit Logo, Farben und fünf Vorlagen
- Zahlungseingänge, Teilzahlungen, Mahnwesen mit Erinnerung und Mahnstufen
- Belege hochladen oder per Scanner einlesen, mit Texterkennung und Vorschlägen
- EÜR-Auswertung nach Zuflussprinzip, Dashboard mit Jahresziel
- Anlagegüter mit Abschreibung
- Umzug von Lexware, Import von WooCommerce-Bestellungen
- Rollen und Rechte, Zwei-Faktor-Anmeldung, Updates per Klick

Die vollständige Liste steht in der [README](../README.md#funktionen).

## Kann ich mit einem Scanner direkt Belege erfassen?

Ja. Der **Scan-Eingang** nimmt Scans von deinem Scanner (z. B. Brother ADS-1800W) über eine eingebaute Netzwerkfreigabe entgegen und legt sie als Belege an, mit Texterkennung. Einschalten geht in den Einstellungen mit einem Haken, siehe [Scanner anbinden](scanner.md).

## Kann ich von Lexware zu steuy umziehen?

Ja. steuy importiert das DATEV-Archiv und die CSV-Zahlungslisten aus Lexware, prüft die Daten und legt sie als Entwürfe an. Ablauf und Grenzen: [Umzug von Lexware](lexware-import.md).

## Werden E-Rechnungen unterstützt?

Eingehende E-Rechnungen (XRechnung, ZUGFeRD) kann steuy einlesen und im Originalformat aufbewahren. Eigene Rechnungen als E-Rechnung zu erzeugen ist noch nicht möglich.

## Ist steuy GoBD-konform?

steuy setzt die technischen Anforderungen um, die die GoBD an Unveränderbarkeit und Nachvollziehbarkeit stellen: Festgeschriebene Buchungen und Rechnungen lassen sich nicht mehr ändern oder löschen (Korrektur nur per Storno), Belege werden mit Prüfsumme unveränderlich abgelegt, jede Änderung steht im Protokoll. Eine Zertifizierung gibt es nicht, und die Verantwortung für die ordnungsgemäße Buchführung bleibt bei dir. Details: [GoBD im Code](domain/gobd.md).

## Wie sichere ich meine Daten?

Ein Skript sichert Datenbank und Belege, auf Wunsch jede Nacht automatisch. Die Sicherung gehört zusätzlich auf ein zweites Gerät. Anleitung: [Betrieb und Sicherung](betrieb.md).

## Wie komme ich zu Updates?

Unter *Einstellungen → Update* in steuy. Die App zeigt, was neu ist, sichert vorher und aktualisiert auf Knopfdruck.

## Wie kann ich mithelfen oder einen Fehler melden?

Als Issue auf GitHub. Sicherheitslücken bitte vertraulich melden, siehe [SECURITY.md](../SECURITY.md). Regeln für Beiträge stehen in [CONTRIBUTING.md](../CONTRIBUTING.md).
