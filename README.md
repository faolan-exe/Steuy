# steuy

Kostenlose, selbst gehostete Buchhaltung (EÜR) für Kleinunternehmer nach § 19 UStG.

> Im Aufbau. Nutzung auf eigene Gefahr, keine Steuerberatung.

Lizenz: [PolyForm Shield 1.0.0](LICENSE). Quelloffen: Nutzung im eigenen Gewerbe und Anpassungen sind erlaubt, steuy als konkurrierendes Produkt oder Dienst anzubieten nicht. Sicherheitslücken bitte privat melden, siehe [SECURITY.md](SECURITY.md).

## Installieren

Du brauchst einen eigenen kleinen Server oder Rechner, auf dem steuy dauerhaft läuft. Drei Wege, vom einfachsten zum aufwendigsten:

| Weg | Für wen | Anleitung |
|---|---|---|
| **Proxmox-Container (LXC)** | Du hast schon einen Proxmox-Server, z. B. im Heimnetz. Container anlegen, ein Befehl, fertig. | [docs/lxc.md](docs/lxc.md) |
| **Docker** | Du hast einen Linux-Server oder -Rechner mit Docker. | unten, Details in [docs/betrieb.md](docs/betrieb.md) |
| **Ohne Docker** | Du möchtest Python, PostgreSQL und Co. selbst verwalten. | [docs/betrieb.md](docs/betrieb.md), Abschnitt „Ohne Docker“ |

### Schnellstart mit Docker

```sh
git clone https://github.com/faolan-exe/Steuy.git steuy && cd steuy
printf 'SECRET_KEY=%s\nPOSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 32)" "$(openssl rand -hex 16)" > .env
docker compose up -d --build   # http://127.0.0.1:8000
```

HTTPS, Updates und Sicherungen: siehe [docs/betrieb.md](docs/betrieb.md).

## Entwicklung einrichten

Voraussetzungen: [uv](https://docs.astral.sh/uv/), PostgreSQL 17 und Pango für die PDF-Erzeugung (ADR 0008). macOS: `brew install uv postgresql@17 pango tesseract`, Debian/Ubuntu: `apt install libpango-1.0-0 libpangoft2-1.0-0 tesseract-ocr tesseract-ocr-deu`. Tesseract ist optional und liest Belegfotos und Scans aus. PostgreSQL geht auch per Docker (siehe unten).

```sh
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
uv sync
cp .env.example .env          # SECRET_KEY eintragen
createdb steuy
createdb steuy_test
uv run flask db upgrade
uv run flask run --debug      # http://127.0.0.1:5000
```

Der Hook blockt direkte Pushes auf `main` lokal.

PostgreSQL per Docker statt lokal:

```sh
docker compose -f docker-compose.dev.yml up -d
```

Dann die beiden Datenbank-URLs in der `.env` wie in `docker-compose.dev.yml` beschrieben setzen.

## Prüfen

```sh
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Beides läuft auch automatisch bei jedem Pull Request.

## Doku

- `CONTRIBUTING.md`: Regeln für die Mitarbeit (harte Regeln, Stack, Git)
- `docs/ziel.md`: Umfang und offene Fragen
- `docs/architektur.md`: Aufbau und Datenmodell
- `docs/domain/`: Fachregeln (GoBD, EÜR, Zahlungen, Rollen, WooCommerce)
- `docs/adr/`: getroffene Entscheidungen
