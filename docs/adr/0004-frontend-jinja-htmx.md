# 0004: Frontend mit Jinja2 und HTMX

- Status: vorgeschlagen
- Datum: 2026-10-19

## Kontext

Das Tool besteht aus Formularen, Listen und Auswertungen. Es gibt keine stark interaktiven Oberflächen. Zwei Entwickler, Python als gemeinsame Stärke.

## Entscheidung

Server-gerenderte Jinja2-Templates. HTMX für Teilaktualisierungen (Tabelle filtern, Beleg hochladen, Buchung festschreiben ohne Seitenwechsel). Ein klassenloses oder schlankes CSS-Framework, über CDN oder lokal eingebunden. Kein Node-Build.

## Verworfene Alternativen

- React/Vue mit Flask als JSON-API: zwei Codebasen, Build-Kette, doppelte Validierung. Für Formularanwendungen kein Gewinn.
- Reines Jinja ohne HTMX: funktioniert, aber jede Aktion lädt die ganze Seite.

## Folgen

Fachlogik bleibt komplett in Python. Endpunkte liefern teils ganze Seiten, teils HTML-Fragmente. Wenn später eine Mobile-App nötig wird, braucht es zusätzlich eine JSON-API.
