# Nutzer, Rollen und Rechte

Fachliche Vorgabe von Philipp (2026-10-21): Eine Installation enthält genau ein Gewerbe (ADR 0007). Mehrere Personen arbeiten darin mit Rollen, deren Rechte einstellbar sind. Standardrechte und Umfang am 2026-10-21 bestätigt: Das Rollenmodell gehört komplett in Version 1.

## Rollen

| Rolle | Für wen |
|---|---|
| **Admin** | Inhaber des Gewerbes. Wird beim Einrichten angelegt. Es muss immer mindestens einen Admin geben. |
| **Buchhalter** | erledigt die laufende Buchhaltung, z. B. Partner oder Bürohilfe |
| **Mitarbeiter** | lädt Belege hoch, bereitet Angebote und Rechnungen vor |
| **Steuerberater** | sieht alles, ändert nichts, lädt Exporte herunter |

## Standardrechte

Der Admin kann die Rechte jeder Rolle außer Admin anpassen. Die Tabelle zeigt die Voreinstellung.

Fest und nicht einstellbar: „ansehen“ haben alle aktiven Nutzer. Einstellungen, Nutzerverwaltung und Jahresabschluss bleiben Admins vorbehalten, sonst könnte sich jemand mit dem Recht „Nutzer verwalten“ selbst zum Admin machen.

| Recht | Admin | Buchhalter | Mitarbeiter | Steuerberater |
|---|:-:|:-:|:-:|:-:|
| Dashboard, Listen und Belege ansehen | ✓ | ✓ | ✓ | ✓ |
| Belege hochladen, unverbuchte Belege löschen | ✓ | ✓ | ✓ | – |
| Kontakte und Artikel bearbeiten | ✓ | ✓ | ✓ | – |
| Angebote und Rechnungen als Entwurf anlegen | ✓ | ✓ | ✓ | – |
| Rechnungen finalisieren und versenden | ✓ | ✓ | – | – |
| Zahlungen erfassen, Gebühren zuordnen | ✓ | ✓ | – | – |
| Buchungen festschreiben und stornieren | ✓ | ✓ | – | – |
| EÜR und Auswertungen ansehen | ✓ | ✓ | – | ✓ |
| Export (ZIP für Steuerberater, CSV) | ✓ | ✓ | – | ✓ |
| Änderungsprotokoll ansehen | ✓ | ✓ | – | ✓ |
| Einstellungen (Firmendaten, Nummernkreise, Shop-Anbindung, Mahnstufen) | ✓ | – | – | – |
| Nutzer verwalten und Rechte ändern | ✓ | – | – | – |
| Geschäftsjahr abschließen | ✓ | – | – | – |

## Regeln

- Jeder Nutzer hat genau eine Rolle.
- Der letzte Admin kann weder gelöscht noch herabgestuft werden.
- Nutzer werden nie gelöscht, nur deaktiviert. Das Änderungsprotokoll verweist weiter auf sie.
- Änderungen an Rollen und Rechten stehen im Änderungsprotokoll.
- Jeder Zugang (außer dem letzten Admin) lässt sich mit Ablaufdatum anlegen, z. B. für den Steuerberater. Am Ablauftag selbst gilt er noch.
- Deaktivierte oder abgelaufene Nutzer verlieren sofort auch laufende Sitzungen.

## Offen / zu prüfen

- [x] Standardrechte bestätigt
- [x] Rollenmodell komplett in Version 1
- [ ] Anmeldung mit Zwei-Faktor-Authentifizierung: Pflicht für Admin und Buchhalter?
