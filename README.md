<div align="center">

```text
     _                    
 ___| |_ ___ _   _ _   _ 
/ __| __/ _ \ | | | | | |
\__ \ ||  __/ |_| | |_| |
|___/\__\___|\__,_|\__, |
                   |___/ 
```

**Einfache Buchhaltung für Kleinunternehmer. Kostenlos, selbst gehostet, deine Daten bleiben bei dir.**

![Version](https://img.shields.io/badge/Version-0.5.0-2ea44f)
![Lizenz](https://img.shields.io/badge/Lizenz-PolyForm%20Shield%201.0.0-blue)
![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-336791?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-bereit-2496ED?logo=docker&logoColor=white)

[Installieren](#-installieren) · [Funktionen](#-funktionen) · [Entwickeln](#%EF%B8%8F-entwicklung-einrichten) · [Doku](#-doku) · [Sicherheit](SECURITY.md)

</div>

---

## 🌱 Für Anfänger gemacht

steuy ist **besonders für Einsteiger geeignet**: ein komplettes Programm, das die Buchführung eines Kleinunternehmers nach **§ 19 UStG** mit **Einnahmen-Überschuss-Rechnung (EÜR)** Schritt für Schritt abbildet. Du brauchst keine Vorkenntnisse. Ein geführter Rundgang erklärt jede Funktion, und die Hilfe in der App sagt dir, was als Nächstes zu tun ist.

- 🏠 **Alle Daten bleiben bei dir.** steuy läuft auf deinem eigenen Server. Deine Buchhaltung wird nirgendwohin hochgeladen, es gibt keine Cloud und kein Konto bei uns.
- 💸 **Kostenlos** und quelloffen.
- 🧩 **Alles in einem:** von der ersten Rechnung bis zu den Werten für deine Steuererklärung.

## ✨ Funktionen

| | |
|---|---|
| 🧾 **Rechnungen** | Rechnungen schreiben mit Positionen, Artikeln und Kunden aus deiner Kontaktliste, automatische Nummern, Rechnungskorrektur und Storno. PDF/A zum Archivieren, Versand per E-Mail. |
| 📝 **Angebote, Lieferscheine** | Vom Angebot zur Rechnung und zum Lieferschein, alles miteinander verknüpft (Belegkette). |
| 🎨 **Eigenes Drucklayout** | Fünf Designs, Logo (links, mittig oder rechts), Farben und Schrift. Live-Vorschau beim Bearbeiten. |
| 💶 **Zahlungen** | Zahlungseingänge erfassen, Teilzahlungen, offene Posten im Blick. |
| ⏰ **Mahnwesen** | Mahnungen von Hand oder automatisch (abschaltbar), mit Mailversand und Verlauf. |
| 📎 **Belege & Ausgaben** | Belege hochladen oder abfotografieren, Texterkennung liest sie aus. Gespeichert mit Prüfsumme, nie überschrieben. |
| 🏗️ **Anlagen & Abschreibung** | Anlagegüter verwalten und abschreiben. |
| 📊 **EÜR & Dashboard** | Zuflussprinzip, Jahresübersicht, Kreisdiagramm, eigenes Jahresziel mit Fortschritt, Werte für die Anlage EÜR. |
| 📅 **Jahreswechsel** | Jahr wechseln, Daten exportieren und bei einem Wechsel mitnehmen. |
| 🔁 **Umzug von Lexware** | Import aus DATEV-Archiv und CSV-Zahlungslisten, Daten werden geprüft und als Entwürfe angelegt. |
| 🛒 **WooCommerce** | Bestellungen aus dem Shop übernehmen. |
| 👥 **Kontakte & Artikel** | Kunden, Lieferanten und Produkte oder Dienstleistungen verwalten. |
| 🔒 **Sicher & nachvollziehbar** | Rollen und Rechte, Zwei-Faktor-Anmeldung, festgeschriebene Buchungen sind unveränderlich (GoBD). |
| 🧭 **Rundgang & Hilfe** | Geführte Tour je nach Vorkenntnissen, Hilfeseiten in der App. |
| 🔄 **Updates per Klick** | Neue Versionen direkt in der App einspielen, mit Sicherung davor. |
| 💾 **Sicherung** | Datenbank und Belege lassen sich mit einem Skript sichern. |

Eine Installation gehört genau einem Gewerbe. Alle Beträge sind exakte Cent-Werte, nie Kommazahlen.

## ⚠️ Haftung und Nutzung auf eigene Gefahr

steuy ist **keine Steuerberatung**. Die Nutzung erfolgt **auf eigene Gefahr**.

- Es wird **keine Haftung** übernommen für Datenverlust, steuerliche Probleme oder Folgen aus falschen Werten, die die Software ausgibt.
- Es wird **keine Haftung** übernommen für Sicherheitslücken in der Software oder in deinem Betrieb.
- Prüfe alle Werte, besonders die der Anlage EÜR, vor der Abgabe selbst oder mit deiner Steuerberatung. Übertragen wird von Hand in ELSTER.
- Sichere deine Daten regelmäßig (siehe [Betrieb](docs/betrieb.md)).

## 📄 Lizenz

[PolyForm Shield 1.0.0](LICENSE): quelloffen. Du darfst steuy im eigenen Gewerbe nutzen, lesen und anpassen. Nicht erlaubt ist, steuy oder eine Abwandlung als konkurrierendes Produkt oder Dienst anzubieten. Sicherheitslücken bitte privat melden, siehe [SECURITY.md](SECURITY.md).

## 🚀 Installieren

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

## 🛠️ Entwicklung einrichten

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

## ✅ Prüfen

```sh
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Beides läuft auch automatisch bei jedem Pull Request.

## 📚 Doku

- [`CONTRIBUTING.md`](CONTRIBUTING.md): Regeln für die Mitarbeit (harte Regeln, Stack, Git)
- [`docs/ziel.md`](docs/ziel.md): Umfang und offene Fragen
- [`docs/architektur.md`](docs/architektur.md): Aufbau und Datenmodell
- [`docs/domain/`](docs/domain/): Fachregeln (GoBD, EÜR, Zahlungen, Rollen, WooCommerce)
- [`docs/adr/`](docs/adr/): getroffene Entscheidungen
