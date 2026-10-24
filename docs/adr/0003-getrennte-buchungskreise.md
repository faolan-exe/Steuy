# 0003: Zwei getrennte Buchungskreise in einer Instanz

- Status: ersetzt durch 0007
- Datum: 2026-10-19

## Kontext

Zwei Personen mit je einem eigenen Gewerbe nutzen ein Tool. Die Daten dürfen sich nie mischen: eigene EÜR, eigene Rechnungsnummern, eigener Shop.

## Entscheidung

- Tabelle `buchungskreis`. Jede fachliche Tabelle hat `buchungskreis_id` (NOT NULL, Fremdschlüssel).
- Der aktive Buchungskreis wird pro Request aus der Session gesetzt und vom Nutzerrecht geprüft.
- Queries laufen über eine Hilfsfunktion, die den Filter immer setzt. Ein Test pro Endpunkt prüft, dass Daten des anderen Buchungskreises nicht sichtbar sind.

## Verworfene Alternativen

- Zwei getrennte Instanzen: doppelter Betrieb, doppelte Updates.
- Getrennte DB-Schemas: mehr Aufwand bei Migrationen, für zwei Mandanten unnötig.
- PostgreSQL Row Level Security: gut, aber für den Start zu viel. Kann später ergänzt werden.

## Folgen

Jede neue Tabelle und jede neue Query muss den Buchungskreis berücksichtigen. Das Review prüft das.
