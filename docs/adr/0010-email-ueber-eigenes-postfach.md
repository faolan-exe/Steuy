# 0010: E-Mail-Versand über das eigene Postfach (SMTP)

- Status: vorgeschlagen
- Datum: 2026-10-22

## Kontext

Rechnungen, Mahnungen, die Wochenmail und der 2FA-Code per Mail müssen verschickt werden. Kunden sollen die Mail als vom Gewerbe kommend erkennen und direkt antworten können.

## Entscheidung

- Versand über den **SMTP-Zugang des eigenen Postfachs**, eingetragen unter Einstellungen → E-Mail. Absender ist die Adresse des Gewerbes, Antworten gehen an die E-Mail aus den Firmendaten.
- Das **SMTP-Passwort** wird mit dem bestehenden Fernet-Schlüssel verschlüsselt (wie die 2FA-Geheimnisse) und nie protokolliert.
- Umsetzung nur mit der Standardbibliothek (`smtplib`, `email`), keine zusätzliche Abhängigkeit. In Tests landen Mails in einem Testausgang.
- **Versandverlauf** je Rechnung in der Tabelle `versand`, nur anhängen (DB-Trigger), auch Fehlversuche mit Grund.
- **Kein automatischer Versand** von Mahnungen (wie in `docs/domain/mahnwesen.md`). Nur Shop-Rechnungen im Auto-Modus gehen ohne Klick raus.
- **2FA per Mail** als zweite Methode neben der App: 6 Ziffern, 10 Minuten, einmal gültig, Fehlversuche in der bestehenden Anmeldesperre.

## Verworfene Alternativen

- **Versanddienst mit API (z. B. Mailgun):** zusätzliches Konto und Kosten, Absender nicht das eigene Postfach.
- **Mails per lokalem MTA:** landen ohne SPF/DKIM schnell im Spam.

## Folgen

- Funktioniert mit jedem Anbieter, der SMTP anbietet. Manche (Gmail, Outlook) verlangen ein App-Passwort.
- Wer den `SECRET_KEY` verliert, muss das SMTP-Passwort neu eintragen.
- 2FA per Mail ist nur so sicher wie das Postfach. Die Oberfläche weist darauf hin.
