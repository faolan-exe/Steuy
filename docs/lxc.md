# steuy in einem LXC-Container installieren (Proxmox)

In drei Schritten: Container anlegen, **einen Befehl** eingeben, die angezeigte Adresse im Browser öffnen. Das Skript richtet alles andere ein (Docker, steuy, Webserver, Zugangsdaten).

> **Getestet:** Das Skript lief am 22.10.2026 in einem echten LXC-Container mit Ubuntu 24.04 durch (Installation, Erreichbarkeit über die IP, zweiter Lauf, Neustart des Containers, Sicherung). Auf Debian 12 und mit einem Container ganz ohne Docker prüft es zusätzlich die automatische Prüfung auf GitHub. Wenn etwas nicht klappt, bitte als Issue melden.

## Was du brauchst

| | Mindestens | Empfohlen |
|---|---|---|
| Kerne | 1 | 2 |
| Arbeitsspeicher | 1,5 GB | 2 GB |
| Festplatte | 8 GB | 16 GB (Belege wachsen mit den Jahren) |
| Betriebssystem im Container | Ubuntu 24.04 oder Debian 12 | Ubuntu 24.04 |

Der Speicher geht beim Bauen und bei der Texterkennung für Belegfotos kurz hoch. Im Alltag braucht steuy deutlich weniger.

## Schritt 1: Container anlegen

### Über die Proxmox-Oberfläche

1. **Vorlage laden:** Datacenter → dein Server → *local* → *CT Templates* → *Templates* → **ubuntu-24.04-standard** herunterladen.
2. **Create CT** (oben rechts):
   - *Hostname:* `steuy`
   - *Passwort:* ein eigenes, sicheres Root-Passwort
   - *Template:* ubuntu-24.04-standard
   - *Disk:* 16 GB, *CPU:* 2 Kerne, *Memory:* 2048 MB, *Swap:* 512 MB
   - *Network:* Bridge `vmbr0`, **DHCP**. Besser: im Router eine feste Adresse für den Container reservieren, dann ändert sie sich nie.
3. **Den Container noch nicht starten.** Erst unter *Options* → *Features* die Haken bei **Nesting** und **keyctl** setzen. Ohne Nesting läuft Docker im Container nicht. Das ist der häufigste Stolperstein.
4. *Options* → *Start at boot* → **Ja**.
5. Container starten.

### Oder per Befehl auf dem Proxmox-Host

Passe Nummer (`200`), Speicher (`local-lvm`) und Netzwerk an. Den genauen Namen der Vorlage zeigt `pveam available --section system`:

```sh
pveam update
pveam download local ubuntu-24.04-standard_24.04-2_amd64.tar.zst
pct create 200 local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst \
  --hostname steuy --cores 2 --memory 2048 --swap 512 \
  --rootfs local-lvm:16 --unprivileged 1 \
  --features nesting=1,keyctl=1 --onboot 1 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp
pct start 200
```

> **Speicher:** Docker verwendet im Container das Dateisystem des Containers. Auf einem Speicher mit **ZFS** kann das Probleme machen. Am zuverlässigsten läuft es auf `local-lvm` oder einem Verzeichnis-Speicher (ext4).

## Schritt 2: Installieren

Öffne die Konsole des Containers (Proxmox → Container → *Console*, oder `pct enter 200` auf dem Host), melde dich als `root` an und gib ein:

```sh
apt-get update && apt-get install -y curl && curl -fsSL https://raw.githubusercontent.com/faolan-exe/Steuy/main/scripts/lxc-installieren.sh -o install.sh && sh install.sh
```

Das war's. Das Skript installiert Docker und den Webserver nginx, lädt steuy nach `/opt/steuy`, erzeugt zufällige Zugangsdaten, baut und startet alles und prüft am Ende, ob steuy antwortet. Beim ersten Mal dauert das einige Minuten, vor allem das Bauen. Du siehst jeden Schritt.

Wer lieber erst lesen möchte, was das Skript tut: mit `curl ... -o install.sh` laden, mit `less install.sh` lesen, dann `sh install.sh`.

## Schritt 3: Loslegen

Am Ende zeigt das Skript eine Adresse an:

```
 Fertig! steuy läuft.

   Öffne im Browser:   http://192.168.1.50
```

Gib sie im Browser ein. Der Einrichtungsassistent fragt nach deinen Firmendaten, prüft kurz, ob die Kleinunternehmerregelung für dich passt, und legt deinen Zugang an.

> **Die Verbindung ist nicht verschlüsselt.** Nutze diese Adresse nur in deinem eigenen Netzwerk (Heimnetz, Büro). Wie du steuy sicher von unterwegs erreichst, steht unten.

> **Solange das Repository privat ist**, funktioniert der Download per `curl` nicht. Dann den Code von Hand in den Container kopieren, per `scp` von deinem Rechner:
>
> ```sh
> # auf deinem Rechner, im Ordner mit dem steuy-Code
> COPYFILE_DISABLE=1 tar czf steuy.tar.gz --exclude=.git --exclude=.venv --exclude=instance --exclude=.env .
> scp steuy.tar.gz root@<IP-des-Containers>:/root/
> # im Container
> mkdir -p /opt/steuy && tar xzf /root/steuy.tar.gz -C /opt/steuy && sh /opt/steuy/scripts/lxc-installieren.sh
> ```
>
> Das Skript erkennt den vorhandenen Code in `/opt/steuy` und nutzt ihn.

## Danach

### Sichern

Zwei Ebenen, am besten beide:

1. **Proxmox-Sicherung des ganzen Containers:** Datacenter → *Backup* → Job für den Container anlegen (Modus *Snapshot*, täglich). Damit lässt sich der Container komplett zurückholen.
2. **Sicherung der Daten mit steuy:** Datenbank und alle Belege in einen Ordner, täglich per Cron:

```sh
apt-get install -y cron
mkdir -p /var/backups/steuy
cat > /etc/cron.d/steuy-sicherung <<'EOF'
0 2 * * * root cd /opt/steuy && scripts/docker-sicherung.sh /var/backups/steuy >> /var/log/steuy-sicherung.log 2>&1
EOF
```

Die Sicherung gehört zusätzlich **auf einen anderen Rechner oder Speicher**. Zurückspielen und Details: [betrieb.md](betrieb.md).

Den `SECRET_KEY` aus `/opt/steuy/.env` solltest du dir im Passwortmanager aufheben (`grep SECRET_KEY /opt/steuy/.env`). Ohne ihn lassen sich gespeicherte Zwei-Faktor- und E-Mail-Zugangsdaten nach einer Wiederherstellung nicht mehr lesen.

### Updaten

Einfach: **Einstellungen → Update**. steuy sucht auf GitHub nach der neuesten Version, zeigt, was neu ist und was behoben wurde, und aktualisiert auf Knopfdruck (mit Sicherung davor, siehe [release.md](release.md)). Von Hand geht es so:

```sh
cd /opt/steuy
scripts/docker-sicherung.sh /var/backups/steuy     # erst sichern
sh scripts/lxc-installieren.sh                     # holt den neuen Stand, baut und startet neu
```

Das Skript ist wiederholbar und lässt `.env`, Daten und Webserver-Einstellungen unangetastet. Datenbank-Änderungen laufen beim Start automatisch.

### Von unterwegs erreichen (HTTPS mit eigener Domain)

Voraussetzungen: eine Domain (z. B. `buchhaltung.example.de`), die auf deinen Router zeigt, und im Router die Ports **80** und **443** auf den Container weitergeleitet.

```sh
sed -i 's/server_name _;/server_name buchhaltung.example.de;/' /etc/nginx/sites-available/steuy
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d buchhaltung.example.de
```

Certbot holt das Zertifikat und stellt nginx auf HTTPS um. Danach in `/opt/steuy/.env` ergänzen und neu starten:

```
SESSION_COOKIE_SECURE=1
BASIS_URL=https://buchhaltung.example.de
```

```sh
cd /opt/steuy && docker compose up -d
```

> **Sicherheit:** Eine Buchhaltung gehört nicht ungeschützt ins Internet. Schalte unter *Profil → Zwei-Faktor-Anmeldung* die 2FA ein und nutze starke Passwörter. Wer nur selten von unterwegs braucht, ist mit einem VPN (z. B. WireGuard oder Tailscale) besser beraten als mit offenen Ports.

## Wenn etwas nicht klappt

| Problem | Lösung |
|---|---|
| Skript meldet „Compose-Plugin konnte nicht installiert werden“ | `docker compose version` muss Version 2 zeigen. Ist Docker aus den Ubuntu-Paketen (`docker.io`), installiert das Skript `docker-compose-v2` nach, sonst das Plugin aus dem Docker-Archiv. Klappt beides nicht, `docker-compose-plugin` nach [docs.docker.com](https://docs.docker.com/engine/install/) von Hand installieren. |
| Skript meldet „Docker startet nicht“ | Im Container unter *Options → Features* **Nesting** und **keyctl** aktivieren, Container neu starten, Skript noch einmal ausführen. |
| Docker-Fehler mit `permission denied` bei `sysctl` oder `AppArmor` in einem Ubuntu-Container | Kann an der Kombination aus Proxmox, AppArmor und der Docker-Version liegen. Auf dem Proxmox-Host in `/etc/pve/lxc/<Nummer>.conf` die Zeile `lxc.apparmor.profile: unconfined` ergänzen, Container neu starten. Das lockert die Abschottung des Containers, nutze es nur, wenn nichts anderes hilft. |
| Bauen bricht ab oder wird „Killed“ | Zu wenig Arbeitsspeicher. Dem Container vorübergehend 3 GB geben. |
| Seite nicht erreichbar | Im Container `cd /opt/steuy && docker compose ps` zeigt, ob `app` und `db` *healthy* sind. Logs mit `docker compose logs app`. Webserver mit `systemctl status nginx` prüfen. |
| Belege lassen sich nicht hochladen („413“) | Die nginx-Einstellung wurde geändert. In `/etc/nginx/sites-available/steuy` muss `client_max_body_size 100m;` stehen. |
| Anmeldung klappt nicht nach dem Umstieg auf HTTPS | `SESSION_COOKIE_SECURE=1` darf nur gesetzt sein, wenn du wirklich über `https://` zugreifst. |
| Meldung „SECRET_KEY fehlt“ | Die Datei `/opt/steuy/.env` fehlt oder ist leer. Das Skript noch einmal auszuführen legt sie neu an. Bei einer Wiederherstellung die alte `.env` zurückkopieren. |

## Deinstallieren

Alles löschen, inklusive Daten (nicht rückgängig zu machen):

```sh
cd /opt/steuy && docker compose down -v
```

Oder einfach den Container in Proxmox löschen.
