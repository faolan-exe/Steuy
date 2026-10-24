# 0002: Festgeschriebene Buchungen sind append-only

- Status: angenommen
- Datum: 2026-10-19

## Kontext

Die GoBD verlangen, dass gebuchte Daten nicht nachträglich unbemerkt verändert werden. Nachträglich in ein bestehendes Modell eingebaut ist das sehr aufwendig.

## Entscheidung

- Buchungen haben `status` = `entwurf` oder `festgeschrieben`.
- Festgeschriebene Buchungen, Belege und Protokolleinträge werden von PostgreSQL-Triggern gegen `UPDATE` und `DELETE` geschützt.
- Korrektur nur über Stornobuchung (`storno_von_id`) und neue Buchung.

## Verworfene Alternativen

- Nur im Code durchsetzen: Ein Bug oder ein manuelles SQL kann es umgehen.
- Soft-Delete mit `deleted_at`: verändert trotzdem den Datensatz.

## Folgen

Tests müssen prüfen, dass der Trigger greift. Testdaten können nicht einfach per `DELETE` aufgeräumt werden: Tests laufen in Transaktionen, die zurückgerollt werden.
