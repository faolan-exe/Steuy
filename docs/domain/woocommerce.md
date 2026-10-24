# WooCommerce-Anbindung

## Grundsatz

Der Abruf erzeugt **Rechnungsentwürfe** (siehe „Rechnungen für Shop-Bestellungen“). Finalisiert wird nach Freigabe unter „Zu prüfen“ oder automatisch im Auto-Modus. Die Einnahme entsteht über die Zahlung an der Rechnung mit dem Zahlungsdatum aus dem Shop (Zuflussprinzip).

## Umsetzungsstand

| Teil | Stand |
|---|---|
| Verbindung (URL, Consumer Key/Secret verschlüsselt), Test, Abruf per Knopf und stündlich (`flask shop-abruf`, Docker-Dienst `zeitplan`) | umgesetzt |
| Bestellungen → Kontakt (per E-Mail zugeordnet) und Rechnungsentwurf mit Positionen, Versand und Gebühren | umgesetzt |
| Freigabe: Finalisieren, Versand per Mail, Zahlung übernehmen; Auto-Modus | umgesetzt |
| Zahlung aus dem Shop, auch nachträglich (Vorkasse) | umgesetzt |
| Erstattungen, Umsatzsteuer im Shop, abweichende Summen | als Hinweis unter „Zu prüfen“, keine automatische Korrektur |
| Rückweg zum Shop (Status, PDF), Produkte als Artikel, automatische Rechnungskorrektur bei Erstattung | später |

## Verbindung

- Eine Shop-Verbindung je Installation (URL, REST-API-Schlüssel), verschlüsselt gespeichert oder als Umgebungsvariable. Für den Rückweg (Status, Rechnungs-PDF) braucht der Schlüssel Schreibrechte. Ohne Rückweg reicht ein Schlüssel mit Leserechten.
- Abruf per WooCommerce REST API, zunächst manuell per Button oder Cronjob. Webhooks erst, wenn der Polling-Weg stabil läuft.

## Rechnungen für Shop-Bestellungen

Geklärt mit Philipp am 2026-10-21.

- **Das Tool schreibt die Rechnungen** mit seinem fortlaufenden Nummernkreis. Der Shop soll keine eigenen Rechnungen erzeugen (Rechnungs-Plugin abschalten), damit es keine doppelten Nummern gibt.
- **Zeitpunkt je Zahlungsart:**
  - Vorkasse per Überweisung: Rechnung sofort bei Bestellung, mit QR-Code zum Bezahlen. Die Einnahme entsteht erst beim Zahlungseingang.
  - PayPal, Karte und andere Sofortzahlungen: Rechnung, sobald die Bestellung bezahlt ist.
- **Versand an den Kunden:** Standard ist, dass die Rechnung in „Zu prüfen“ auf Freigabe wartet und mit einem Klick verschickt wird. In den Einstellungen lässt sich ein **Auto-Modus** einschalten, der sofort verschickt.

## Synchronisierung

Vollständig in beide Richtungen, wenn ein Shop angebunden ist:

| Richtung | Was |
|---|---|
| Shop → Tool | Bestellungen, Erstattungen (erzeugen automatisch eine Rechnungskorrektur), Kunden als Kontakte, Produkte als Artikel |
| Tool → Shop | Status „bezahlt“, wenn die Zahlung im Tool markiert wird; Rechnungs-PDF an der Bestellung, damit der Kunde sie im Kundenkonto sieht |

Für den Rückweg braucht der API-Schlüssel Schreibrechte (siehe „Verbindung“).

## Was importiert wird

| WooCommerce | In steuy | Datum |
|---|---|---|
| Vorkasse (`bacs`), auch „in Wartestellung“ | Rechnungsentwurf mit QR-Code | Rechnungsdatum = Bestelldatum |
| Bestellung bezahlt (`processing`/`completed` mit `date_paid`) | Rechnungsentwurf, nach Freigabe Zahlung | Zahlungsdatum = `date_paid` |
| Erstattung | Hinweis unter „Zu prüfen“ | |
| Bestellung ohne Zahlung, storniert, fehlgeschlagen | nichts | |

Zahlungsarten: `bacs` → Überweisung, PayPal-Gateways → PayPal, Stripe und WooCommerce Payments → Karte, `cod` → Bar, alles andere → Sonstige.

## Idempotenz

- Eindeutig über `(quelle, externe_id)`. Ein zweiter Import derselben Bestellung erzeugt keine zweite Buchung.
- Original-Payload in `shop_bestellung.rohdaten` speichern.
- Ändert sich eine Bestellung nach dem Import (z. B. Teilerstattung), wird eine neue Buchung erzeugt, nie die alte geändert.

## Zahlungsgebühren

- Gebühren von Stripe, PayPal usw. sind Betriebsausgaben und stehen meist **nicht** zuverlässig in den Bestelldaten.
- Quelle dafür: Abrechnungs-Export des Zahlungsanbieters (CSV). Eigener Importer pro Anbieter, Ausgabe-Kategorie „Gebühren“.
- Achtung Zufluss: Bei Auszahlung gesammelt abzüglich Gebühren trotzdem Einnahme brutto und Gebühr als Ausgabe buchen, nicht nur den Netto-Auszahlungsbetrag.

## Offen / zu prüfen

- [ ] **Lieferdatum auf Shop-Rechnungen:** steuy setzt das Bestelldatum als Lieferdatum vor, änderbar vor der Freigabe. Klären: Reicht das, oder muss das tatsächliche Versanddatum stehen (der Shop kennt es oft nicht)?
- [ ] Welche Zahlungsanbieter sind im Einsatz?
- [ ] Ist `date_paid` bei allen Zahlarten gesetzt (z. B. Vorkasse per Überweisung)?
- [x] Rechnungen: Das Tool erzeugt sie, nicht WooCommerce (siehe „Rechnungen für Shop-Bestellungen“).
- [ ] Rechnungs-PDF an die Bestellung hängen: Gibt die WooCommerce REST API das ohne Zusatz-Plugin her? Sonst Link in einer Bestellnotiz für den Kunden.
- [ ] Shop → Tool bei Produkten: Was gilt, wenn ein Artikel im Tool und im Shop unterschiedlich geändert wird? Vorschlag: Der Shop ist führend für Produkte.
