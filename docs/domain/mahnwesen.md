# Mahnwesen

Fachliche Vorgabe von Philipp: Das Mahnwesen gehört in Version 1. Keine Rechnung soll in Vergessenheit geraten (`docs/ziel.md`, Punkt 8).

## Stufen

Drei Stufen, Bezeichnung, Abstände und Texte sind in den Einstellungen änderbar:

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

## Mahnsperre

- Je Rechnung oder je Kontakt, z. B. bei vereinbarter Ratenzahlung oder Stammkunden. Mit optionalem Grund.
- Gesperrte Rechnungen erscheinen nicht als „Mahnung fällig“, bleiben aber offen.

## Erinnerung

- Fällige Mahnstufen erscheinen in „Zu prüfen“ und auf dem Dashboard.
- Fällige Mahnungen stehen in der wöchentlichen E-Mail-Zusammenfassung.

## Bewusst noch nicht (Version 1.x)

- Verzugszinsen (Basiszinssatz + 5 bzw. 9 Prozentpunkte, § 288 BGB) und 40-€-Pauschale bei Firmenkunden
- Mahngebühren als eigene Position
- Automatischer Versand

## Offen / zu prüfen

- [ ] Verzug tritt nach § 286 Abs. 3 BGB spätestens 30 Tage nach Fälligkeit und Zugang ein, bei Verbrauchern nur mit Hinweis auf der Rechnung. Soll die Rechnung diesen Hinweis standardmäßig tragen?
