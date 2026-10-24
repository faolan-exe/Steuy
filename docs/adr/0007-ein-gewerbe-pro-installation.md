# 0007: Ein Gewerbe pro Installation

- Status: angenommen
- Datum: 2026-10-21
- Ersetzt bei Annahme: 0003

## Kontext

ADR 0003 sieht zwei getrennte Buchungskreise in einer Instanz vor, damit wir beide ein gemeinsames System nutzen. Mit ADR 0005 wird das Tool ein öffentliches Projekt, das jeder selbst betreibt.

Fachliche Vorgabe von Philipp (2026-10-21): Jeder setzt für sein Gewerbe ein eigenes System auf. Ein System enthält genau ein Gewerbe. Mehrere Personen arbeiten über Nutzerrollen im selben System (siehe `docs/domain/rollen.md`).

Noch gibt es keinen Anwendungscode. Eine Änderung am Datenmodell kostet jetzt fast nichts.

## Entscheidung

- Eine Installation enthält **genau ein Gewerbe**. Die Firmendaten (Name, Inhaber, Anschrift, Steuernummer, Nummernkreise) liegen in einer Einzel-Tabelle `gewerbe` mit genau einer Zeile.
- Es gibt **keine `buchungskreis_id`** in den fachlichen Tabellen und keinen Buchungskreis-Filter in Queries.
- Wer mehrere Gewerbe hat, z. B. wir beide, betreibt mehrere Installationen. Docker Compose macht das mit einem weiteren Projektverzeichnis und eigenem Port einfach.
- Zugriffsrechte regelt das Rollenmodell (Admin, Buchhalter, Mitarbeiter, Steuerberater), nicht der Buchungskreis.
- Harte Regel 3 in `CONTRIBUTING.md` entfällt nach Annahme. `docs/architektur.md` wird angepasst.

## Verworfene Alternativen

- **Mehrere Buchungskreise je Installation (ADR 0003 beibehalten):** Jede Tabelle und jede Query braucht den Filter, jeder Endpunkt einen Test gegen fremde Daten. Das ist viel Aufwand und eine ständige Fehlerquelle für einen Fall, den die Zielgruppe kaum hat.
- **`buchungskreis_id` vorsorglich behalten, aber nur einen Buchungskreis anlegen:** Der Aufwand bleibt gleich, nur ohne Nutzen. Falls mehrere Gewerbe je Installation später doch nötig werden, ist eine Migration möglich.

## Folgen

- Datenmodell, Queries und Tests werden einfacher. Daten verschiedener Gewerbe können sich technisch nicht mischen, weil sie in getrennten Datenbanken liegen.
- Wir beide betreiben zwei Installationen statt einer, mit getrennten Backups und Updates.
- Eine gemeinsame Übersicht über mehrere Gewerbe gibt es nicht.
- Datensicherung und Wiederherstellung beziehen sich immer auf ein ganzes Gewerbe, was das Verfahren vereinfacht.
