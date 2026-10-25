# Scanner anbinden: Belege direkt vom Scanner übernehmen

Mit dem **Scan-Eingang** speichert dein Scanner Belege direkt auf dem Rechner, auf dem steuy läuft. steuy übernimmt sie dort etwa alle 30 Sekunden als Belege, mit Texterkennung und Vorschlägen für Betrag und Datum, genau wie beim Hochladen im Browser. Du legst den Beleg ein, drückst die Taste am Scanner, und er erscheint in steuy unter **Belege** und in **Zu prüfen**.

Beschrieben ist der **Brother ADS-1800W**. Der Ablauf passt auch zu anderen Scannern und Multifunktionsgeräten, die „Scan to Network“ (SMB/CIFS) oder „Scan to FTP“ können. Die Namen der Menüpunkte unterscheiden sich je nach Gerät und Firmware ein wenig.

## So funktioniert es

```
Scanner ──(Netzwerkfreigabe "scan")──► steuy-Rechner ──► steuy ──► Belege
```

Die Freigabe gehört zu steuy: Beim normalen Installieren (Docker) startet ein kleiner Samba-Container mit. Es ist **nichts extra zu installieren**. Er bleibt aus, bis du den Scan-Eingang in den Einstellungen einschaltest.

- Der Scanner schreibt eine Datei (PDF, JPG oder PNG) in die Freigabe.
- Sobald die Datei einige Sekunden unverändert ist, übernimmt steuy sie als Beleg und verschiebt die Datei in den Unterordner `verarbeitet/<Jahr-Monat>/`.
- Gleiche Datei schon vorhanden? Sie landet in `doppelt/`. Nicht lesbar oder zu groß (über 20 MB)? Sie landet in `fehler/`, und in steuy steht der Grund.
- Der Beleg selbst liegt unveränderlich in der Ablage von steuy. Die Dateien in den Unterordnern sind nur Arbeitskopien und werden nach 30 Tagen automatisch gelöscht.

## Schritt 1: In steuy einschalten

*Einstellungen → Scanner →* **„Scan-Eingang einschalten“** anhaken und speichern. Mit dem Haken ist auch die Netzwerkfreigabe an. Ausschalten geht genauso: Haken weg, speichern, die Freigabe schließt sich nach wenigen Sekunden.

Direkt darunter erscheinen die Angaben für den Scanner. Beim ersten Einschalten erzeugt steuy ein zufälliges Passwort:

| Angabe | Wert |
|---|---|
| Rechner (Host) | die Adresse, unter der du steuy aufrufst, z. B. `192.168.178.40` |
| Freigabename | `scan` (Netzwerkpfad `\\192.168.178.40\scan`) |
| Benutzername | `scanner` |
| Passwort | steht auf der Seite, **Neues Passwort erzeugen** tauscht es aus |

Der Rechner sollte eine **feste IP-Adresse** haben (siehe [thinclient.md](thinclient.md), Schritt 4), sonst findet der Scanner ihn nach einem Neustart vielleicht nicht mehr.

Der Punkt „Freigabe“ zeigt **läuft**, sobald der Samba-Container bereit ist (wenige Sekunden). Mit **„Jetzt prüfen“** musst du nicht auf die automatische Prüfung (alle 30 Sekunden) warten.

## Schritt 2: Profil im Brother ADS-1800W anlegen

1. Öffne die Weboberfläche des Scanners: die IP-Adresse des Scanners im Browser eingeben (sie steht am Display unter *Einstellungen → Netzwerk*). Melde dich an (das Standardkennwort steht auf dem Gerät, meist auf einem Aufkleber).
2. Gehe zu **Scannen → Scannen auf FTP/SFTP/Netzwerk/SharePoint** und wähle für ein Profil **Netzwerk**.
3. Trage ein:

   | Feld | Wert |
   |---|---|
   | Profilname | `steuy` (erscheint später am Display) |
   | Hostadresse / Netzwerkordnerpfad | `\\192.168.178.40\scan` (die Adresse von der Einstellungsseite) |
   | Benutzername | `scanner` |
   | Kennwort | das Passwort von der Einstellungsseite |
   | Speicherordner | leer lassen |
   | Dateiname | z. B. `Scan` (der Scanner hängt Datum und Nummer an) |
   | Dateityp | **PDF** (mehrseitig) |
   | Qualität | Farbe 200 dpi reicht für Belege, 300 dpi für schlechte Kassenbons |
   | Dokumentgröße | Auto |
   | Doppelseitiger Scan | je nach Beleg |

4. Speichern, dann den **Verbindungstest** (falls vorhanden) ausführen. Er sollte erfolgreich sein.
5. Am Gerät: **Scannen auf FTP/Netzwerk** wählen, das Profil `steuy` antippen, Beleg einlegen, Start.

Tipp: Lege das Profil auf eine **Kurzwahltaste** (am Display unter *Verknüpfungen*), dann reicht ein Tipp.

## Tipps für gute Ergebnisse

- **Mehrseitige Belege als eine PDF-Datei** scannen (Dateityp PDF mit mehreren Seiten). Bei JPG oder PNG entsteht pro Seite ein eigener Beleg.
- Kassenbons und Kontoauszüge mit **Farbe oder Graustufen** scannen, nicht schwarz-weiß: Die Texterkennung liest sie besser.
- Mehrere Belege hintereinander einlegen und mit der Funktion **„Dokument trennen“ / „Leerseite überspringen“** des Scanners trennen, falls dein Gerät das kann. So wird aus jedem Beleg eine eigene Datei.
- Sieh gelegentlich in *Zu prüfen* nach: Scans sind neue Belege, die du noch buchen musst.

## Wenn etwas nicht klappt

| Problem | Lösung |
|---|---|
| Der Verbindungstest am Scanner schlägt fehl | Zeigt die Einstellungsseite bei „Freigabe“ **läuft**? Stimmen Adresse, Benutzer `scanner` und Passwort? Im Zweifel **„Neues Passwort erzeugen“** und es im Scanner neu eintragen. |
| Der Scanner meldet „Zugriff verweigert“ oder kann sich gar nicht verbinden | Ältere Scanner sprechen nur die alte SMB-Version. In den Einstellungen **„Auch ältere Scanner zulassen“** anhaken und speichern. Aktuelle Firmware des Scanners einspielen ist besser. |
| `docker compose up` meldet, Port 445 sei belegt | Auf dem Rechner läuft schon ein Samba- oder Windows-Freigabedienst. Den anderen Dienst abschalten. Kann dein Scanner einen anderen Port, trägst du ihn in der `.env` als `SCAN_PORT=4450` ein. |
| Die Datei liegt in der Freigabe, steuy übernimmt sie nicht | In *Einstellungen → Scanner* eingeschaltet? Die Datei muss **PDF, JPG oder PNG** sein und einige Sekunden unverändert. Mit „Jetzt prüfen“ nachsehen, die Meldung nennt den Grund. |
| Beleg erscheint doppelt | Zweimal dieselbe Seite gescannt? Doppelte Dateien erkennt steuy am Inhalt und legt sie unter `doppelt/` ab. Verschiedene Scans derselben Seite sind für steuy verschiedene Dateien. |
| Es werden unleserliche Zahlen vorgeschlagen | Texterkennung ist nur ein Vorschlag. Prüfe Betrag und Datum beim Buchen. Bessere Qualität (300 dpi, gerade eingelegt) hilft. |

## Sicherheit

- Die Freigabe ist nur für den Benutzer `scanner` mit eigenem Zufallspasswort und nur **im Heimnetz** gedacht. Stelle Port 445 nie im Router ins Internet frei.
- Der Benutzer `scanner` kann nur in diesen einen Ordner schreiben und sich nirgends anmelden. Der Samba-Container läuft getrennt von der App und kennt weder die Datenbank noch die Belege.
- Ist der Scan-Eingang ausgeschaltet, läuft im Samba-Container kein Freigabedienst.
- steuy folgt keinen Verknüpfungen (Symlinks) im Ordner und übernimmt nur Dateien aus dem Ordner selbst und einer Unterebene.

## Ohne Docker

Läuft steuy ohne Docker, gibt es den Samba-Container nicht. Dann richtest du selbst einen Ordner ein, den dein Scanner erreicht (Samba oder FTP), setzt `SCAN_VERZEICHNIS=/pfad/zum/ordner` in der `.env` und startest zusätzlich zum Webserver den Dienst (z. B. als systemd-Dienst):

```bash
uv run flask scan-dienst
```

Alternativ ruft ein Cron-Job jede Minute `uv run flask scan-abruf` auf. Der Haken „Scan-Eingang einschalten“ in den Einstellungen gilt auch hier.
