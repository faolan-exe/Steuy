import re
from datetime import date, timedelta

from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import (
    BooleanField,
    DateField,
    EmailField,
    IntegerField,
    PasswordField,
    RadioField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)

from app.domain.geld import GeldFormatFehler, euro_zu_cent
from app.domain.passwort import MINDESTLAENGE, schwaches_passwort
from app.domain.rollen import ROLLEN_NAMEN
from app.domain.stammdaten import EINHEITEN
from app.domain.zahlung import ZAHLUNGSARTEN

PFLICHT = "Pflichtfeld"
EMAIL = "Bitte eine gültige E-Mail-Adresse eingeben."


def _ohne_leerzeichen(wert):
    return wert.strip() if isinstance(wert, str) else wert


OHNE_LEERZEICHEN = [_ohne_leerzeichen]


def pruefe_steuernummer(form, feld):
    text = feld.data or ""
    ziffern = re.sub(r"\D", "", text)
    if re.search(r"[^\d/\s-]", text) or not 10 <= len(ziffern) <= 13:
        raise ValidationError(
            "Bitte nur Ziffern, Schrägstriche und Bindestriche, 10 bis 13 Ziffern."
        )


def starkes_passwort(*kontextfelder: str):
    """Prüft Häufigkeit und Bezug zu Name oder E-Mail (Felder des Formulars, sonst der Nutzer)."""

    def pruefe(form, feld):
        persoenlich = [getattr(form, name).data for name in kontextfelder if hasattr(form, name)]
        if not persoenlich:
            from flask_login import current_user

            if current_user.is_authenticated:
                persoenlich = [current_user.email, current_user.name]
        grund = schwaches_passwort(feld.data or "", tuple(persoenlich))
        if grund:
            raise ValidationError(grund)

    return pruefe


class FirmendatenFormular(FlaskForm):
    name = StringField("Name des Gewerbes", [DataRequired(PFLICHT), Length(max=200)])
    inhaber = StringField("Inhaber", [DataRequired(PFLICHT), Length(max=200)])
    strasse = StringField("Straße und Hausnummer", [DataRequired(PFLICHT), Length(max=200)])
    plz = StringField(
        "PLZ",
        [DataRequired(PFLICHT), Regexp(r"^\d{5}$", message="Bitte fünfstellige Postleitzahl.")],
    )
    ort = StringField("Ort", [DataRequired(PFLICHT), Length(max=100)])
    email = EmailField(
        "E-Mail", [DataRequired(PFLICHT), Email(EMAIL), Length(max=254)], filters=OHNE_LEERZEICHEN
    )
    telefon = StringField("Telefon", [Optional(), Length(max=50)])
    steuernummer = StringField("Steuernummer", [Optional(), Length(max=30), pruefe_steuernummer])
    ust_idnr = StringField(
        "USt-IdNr.",
        [
            Optional(),
            Regexp(r"^DE\d{9}$", message="Format: DE und 9 Ziffern, z. B. DE123456789."),
        ],
    )


KLEINUNTERNEHMER = (
    "steuy ist nur für Kleinunternehmer nach § 19 UStG gedacht, "
    "die als Einzelunternehmen oder Freiberufler arbeiten."
)


class EinrichtungFormular(FirmendatenFormular):
    einzelunternehmen = BooleanField("Ich arbeite als Einzelunternehmer oder Freiberufler.")
    umsatz_passt = BooleanField(
        "Mein Umsatz im letzten Jahr lag unter der Grenze oder ich habe dieses Jahr gegründet."
    )
    erfahrung = RadioField(
        "Wie fit bist du in Buchhaltung?",
        choices=[
            ("anfaenger", "Kompletter Anfänger"),
            ("erfahren", "Bereits mal gemacht"),
            ("experte", "Experte"),
        ],
        default="anfaenger",
    )
    kennt_steuy = RadioField(
        "Hast du schon mit steuy gearbeitet?",
        choices=[("nein", "Nein, ich bin neu hier"), ("ja", "Ja")],
        default="nein",
    )
    admin_name = StringField("Dein Name", [DataRequired(PFLICHT), Length(max=200)])
    admin_email = EmailField(
        "E-Mail für die Anmeldung",
        [DataRequired(PFLICHT), Email(EMAIL), Length(max=254)],
        filters=OHNE_LEERZEICHEN,
    )
    passwort = PasswordField(
        "Passwort",
        [
            DataRequired(PFLICHT),
            Length(min=MINDESTLAENGE, message=f"Bitte mindestens {MINDESTLAENGE} Zeichen."),
            starkes_passwort("admin_email", "admin_name", "inhaber", "name"),
        ],
    )
    passwort_wiederholen = PasswordField(
        "Passwort wiederholen",
        [
            DataRequired(PFLICHT),
            EqualTo("passwort", message="Die Passwörter stimmen nicht überein."),
        ],
    )

    def validate_einzelunternehmen(self, feld):
        if not feld.data:
            raise ValidationError(KLEINUNTERNEHMER)

    def validate_umsatz_passt(self, feld):
        if not feld.data:
            raise ValidationError(KLEINUNTERNEHMER)


class CodeFormular(FlaskForm):
    code = StringField(
        "Code aus der App oder Wiederherstellungscode",
        [DataRequired(PFLICHT), Length(max=20)],
        filters=OHNE_LEERZEICHEN,
    )


class PasswortAendernFormular(FlaskForm):
    alt = PasswordField("Bisheriges Passwort", [DataRequired(PFLICHT)])
    neu = PasswordField(
        "Neues Passwort",
        [
            DataRequired(PFLICHT),
            Length(min=MINDESTLAENGE, message=f"Bitte mindestens {MINDESTLAENGE} Zeichen."),
            starkes_passwort(),
        ],
    )
    wiederholen = PasswordField(
        "Neues Passwort wiederholen",
        [DataRequired(PFLICHT), EqualTo("neu", message="Die Passwörter stimmen nicht überein.")],
    )


class AnmeldeFormular(FlaskForm):
    email = EmailField("E-Mail", [DataRequired(PFLICHT)], filters=OHNE_LEERZEICHEN)
    passwort = PasswordField("Passwort", [DataRequired(PFLICHT)])


ROLLEN_AUSWAHL = [(rolle.value, name) for rolle, name in ROLLEN_NAMEN.items()]


MAX_TAGE_VORAUS = 30
PASSWORT_LAENGE = Length(min=MINDESTLAENGE, message=f"Bitte mindestens {MINDESTLAENGE} Zeichen.")


class AuswahlFeld(SelectField):
    """Auswahlliste mit deutscher Fehlermeldung."""

    def pre_validate(self, form):
        if self.data not in {wert for wert, *_ in self.iter_choices()}:
            raise ValidationError("Bitte aus der Liste wählen.")


class Datumsfeld(DateField):
    """Datumsfeld mit deutscher Fehlermeldung."""

    def process_formdata(self, valuelist):
        try:
            super().process_formdata(valuelist)
        except ValueError:
            self.data = None
            raise ValueError("Bitte ein gültiges Datum eingeben.") from None


class NutzerAnlegenFormular(FlaskForm):
    name = StringField("Name", [DataRequired(PFLICHT), Length(max=200)])
    email = EmailField(
        "E-Mail", [DataRequired(PFLICHT), Email(EMAIL), Length(max=254)], filters=OHNE_LEERZEICHEN
    )
    rolle = AuswahlFeld("Rolle", choices=ROLLEN_AUSWAHL, default="mitarbeiter")
    passwort = PasswordField(
        "Erstes Passwort",
        [DataRequired(PFLICHT), PASSWORT_LAENGE, starkes_passwort("email", "name")],
    )
    zugang_bis = Datumsfeld("Zugang bis", [Optional()])

    def validate_zugang_bis(self, feld):
        if feld.data and feld.data < date.today():
            raise ValidationError("Das Datum liegt in der Vergangenheit.")


class NutzerBearbeitenFormular(FlaskForm):
    name = StringField("Name", [DataRequired(PFLICHT), Length(max=200)])
    email = EmailField(
        "E-Mail", [DataRequired(PFLICHT), Email(EMAIL), Length(max=254)], filters=OHNE_LEERZEICHEN
    )
    rolle = AuswahlFeld("Rolle", choices=ROLLEN_AUSWAHL)
    aktiv = BooleanField("Zugang aktiv")
    zugang_bis = Datumsfeld("Zugang bis", [Optional()])
    neues_passwort = PasswordField(
        "Neues Passwort", [Optional(), PASSWORT_LAENGE, starkes_passwort("email", "name")]
    )


def pruefe_ust_idnr(form, feld):
    wert = (feld.data or "").upper()
    deutsch = re.fullmatch(r"DE\d{9}", wert)
    ausland = not wert.startswith("DE") and re.fullmatch(r"[A-Z]{2}[0-9A-Z+*.]{2,12}", wert)
    if not (deutsch or ausland):
        raise ValidationError("USt-IdNr. bitte mit Länderkürzel, z. B. DE123456789.")


class KontaktFormular(FlaskForm):
    art = RadioField("Art", choices=[("firma", "Firma"), ("person", "Person")], default="firma")
    firmenname = StringField("Firmenname", [Length(max=200)])
    anrede = StringField("Anrede", [Optional(), Length(max=30)])
    vorname = StringField("Vorname", [Optional(), Length(max=100)])
    nachname = StringField("Nachname", [Length(max=100)])
    typ = AuswahlFeld(
        "Typ",
        choices=[("kunde", "Kunde"), ("lieferant", "Lieferant"), ("beides", "Kunde und Lieferant")],
        default="kunde",
    )
    adresszusatz = StringField("Adresszusatz", [Optional(), Length(max=200)])
    strasse = StringField(
        "Straße und Hausnummer", [Optional(), Length(max=200)], description="kontakt"
    )
    plz = StringField("PLZ", [Optional(), Length(max=10)])
    ort = StringField("Ort", [Optional(), Length(max=100)])
    land = StringField("Land", [DataRequired(PFLICHT), Length(max=100)], default="Deutschland")
    email = EmailField(
        "E-Mail",
        [Optional(), Email(EMAIL), Length(max=254)],
        filters=OHNE_LEERZEICHEN,
        description="kontakt",
    )
    telefon = StringField("Telefon", [Optional(), Length(max=50)], description="kontakt")
    leitweg_id = StringField(
        "Leitweg-ID (nur bei Behörden)", [Optional(), Length(max=46)], description="kontakt"
    )
    steuernummer = StringField("Steuernummer", [Optional(), Length(max=30)], description="kontakt")
    ust_idnr = StringField(
        "USt-IdNr.", [Optional(), pruefe_ust_idnr], filters=OHNE_LEERZEICHEN, description="kontakt"
    )
    notiz = TextAreaField("Notiz (intern)", [Optional()])
    mahnsperre = BooleanField("Mahnsperre: Diesen Kontakt nie mahnen")

    def validate_firmenname(self, feld):
        if self.art.data == "firma" and not (feld.data or "").strip():
            raise ValidationError("Firmenname fehlt.")

    def validate_nachname(self, feld):
        if self.art.data == "person" and not (feld.data or "").strip():
            raise ValidationError("Nachname fehlt.")

    def validate_plz(self, feld):
        deutschland = (self.land.data or "").strip().lower() in {"deutschland", "de"}
        if deutschland and feld.data and not re.fullmatch(r"\d{5}", feld.data.strip()):
            raise ValidationError("Bitte fünfstellige Postleitzahl.")


class ArtikelFormular(FlaskForm):
    typ = RadioField(
        "Typ", choices=[("produkt", "Produkt"), ("service", "Service")], default="produkt"
    )
    bezeichnung = StringField("Bezeichnung", [DataRequired(PFLICHT), Length(max=200)])
    beschreibung = TextAreaField("Beschreibung", [Optional()])
    artikelnummer = StringField("Artikelnummer", [Optional(), Length(max=50)])
    gtin = StringField(
        "GTIN/EAN",
        [Optional(), Regexp(r"^(\d{8}|\d{12,14})$", message="GTIN hat 8, 12, 13 oder 14 Ziffern.")],
        filters=OHNE_LEERZEICHEN,
    )
    einheit = AuswahlFeld("Einheit", choices=[(e, e) for e in EINHEITEN], default="Stück")
    preis = StringField("Preis", [DataRequired(PFLICHT)])
    notiz = TextAreaField("Notiz (intern)", [Optional()])

    preis_cent: int | None = None

    def validate_preis(self, feld):
        try:
            self.preis_cent = euro_zu_cent(feld.data)
        except GeldFormatFehler as fehler:
            raise ValidationError(str(fehler).split(":")[0] + ".") from fehler


def pruefe_iban_feld(form, feld):
    from app.domain.iban import IbanFehler, pruefe_iban

    try:
        feld.data = pruefe_iban(feld.data)
    except IbanFehler as fehler:
        raise ValidationError(str(fehler)) from fehler


def pruefe_hinweis_19(form, feld):
    if "19" not in (feld.data or ""):
        raise ValidationError("Der Hinweis muss § 19 UStG nennen.")


class RechnungseinstellungenFormular(FlaskForm):
    kontoinhaber = StringField("Kontoinhaber", [Optional(), Length(max=70)])
    iban = StringField("IBAN", [Optional(), pruefe_iban_feld])
    bic = StringField(
        "BIC",
        [
            Optional(),
            Regexp(r"^[A-Za-z0-9]{8}([A-Za-z0-9]{3})?$", message="BIC hat 8 oder 11 Zeichen."),
        ],
        filters=[lambda w: w.strip().upper() if isinstance(w, str) else w],
    )
    bank = StringField("Bank", [Optional(), Length(max=100)])
    praefix = StringField("Präfix", [Optional(), Length(max=20)], default="RE")
    stellen = IntegerField(
        "Stellen", [InputRequired(PFLICHT), NumberRange(1, 8, "Zwischen 1 und 8.")], default=4
    )
    naechste_nummer = IntegerField(
        "Nächste Nummer", [InputRequired(PFLICHT), NumberRange(1, message="Mindestens 1.")]
    )
    zahlungsziel_tage = IntegerField(
        "Zahlungsziel in Tagen",
        [InputRequired(PFLICHT), NumberRange(0, 365, "Zwischen 0 und 365.")],
    )
    angebot_gueltig_tage = IntegerField(
        "Angebote gültig (Tage)",
        [InputRequired(PFLICHT), NumberRange(1, 365, "Zwischen 1 und 365.")],
        default=30,
    )
    hinweis_steuerbefreiung = TextAreaField(
        "Hinweis auf die Steuerbefreiung", [DataRequired(PFLICHT), pruefe_hinweis_19]
    )
    rechnung_einleitung = TextAreaField("Einleitungstext", [Optional()])
    rechnung_nachbemerkung = TextAreaField("Nachbemerkung", [Optional()])
    e_rechnung = BooleanField("E-Rechnung zu jeder Rechnung erzeugen (ZUGFeRD)")


class ZahlungFormular(FlaskForm):
    datum = Datumsfeld("Bezahlt am", [InputRequired(PFLICHT)])
    betrag = StringField("Betrag €", [DataRequired(PFLICHT)])
    zahlungsart = AuswahlFeld("Zahlungsart", choices=list(ZAHLUNGSARTEN.items()))
    angekommen = StringField("Tatsächlich angekommen €", [Optional()])
    notiz = StringField("Notiz", [Optional(), Length(max=500)])
    referenz = StringField("Referenz", [Optional(), Length(max=100)])
    nachweis = FileField("Nachweis (optional)")

    betrag_cent: int | None = None
    angekommen_cent: int | None = None

    def validate_betrag(self, feld):
        try:
            self.betrag_cent = euro_zu_cent(feld.data)
        except GeldFormatFehler as fehler:
            raise ValidationError("Ungültiger Betrag, z. B. 152,20.") from fehler

    def validate_angekommen(self, feld):
        if not (feld.data or "").strip():
            self.angekommen_cent = None
            return
        try:
            self.angekommen_cent = euro_zu_cent(feld.data)
        except GeldFormatFehler as fehler:
            raise ValidationError("Ungültiger Betrag, z. B. 147,50.") from fehler


class BuchungFormular(FlaskForm):
    art = RadioField(
        "Art", choices=[("ausgabe", "Ausgabe"), ("einnahme", "Einnahme")], default="ausgabe"
    )
    kontakt_id = SelectField("Kontakt", choices=[("", "– kein Kontakt –")], default="")
    partner = StringField("Lieferant / Zahler", [Optional(), Length(max=200)])
    belegdatum = Datumsfeld("Belegdatum", [InputRequired(PFLICHT)])

    def validate_belegdatum(self, feld):
        if feld.data and feld.data > date.today() + timedelta(days=MAX_TAGE_VORAUS):
            raise ValidationError(
                f"Das Belegdatum liegt mehr als {MAX_TAGE_VORAUS} Tage in der Zukunft. "
                "Bitte Jahr und Tag prüfen."
            )

    belegnummer = StringField("Belegnummer", [Optional(), Length(max=60)])
    betrag = StringField("Betrag brutto €", [DataRequired(PFLICHT)])
    kategorie_id = SelectField("Kategorie", choices=[("", "– bitte wählen –")], default="")
    betrieblich_prozent = IntegerField(
        "Betrieblicher Anteil %",
        [InputRequired(PFLICHT), NumberRange(0, 100, "Zwischen 0 und 100.")],
        default=100,
    )
    beschreibung = TextAreaField("Beschreibung", [Optional()])
    bereits_bezahlt = BooleanField("Bereits bezahlt")
    bezahlt_am = Datumsfeld("Bezahlt am", [Optional()])
    zahlungsart = AuswahlFeld("Zahlungsart", choices=list(ZAHLUNGSARTEN.items()))

    betrag_cent: int | None = None

    def validate_betrag(self, feld):
        try:
            self.betrag_cent = euro_zu_cent(feld.data)
        except GeldFormatFehler as fehler:
            raise ValidationError("Ungültiger Betrag, z. B. 49,90.") from fehler
        if self.betrag_cent <= 0:
            raise ValidationError("Der Betrag muss größer als 0 sein.")

    def validate(self, extra_validators=None):
        gueltig = super().validate(extra_validators)
        if self.bereits_bezahlt.data and not self.bezahlt_am.data:
            self.bezahlt_am.errors = [*self.bezahlt_am.errors, "Bitte das Zahlungsdatum angeben."]
            return False
        return gueltig


class BuchungsZahlungFormular(FlaskForm):
    datum = Datumsfeld("Bezahlt am", [InputRequired(PFLICHT)])
    betrag = StringField("Betrag €", [DataRequired(PFLICHT)])
    zahlungsart = AuswahlFeld("Zahlungsart", choices=list(ZAHLUNGSARTEN.items()))
    notiz = StringField("Notiz", [Optional(), Length(max=500)])

    betrag_cent: int | None = None

    def validate_betrag(self, feld):
        try:
            self.betrag_cent = euro_zu_cent(feld.data)
        except GeldFormatFehler as fehler:
            raise ValidationError("Ungültiger Betrag.") from fehler


class WechselExportFormular(FlaskForm):
    kontenrahmen = SelectField(
        "Kontenrahmen",
        choices=[("SKR03", "SKR03"), ("SKR04", "SKR04")],
        default="SKR03",
    )
    beraternummer = IntegerField(
        "Beraternummer",
        default=1001,
        validators=[InputRequired(), NumberRange(1001, 9999999, "Zwischen 1001 und 9999999.")],
    )
    mandantennummer = IntegerField(
        "Mandantennummer",
        default=1,
        validators=[InputRequired(), NumberRange(1, 99999, "Zwischen 1 und 99999.")],
    )


class MailEinstellungenFormular(FlaskForm):
    smtp_server = StringField("SMTP-Server", [Optional(), Length(max=200)])
    smtp_port = IntegerField(
        "Port", [InputRequired(PFLICHT), NumberRange(1, 65535, "Zwischen 1 und 65535.")]
    )
    smtp_verschluesselung = SelectField(
        "Verschlüsselung",
        choices=[
            ("starttls", "STARTTLS (meist Port 587)"),
            ("ssl", "SSL/TLS (meist Port 465)"),
            ("keine", "Keine (nicht empfohlen)"),
        ],
    )
    smtp_benutzer = StringField("Benutzername", [Optional(), Length(max=200)])
    smtp_passwort = PasswordField("Passwort", [Optional(), Length(max=500)])
    mail_absender = EmailField(
        "Absenderadresse", [Optional(), Email("Bitte eine gültige E-Mail-Adresse angeben.")]
    )

    def validate(self, extra_validators=None):
        gueltig = super().validate(extra_validators)
        # Optional() beendet die Prüfung leerer Felder, daher hier statt validate_mail_absender
        if self.smtp_server.data and not self.mail_absender.data:
            self.mail_absender.errors = [
                *self.mail_absender.errors,
                "Bitte die Adresse angeben, von der gesendet wird.",
            ]
            return False
        return gueltig


class SendenFormular(FlaskForm):
    an = EmailField("An", [DataRequired(PFLICHT), Email("Bitte eine gültige E-Mail-Adresse.")])
    kopie_an_mich = BooleanField("Kopie an mich")
    betreff = StringField("Betreff", [DataRequired(PFLICHT), Length(max=200)])
    text = TextAreaField(
        "Nachricht", [DataRequired(PFLICHT), Length(max=10000)], render_kw={"rows": 12}
    )


class ShopFormular(FlaskForm):
    shop_url = StringField("Adresse des Shops", [Optional(), Length(max=300)])
    shop_schluessel = PasswordField("Consumer Key", [Optional(), Length(max=200)])
    shop_geheimnis = PasswordField("Consumer Secret", [Optional(), Length(max=200)])
    shop_auto_versand = BooleanField(
        "Shop-Rechnungen sofort erstellen und verschicken (Auto-Modus)"
    )


class AnlagegutFormular(FlaskForm):
    bezeichnung = StringField("Bezeichnung", [DataRequired(PFLICHT), Length(max=200)])
    art = RadioField(
        "Was ist es?",
        choices=[
            ("computer", "Computer, Laptop, Tablet, Drucker oder anderes Zubehör"),
            ("software", "Software"),
            ("beweglich", "Etwas anderes zum Anfassen (z. B. Möbel, Kamera, Fahrzeug)"),
            ("immateriell", "Etwas anderes Nicht-Greifbares (z. B. Lizenz, Website)"),
        ],
        default="computer",
    )
    anschaffungsdatum = Datumsfeld("Angeschafft am", [InputRequired(PFLICHT)])
    nutzungsdauer_jahre = IntegerField(
        "Nutzungsdauer in Jahren",
        [Optional(), NumberRange(1, 50, "Zwischen 1 und 50 Jahren.")],
    )

    def validate(self, extra_validators=None):
        gueltig = super().validate(extra_validators)
        # Optional() beendet die Prüfung leerer Felder, daher hier
        if self.art.data in ("beweglich", "immateriell") and not self.nutzungsdauer_jahre.data:
            self.nutzungsdauer_jahre.errors = [
                *self.nutzungsdauer_jahre.errors,
                "Bitte die Nutzungsdauer angeben.",
            ]
            return False
        return gueltig
