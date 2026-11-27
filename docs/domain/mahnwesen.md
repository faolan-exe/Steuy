# Mahnwesen

Fachliche Vorgabe von Philipp: Das Mahnwesen gehört in Version 1. Keine Rechnung soll in Vergessenheit geraten (`docs/ziel.md`, Punkt 8).

## Stufen

Drei Stufen. Bezeichnung, Abstände und Texte sind in den Einstellungen änderbar:

| Stufe | Standard-Bezeichnung | Fällig (Standard) | Neue Zahlungsfrist (Standard) |
|---|---|---|---|
| 1 | Zahlungserinnerung | 7 Tage nach Fälligkeit der Rechnung | 7 Tage |
| 2 | 1. Mahnung | 14 Tage nach der Zahlungserinnerung | 7 Tage |
| 3 | 2. Mahnung | 14 Tage nach der 1. Mahnung | 7 Tage |

Die Standardabstände stammen aus Philipps Anforderungsliste (MA-02).

- Eine Stufe ist **fällig**, wenn die Rechnung noch offen oder teilbezahlt ist, keine Mahnsperre besteht, die vorherige Stufe erstellt wurde und der Abstand seit der Fälligkeit (Stufe 1) bzw. seit der vorherigen Mahnung abgelaufen ist.
- Nach Stufe 3 schlägt das Tool keine weitere Stufe vor.
- Die Mahnung nennt Rechnungsnummer und -datum, den **offenen Betrag** zum Erstellungszeitpunkt, die neue Frist und enthält einen QR-Code über den offenen Betrag.
- Zahlungseingang stoppt den Mahnlauf automatisch: Bezahlte Rechnungen erscheinen nicht mehr.
- Eine Mahnung wird beim Erstellen als PDF abgelegt und ist danach unveränderlich, wie Rechnungen.
- Philipps Vorgabe (27.11.2026): Versehentlich erstellte Mahnungen müssen weg können.
  - **Löschen**, solange sie nie verschickt wurde (auch kein fehlgeschlagener Versuch). Das Protokoll hält Stufe, Betrag und Prüfsumme fest, die PDF-Datei bleibt in der Ablage.
  - **Zurückziehen**, wenn sie schon verschickt wurde: Sie bleibt mit PDF und Versandnachweis erhalten, ist als zurückgezogen markiert, zählt nicht mehr als Stufe, erscheint nicht mehr im Kundenportal und lässt sich nicht mehr senden. Die Stufe kann danach neu erstellt werden.
  - Beides nur für die jüngste gültige Mahnung einer Rechnung, damit die Reihenfolge der Stufen stimmt. Die Datenbank erlaubt nur genau diese Änderungen.

## Text und Vorlagen

- Jede Stufe hat einen vorgefertigten Brieftext mit Anrede (Einstellungen → Mahnwesen, änderbar).
- Beim Erstellen öffnet sich eine eigene Seite: Dort wählst du einen der drei Stufentexte, eine eigene Vorlage oder „Eigenen Text schreiben“ und kannst den Text frei ändern. Eine PDF-Vorschau zeigt das Schreiben, bevor es unveränderlich abgelegt wird.
- Einen geänderten Text kannst du als eigene Vorlage unter einem Namen speichern. Löschen geht in den Einstellungen.
- Platzhalter: `{nummer}`, `{rechnungsdatum}`, `{faellig}`, `{frist}`, `{betrag}` (offener Rechnungsbetrag), `{gesamt}` (mit Verzugspauschale), `{pauschale}` (Satz zur Pauschale, leer ohne Pauschale).
- Ist die Stufe laut Zeitplan noch nicht dran, zeigt die Seite, ab wann sie fällig wäre. Erstellen geht trotzdem.

## Verzugspauschale (40 €)

- Ab der zweiten Stufe kann die Pauschale von 40 € nach § 288 Abs. 5 BGB dazukommen. Sie steht als eigene Zeile unter dem offenen Betrag, der QR-Code und der Überweisungstext nennen den Gesamtbetrag.
- Philipps Vorgabe (27.11.2026): Ab Stufe 2 ist sie standardmäßig dabei, auch beim automatischen Mahnen. Wer sie bei Stufe 2 abwählt, hat sie auch bei Stufe 3 abgewählt. Verbraucher schulden sie nach § 288 Abs. 5 BGB nicht, deshalb warnt die Seite bei Kontakten vom Typ Person.
- Stufe 1 droht die Verzugskosten (Pauschale und Zinsen) schon an, Stufe 2 und 3 kündigen weitere Kosten an.
- Die Pauschale verändert die Rechnung nicht. Zahlt der Kunde sie, wird sie als eigene Einnahme erfasst.

## Mahnsperre

- Je Rechnung oder je Kontakt, z. B. bei vereinbarter Ratenzahlung oder Stammkunden. Mit optionalem Grund.
- Gesperrte Rechnungen erscheinen nicht als „Mahnung fällig“, bleiben aber offen.

## Erinnerung

- Fällige Mahnstufen erscheinen in „Zu prüfen“ und auf dem Dashboard.
- Fällige Mahnungen stehen in der wöchentlichen E-Mail-Zusammenfassung.

## Bewusst noch nicht (Version 1.x)

- Verzugszinsen (Basiszinssatz + 5 bzw. 9 Prozentpunkte, § 288 BGB)
- Mahngebühren als eigene Position

## Offen / zu prüfen

- [ ] Verzug tritt nach § 286 Abs. 3 BGB spätestens 30 Tage nach Fälligkeit und Zugang ein, bei Verbrauchern nur mit Hinweis auf der Rechnung. Soll die Rechnung diesen Hinweis standardmäßig tragen?
