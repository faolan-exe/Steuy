# GoBD: was das für den Code heißt

Die GoBD (Grundsätze ordnungsmäßiger Buchführung in elektronischer Form) gelten auch für die EÜR. Hier nur die Punkte, die das Datenmodell und den Code betreffen. Keine Rechtsberatung, im Zweifel Steuerberatung fragen.

## Unveränderbarkeit

- Eine Buchung ist erst **Entwurf**, dann **festgeschrieben**. Entwürfe dürfen geändert und gelöscht werden.
- Festgeschriebene Buchungen werden nie geändert oder gelöscht.
- Korrektur: **Stornobuchung** mit umgekehrtem Vorzeichen und Verweis (`storno_von_id`), danach die richtige Buchung neu.
- Festschreiben soll zeitnah passieren, nicht erst zum Jahresende. Das Tool erinnert **wöchentlich** an offene Entwürfe (zusammen mit „Zu prüfen“, siehe `zahlungen-und-pruefung.md`).

## Belege löschen oder stornieren

Geklärt mit Philipp am 2026-10-21, Vorschlag in ADR 0006.

- **Noch nicht verbucht** (Upload in „Zu prüfen“, nur an Entwürfen hängend): Der Beleg darf gelöscht werden, z. B. bei Fehl-Upload, Dublette oder privater Quittung. Das Löschen wird protokolliert (wer, wann, Dateiname, Hash), die Datei selbst wird entfernt.
- **Verbucht** (an einer festgeschriebenen Buchung): kein Löschen. Der Button heißt dann **„Stornieren“**. Nach einem Warnhinweis erzeugt das Tool automatisch die Stornobuchung für Beleg und Zahlung. Danach erscheint der Beleg nicht mehr in den normalen Listen und zählt nicht mehr in der EÜR. Er bleibt aber unter „Storniert“ erhalten.
- **Ausgangsrechnungen** werden nie gelöscht, auch nicht als Entwurf mit vergebener Nummer. Korrektur nur per Storno oder Rechnungskorrektur. Entwürfe ohne Nummer dürfen gelöscht werden.

## Nachvollziehbarkeit

- Jede Buchung verweist auf mindestens einen Beleg (Ausnahme: Eigenbelege, die selbst als Beleg erzeugt werden).
- Änderungsprotokoll: wer, wann, welche Aktion, welcher Datensatz. Append-only.
- Importierte Daten (WooCommerce) behalten den Original-Payload.

## Aufbewahrung

- Das Tool löscht nie automatisch Buchungen, Belege oder Protokolleinträge.
- Eingehende E-Rechnungen im Originalformat (XML) aufbewahren, nicht nur ein PDF davon.

## Verfahrensdokumentation

Die GoBD verlangen eine Beschreibung, wie die Buchhaltung organisiert ist. `docs/` ist die Grundlage dafür. Später daraus eine knappe Verfahrensdokumentation pro Gewerbe ableiten.

## Offen / zu prüfen

- [ ] Ab wann muss spätestens festgeschrieben sein?
- [ ] Reicht die Hash-Prüfung als Schutz der Belege, oder braucht es zusätzlich eine externe Sicherung mit Zeitstempel?
