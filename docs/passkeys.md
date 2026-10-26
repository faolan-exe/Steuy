# Anmelden mit Passkey

Mit einem **Passkey** meldest du dich per Fingerabdruck, Gesichtserkennung oder Geräte-PIN an, ohne Passwort und ohne Code. Der private Schlüssel bleibt in deinem Gerät oder Passwortmanager, steuy speichert nur den öffentlichen. Auch wer steuy-Daten stiehlt, kann damit keinen Passkey nachmachen. Ein Passkey mit PIN oder Biometrie ersetzt Passwort und zweiten Faktor zugleich.

## Voraussetzung: HTTPS und ein Domainname

Browser erlauben Passkeys nur auf **verschlüsselten Verbindungen mit einem Domainnamen**, nicht über `http://192.168.x.x`. Zum Ausprobieren genügt `http://localhost`. Im Alltag brauchst du:

1. einen Namen für deinen steuy-Rechner (z. B. `buchhaltung.example.de`), der im Heimnetz auf ihn zeigt, und
2. HTTPS davor, zum Beispiel über einen Reverse Proxy mit Zertifikat (siehe [Betrieb](betrieb.md), Abschnitt „Von außen erreichbar machen“).

Steht der Reverse Proxy davor, setze in der `.env` `PROXY_ANZAHL=1` (und `SESSION_COOKIE_SECURE=1`), damit steuy die Adresse und HTTPS richtig erkennt. Fehlt eine Voraussetzung, sagt dir die Profilseite genau, was fehlt.

Hinweis: Ein Passkey gehört zu genau dieser Adresse. Ändert sich der Name von steuy, funktionieren die alten Passkeys nicht mehr, du meldest dich dann mit Passwort an und richtest neue ein.

## Einrichten

1. Mit Passwort anmelden, *Profil* öffnen (Symbol rechts oben).
2. Im Abschnitt **Passkeys** einen Namen eintragen (z. B. „Handy“) und **Passkey hinzufügen** klicken.
3. Dein Gerät fragt nach Fingerabdruck, Gesicht oder PIN. Fertig.

Richte am besten **zwei Passkeys auf zwei Geräten** ein (z. B. Handy und Laptop), damit du dich auch aussperrst, wenn eines verloren geht. Maximal sind 10 pro Konto möglich.

## Anmelden

Auf der Anmeldeseite **„Mit Passkey anmelden“** klicken, Gerät bestätigen, fertig. Du musst keine E-Mail-Adresse eintippen: Der Passkey sagt steuy, wer du bist.

## Passwort und Zwei-Faktor bleiben

Die Anmeldung mit Passwort (und Code, falls Zwei-Faktor eingeschaltet ist) funktioniert weiter. Das ist dein Rückweg, wenn ein Passkey nicht verfügbar ist. Ist die **Zwei-Faktor-Anmeldung für alle** vorgeschrieben (Einstellungen), gilt ein Passkey als erfüllt. Wer sich nur mit Passwort anmeldet, muss weiter Zwei-Faktor einrichten.

## Passkey entfernen

*Profil → Passkeys → Entfernen.* Danach lässt sich dieses Gerät nicht mehr zur Anmeldung nutzen. Ist ein Gerät verloren, entferne seinen Passkey sofort. Ein Admin kann bei einem gesperrten Konto auch über *Einstellungen → Nutzer* das Konto deaktivieren, dann geht auch der Passkey nicht mehr.

## Sicherheit in Kürze

- Die Anmeldung ist an die Adresse von steuy gebunden. Eine gefälschte Seite bekommt vom Gerät keine gültige Antwort (Schutz vor Phishing).
- Jede Anmeldung nutzt eine einmalige Herausforderung, die nach 5 Minuten verfällt und nur einmal gilt. Eine mitgeschnittene Antwort lässt sich nicht wiederholen.
- Ein Zähler im Passkey erkennt kopierte Schlüssel: Geht er zurück, wird die Anmeldung abgelehnt.
- Passkeys verlangen immer PIN oder Biometrie (Nutzerprüfung), eine reine Berührung des Geräts reicht nicht.
- Anmeldungen, neue und entfernte Passkeys stehen im Protokoll.
