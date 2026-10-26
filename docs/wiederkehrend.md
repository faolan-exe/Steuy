# Wiederkehrende Rechnungen: Abos und Dauerkunden automatisch abrechnen

Für alles, was du regelmäßig abrechnest (Abo, Wartungsvertrag, Miete, Hosting), legst du **einmal eine Vorlage** an. steuy erzeugt daraus zu jedem Termin eine Rechnung. Du findest die Vorlagen unter *Rechnungen → Wiederkehrende Rechnungen*.

## Vorlage anlegen

Zwei Wege:

1. **Aus einer vorhandenen Rechnung:** Rechnung öffnen und **„Wiederkehrend machen“** wählen. Kunde, Texte und Positionen werden übernommen.
2. **Neu:** *Wiederkehrende Rechnungen → Neue Vorlage*.

In der Vorlage stellst du ein:

| Einstellung | Bedeutung |
|---|---|
| **Wie oft** | jeden Monat, jedes Quartal, jedes halbe Jahr oder jedes Jahr |
| **Nächste Rechnung am** | der erste Termin. Sein Tag im Monat bleibt der Rhythmus (am 15. bleibt am 15.). Beim 29. bis 31. nehmen kürzere Monate ihren letzten Tag und kehren danach zum eingestellten Tag zurück. |
| **Ende** | optional. Nach diesem Datum entstehen keine Rechnungen mehr. |
| **Was passiert am Termin?** | siehe unten |
| **Aktiv** | ohne Haken ist die Vorlage pausiert |

Der **Abrechnungszeitraum** beginnt am Termin und endet am Tag vor dem nächsten Termin. Er steht automatisch als *Leistungszeitraum* auf der Rechnung (bei einer monatlichen Rechnung zum 1. November also 01.11. bis 30.11.).

## Platzhalter in den Texten

In Titel, Einleitung, Positionsbezeichnungen, Beschreibungen und Nachbemerkung kannst du Platzhalter nutzen, die beim Erzeugen durch den Zeitraum ersetzt werden:

| Platzhalter | Beispiel |
|---|---|
| `{monat}` | November 2026 |
| `{quartal}` | Q4 2026 |
| `{jahr}` | 2026 |
| `{zeitraum}` | 01.11.2026 bis 30.11.2026 |
| `{von}` und `{bis}` | 01.11.2026 und 30.11.2026 |

Beispiel: Die Position „Wartungsvertrag {monat}“ wird zu „Wartungsvertrag November 2026“.

## Was passiert am Termin?

- **Entwurf anlegen** (Standard, am sichersten): Du bekommst einen Rechnungsentwurf, prüfst ihn und schreibst ihn selbst fest. Entwürfe erscheinen im Dashboard unter „Zu prüfen“.
- **Automatisch festschreiben:** steuy vergibt die Rechnungsnummer und erzeugt das PDF. Danach lässt sich die Rechnung nicht mehr ändern. Versand machst du von Hand.
- **Festschreiben und per E-Mail schicken:** zusätzlich geht die Rechnung an die E-Mail-Adresse des Kunden. Dafür muss der E-Mail-Versand eingerichtet sein (*Einstellungen → E-Mail*) und der Kunde eine Adresse haben.

Fehlen Angaben (zum Beispiel die Anschrift), bleibt die Rechnung ein **Entwurf**, und die Vorlage zeigt den Grund. Schlägt nur der Mailversand fehl, bleibt die festgeschriebene Rechnung bestehen und du kannst sie von Hand verschicken.

## So läuft es ab

- Der Zeitplan-Dienst prüft **stündlich**, ob eine Vorlage fällig ist. Mit **„Jetzt prüfen“** geht es sofort.
- Wurde steuy länger nicht geprüft (Rechner aus), holt der nächste Lauf verpasste Termine nach, höchstens 12 auf einmal. Das Rechnungsdatum ist dann der Tag des Laufs, der Leistungszeitraum bleibt der des jeweiligen Termins.
- Der nächste Termin rückt **vor** dem Festschreiben weiter. Stürzt etwas ab, bleibt höchstens ein Entwurf, aber nie eine doppelte Rechnung.
- **Jetzt anlegen** erzeugt die nächste Rechnung sofort als Entwurf, zum Beispiel für eine Sonderabrechnung.
- Eine Vorlage mit erzeugten Rechnungen lässt sich nicht löschen (die Rechnungen sind unveränderlich), nur pausieren.

## Hinweise

- Steuerliche Fragen (z. B. zu Dauerleistungen und dem Leistungszeitraum) klärst du mit deiner Steuerberatung. steuy nimmt nur die Eingaben, die du in der Vorlage machst.
- Ändert sich der Preis, ändere die Vorlage. Bereits erzeugte Rechnungen bleiben, wie sie sind.
