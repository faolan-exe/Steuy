# Betrieb: Installation, Sicherung und Wiederherstellung

Datenbank und Ablage (`ABLAGE_VERZEICHNIS`, Rechnungs-PDFs und Belege) gehören zusammen. Sie werden immer gemeinsam gesichert und gemeinsam wiederhergestellt, sonst passen Buchungen und Dateien nicht zusammen.

## Betrieb mit Docker (empfohlen)

Auf einem Proxmox-Server geht es am einfachsten in einem LXC-Container, siehe [lxc.md](lxc.md).

Voraussetzung: ein Server oder Rechner mit Docker und Docker Compose. Alles Weitere bringt das Image mit (PDF-Erzeugung, Texterkennung, Datenbank-Migrationen).

### Einrichten

```sh
git clone https://github.com/faolan-exe/Steuy.git steuy && cd steuy
printf 'SECRET_KEY=%s\nPOSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 32)" "$(openssl rand -hex 16)" > .env
docker compose up -d --build
```

Danach `http://127.0.0.1:8000` öffnen und den Einrichtungsassistenten durchlaufen.

- `SECRET_KEY` und `POSTGRES_PASSWORD` **nie ändern und gut aufheben** (z. B. im Passwortmanager). Mit einem anderen `SECRET_KEY` lassen sich die Zwei-Faktor-Einstellungen nicht mehr lesen.
- Daten liegen in den Docker-Volumes `pgdaten` (Datenbank) und `ablage` (PDFs, Belege). `docker compose down -v` löscht sie, also nie mit `-v` aufrufen.
- Weitere Einstellungen in der `.env`: `PORT` (Standard 8000), `WEB_WORKER` (Standard 2), `TEXTERKENNUNG=0` zum Abschalten der Texterkennung.

### Von außen erreichbar machen (HTTPS)

Der Container lauscht nur auf `127.0.0.1`. Für den Zugriff aus dem Internet gehört ein Reverse Proxy mit HTTPS davor, z. B. Caddy:

```
buchhaltung.example.de {
    reverse_proxy 127.0.0.1:8000
}
```

Dann in der `.env` ergänzen und neu starten (`docker compose up -d`):

```
SESSION_COOKIE_SECURE=1
PROXY_ANZAHL=1
```

### Update

```sh
git pull
docker compose up -d --build
```

Datenbank-Migrationen laufen beim Start automatisch. Vor jedem Update eine Sicherung machen.

### Sicherung und Wiederherstellung

```sh
scripts/docker-sicherung.sh /mnt/sicherung
scripts/docker-wiederherstellen.sh /mnt/sicherung/steuy-2026-10-22_020000
```

Das Format ist dasselbe wie bei `scripts/sicherung.sh`, Sicherungen lassen sich also zwischen Docker- und Direktinstallation umziehen. Für eine tägliche Sicherung per Cron (im Projektordner):

```
0 2 * * * cd /opt/steuy && scripts/docker-sicherung.sh /mnt/sicherung >> /var/log/steuy-sicherung.log 2>&1
```

Die Sicherung gehört zusätzlich auf einen anderen Rechner oder Speicher.

## Ohne Docker

Für eine Installation direkt auf dem Server (Python, PostgreSQL, Pango und Tesseract selbst installiert):

### Sicherung

```sh
set -a; . ./.env; set +a
scripts/sicherung.sh /mnt/sicherung
```

Das Skript legt einen Ordner `steuy-JJJJ-MM-TT_HHMMSS` an mit:

- `datenbank.dump` (PostgreSQL, `pg_dump --format=custom`)
- `ablage.tar.gz` (alle Dateien der Ablage)
- `pruefsummen.txt` (SHA-256 beider Dateien)

Empfehlung: täglich per Cronjob, zusätzlich eine Kopie außer Haus (zweiter Rechner, NAS, verschlüsselter Cloud-Speicher). Aufbewahrungspflicht beachten: Belege 8 Jahre, Bücher und EÜR 10 Jahre.

### Wiederherstellung

```sh
set -a; . ./.env; set +a
scripts/wiederherstellen.sh /mnt/sicherung/steuy-2026-10-21_020000
```

Prüft zuerst die Prüfsummen, ersetzt dann Datenbank und Ablage. Danach `uv run flask db upgrade`, falls die Sicherung älter als die installierte Version ist.

## E-Mail-Versand

Unter Einstellungen → E-Mail den Postausgang (SMTP) des eigenen Postfachs eintragen und mit „Test-Mail senden“ prüfen. Danach haben Rechnungen, Angebote und Mahnungen den Knopf „Per E-Mail senden“: Text und Empfänger sind vorbelegt, das unveränderte PDF hängt an. Jede verschickte Mail (auch Fehlversuche) steht unveränderlich im Versandverlauf der Rechnung.

- Das SMTP-Passwort wird mit dem `SECRET_KEY` verschlüsselt gespeichert.
- Mails gehen von der eingetragenen Absenderadresse raus, Antworten an die E-Mail-Adresse aus den Firmendaten.
- Gmail und Outlook verlangen meist ein App-Passwort statt des normalen Passworts.

**Wöchentliche Zusammenfassung:** Montags ab 7 Uhr (Winterzeit, im Sommer 8 Uhr) bekommt jede Person mit Arbeitsrechten eine Mail, wenn unter „Zu prüfen“ etwas liegt. Abbestellen geht im Profil. Unter Docker erledigt das der Dienst `zeitplan` automatisch. Ohne Docker per Cron, z. B. stündlich:

```
0 * * * * cd /opt/steuy && set -a && . ./.env && set +a && uv run flask erinnerungen
```

Mit `BASIS_URL=https://buchhaltung.example.de` in der `.env` enthält die Mail einen Link zu „Zu prüfen“.

## Gesamtexport

Zusätzlich können Admins unter Einstellungen → Firmendaten alle Daten (CSV je Tabelle) und alle Dateien als ZIP herunterladen. Das ist keine Sicherung zum Zurückspielen, sondern ein lesbarer Export, z. B. für einen Umzug oder die Steuerberatung.

## Unveränderlichkeit

Die Ablage-Dateien sind schreibgeschützt (`0444`) und tragen ihren SHA-256 als Namen. steuy prüft den Hash bei jedem Lesen. Eine veränderte Datei wird als Fehler angezeigt und muss aus der Sicherung zurückgeholt werden.
