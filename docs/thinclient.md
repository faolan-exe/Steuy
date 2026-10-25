# steuy auf einem Thin Client installieren (ohne Vorkenntnisse)

Diese Anleitung bringt steuy auf einen kleinen, gebrauchten Rechner, zum Beispiel einen **Dell Wyse 5070**. Du brauchst keine Linux-Kenntnisse: Jeder Schritt sagt, was du klickst oder tippst. Rechne mit etwa einer Stunde.

> Getestet ist das Installationsskript auf Debian und Ubuntu (in Containern). Auf einem echten Thin Client läuft derselbe Ablauf, die Bildschirme beim Installieren von Debian können je nach Version leicht anders aussehen. Wenn etwas nicht passt, melde es bitte als Issue.

## Was du brauchst

| Was | Hinweis |
|---|---|
| **Thin Client oder Mini-PC** | Empfohlen: Wyse 5070 mit mindestens 4 GB RAM und einer SSD ab 32 GB. Ein Wyse 3040 geht auch, ist aber knapp (siehe [Mindestanforderungen](../README.md#mindestanforderungen)). |
| **USB-Stick** | mindestens 4 GB. Wird dabei komplett gelöscht. |
| **Bildschirm, Tastatur** | nur für die Installation, danach nicht mehr. Der Wyse hat DisplayPort, ggf. einen Adapter auf HDMI nehmen. |
| **Netzwerkkabel** | Der Thin Client hängt per Kabel an deinem Router oder Switch. |
| **Dein normaler Computer** | zum Vorbereiten des USB-Sticks und später zum Benutzen von steuy im Browser. |
| **Externe Festplatte oder USB-Stick** | für Sicherungen (sehr empfohlen). |

## Schritt 1: Installations-Stick vorbereiten (auf deinem Computer)

1. Lade das Debian-Abbild herunter: auf **debian.org** auf „Download“ klicken. Du bekommst eine Datei wie `debian-13.x.x-amd64-netinst.iso` (etwa 700 MB).
2. Lade das Programm **balenaEtcher** (etcher.balena.io) herunter und installiere es. Es gibt es für Windows, macOS und Linux.
3. Stecke den USB-Stick ein, starte balenaEtcher:
   - **Flash from file:** die Debian-Datei wählen
   - **Select target:** den USB-Stick wählen (genau hinschauen, nicht die falsche Festplatte!)
   - **Flash!** klicken und warten, bis „Flash Complete“ erscheint.

## Schritt 2: Thin Client vom USB-Stick starten

1. Bildschirm, Tastatur, Netzwerkkabel und den USB-Stick an den Thin Client anschließen.
2. Einschalten und sofort mehrmals **F12** drücken. Es erscheint ein Startmenü.
3. Den USB-Stick auswählen (heißt meist „USB“ oder trägt den Namen des Sticks) und Enter drücken.

Wenn kein Startmenü kommt oder der Stick fehlt:
- Beim Einschalten **F2** drücken, das öffnet das BIOS. Fragt es nach einem Passwort, ist es bei Wyse-Geräten oft `Fireport`.
- Dort unter *Boot* das Starten von USB erlauben (Optionen wie „USB Boot“ oder „Boot from USB“ einschalten), speichern, neu starten und wieder F12 drücken.

## Schritt 3: Debian installieren

Im Menü des Sticks **„Install“** oder **„Graphical install“** wählen, beides geht. Dann der Reihe nach:

| Frage | Antwort |
|---|---|
| Sprache, Land, Tastatur | Deutsch, Deutschland, Deutsch |
| Rechnername (Hostname) | `steuy` |
| Domain | leer lassen |
| Root-Passwort | ein **langes, eigenes Passwort**. Notiere es im Passwortmanager. |
| Neuer Benutzer, Name und Passwort | z. B. `verwaltung`, ebenfalls ein eigenes Passwort |
| Festplatte partitionieren | „Geführt – vollständige Festplatte verwenden“, die eingebaute SSD wählen (**nicht** den USB-Stick), „Alle Dateien auf eine Partition“, „Änderungen übernehmen“, „Ja“ |
| Paketmanager-Spiegel | Deutschland, `deb.debian.org` |
| Softwareauswahl | **Nur** „SSH-Server“ und „Standard-Systemwerkzeuge“ ankreuzen. **Keine** Desktop-Umgebung (Haken bei „Debian desktop environment“ und „GNOME“ entfernen). |
| GRUB-Bootloader installieren | Ja, auf die eingebaute SSD |

Am Ende „Weiter“: Der Rechner startet neu. Jetzt den USB-Stick abziehen.

Nach dem Neustart siehst du nur Text und `steuy login:`. Das ist richtig so, steuy braucht keinen Desktop.

## Schritt 4: Feste Adresse im Heimnetz

Damit du steuy immer unter derselben Adresse findest, soll der Router dem Thin Client immer dieselbe IP-Adresse geben.

1. Am Thin Client als `root` mit dem Root-Passwort anmelden.
2. Die aktuelle Adresse anzeigen:
   ```bash
   hostname -I
   ```
   Die erste Zahl, z. B. `192.168.178.40`, ist die Adresse. Notieren.
3. Im Router festlegen, dass das Gerät diese Adresse behält:
   - **FRITZ!Box:** *Heimnetz → Netzwerk →* beim Gerät `steuy` auf den Stift klicken → **„Diesem Netzwerkgerät immer die gleiche IPv4-Adresse zuweisen“** anhaken → OK.
   - **Andere Router:** suche nach „DHCP-Reservierung“ oder „feste IP zuweisen“.

## Schritt 5: steuy installieren

Weiterhin am Thin Client als `root` angemeldet diesen einen Befehl abtippen und Enter drücken:

```bash
apt-get update && apt-get install -y curl && curl -fsSL https://raw.githubusercontent.com/faolan-exe/Steuy/main/scripts/lxc-installieren.sh -o install.sh && sh install.sh
```

Das Skript installiert Docker und den Webserver, lädt steuy herunter, erzeugt zufällige Schlüssel und startet alles. Beim ersten Mal dauert das **10 bis 30 Minuten**, je nach Gerät und Internet. Der Name „lxc“ im Skript stört nicht, es funktioniert auch auf einem normalen Rechner.

Am Ende steht:

```
Fertig! steuy läuft.
   Öffne im Browser:   http://192.168.178.40
```

## Schritt 6: Im Browser einrichten

1. Auf deinem normalen Computer den Browser öffnen und die angezeigte Adresse eingeben, z. B. `http://192.168.178.40`.
2. Der **Einrichtungsassistent** fragt nach deiner Firma und legt dein Konto an. Danach startet auf Wunsch ein Rundgang durch alle Funktionen.
3. Ab jetzt brauchst du am Thin Client keinen Bildschirm und keine Tastatur mehr. Er kann irgendwo neben dem Router stehen, Hauptsache er bleibt eingeschaltet.

## Schritt 7: Sicherungen einrichten (wichtig!)

Buchhaltungsdaten musst du bis zu 10 Jahre aufbewahren. Ein Thin Client kann kaputtgehen. Deshalb täglich sichern, und zwar zusätzlich **auf ein zweites Gerät**.

### Tägliche Sicherung auf dem Thin Client

Als `root` am Thin Client (oder per SSH, siehe unten):

```bash
cat > /etc/cron.d/steuy-sicherung <<'EOF'
0 2 * * * root cd /opt/steuy && scripts/docker-sicherung.sh /var/backups/steuy >> /var/log/steuy-sicherung.log 2>&1
EOF
```

Jede Nacht um 2 Uhr entsteht unter `/var/backups/steuy` ein Ordner mit Datenbank und allen Belegen.

### Zusätzlich auf eine USB-Festplatte

1. Die USB-Festplatte anstecken und ihren Namen herausfinden:
   ```bash
   lsblk -f
   ```
   Such die Zeile mit der Größe deiner Festplatte, z. B. `sdb1` mit `ext4` oder `exfat`.
2. Einen Ordner anlegen und die Festplatte dort einhängen (`sdb1` durch deinen Namen ersetzen):
   ```bash
   mkdir -p /mnt/sicherung && mount /dev/sdb1 /mnt/sicherung
   ```
3. Die Sicherungen hinüberkopieren:
   ```bash
   cp -r /var/backups/steuy /mnt/sicherung/ && umount /mnt/sicherung
   ```

Mach das regelmäßig, z. B. einmal pro Woche, und bewahre die Festplatte an einem anderen Ort auf. Wie du eine Sicherung zurückspielst, steht in [betrieb.md](betrieb.md).

## Updates

In steuy unter **Einstellungen → Update**. steuy zeigt, was neu ist, sichert vorher und aktualisiert auf Knopfdruck.

Das Betriebssystem hältst du so aktuell (etwa einmal im Monat, als `root`):

```bash
apt-get update && apt-get upgrade -y
```

Oder automatisch:

```bash
apt-get install -y unattended-upgrades
```

## Bequemer: Per SSH statt am Bildschirm

Statt Bildschirm und Tastatur anzuschließen, kannst du dich von deinem Computer aus anmelden. Unter Windows, macOS und Linux im Terminal bzw. in der Eingabeaufforderung:

```bash
ssh verwaltung@192.168.178.40
```

Danach mit `su -` und dem Root-Passwort zum Administrator werden.

## Sicherheit

- steuy ist so nur **in deinem Heimnetz** erreichbar. Die Verbindung ist dort nicht verschlüsselt, das ist im eigenen Netz in Ordnung.
- **Stelle steuy nicht ungeschützt ins Internet** (keine Portfreigabe im Router). Für den Zugriff von unterwegs ist ein VPN am sichersten, z. B. das VPN der FRITZ!Box oder WireGuard. Alternativ HTTPS über einen Reverse Proxy, siehe [betrieb.md](betrieb.md).
- Nutze für steuy, Root und den Benutzer jeweils eigene, lange Passwörter und schalte in steuy die Zwei-Faktor-Anmeldung ein (Profil).

## Wenn etwas nicht klappt

| Problem | Lösung |
|---|---|
| Der Thin Client startet nicht vom Stick | BIOS mit F2 öffnen, USB-Boot erlauben, „Secure Boot“ testweise ausschalten. |
| Die Installation von Debian findet kein Netzwerk | Netzwerkkabel prüfen, am Router eine Netzwerkbuchse nutzen (kein WLAN). |
| Das steuy-Skript bricht mit einer Meldung ab | Die Meldung sagt, was zu tun ist. Danach den Befehl aus Schritt 5 einfach noch einmal ausführen, das ist ungefährlich. |
| Im Browser erscheint nichts | Stimmt die Adresse? Am Thin Client `hostname -I` prüfen. Laufen die Dienste? `cd /opt/steuy && docker compose ps` |
| Speicher voll (vor allem beim Wyse 3040) | Alte Sicherungen löschen oder auf die USB-Platte verschieben, alte Docker-Images aufräumen: `docker image prune -f` |
