# Rundgang durch steuy

Bei der Einrichtung fragt steuy zwei Dinge: **Wie fit bist du in Buchhaltung?** (Kompletter Anfänger, Bereits mal gemacht, Experte) und **Hast du schon mit steuy gearbeitet?** (Ja, Nein). Daraus entsteht ein Rundgang, bei dem man immer nur auf „Weiter“ klicken muss.

| Antworten | Was passiert |
|---|---|
| Anfänger oder „Bereits mal gemacht“, neu bei steuy | Der Rundgang startet sofort. |
| Experte | steuy fragt, ob der Rundgang trotzdem gestartet werden soll. |
| Schon mit steuy gearbeitet | steuy fragt, ob der Rundgang übersprungen werden soll. |
| Experte und schon mit steuy gearbeitet | steuy fragt, ob er trotzdem gezeigt werden soll. |

Der Rundgang läuft als Fenster unten rechts auf den echten Seiten. Jeder Schritt öffnet die passende Seite, hebt das Element hervor, um das es geht, und erklärt, was es ist, wo es steht und warum man es braucht. „Zurück“, „Weiter“ und „Beenden“ gibt es in jedem Schritt. Im Profil lässt sich die Stufe ändern und der Rundgang jederzeit neu starten.

- **Kompletter Anfänger:** alle Schritte plus Grundlagen (Kleinunternehmer, EÜR, Zuflussprinzip) und zusätzliche Erklärungen.
- **Bereits mal gemacht und Experte:** dieselben Seiten, kürzer und ohne Grundlagen.
- Wer ein Recht nicht hat (z. B. Einstellungen), sieht die zugehörigen Schritte nicht.

Die Schritte stehen in `app/domain/rundgang.py` (Titel, Text, Seite, hervorgehobenes Element, Zusatztext für Einsteiger). Ein Test prüft, dass jeder Schritt auf eine erreichbare Seite führt und die wichtigsten Funktionen vorkommen.
