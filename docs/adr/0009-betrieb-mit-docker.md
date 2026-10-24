# 0009: Betrieb mit Docker Compose und Zeitplan-Dienst

- Status: vorgeschlagen
- Datum: 2026-10-22

## Kontext

steuy richtet sich an Kleinunternehmer ohne IT-Kenntnisse. Die Direktinstallation braucht Python, PostgreSQL, Pango und Tesseract in passenden Versionen. Dazu kommen wiederkehrende Aufgaben (Wochenmail, Shop-Abruf), für die es bisher keinen Mechanismus gab.

## Entscheidung

- **Docker Compose** ist der empfohlene Betrieb: Dienste `app` (Gunicorn), `db` (PostgreSQL 17) und `zeitplan`. Das Image bringt PDF und deutsche Texterkennung mit und läuft ohne root.
- **Zugangsdaten** (`SECRET_KEY`, `POSTGRES_PASSWORD`) nur aus der `.env`, Pflicht beim Start. Kein festes Passwort im Repo, auch nicht für Dev und CI.
- Die App lauscht nur auf `127.0.0.1`. HTTPS übernimmt ein Reverse Proxy (Beispiel Caddy in `docs/betrieb.md`).
- **Migrationen** laufen beim Start des App-Containers.
- **Wiederkehrende Aufgaben** sind CLI-Befehle (`flask shop-abruf`, `flask erinnerungen`). Der Dienst `zeitplan` ruft sie stündlich auf. Jede Aufgabe ist idempotent (Wochenmail höchstens einmal je Woche, Shop-Abruf über Bestell-IDs), deshalb schadet ein zusätzlicher Lauf nicht.
- **Sicherung** mit `scripts/docker-sicherung.sh`. `pg_dump` läuft im DB-Container, damit die Version zum Server passt. Gleiches Format wie die Direktinstallation.
- Die CI baut das Image, startet es und spielt eine Sicherung hin und zurück.

## Verworfene Alternativen

- **Cron im App-Container:** zweiter Prozess im Container, schwerer zu überwachen.
- **Scheduler in der App (z. B. APScheduler):** läuft je Gunicorn-Worker mehrfach.
- **Fertiges Image auf einer Registry:** später sinnvoll, vorerst baut jeder lokal (keine Release-Pipeline nötig).

## Folgen

- Installation mit drei Befehlen, Updates mit `git pull && docker compose up -d --build`.
- `docker compose down -v` löscht alle Daten. Die Doku warnt davor.
- Ohne Docker braucht es weiterhin Cron für die wiederkehrenden Aufgaben (in der Doku beschrieben).
