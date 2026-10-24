# Architektur

## Schichten

```
app/
  __init__.py        App-Factory create_app()
  config.py          Konfiguration aus Umgebungsvariablen
  extensions.py      db, migrate, login_manager
  models/            SQLAlchemy-Modelle
  domain/            Fachlogik, ohne Flask-Import, voll testbar
  services/          Abläufe über mehrere Modelle: Festschreiben, Storno, Import
  integrations/
    woocommerce/     API-Client und Mapping Bestellung → Buchungsentwurf
  web/               Blueprints, Formulare, Jinja-Templates, HTMX-Partials
migrations/          Alembic
tests/
docs/
```

Abhängigkeitsrichtung: `web` → `services` → `domain` / `models`. `domain` kennt weder Flask noch HTTP.

## Kern-Datenmodell

Eine Installation enthält genau ein Gewerbe (ADR 0007). Es gibt keine Mandanten-Spalte.

| Tabelle | Zweck | Besonderheit |
|---|---|---|
| `gewerbe` | Firmendaten, Bankverbindung, Vorgaben für Rechnungen | genau eine Zeile (CHECK `id = 1`) |
| `nutzer` | Login | Rolle (Admin, Buchhalter, Mitarbeiter, Steuerberater), nie gelöscht, nur deaktiviert |
| `rollenrecht` | vergebene Rechte je Rolle | Admin hat immer alle Rechte, siehe `domain/rollen.md` |
| `kleinunternehmergrenze` | Umsatzgrenzen nach § 19 je Gültigkeitsjahr | Daten statt Konstanten im Code |
| `kontakt` | Kunden und Lieferanten | Kunden- und Lieferantennummer fortlaufend, archivieren statt löschen |
| `artikel` | Produkte und Services | Preis in Cent, kein Steuersatz |
| `nummernkreis` | fortlaufende Belegnummern | Vergabe mit `SELECT … FOR UPDATE` |
| `rechnung` / `rechnungsposition` | Ausgangsrechnung | nach dem Finalisieren unveränderlich (Trigger), PDF in der Ablage |
| `kategorie` | Kategorie für Einnahmen und Ausgaben | Zuordnung zu Zeilen der Anlage EÜR je Steuerjahr folgt mit der EÜR-Auswertung |
| `buchung` | Einnahme oder Ausgabe ohne eigene Rechnung | `betrag_cent`, `status` (entwurf/festgeschrieben), `storno_von_id`, `betrieblich_prozent`; nach dem Festschreiben unveränderlich (Trigger) |
| `zahlung` | Zahlungsein- und -ausgänge | gehört zu genau einer Rechnung oder Buchung, append-only; Datum bestimmt das EÜR-Jahr |
| `buchung_gebuehr` | Gebühren-Ausgabe ↔ Zahlungen mit Gebühr | |
| `beleg` | hochgeladene Datei | `sha256`, Datei-Angaben unveränderlich, nie gelöscht, nur verworfen (Trigger) |
| `import_rohdaten` | Original-Payload aus WooCommerce | Nachvollziehbarkeit, Idempotenz (geplant) |
| `protokoll` | Änderungsprotokoll | append-only (Trigger) |

## Unveränderlichkeit

Durchgesetzt auf zwei Ebenen:

1. **Service-Schicht:** Es gibt keine Funktion zum Ändern oder Löschen festgeschriebener Datensätze.
2. **Datenbank:** PostgreSQL-Trigger lehnen `UPDATE` und `DELETE` auf `protokoll`, auf finalisierte `rechnung`-Zeilen samt Positionen und später auf festgeschriebene `buchung`-Zeilen und `beleg` ab. Die Trigger liegen in Alembic-Migrationen.

Damit ist auch ein Fehler im Code oder ein manuelles SQL kein stiller Weg, die Bücher zu ändern.

## Belegablage

Dateien liegen außerhalb der DB in einem Verzeichnis, Dateiname = SHA-256. Die DB speichert Hash, Originalname, MIME-Typ. Beim Lesen wird der Hash geprüft. Das Verzeichnis gehört ins Backup.

## Betrieb

Docker Compose mit App (gunicorn) und PostgreSQL, z. B. im Homelab hinter einem Reverse Proxy. Jedes Gewerbe bekommt eine eigene Installation. Beide Container mit `restart: always`. Backup von DB-Dump und Belegverzeichnis gemeinsam, sonst passen Belege und Buchungen nicht zusammen.
