# Neue Version veröffentlichen

steuy prüft unter *Einstellungen → Update* auf GitHub, ob es ein neueres **Release** gibt, und zeigt dessen Beschreibung an. Damit das funktioniert:

1. **Version erhöhen** in `app/version.py` und `pyproject.toml` (gleiche Nummer, Form `X.Y.Z`; ein Test prüft, dass beide übereinstimmen). Kleine Fehlerkorrekturen erhöhen die letzte Stelle, neue Funktionen die mittlere.
2. Per PR nach `main` bringen, wie jede Änderung.
3. **Release anlegen** auf GitHub: *Releases → Draft a new release*, Tag `vX.Y.Z` (z. B. `v0.3.0`) auf `main`. Oder per Befehl:

   ```sh
   gh release create v0.3.0 --target main --title "steuy 0.3.0" --notes-file notizen.md
   ```

4. **Beschreibung** (die sieht der Nutzer vor dem Update), in dieser Form:

   ```markdown
   ## Neu
   - Lieferschein aus der Rechnung
   - Ziel auf dem Dashboard anpassen

   ## Behoben
   - Summe im Editor wurde erst nach dem Speichern angezeigt

   ## Geändert
   - Dashboard neu aufgeteilt
   ```

   Die Überschriften „Neu“, „Behoben“ und „Geändert“ werden erkannt, jede Zeile mit `-` wird ein Eintrag. Ohne Überschriften erscheint der Text als „Hinweise“.

Hinweise:

- Das Repository muss **öffentlich** sein oder die Installation einen Token haben (`UPDATE_TOKEN` in der `.env`, nur Leserechte auf das Repository), sonst findet steuy keine Releases.
- Auf Releases mit Tags wie `v1.0.0-rc1` reagiert steuy nicht (nur `vX.Y.Z`).
- Ein anderes Repository (z. B. ein Fork) trägst du in der `.env` als `UPDATE_REPO=besitzer/name` ein.

## So läuft das Update auf dem Server (LXC)

Das Installationsskript richtet einen Dienst ein (`steuy-update.path` und `steuy-update.service`). Der Knopf „Updaten“ legt nur eine Anfrage in `/opt/steuy/update/` ab. Der Dienst führt dann `scripts/update-ausfuehren.sh` aus:

1. Sicherung von Datenbank und Belegen nach `/var/backups/steuy`.
2. Die Version von GitHub laden und prüfen (muss steuy mit genau dieser Versionsnummer sein).
3. Den alten Programmstand als `programm-vor-vX.Y.Z.tar.gz` sichern und den Code ersetzen (`.env` und Daten bleiben).
4. Neu bauen, starten, auf `/gesund` warten. Klappt etwas nicht, stellt das Skript den alten Stand her und meldet den Fehler in den Einstellungen.

Der Fortschritt steht in `/opt/steuy/update/status.json` und wird in den Einstellungen angezeigt. Wer steuy ohne dieses Skript betreibt (reines Docker, Entwicklung), sieht den Hinweis auf `git pull && docker compose up -d --build`.
