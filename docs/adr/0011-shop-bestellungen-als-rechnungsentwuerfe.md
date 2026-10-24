# 0011: Shop-Bestellungen werden Rechnungsentwürfe mit Freigabe

- Status: vorgeschlagen
- Datum: 2026-10-22

## Kontext

Laut Philipp schreibt steuy die Rechnungen für WooCommerce-Bestellungen (`docs/domain/woocommerce.md`). Die ältere Idee „Import als Buchungsentwürfe“ passt dazu nicht mehr. Shop-Daten sind nicht immer sauber (Steuer im Shop berechnet, Erstattungen, Summen), und das Lieferdatum kennt der Shop oft nicht.

## Entscheidung

- Der Abruf legt je relevanter Bestellung **Kontakt und Rechnungsentwurf** an, eindeutig über die Bestell-ID (`shop_bestellung`, Rohdaten gespeichert).
- **Freigabe unter „Zu prüfen“:** finalisieren, per Mail senden, Zahlung mit `date_paid` als Zahlungsdatum übernehmen. Der **Auto-Modus** erledigt das sofort, außer bei Auffälligkeiten.
- **Auffälligkeiten werden Hinweise, keine Automatik:** Erstattungen, Umsatzsteuer im Shop, Summen, die nicht aufgehen.
- Netzwerkzugriff mit `urllib`, nur über HTTPS, Schlüssel verschlüsselt gespeichert.

## Verworfene Alternativen

- **Rechnungen sofort finalisieren:** Fehler im Shop würden zu unveränderlichen Rechnungen mit vergebener Nummer.
- **Rechnungen aus dem Shop übernehmen:** doppelte Nummernkreise, kein PDF/A mit GiroCode.

## Folgen

- Jede Shop-Bestellung braucht standardmäßig einen Klick, das ist bewusst so.
- Rückweg zum Shop, Produktabgleich und automatische Rechnungskorrektur bei Erstattung brauchen noch Fachentscheidungen (Teil 2).
