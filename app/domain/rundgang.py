"""Der Rundgang durch steuy: Schritte, Stufen und Reihenfolge (ohne Flask).

Jeder Schritt gehört zu einer Seite (Endpunkt), erklärt in einfachen Worten, was dort ist und
warum man es braucht, und hebt auf Wunsch ein Element der Seite hervor. Einsteiger bekommen mehr
Erklärung (Absätze unter `einsteiger`) und zusätzliche Grundlagen-Schritte."""

from dataclasses import dataclass, field

ANFAENGER = "anfaenger"
ERFAHREN = "erfahren"
EXPERTE = "experte"

STUFEN = {
    ANFAENGER: "Kompletter Anfänger",
    ERFAHREN: "Bereits mal gemacht",
    EXPERTE: "Experte",
}


@dataclass(frozen=True)
class Schritt:
    kennung: str
    titel: str
    absaetze: tuple[str, ...]
    endpunkt: str = "allgemein.start"
    licht: str | None = None  # CSS-Auswahl des Elements, das hervorgehoben wird
    einsteiger: tuple[str, ...] = field(default=())  # nur für „Kompletter Anfänger“
    nur_einsteiger: bool = False  # ganzer Schritt nur für Anfänger
    recht: str | None = None  # ohne dieses Recht wird der Schritt übersprungen


SCHRITTE: tuple[Schritt, ...] = (
    Schritt(
        "willkommen",
        "Willkommen bei steuy",
        (
            "In diesem Rundgang zeigen wir dir Schritt für Schritt, was steuy kann und wo du "
            "alles findest. Du musst nur auf „Weiter“ klicken. Du kannst jederzeit „Rundgang "
            "beenden“ wählen und im Profil neu starten.",
            "steuy ist eine kostenlose Buchhaltung für Kleinunternehmer: Angebote und Rechnungen "
            "schreiben, Ausgaben erfassen, Zahlungen verfolgen und am Jahresende die Werte für die "
            "Steuererklärung (Anlage EÜR) bekommen.",
        ),
        einsteiger=(
            "Keine Sorge, wenn dir Begriffe wie „EÜR“ oder „Kleinunternehmer“ noch nichts sagen. "
            "Wir erklären alles, wenn es zum ersten Mal vorkommt. steuy ersetzt keine "
            "Steuerberatung, nimmt dir aber viel Rechenarbeit und Zettelwirtschaft ab.",
        ),
    ),
    Schritt(
        "grundlagen",
        "Die Grundlagen in zwei Minuten",
        (
            "Als Kleinunternehmer nach § 19 UStG weist du auf deinen Rechnungen keine "
            "Umsatzsteuer aus. Dafür darfst du dir auch keine Vorsteuer erstatten lassen. Der "
            "Rechnungsbetrag ist also gleichzeitig dein Einnahmebetrag.",
            "Dein Gewinn wird über die Einnahmen-Überschuss-Rechnung (EÜR) ermittelt: Einnahmen "
            "minus Ausgaben. Es zählt, wann das Geld tatsächlich geflossen ist, nicht wann du die "
            "Rechnung geschrieben hast (Zuflussprinzip).",
            "Ein Einzelunternehmen führt keine doppelte Buchführung. Du musst keine Konten und "
            "Buchungssätze verstehen: steuy ordnet alles für dich den richtigen Zeilen der "
            "Steuererklärung zu.",
        ),
        nur_einsteiger=True,
    ),
    Schritt(
        "menue",
        "Das Menü oben",
        (
            "Über das Menü oben erreichst du alles Wichtige: Dashboard, Zu prüfen, Angebote, "
            "Rechnungen, Belege, Kontakte, Artikel und Auswertung. Rechts findest du Suche, "
            "Hilfe, Einstellungen und dein Profil.",
        ),
        licht=".hauptnavi",
        einsteiger=(
            "Merke dir die Reihenfolge: Erst kommen Kunden und Artikel (Kontakte, Artikel), dann "
            "Angebote und Rechnungen, danach Belege für deine Ausgaben, am Ende die Auswertung.",
        ),
    ),
    Schritt(
        "dashboard",
        "Dashboard: dein Überblick",
        (
            "Das Dashboard zeigt auf einen Blick, wie es um dein Geschäft steht: offene "
            "Aufgaben, offene Forderungen, Einnahmen und Ausgaben des Jahres und wie weit du von "
            "der Kleinunternehmergrenze entfernt bist.",
        ),
        licht=".raster",
    ),
    Schritt(
        "zu_pruefen_karte",
        "Zu prüfen: was jetzt zu tun ist",
        (
            "Dieser Kasten sammelt alles, was auf dich wartet: offene Rechnungen, fällige "
            "Mahnungen, neue Belege, Entwürfe. Wenn dort „Keine offenen …“ steht, bist du auf dem "
            "neuesten Stand. Ein Klick auf den Titel öffnet die ganze Liste.",
        ),
        licht='[aria-labelledby="aufgaben"]',
    ),
    Schritt(
        "finanzen",
        "Finanzen, Rechnungen und Ziel",
        (
            "„Offene Forderungen“ ist Geld, das Kunden dir noch schulden. „Offene Ausgaben“ sind "
            "Rechnungen, die du selbst noch bezahlen musst. Der Kreis zeigt deine Rechnungen: "
            "grün bezahlt, gelb noch offen, rot überfällig.",
            "Unter „Dein Ziel“ legst du fest, was du dieses Jahr erreichen willst (Aufträge, "
            "Umsatz oder Gewinn). Ist es geschafft, glänzt der Kasten.",
        ),
        licht='[aria-labelledby="finanzen"]',
    ),
    Schritt(
        "grenze",
        "Die Kleinunternehmergrenze",
        (
            "Kleinunternehmer dürfen nur bis zu einer bestimmten Jahreseinnahme bleiben. steuy "
            "zeigt dir mit dem Balken, wie viel davon du erreicht hast, und warnt dich, wenn es "
            "eng wird. Bei Fragen dazu hilft die Steuerberatung.",
        ),
        licht='[aria-labelledby="grenze"]',
        einsteiger=(
            "Wichtig: Es zählen die Zahlungseingänge. Wirst du über die Grenze kommen, musst du "
            "ab dem nächsten Jahr Umsatzsteuer ausweisen. Dann sprich bitte mit deiner "
            "Steuerberatung, bevor du weiterarbeitest.",
        ),
    ),
    Schritt(
        "fragezeichen",
        "Die kleinen Fragezeichen",
        (
            "Überall in steuy siehst du kleine Fragezeichen neben Wörtern und Feldern. Ein Klick "
            "erklärt in einfachen Worten, was gemeint ist und warum es wichtig ist.",
            "Wer sie nicht mehr braucht, schaltet sie im Profil ab. Im Menü oben rechts gibt es "
            "dafür auch eine Abkürzung.",
        ),
        licht=".leiste-knopf.optional, .titellink + .hilfe, .hilfe",
        einsteiger=(
            "Probiere es gleich aus: Klicke auf das Fragezeichen neben „Zu prüfen“ auf dem "
            "Dashboard. Ein Fenster erklärt dir dort, was der Kasten bedeutet.",
        ),
    ),
    Schritt(
        "suche",
        "Suche",
        (
            "Mit der Lupe findest du Kunden, Rechnungen, Belege, Artikel und sogar Beträge. Gib "
            "einfach einen Namen, eine Nummer oder einen Betrag ein.",
        ),
        endpunkt="allgemein.suche_seite",
    ),
    Schritt(
        "firmendaten",
        "Einstellungen: Firmendaten",
        (
            "Hier stehen Name, Anschrift, Steuernummer und Kontakt deines Gewerbes. Diese Angaben "
            "erscheinen auf jeder Rechnung. Jede Änderung wird protokolliert.",
        ),
        endpunkt="einstellungen.firmendaten",
        recht="einstellungen",
        einsteiger=(
            "Warum? Eine Rechnung ist nur gültig, wenn bestimmte Angaben darauf stehen: dein "
            "Name und deine Anschrift, die Anschrift des Kunden, ein Datum, eine fortlaufende "
            "Nummer, die Leistung und eine Steuernummer. Trage deine Steuernummer ein, sobald du "
            "sie vom Finanzamt hast.",
        ),
    ),
    Schritt(
        "rechnungseinstellungen",
        "Einstellungen: Rechnungen und Bankverbindung",
        (
            "Hier trägst du deine Bankverbindung ein. Sie kommt auf die Rechnung und in den "
            "QR-Code, mit dem Kunden direkt aus der Banking-App bezahlen können. Außerdem "
            "legst du das Zahlungsziel und die Rechnungsnummern fest.",
        ),
        endpunkt="einstellungen.rechnungen",
        recht="einstellungen",
        einsteiger=(
            "Rechnungsnummern müssen fortlaufend und ohne Lücken sein. steuy zählt das für dich. "
            "Wenn du schon Rechnungen aus einem anderen Programm hast, trage hier die nächste "
            "freie Nummer ein.",
        ),
    ),
    Schritt(
        "drucklayout",
        "Einstellungen: Drucklayout",
        (
            "Hier gestaltest du das Aussehen deiner Rechnungen, Angebote, Lieferscheine und "
            "Mahnungen: fünf Layouts, dein Logo, Farbe, Schrift. Rechts siehst du sofort eine "
            "Vorschau.",
            "Bereits erstellte Rechnungen ändern sich nicht mehr (das ist Pflicht). Nur neue "
            "Belege bekommen das neue Aussehen.",
        ),
        endpunkt="einstellungen.drucklayout",
        recht="einstellungen",
    ),
    Schritt(
        "mahnwesen",
        "Einstellungen: Mahnwesen",
        (
            "Zahlt ein Kunde nicht pünktlich, kannst du ihn in drei Stufen erinnern und mahnen. "
            "Hier stellst du ein, nach wie vielen Tagen und mit welchem Text.",
            "Das automatische Mahnen ist standardmäßig ausgeschaltet. Du entscheidest, ob steuy "
            "fällige Mahnungen von selbst erstellt und verschickt.",
        ),
        endpunkt="einstellungen.mahnwesen",
        recht="einstellungen",
    ),
    Schritt(
        "email",
        "Einstellungen: E-Mail-Versand",
        (
            "Damit steuy Rechnungen und Angebote direkt per E-Mail verschicken kann, trägst du "
            "hier die Zugangsdaten deines E-Mail-Anbieters ein (SMTP). Die findest du in deinem "
            "Postfach unter „Postausgangsserver“.",
        ),
        endpunkt="einstellungen.email",
        recht="einstellungen",
        einsteiger=(
            "Das ist optional. Ohne diese Einstellung lädst du das PDF herunter und verschickst "
            "es selbst. Tipp: Teste den Versand zuerst mit einer E-Mail an dich selbst.",
        ),
    ),
    Schritt(
        "weitere_einstellungen",
        "Einstellungen: Shop, Import, Update, Nutzer",
        (
            "Unter „Shop“ verbindest du einen WooCommerce-Shop, dessen Bestellungen steuy "
            "abholt. „Import/Export“ holt Daten aus anderen Programmen (z. B. Lexware) und "
            "exportiert alles wieder. Unter „Update“ siehst du, ob es eine neue steuy-Version "
            "gibt.",
            "Unter „Nutzer“ und „Rechte“ legst du weitere Personen an, etwa den Buchhalter oder "
            "die Steuerberatung, und bestimmst genau, was sie dürfen.",
        ),
        endpunkt="einstellungen.import_export",
        recht="einstellungen",
    ),
    Schritt(
        "kontakte",
        "Kontakte: Kunden und Lieferanten",
        (
            "Hier verwaltest du alle Personen und Firmen, mit denen du zu tun hast. Wenn du bei "
            "einer Rechnung einen Kunden auswählst, trägt steuy die Anschrift automatisch ein.",
            "Auf der Seite eines Kunden siehst du alle seine Angebote, Rechnungen und offenen "
            "Beträge. Dort kannst du auch eine Mahnsperre setzen.",
        ),
        endpunkt="kontakte.liste",
        licht='.hauptnavi a[href="/kontakte"]',
        recht="ansehen",
        einsteiger=(
            "Lege den ersten Kunden am besten gleich an: Klick auf „Neuer Kontakt“. Name und "
            "Anschrift reichen.",
        ),
    ),
    Schritt(
        "artikel",
        "Artikel: deine Produkte und Dienstleistungen",
        (
            "Hier legst du an, was du verkaufst, mit Preis und Einheit (Stunde, Stück, "
            "Pauschal …). In Angeboten und Rechnungen wählst du sie mit einem Klick aus. Du "
            "musst sie nicht jedes Mal neu eintippen.",
            "Als Kleinunternehmer sind alle Preise Endpreise: Es kommt keine Umsatzsteuer dazu.",
        ),
        endpunkt="artikel.liste",
        licht='.hauptnavi a[href="/artikel"]',
        recht="ansehen",
    ),
    Schritt(
        "angebote",
        "Angebote",
        (
            "Mit einem Angebot machst du dem Kunden ein Preisangebot. Es hat eine Gültigkeit, du "
            "kannst es per E-Mail schicken und danach als „angenommen“ oder „abgelehnt“ "
            "markieren.",
            "Wurde es angenommen, wird daraus mit einem Klick eine Rechnung. Positionen, Preise "
            "und Kunde werden übernommen.",
        ),
        endpunkt="angebote.angebote",
        licht='.hauptnavi a[href="/angebote"]',
        recht="ansehen",
    ),
    Schritt(
        "rechnungen",
        "Rechnungen schreiben",
        (
            "Eine neue Rechnung beginnt als Entwurf. Du wählst den Kunden, fügst Artikel oder "
            "freie Positionen hinzu und siehst die Summe sofort. Über die Vorschau prüfst du das "
            "PDF.",
            "Erst beim „Finalisieren“ bekommt die Rechnung ihre Nummer. Danach ist sie "
            "unveränderlich, so verlangt es das Gesetz. Fehler korrigierst du mit einer "
            "Rechnungskorrektur (Storno).",
        ),
        endpunkt="rechnungen.liste",
        licht='.hauptnavi a[href="/rechnungen"]',
        recht="ansehen",
        einsteiger=(
            "Keine Angst vor dem Finalisieren: Vorher kannst du alles beliebig ändern, und "
            "steuy zeigt dir an, wenn Pflichtangaben fehlen.",
        ),
    ),
    Schritt(
        "zahlungen",
        "Zahlungen erfassen",
        (
            "Wenn ein Kunde bezahlt hat, öffnest du die Rechnung und erfasst die Zahlung mit "
            "Datum und Betrag. Auch Teilzahlungen sind möglich. Erst dann zählt die Einnahme in "
            "deiner Auswertung.",
            "Hat jemand zu viel oder zu wenig überwiesen, etwa wegen PayPal-Gebühren, trägst du "
            "das ein. steuy erinnert dich, die Gebühr als Ausgabe zu buchen.",
        ),
        endpunkt="rechnungen.liste",
        recht="zahlungen",
    ),
    Schritt(
        "mahnungen",
        "Mahnungen und Lieferscheine",
        (
            "Ist eine Rechnung überfällig, erstellst du über die Rechnung eine Zahlungserinnerung "
            "oder Mahnung und schickst sie dem Kunden. Mit der Mahnsperre pausierst du das, "
            "zum Beispiel bei vereinbarter Ratenzahlung.",
            "Zu jeder Rechnung kannst du außerdem einen Lieferschein ohne Preise erzeugen. Alle "
            "zusammengehörigen Belege (Angebot, Rechnung, Lieferschein, Mahnung) siehst du "
            "untereinander verlinkt auf jeder Seite.",
        ),
        endpunkt="rechnungen.liste",
        recht="ansehen",
    ),
    Schritt(
        "belege",
        "Belege und Ausgaben",
        (
            "Für alles, was du fürs Geschäft ausgibst, lädst du den Beleg hoch: PDF, Foto oder "
            "E-Rechnung. steuy liest Datum, Betrag und Lieferant aus, du wählst die Kategorie und "
            "schreibst die Buchung fest.",
            "Bei gemischter Nutzung (zum Beispiel Handy privat und geschäftlich) gibst du den "
            "betrieblichen Anteil in Prozent an. Nur dieser Teil zählt als Ausgabe.",
        ),
        endpunkt="belege.liste",
        licht='.hauptnavi a[href="/belege"]',
        recht="belege",
        einsteiger=(
            "Warum alle Belege? Das Finanzamt kann jede Ausgabe prüfen. Ohne Beleg erkennt es sie "
            "unter Umständen nicht an. steuy speichert die Dateien unveränderlich und zehn Jahre "
            "lang nachprüfbar.",
        ),
    ),
    Schritt(
        "anlagen",
        "Größere Anschaffungen",
        (
            "Kaufst du etwas Teures, etwa einen Computer oder eine Kamera, gilt es oft nicht "
            "einfach als Ausgabe im Jahr des Kaufs. steuy fragt dann nach und führt ein "
            "Anlagenverzeichnis für Abschreibungen.",
        ),
        endpunkt="anlagen.verzeichnis_seite",
        recht="auswertungen",
        einsteiger=(
            "Abschreibung heißt: Du verteilst die Kosten über mehrere Jahre. Für kleine "
            "Anschaffungen gibt es Sonderregeln. Wenn du unsicher bist, lass dich einmal von der "
            "Steuerberatung beraten.",
        ),
    ),
    Schritt(
        "auswertung",
        "Auswertung: deine EÜR",
        (
            "Hier siehst du die Einnahmen-Überschuss-Rechnung des Jahres, sortiert nach den "
            "Zeilen der Anlage EÜR. Die Werte kannst du als PDF oder CSV herunterladen und in "
            "ELSTER eintragen oder an die Steuerberatung geben.",
            "Mit „Export“ erzeugst du ein Paket mit allen Belegen und Auswertungen für die "
            "Steuerberatung.",
        ),
        endpunkt="auswertung.euer",
        licht='.hauptnavi a[href="/auswertung"]',
        recht="auswertungen",
        einsteiger=(
            "steuy überträgt nichts automatisch an das Finanzamt. Du trägst die Werte selbst in "
            "ELSTER ein. Das geht schnell, weil sie schon passend sortiert sind.",
        ),
    ),
    Schritt(
        "profil",
        "Dein Profil und die Sicherheit",
        (
            "Im Profil änderst du dein Passwort, richtest die Zwei-Faktor-Anmeldung ein "
            "(zusätzlicher Code beim Login) und schaltest die Hilfe-Fragezeichen und die "
            "Wochen-Mail ein oder aus. Hier kannst du auch diesen Rundgang neu starten.",
        ),
        endpunkt="profil.profil",
        einsteiger=(
            "Bitte schalte die Zwei-Faktor-Anmeldung ein: In deiner Buchhaltung stehen "
            "sensible Daten. Mit einem Authenticator auf dem Handy oder einem Code per E-Mail "
            "schützt du sie gut.",
        ),
    ),
    Schritt(
        "sicherung",
        "Sicherung und Updates",
        (
            "steuy speichert alles in einer Datenbank auf deinem eigenen Server. Sichere sie "
            "regelmäßig, am besten täglich und auf einen zweiten Speicherort. Unter "
            "Einstellungen → Import/Export lädst du außerdem alles als ZIP herunter.",
            "Unter Einstellungen → Update siehst du, ob eine neue Version da ist, mit "
            "Beschreibung dessen, was neu ist.",
        ),
        endpunkt="einstellungen.update",
        recht="einstellungen",
    ),
    Schritt(
        "fertig",
        "Geschafft: so geht es weiter",
        (
            "Das war der Rundgang. Ein guter Start in vier Schritten: 1. Firmendaten und "
            "Bankverbindung prüfen. 2. Ersten Kunden und deine Artikel anlegen. 3. Dein erstes "
            "Angebot oder deine erste Rechnung schreiben. 4. Belege deiner Ausgaben hochladen.",
            "Den Rundgang findest du jederzeit im Profil wieder. Viel Erfolg mit deinem Geschäft!",
        ),
        endpunkt="allgemein.start",
    ),
)


def schritte_fuer(erfahrung: str | None, hat_recht) -> list[Schritt]:
    """Die Schritte für eine Stufe. `hat_recht(name)` entscheidet über Schritte mit Recht."""
    einsteiger = erfahrung == ANFAENGER
    return [
        s
        for s in SCHRITTE
        if (einsteiger or not s.nur_einsteiger) and (s.recht is None or hat_recht(s.recht))
    ]


def absaetze(schritt: Schritt, erfahrung: str | None) -> list[str]:
    return [*schritt.absaetze, *(schritt.einsteiger if erfahrung == ANFAENGER else ())]


def frage_zum_start(erfahrung: str | None, kennt_steuy: bool | None) -> str:
    """Was beim ersten Start gefragt wird: „starten“ (direkt), „experte“, „kennt“ oder „beides“."""
    if erfahrung == EXPERTE and kennt_steuy:
        return "beides"
    if kennt_steuy:
        return "kennt"
    if erfahrung == EXPERTE:
        return "experte"
    return "starten"
