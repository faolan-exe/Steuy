# Kundenportal: Belege per Link

Jede E-Mail zu einer Rechnung, einem Angebot, einem Lieferschein oder einer Mahnung bekommt einen **persönlichen Link**. Darüber kann dein Kunde ohne Konto und ohne App:

- den Beleg mit **Status** sehen (offen, teilweise bezahlt, überfällig, bezahlt, angenommen …)
- das **PDF** ansehen und herunterladen, bei E-Rechnungen zusätzlich das **XML**
- direkt **bezahlen**: QR-Code für die Banking-App über den *offenen* Betrag, IBAN, Betrag und Verwendungszweck zum Kopieren
- ein **Angebot annehmen oder ablehnen**, mit Namen und einer Nachricht an dich
- Zahlungserinnerungen zur Rechnung abrufen

Du siehst am Beleg unter **Kundenlink**, ob und wann der Kunde den Link geöffnet hat. Nimmt er ein Angebot an, bekommst du eine Mail und kannst daraus mit einem Klick die Rechnung erstellen.

## Einschalten

*Einstellungen → Rechnungen → Kundenportal*

1. **Link zum Kundenportal in jede E-Mail einfügen**: standardmäßig an.
2. **Postleitzahl abfragen**: Vor dem Öffnen fragt steuy die PLZ der Rechnungsadresse ab. Das schützt, falls eine Mail weitergeleitet wird. Nach 5 falschen Versuchen ist der Link 15 Minuten gesperrt.
3. **Öffentliche Adresse**: Unter dieser Adresse muss steuy aus dem Internet erreichbar sein, immer mit HTTPS, z. B. `https://rechnung.meinefirma.de`. Ohne Adresse gibt es keine Links.

In der Mail steht der Link als Text und in der HTML-Fassung als Knopf. Löschst du die Zeile beim Senden aus dem Text, geht die Mail ohne Link raus.

## Sicher nach außen öffnen

steuy selbst bleibt am besten im eigenen Netz. Nach außen gibst du **nur das Portal** frei: die Pfade `/k/` und `/static/`. Alles andere (Anmeldung, Buchhaltung) beantwortet der Proxy von außen mit 404.

Beispiel mit [Caddy](https://caddyserver.com) (holt das HTTPS-Zertifikat selbst):

```
rechnung.meinefirma.de {
    @portal path /k/* /static/*
    handle @portal {
        reverse_proxy 192.168.1.20
    }
    handle {
        respond 404
    }
}
```

`192.168.1.20` ist die Adresse des steuy-Containers (nginx auf Port 80, Installation mit dem Proxmox- oder LXC-Skript). Läuft Caddy auf demselben Rechner wie eine Docker-Installation, heißt das Ziel `127.0.0.1:8000`.

Aus dem Internet beantwortet steuy ohnehin nur verschlüsselte Aufrufe (siehe [Betrieb](betrieb.md), Abschnitt „Von außen nur über HTTPS“). Der Proxy mit Zertifikat steht im eigenen Netz, deshalb lässt steuy durch, was er weiterreicht.

In der `.env` von steuy dazu:

```
PROXY_ANZAHL=1
BASIS_URL=https://rechnung.meinefirma.de
```

`BASIS_URL` mit `https://` schaltet außerdem sichere Cookies ein. Möchtest du auch die Anmeldung von unterwegs erreichen, gib den ganzen Server frei und richte für alle Konten die Zwei-Faktor-Anmeldung oder Passkeys ein (*Einstellungen → Nutzer → verpflichtend*).

## Wie sicher ist der Link?

- Der Schlüssel im Link ist zufällig (192 Bit) und nicht zu erraten. steuy speichert davon nur eine Prüfsumme und eine verschlüsselte Kopie.
- Ein Link öffnet genau **einen** Beleg. Andere Belege, Kunden oder die Buchhaltung sind darüber nicht erreichbar.
- Ungültige und gesperrte Links sehen gleich aus und verraten nichts.
- Die Seiten werden nicht zwischengespeichert, nicht von Suchmaschinen erfasst und geben den Link nicht als Referrer weiter.
- Ging eine Mail an die falsche Adresse, sperrst du am Beleg mit **Link sperren und neu erzeugen** den alten Link sofort.
- Jede Entscheidung zu einem Angebot steht mit Name, Nachricht, Zeit und IP-Adresse im Änderungsprotokoll.

Ändert sich der `SECRET_KEY`, lassen sich bestehende Links nicht mehr anzeigen. Erzeuge sie dann am Beleg neu.
