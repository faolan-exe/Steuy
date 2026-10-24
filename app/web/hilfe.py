"""Erklärungen hinter den kleinen Fragezeichen, geschrieben für Einsteiger ins Kleingewerbe.

Jeder Text beantwortet: Was ist das? Warum braucht steuy (oder das Finanzamt) das?
Keine Steuerberatung: Bei Grenzfällen verweisen die Texte auf die Steuerberatung.
Felder werden über ihre Beschriftung gefunden, sonst über ihren Namen.
"""

from markupsafe import Markup, escape

# ---------- Formularfelder: zuerst nach Beschriftung, dann nach Feldname ----------

NACH_BESCHRIFTUNG = {
    "Betrag brutto €": (
        "Der Betrag, den du tatsächlich bezahlt hast, inklusive Mehrwertsteuer. Als "
        "Kleinunternehmer bekommst du die Mehrwertsteuer nicht vom Finanzamt zurück, deshalb "
        "zählt der volle Betrag als Ausgabe."
    ),
    "Betrag €": (
        "Wie viel Geld gekommen ist, z. B. 152,20. Bei einer Teilzahlung nur den Teil "
        "eintragen, die Rechnung bleibt dann teilweise offen."
    ),
    "Bezahlt am": (
        "Der Tag, an dem das Geld wirklich geflossen ist (Kontoauszug). Für die Steuer zählt "
        "dieses Datum, nicht das Rechnungsdatum: Was im Januar ankommt, gehört ins neue Jahr."
    ),
    "Name des Gewerbes": (
        "So heißt dein Unternehmen auf Rechnungen, z. B. „Lisa Weber Fotografie“. Ohne Eintrag "
        "im Handelsregister muss außerdem dein voller Name erkennbar sein, dafür gibt es das "
        "Feld Inhaber."
    ),
    "Inhaber": (
        "Dein Vor- und Nachname. Er steht auf jeder Rechnung, weil das Finanzamt und deine "
        "Kunden wissen müssen, wer hinter dem Gewerbe steht."
    ),
    "Notiz (intern)": "Nur für dich sichtbar, erscheint nie auf Rechnungen oder Mahnungen.",
    "Lieferant / Zahler": (
        "Von wem der Beleg stammt, z. B. „Telekom“. Hilft dir und dem Finanzamt, die Ausgabe "
        "später zuzuordnen."
    ),
    "Nachweis (optional)": (
        "Ein Beleg, dass das Geld gekommen ist, z. B. Kontoauszug oder PayPal-Bestätigung. "
        "Pflicht ist das nicht, hilft aber bei Rückfragen vom Finanzamt."
    ),
}

NACH_NAME = {
    # Firmendaten
    "strasse": "Deine Geschäftsadresse. Sie ist Pflicht auf jeder Rechnung.",
    "steuernummer": (
        "Bekommst du vom Finanzamt, nachdem du dein Gewerbe angemeldet und den Fragebogen zur "
        "steuerlichen Erfassung abgegeben hast. Auf jeder Rechnung muss die Steuernummer oder "
        "die USt-IdNr. stehen."
    ),
    "ust_idnr": (
        "Umsatzsteuer-Identifikationsnummer, beginnt mit DE. Als Kleinunternehmer brauchst du "
        "sie meist nur für Geschäfte mit Firmen im EU-Ausland. Beantragen kannst du sie beim "
        "Bundeszentralamt für Steuern."
    ),
    "email": "Für Rückfragen. Bei deinen Firmendaten steht sie auf Rechnungen.",
    "telefon": "Optional. Steht bei deinen Firmendaten im Fuß der Rechnung.",
    # Bank
    "iban": (
        "Deine Kontonummer im internationalen Format (DE und 20 Ziffern). Sie steht auf "
        "Rechnungen und im QR-Code, damit Kunden schnell und fehlerfrei überweisen. Tipp: Ein "
        "eigenes Konto fürs Gewerbe trennt Privates und Berufliches sauber."
    ),
    "bic": "Kennung der Bank. Für Überweisungen in Deutschland und der EU meist nicht nötig.",
    "bank": "Name deiner Bank, steht auf der Rechnung neben der IBAN.",
    "kontoinhaber": (
        "Der Name, auf den das Konto läuft. Manche Banking-Apps prüfen, ob Name und IBAN "
        "zusammenpassen, und warnen sonst den Kunden."
    ),
    # Rechnungseinstellungen
    "praefix": (
        "Steht vor jeder Rechnungsnummer, z. B. RE für RE0001. Rechnungsnummern müssen einmalig "
        "sein, steuy zählt sie automatisch ohne Lücken hoch."
    ),
    "stellen": "Wie viele Ziffern die Nummer hat, z. B. 4 für RE0001.",
    "naechste_nummer": (
        "Kommst du von einem anderen Programm, trag hier die nächste freie Nummer ein, damit "
        "keine Nummer doppelt vergeben wird."
    ),
    "zahlungsziel_tage": (
        "So viele Tage hat dein Kunde Zeit zum Zahlen. Daraus berechnet steuy das "
        "Fälligkeitsdatum und zeigt dir, wenn eine Rechnung überfällig ist. Üblich sind 14 Tage."
    ),
    "angebot_gueltig_tage": (
        "So lange gilt dein Angebot. Danach bist du nicht mehr an Preis und Leistung gebunden."
    ),
    "rechnung_einleitung": "Der Begrüßungstext über den Positionen, z. B. „Vielen Dank …“.",
    "einleitung": "Der Begrüßungstext über den Positionen, z. B. „Vielen Dank …“.",
    "rechnung_nachbemerkung": "Text unter den Positionen, z. B. ein Gruß oder Zahlungshinweis.",
    "nachbemerkung": "Text unter den Positionen, z. B. ein Gruß oder Zahlungshinweis.",
    "hinweis_steuerbefreiung": (
        "Als Kleinunternehmer stellst du keine Umsatzsteuer in Rechnung. Auf jeder Rechnung "
        "muss deshalb ein Hinweis auf die Steuerbefreiung stehen, z. B. „Gemäß § 19 UStG wird "
        "keine Umsatzsteuer berechnet.“"
    ),
    # Rechnungseditor
    "empfaenger_name": (
        "Wer das Angebot oder die Rechnung bekommt. Name und Anschrift sind Pflichtangaben."
    ),
    "rechnungsdatum": "Das Ausstellungsdatum des Dokuments. Bei Rechnungen ist es Pflichtangabe.",
    "leistung_von": (
        "Wann du die Leistung erbracht oder die Ware geliefert hast. Das ist eine eigene "
        "Pflichtangabe, auch wenn es derselbe Tag wie das Rechnungsdatum ist."
    ),
    "titel": "Überschrift des Dokuments, meist einfach „Rechnung“ oder „Angebot“.",
    "menge": "Wie viel, z. B. 2 Stunden oder 3 Stück.",
    "einheit": "Wofür der Preis gilt, z. B. Stunde, Stück oder pauschal.",
    "rabatt": "Nachlass in Prozent auf diese Position.",
    "qr_ueberweisung": (
        "Druckt einen GiroCode auf die Rechnung. Den scannt dein Kunde mit der Banking-App, "
        "Betrag, IBAN und Verwendungszweck sind dann schon ausgefüllt."
    ),
    # Zahlungen
    "zahlungsart": (
        "Wie bezahlt wurde. Wichtig, um Gebühren (z. B. bei PayPal) zu erkennen und um später "
        "Bank und Bargeld auseinanderzuhalten."
    ),
    "angekommen": (
        "Nur ausfüllen, wenn weniger ankam, als der Kunde bezahlt hat, z. B. weil PayPal "
        "Gebühren abzieht. Die Differenz ist eine Betriebsausgabe, steuy schlägt sie dir "
        "unter „Zu prüfen“ zum Buchen vor."
    ),
    "referenz": (
        "Eine Nummer, mit der du die Zahlung wiederfindest, z. B. die PayPal-Transaktions-ID "
        "oder der Verwendungszweck vom Kontoauszug."
    ),
    "notiz": "Freier Text für dich, z. B. „Rest kommt nächsten Monat“.",
    # Belege und Buchungen
    "belegdatum": "Das Datum auf der Rechnung oder Quittung, die du bekommen hast.",
    "belegnummer": (
        "Die Rechnungsnummer deines Lieferanten. Damit findest du den Beleg bei Rückfragen "
        "vom Finanzamt schnell wieder."
    ),
    "kategorie_id": (
        "Sortiert die Buchung in die passende Zeile der Steuererklärung (Anlage EÜR). Unsicher? "
        "Nimm „Sonstige Ausgaben“ und kläre es mit deiner Steuerberatung."
    ),
    "betrieblich_prozent": (
        "Nutzt du etwas auch privat, z. B. Handy oder Internet, zählt nur der berufliche Teil "
        "als Ausgabe. Schätze ihn ehrlich und realistisch, z. B. 50 %, und bleib dabei."
    ),
    "bereits_bezahlt": (
        "Ist das Geld schon von deinem Konto weg? Dann zählt die Ausgabe ab dem Zahltag. Sonst "
        "merkt steuy sie als offen vor."
    ),
    "kontakt_id": (
        "Verknüpft den Beleg mit einem Kontakt, damit du im Kundenprofil alles auf einen Blick "
        "siehst."
    ),
    "beschreibung": "Worum es geht, z. B. „Druckerpatronen“. Hilft dir beim Wiederfinden.",
    # Kontakte
    "firmenname": "Name der Firma, wie er auf der Rechnung stehen soll.",
    "adresszusatz": "Z. B. Abteilung, c/o oder Hinterhaus.",
    "land": (
        "Bei Kunden im Ausland können andere Regeln gelten (z. B. bei Firmen in der EU). Im "
        "Zweifel die Steuerberatung fragen."
    ),
    "mahnsperre": (
        "Für diesen Kontakt schlägt steuy nie Mahnungen vor, z. B. bei Stammkunden oder "
        "vereinbarter Ratenzahlung."
    ),
    # Artikel
    "artikelnummer": "Deine eigene Nummer für den Artikel. Optional, hilft bei vielen Artikeln.",
    "bezeichnung": "So erscheint der Artikel auf Angeboten und Rechnungen.",
    "preis": (
        "Endpreis in Euro. Als Kleinunternehmer gibt es keine Mehrwertsteuer obendrauf, der "
        "Preis ist also das, was der Kunde zahlt."
    ),
    "gtin": "Die Strichcode-Nummer (EAN) eines Produkts. Für Dienstleistungen leer lassen.",
    # Einrichtung und Nutzer
    "einzelunternehmen": (
        "steuy ist für Einzelunternehmer und Freiberufler gebaut. Für GmbH, UG oder GbR "
        "gelten andere Regeln (z. B. Bilanz statt EÜR)."
    ),
    "kleinunternehmer": (
        "Kleinunternehmer nach § 19 UStG darfst du sein, wenn dein Umsatz im Vorjahr höchstens "
        "25.000 € war und im laufenden Jahr 100.000 € nicht übersteigt. Dann berechnest du keine "
        "Umsatzsteuer."
    ),
    "rolle": (
        "Bestimmt, was jemand darf: Admin alles, Buchhalter buchen und auswerten, Mitarbeiter "
        "Rechnungen schreiben, Steuerberater nur lesen und exportieren."
    ),
    "zugang_bis": (
        "Danach kann sich die Person nicht mehr anmelden, praktisch z. B. für die "
        "Steuerberatung während der Jahreserklärung."
    ),
    "kontenrahmen": (
        "Eine Liste mit Kontonummern für die Buchhaltung. SKR03 und SKR04 sind die beiden "
        "üblichen. Frag deine Steuerberatung, welchen sie nutzt."
    ),
    "beraternummer": "Bekommst du von deiner Steuerberatung, falls sie mit DATEV arbeitet.",
    # Anlagegüter
    "art": (
        "Computer und Software haben eine Nutzungsdauer von einem Jahr und zählen voll im "
        "Jahr der Anschaffung. Alles andere wird über mehrere Jahre verteilt."
    ),
    "anschaffungsdatum": (
        "Ab diesem Monat wird abgeschrieben. Im ersten Jahr zählen nur die Monate ab der "
        "Anschaffung."
    ),
    "nutzungsdauer_jahre": (
        "Wie viele Jahre du das Ding üblicherweise nutzt. Die Werte gibt das Finanzamt in "
        "der AfA-Tabelle vor, z. B. 13 Jahre für Büromöbel."
    ),
    # Shop
    "shop_url": "Die Adresse deines Shops, z. B. https://mein-shop.de (ohne /wp-admin).",
    "shop_schluessel": (
        "Erzeugst du im Shop unter WooCommerce → Einstellungen → Erweitert → REST-API. "
        "„Lesen“ reicht zum Abrufen. steuy speichert den Schlüssel verschlüsselt."
    ),
    "shop_geheimnis": "Gehört zum Consumer Key und wird nur einmal im Shop angezeigt.",
    "shop_auto_versand": (
        "Aus: Neue Shop-Rechnungen warten unter „Zu prüfen“ auf deine Freigabe. An: steuy "
        "erstellt und verschickt sie sofort. Bestellungen mit Auffälligkeiten warten immer."
    ),
    # E-Mail
    "smtp_server": (
        "Der Postausgangsserver deines E-Mail-Anbieters. Steht in dessen Hilfe unter „SMTP“, "
        "z. B. smtp.ionos.de. Damit verschickt steuy Mails so, als kämen sie aus deinem Postfach."
    ),
    "smtp_port": "Meist 587 (STARTTLS) oder 465 (SSL/TLS). Steht beim Anbieter neben dem Server.",
    "smtp_verschluesselung": (
        "Schützt Passwort und Inhalt auf dem Weg zum Server. Nimm, was dein Anbieter angibt, "
        "fast immer STARTTLS oder SSL/TLS."
    ),
    "smtp_benutzer": "Dein Login beim E-Mail-Anbieter, meist die E-Mail-Adresse.",
    "smtp_passwort": (
        "Das Passwort deines Postfachs. Manche Anbieter (z. B. Gmail) verlangen ein eigenes "
        "App-Passwort. steuy speichert es verschlüsselt."
    ),
    "mail_absender": (
        "Von dieser Adresse kommen die Mails. Sie sollte zum Postfach gehören, sonst landen "
        "Mails beim Kunden leicht im Spam."
    ),
    "an": "Die E-Mail-Adresse deines Kunden. Vorbelegt aus dem Kontakt, falls dort hinterlegt.",
    "kopie_an_mich": "Du bekommst eine unsichtbare Kopie (BCC), so hast du die Mail im Postfach.",
    "betreff": "Die Betreffzeile. Mit Belegnummer findet dein Kunde die Mail leichter wieder.",
    "mandantennummer": "Deine Nummer bei der Steuerberatung, auch für DATEV.",
}

# ---------- Begriffe an Überschriften, Kennzahlen und Spalten ----------

BEGRIFFE = {
    "kleinunternehmergrenze": (
        "Wer im Vorjahr höchstens 25.000 € Umsatz hatte, darf dieses Jahr Kleinunternehmer "
        "sein. Wird im laufenden Jahr die Grenze von 100.000 € überschritten, endet das sofort. "
        "Grün heißt: unter 25.000 €. Gelb: Du liegst darüber, dann bist du nächstes Jahr "
        "voraussichtlich kein Kleinunternehmer mehr. Sprich frühzeitig mit der Steuerberatung."
    ),
    "umsatz": (
        "Summe der Zahlungen, die in diesem Jahr wirklich angekommen sind. Gestellte, aber "
        "unbezahlte Rechnungen zählen noch nicht."
    ),
    "euer": (
        "Einnahmen-Überschuss-Rechnung: Einnahmen minus Ausgaben ergibt deinen Gewinn. Als "
        "Kleinunternehmer gibst du sie jedes Jahr mit der Steuererklärung als „Anlage EÜR“ in "
        "ELSTER ab. steuy füllt die Zeilen für dich vor, abtippen musst du sie selbst."
    ),
    "zuflussprinzip": (
        "Für die EÜR zählt, wann Geld fließt, nicht wann die Rechnung geschrieben wurde. Eine "
        "Rechnung vom Dezember, die im Januar bezahlt wird, gehört ins neue Jahr."
    ),
    "zeile_kennzahl": (
        "Zeile und Kennzahl im amtlichen Formular Anlage EÜR. In ELSTER suchst du die Kennzahl "
        "und trägst dort den Betrag ein."
    ),
    "gewinn": (
        "Betriebseinnahmen minus Betriebsausgaben. Auf den Gewinn zahlst du Einkommensteuer, "
        "zusammen mit deinem übrigen Einkommen. Ab einer gewissen Höhe kann auch Gewerbesteuer "
        "anfallen."
    ),
    "zu_pruefen": (
        "Alles, was eine Entscheidung von dir braucht: offene und überfällige Rechnungen, "
        "Belege ohne Buchung, Gebühren, Angebote ohne Antwort. Ist die Liste leer, ist alles "
        "erledigt."
    ),
    "zahlungen": (
        "Jede eingegangene Zahlung mit Datum. Eine Zahlung lässt sich nicht löschen, nur "
        "rückgängig machen: Dann entsteht eine Gegenbuchung. So bleibt nachvollziehbar, was "
        "passiert ist, wie es die GoBD verlangen."
    ),
    "gegenbuchung": (
        "Hebt eine Buchung auf, ohne sie zu löschen: Der gleiche Betrag mit Minus. Die "
        "Grundsätze ordnungsmäßiger Buchführung (GoBD) verbieten, Gebuchtes nachträglich zu "
        "ändern oder zu löschen."
    ),
    "gebuehr": (
        "Differenz zwischen gezahltem und angekommenem Betrag, z. B. PayPal-Gebühren. Das ist "
        "eine Betriebsausgabe und senkt deinen Gewinn, deshalb solltest du sie buchen."
    ),
    "mahnungen": (
        "Zahlt ein Kunde nicht pünktlich, erinnerst du ihn erst freundlich und mahnst dann. "
        "steuy schlägt die nächste Stufe vor, sobald die Frist abgelaufen ist."
    ),
    "belegkette": (
        "Angebot, Rechnung, Lieferschein, Rechnungskorrektur und Mahnungen, die zusammengehören. "
        "Ein Klick führt zum jeweiligen Beleg."
    ),
    "mahnsperre": (
        "Für diese Rechnung oder diesen Kunden werden keine Mahnungen vorgeschlagen, z. B. bei "
        "vereinbarter Ratenzahlung."
    ),
    "pruefsumme": (
        "Ein digitaler Fingerabdruck der PDF-Datei. Ändert jemand auch nur ein Zeichen, passt "
        "die Prüfsumme nicht mehr. So lässt sich zeigen, dass die Rechnung unverändert ist."
    ),
    "finalisieren": (
        "Mit dem Finalisieren bekommt das Dokument seine Nummer und wird unveränderlich. Bei einer "
        "Rechnung korrigierst du Fehler danach per Storno mit einer Rechnungskorrektur."
    ),
    "rechnungskorrektur": (
        "Ein Storno einer Rechnung mit eigener Nummer. Die ursprüngliche Rechnung bleibt "
        "erhalten, die Korrektur hebt sie auf. Danach kannst du eine neue, richtige Rechnung "
        "schreiben."
    ),
    "festschreiben": (
        "Erst festgeschriebene Buchungen zählen in der EÜR. Danach sind sie unveränderlich, "
        "Fehler korrigierst du per Storno."
    ),
    "beleg": (
        "Jede Rechnung oder Quittung, die du bezahlst, ist ein Beleg. Ohne Beleg erkennt das "
        "Finanzamt eine Ausgabe oft nicht an. Belege musst du in der Regel 8 Jahre aufbewahren, "
        "steuy speichert sie unveränderlich."
    ),
    "e_rechnung": (
        "Seit 2025 musst du E-Rechnungen (XRechnung, ZUGFeRD) von Firmen empfangen können. "
        "Lade die Datei einfach hier hoch, steuy liest die Daten aus."
    ),
    "privatanteil": (
        "Der Teil einer Ausgabe, der privat ist, z. B. 50 % vom Handyvertrag. Er zählt nicht "
        "als Betriebsausgabe."
    ),
    "angebot": (
        "Ein unverbindlicher Preisvorschlag an einen Kunden. Nimmt er an, machst du mit einem "
        "Klick eine Rechnung daraus."
    ),
    "export_steuerberatung": (
        "Ein ZIP mit allem, was die Steuerberatung für ein Jahr braucht: EÜR, alle Zahlungen, "
        "Rechnungen und Belege im Original."
    ),
    "wechsel_export": (
        "Deine Daten gehören dir. Damit nimmst du Buchungen, Kunden und Artikel in ein anderes "
        "Programm mit."
    ),
    "smtp": (
        "SMTP ist der Weg, über den E-Mails verschickt werden. steuy nutzt dafür dein eigenes "
        "Postfach. Die Mails kommen also von deiner Adresse, Antworten landen bei dir."
    ),
    "wochenmail": (
        "Damit nichts liegen bleibt: Einmal pro Woche erinnert dich steuy an offene Punkte. "
        "Dafür muss der E-Mail-Versand unter Einstellungen → E-Mail eingerichtet sein."
    ),
    "shop": (
        "Bestellungen aus deinem WooCommerce-Shop. steuy schreibt dafür die Rechnungen mit "
        "fortlaufender Nummer und übernimmt das Zahlungsdatum. Für die Steuer zählt, wann das "
        "Geld kam, nicht wann bestellt wurde."
    ),
    "jahreswechsel": (
        "Normalerweise zählt der Tag der Zahlung. Ausnahme: Regelmäßige Zahlungen wie Miete "
        "oder Abos, die kurz vor oder nach Silvester gezahlt und fällig sind, zählen in dem "
        "Jahr, zu dem sie gehören. steuy erkennt mögliche Fälle, entscheiden musst du."
    ),
    "afa": (
        "AfA heißt Absetzung für Abnutzung: Was länger als ein Jahr hält und mehr als 800 € "
        "netto kostet, zählt nicht auf einmal als Ausgabe, sondern verteilt über die "
        "Nutzungsdauer. Computer und Software dürfen sofort voll abgeschrieben werden."
    ),
    "anlagenverzeichnis": (
        "Liste deiner abgeschriebenen Anschaffungen mit Restwert. Das Finanzamt will sie mit "
        "der EÜR als Anlage AVEÜR sehen. Bewahre die Rechnungen auf, solange du die Dinge "
        "nutzt, und danach noch die üblichen Fristen."
    ),
    "import": (
        "Damit du beim Umstieg nicht alles abtippen musst: Kunden, Lieferanten und Artikel "
        "aus einer CSV-Datei übernehmen. Belege und Buchungen alter Jahre bleiben im alten "
        "Programm bzw. in dessen Export, die musst du dort aufbewahren."
    ),
    "versand": (
        "Jede verschickte Mail wird hier festgehalten, mit Empfänger und Zeitpunkt. So kannst "
        "du nachweisen, wann eine Rechnung oder Mahnung rausging."
    ),
    "zwei_faktor": (
        "Zusätzlich zum Passwort fragt steuy nach einem Code: aus einer App auf deinem Handy "
        "oder per E-Mail. Kennt jemand dein Passwort, kommt er trotzdem nicht an deine "
        "Buchhaltung."
    ),
}


def _symbol(text: str) -> Markup:
    return Markup(
        '<span class="hilfe" tabindex="0" role="img" aria-label="Erklärung: {t}" '
        'title="{t}" data-hilfe="{t}">?</span>'
    ).format(t=escape(text))


# Felder mit gleichem Namen, aber anderer Bedeutung. Das Formular nennt seinen Bereich über
# `description=...`, damit z. B. die E-Mail eines Kunden nicht wie die eigene erklärt wird.
NACH_BEREICH = {
    "kontakt": {
        "strasse": (
            "Die Rechnungsadresse deines Kunden. Sie wird auf Rechnungen und Angeboten als "
            "Empfänger gedruckt und ist dort Pflichtangabe."
        ),
        "email": (
            "Wohin du Rechnungen und Erinnerungen per E-Mail schickst. steuy schlägt sie beim "
            "Senden automatisch vor."
        ),
        "telefon": "Nur für dich zum Nachschlagen. Erscheint nicht auf Rechnungen.",
        "steuernummer": (
            "Optional. Du brauchst sie nur, wenn dein Kunde sie ausdrücklich auf der Rechnung "
            "verlangt."
        ),
        "ust_idnr": (
            "Die Umsatzsteuer-ID deines Kunden (beginnt mit DE). Optional, wichtig vor allem bei "
            "Firmen im EU-Ausland. Im Zweifel die Steuerberatung fragen."
        ),
    }
}


def text_fuer_feld(feld) -> str | None:
    beschriftung = getattr(getattr(feld, "label", None), "text", None)
    bereich = NACH_BEREICH.get(getattr(feld, "description", None) or "", {})
    return bereich.get(feld.name) or NACH_BESCHRIFTUNG.get(beschriftung) or NACH_NAME.get(feld.name)


def symbol_fuer_feld(feld, an: bool) -> Markup:
    text = text_fuer_feld(feld) if an else None
    return _symbol(text) if text else Markup("")


def symbol_fuer_name(name: str, an: bool) -> Markup:
    text = NACH_NAME.get(name) if an else None
    return _symbol(text) if text else Markup("")


def symbol_fuer_begriff(schluessel: str, an: bool) -> Markup:
    if not an:
        return Markup("")
    return _symbol(BEGRIFFE[schluessel])


def _an() -> bool:
    from flask import request
    from flask_login import current_user

    # Auf der Anmeldeseite stört die Hilfe nur, in der Einrichtung ist sie immer an
    if request.blueprint == "auth":
        return False
    return not current_user.is_authenticated or bool(current_user.hilfe_anzeigen)


def registriere(app) -> None:
    app.jinja_env.globals.update(
        hilfe=lambda schluessel: symbol_fuer_begriff(schluessel, _an()),
        feldhilfe=lambda feld: symbol_fuer_feld(feld, _an()),
        namenhilfe=lambda name: symbol_fuer_name(name, _an()),
    )
