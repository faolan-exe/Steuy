"""E-Mail-Versand per SMTP mit den Zugangsdaten aus Einstellungen → E-Mail."""

import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app

from app.domain.mail import Anhang, EmailUngueltig, baue_nachricht
from app.services.einrichtung import aktuelles_gewerbe
from app.services.geheimnis import entschluessele

ZEITLIMIT = 20  # Sekunden


class MailFehler(RuntimeError):
    pass


def eingerichtet() -> bool:
    gewerbe = aktuelles_gewerbe()
    return bool(gewerbe and gewerbe.smtp_server and gewerbe.mail_absender)


def ausgang() -> list[EmailMessage]:
    """Im Testbetrieb landen Mails hier statt beim SMTP-Server."""
    return current_app.extensions.setdefault("mail_ausgang", [])


def _sende_smtp(nachricht: EmailMessage) -> None:
    gewerbe = aktuelles_gewerbe()
    passwort = entschluessele(gewerbe.smtp_passwort) if gewerbe.smtp_passwort else None
    kontext = ssl.create_default_context()
    try:
        if gewerbe.smtp_verschluesselung == "ssl":
            verbindung = smtplib.SMTP_SSL(
                gewerbe.smtp_server, gewerbe.smtp_port, timeout=ZEITLIMIT, context=kontext
            )
        else:
            verbindung = smtplib.SMTP(gewerbe.smtp_server, gewerbe.smtp_port, timeout=ZEITLIMIT)
        with verbindung:
            if gewerbe.smtp_verschluesselung == "starttls":
                verbindung.starttls(context=kontext)
            if gewerbe.smtp_benutzer:
                verbindung.login(gewerbe.smtp_benutzer, passwort or "")
            verbindung.send_message(nachricht)
    except smtplib.SMTPAuthenticationError as fehler:
        raise MailFehler(
            "Anmeldung am Mailserver fehlgeschlagen. Benutzer und Passwort prüfen."
        ) from fehler
    except smtplib.SMTPRecipientsRefused as fehler:
        raise MailFehler("Der Mailserver hat die Empfängeradresse abgelehnt.") from fehler
    except (smtplib.SMTPException, OSError) as fehler:
        current_app.logger.warning("Mailversand fehlgeschlagen", exc_info=True)
        raise MailFehler(
            f"Der Mailserver ist nicht erreichbar oder lehnt ab ({type(fehler).__name__}). "
            "Server, Port und Verschlüsselung prüfen."
        ) from fehler


def sende(
    *,
    an: str,
    betreff: str,
    text: str,
    kopie_an: str | None = None,
    anhaenge: tuple[Anhang, ...] = (),
) -> EmailMessage:
    if not eingerichtet():
        raise MailFehler("E-Mail-Versand ist noch nicht eingerichtet (Einstellungen → E-Mail).")
    gewerbe = aktuelles_gewerbe()
    try:
        nachricht = baue_nachricht(
            absender=gewerbe.mail_absender,
            absender_name=gewerbe.name,
            an=an,
            betreff=betreff,
            text=text,
            kopie_an=kopie_an,
            antwort_an=gewerbe.email,
            anhaenge=anhaenge,
        )
    except EmailUngueltig as fehler:
        raise MailFehler(str(fehler)) from fehler
    if current_app.config.get("MAIL_TESTBETRIEB"):
        ausgang().append(nachricht)
    else:
        _sende_smtp(nachricht)
    return nachricht
