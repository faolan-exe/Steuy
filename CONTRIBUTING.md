# Mitarbeit an steuy

Kostenloses, selbst gehostetes quelloffenes Buchhaltungstool für Kleinunternehmer nach § 19 UStG (ADR 0005). Eine Installation gehört genau einem Gewerbe (ADR 0007).
Kern: Einnahmen-Überschuss-Rechnung, Belegverwaltung, Angebote und Rechnungen, Zahlungen und Mahnwesen, WooCommerce-Import.
Keine Umsatzsteuer-Logik, keine ELSTER-Schnittstelle: Das Tool gibt die Werte der Anlage EÜR aus, übertragen wird von Hand.

Details: `docs/ziel.md` (Umfang), `docs/architektur.md` (Aufbau), `docs/domain/` (Fachregeln), `docs/adr/` (Entscheidungen).

## Harte Regeln (nie brechen, auch nicht "vorübergehend")

1. **Geld nur als Integer-Cent** (`BigInteger` in der DB, `int` in Python). Kein `float`, nirgends. Formatierung nur in der Anzeige. → ADR 0001
2. **Festgeschriebene Buchungen sind unveränderlich.** Kein UPDATE, kein DELETE. Korrektur = Stornobuchung + neue Buchung. Die DB erzwingt das per Trigger, nicht nur der Code. → ADR 0002, `docs/domain/gobd.md`
3. **Jede Route prüft Rechte.** Jede Route außer Anmeldung, Einrichtung und `/gesund` hat `@braucht_recht(...)`, Templates blenden Aktionen über `darf(...)` aus. Ein Gewerbe pro Installation, keine Mandanten-Logik. → ADR 0007, `docs/domain/rollen.md`
4. **Zuflussprinzip:** Für die EÜR zählt das Zahlungsdatum, nicht Bestell- oder Rechnungsdatum. → `docs/domain/euer.md`
5. **Belege sind unveränderlich:** Datei wird mit SHA-256 gespeichert, nie überschrieben, nie gelöscht.
6. **Keine Fachregel raten.** Wenn eine steuerliche Regel unklar ist: nachfragen oder als offene Frage in `docs/domain/` markieren, nicht implementieren.

## Stack

- Python 3.12+, Flask (App-Factory, Blueprints), SQLAlchemy 2.x (typisierter `Mapped[]`-Stil), Alembic
- PostgreSQL (auch in Tests)
- Frontend: Jinja2-Templates + HTMX, kein Build-Schritt → ADR 0004
- Paketverwaltung: `uv`; Lint/Format: `ruff`; Tests: `pytest`

## Befehle

- Abhängigkeiten: `uv sync`
- Tests: `uv run pytest`
- Lint: `uv run ruff check . && uv run ruff format --check .`
- Migration erzeugen: `uv run flask db revision --autogenerate -m "<kurz>"`
- Migration anwenden: `uv run flask db upgrade`
- App starten: `uv run flask run --debug`

## Code-Regeln

- Fachlogik in `app/domain/` ohne Flask-Import. Routen sind dünn: Eingabe prüfen, Domain aufrufen, rendern.
- Jede Fachregel bekommt einen Test, der den Grenzfall abdeckt (Jahreswechsel, Storno, Teilerstattung, fehlendes Recht).
- Schema nur per Alembic-Migration ändern, nie per `create_all` in Produktion.
- Keine Secrets im Code. Konfiguration über Umgebungsvariablen, `.env` ist in `.gitignore`.
- Kleine, fokussierte Änderungen. Kein Refactoring nebenbei, das nicht zur Aufgabe gehört.

## Git

- Nie direkt auf `main` pushen, nie force-pushen auf geteilte Branches.
- Branch pro Issue: `feat/<nr>-<kurz>`, `fix/<nr>-<kurz>`, `docs/<kurz>`.
- Commits nach Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- PR nach `main`, Squash-Merge, sobald CI (Tests + Lint) grün ist. Review bei Bedarf auch nachträglich.
- Vor dem PR: Tests und Lint grün.

## Arbeitsweise

- Zu Beginn: `git pull`, zugehöriges Issue lesen. Offene Arbeit steht in GitHub-Issues.
- Eine Architektur- oder Fachentscheidung getroffen → ADR in `docs/adr/` anlegen (Vorlage `0000-vorlage.md`, Status `vorgeschlagen`, bis beide zugestimmt haben).
