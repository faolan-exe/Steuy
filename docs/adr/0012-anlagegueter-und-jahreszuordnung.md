# 0012: Anlagegüter und Jahreszuordnung neben der Zahlung speichern

- Status: vorgeschlagen
- Datum: 2026-10-22

## Kontext

Zahlungen und festgeschriebene Buchungen sind unveränderlich (ADR 0002). Für die AfA und für regelmäßige Zahlungen am Jahreswechsel (§ 11 EStG) zählt in der EÜR aber ein anderer Zeitpunkt als das Zahlungsdatum.

## Entscheidung

- **Anlagegut** (`anlagegut`) verweist auf eine festgeschriebene Ausgabe. Die EÜR lässt die Zahlung dieser Buchung weg und rechnet stattdessen die AfA des Jahres (Kz 130/131). Die AfA wird bei jeder Auswertung aus Kosten, Datum, Art und Nutzungsdauer berechnet, nicht gespeichert.
- **Jahreszuordnung** (`jahreszuordnung`) hält fest, in welches EÜR-Jahr eine Zahlung am Jahreswechsel gehört, mit Person und Zeitpunkt der Bestätigung.
- Beide Tabellen sind unveränderlich (DB-Trigger). Korrektur über Storno der Buchung, das hebt Anlagegut und Zuordnung auf.
- Grenzwerte (GWG) und Nutzungsdauer-Vorschläge stehen als Daten in der DB.

## Verworfene Alternativen

- **Felder an Zahlung oder Buchung:** würde deren Unveränderlichkeit aufweichen.
- **AfA-Beträge je Jahr speichern:** doppelte Wahrheit, schwer korrigierbar.

## Folgen

- Die EÜR bleibt jederzeit aus den Ursprungsdaten nachrechenbar.
- Abgänge (Verkauf, Entnahme) und private Mitnutzung von Anlagegütern fehlen noch (offene Fragen in `docs/domain/euer.md`).
