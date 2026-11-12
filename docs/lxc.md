# Buchhaltungssoftware selbst hosten: steuy in einem Proxmox-LXC-Container installieren

Am schnellsten mit dem **Proxmox-Helper-Skript**: ein Befehl auf dem Proxmox-Host, und steuy läuft in einem eigenen Container. Wer den Container lieber selbst anlegt, folgt den drei Schritten weiter unten.

## Am schnellsten: ein Befehl auf dem Proxmox-Host

Öffne die Shell des Proxmox-Hosts (Proxmox-Oberfläche → dein Server → *Shell*, oder per SSH als `root`) und gib ein:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/faolan-exe/Steuy/main/scripts/proxmox-installieren.sh)"
```

Das Skript zeigt einen Vorschlag (nächste freie Nummer, 2 Kerne, 2 GB RAM, 16 GB Festplatte, DHCP, Ubuntu 24.04). Du übernimmst ihn mit Enter oder legst unter *Selbst festlegen* Nummer, Hostname, Größe, Speicher, Netzwerk-Bridge, eine feste Adresse und das System (Ubuntu 24.04, Debian 12 oder 13) selbst fest. Danach läuft alles von allein:

1. Vorlage für das System laden (falls noch nicht vorhanden)
2. Container anlegen: unprivilegiert, mit **Nesting** und **keyctl** (ohne die läuft Docker nicht), Start beim Booten, Markierung `steuy`
3. Container starten und warten, bis er im Internet ist
4. steuy im Container installieren, mit demselben Skript wie in Schritt 2 unten
5. Adresse, Konsolenbefehl und ein zufälliges root-Passwort anzeigen und die Adresse in die *Notes* des Containers schreiben

Am Ende siehst du:

```
 steuy läuft in Container 105.

   Öffne im Browser:   http://192.168.1.77
   Konsole:            pct enter 105
   root-Passwort:      …
```

Bricht etwas ab, bleibt der Container zur Fehlersuche stehen und das Skript nennt die Befehle zum Nachsehen (`pct enter`) und Löschen (`pct destroy`). Gelöscht wird nie etwas ungefragt.

> **Erst lesen, dann ausführen:** `curl -fsSL https://raw.githubusercontent.com/faolan-exe/Steuy/main/scripts/proxmox-installieren.sh -o steuy-proxmox.sh`, mit `less steuy-proxmox.sh` ansehen, dann `bash steuy-proxmox.sh`.

<details>
<summary>Ohne Rückfragen, z. B. für Ansible oder eigene Skripte</summary>

Alle Werte sind optional, nicht gesetzte nehmen den Vorschlag:

```sh
STEUY_JA=1 STEUY_CTID=210 STEUY_HOSTNAME=steuy STEUY_KERNE=2 STEUY_RAM=2048 STEUY_DISK=16 \
STEUY_SPEICHER=local-lvm STEUY_BRIDGE=vmbr0 STEUY_IP=192.168.1.50/24 STEUY_GATEWAY=192.168.1.1 \
STEUY_OS=ubuntu-24.04 bash steuy-proxmox.sh
```

| Variable | Vorschlag | Bedeutung |
|---|---|---|
| `STEUY_CTID` | nächste freie Nummer | Nummer des Containers |
| `STEUY_HOSTNAME` | `steuy` | Name im Netzwerk |
| `STEUY_KERNE` / `STEUY_RAM` / `STEUY_DISK` | 2 / 2048 MB / 16 GB | Größe |
| `STEUY_SPEICHER` | erster LVM-Thin-Speicher | Speicher für die Festplatte |
| `STEUY_BRIDGE` | `vmbr0` | Netzwerk-Bridge |
| `STEUY_IP` / `STEUY_GATEWAY` | `dhcp` | feste Adresse mit Netzmaske und Gateway |
| `STEUY_OS` | `ubuntu-24.04` | oder `debian-12`, `debian-13` |

</details>

## Oder Schritt für Schritt

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
