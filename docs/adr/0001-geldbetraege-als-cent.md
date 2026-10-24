# 0001: Geldbeträge als Integer-Cent

- Status: angenommen
- Datum: 2026-10-19

## Kontext

Fließkommazahlen können Dezimalbeträge nicht exakt darstellen (`0.1 + 0.2 != 0.3`). Summen über ein Jahr weichen dann um Cent-Beträge ab.

## Entscheidung

Alle Beträge sind `int` in Cent, in der DB `BigInteger`. Umrechnung in Euro nur beim Anzeigen und beim Einlesen von Formularen und Importen. Die Umrechnung liegt an genau einer Stelle (`app/domain/geld.py`) und ist getestet.

## Verworfene Alternativen

- `float`: ungenau.
- `Decimal` / `Numeric(12,2)`: genau, aber SQLAlchemy und JSON-Importe liefern leicht wieder `float` zurück, und Rundungsregeln müssen überall mitgedacht werden. Integer-Cent macht Fehler sichtbarer.

## Folgen

Einlesen von „12,50“ oder „12.5“ braucht eine strikte Parse-Funktion. Prozentrechnungen (z. B. Gebühren) runden explizit, kaufmännisch.
