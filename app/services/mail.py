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
        raise MailFehler(_erklaere(fehler, gewerbe)) from fehler


def _erklaere(fehler: Exception, gewerbe) -> str:
    """Verständliche Meldung statt technischer Fehlernamen wie „gaierror“."""
    import socket

    port, art = gewerbe.smtp_port, gewerbe.smtp_verschluesselung
    passt_nicht = (port == 465 and art != "ssl") or (port == 587 and art == "ssl")
    tipp = (
        " Port und Verschlüsselung passen nicht zusammen: 465 gehört zu SSL, 587 zu STARTTLS."
        if passt_nicht
        else ""
    )
    if isinstance(fehler, socket.gaierror):
        return (
            f"Den Mailserver „{gewerbe.smtp_server}“ gibt es nicht oder er ist gerade nicht "
            "erreichbar. Bitte die Schreibweise prüfen." + tipp
        )
    if isinstance(fehler, TimeoutError | ConnectionRefusedError | ssl.SSLError):
        return (
            f"Der Mailserver ist über Port {port} nicht erreichbar. Port und "
            "Verschlüsselung prüfen." + tipp
        )
    return (
        "Der Mailserver ist nicht erreichbar oder lehnt ab. "
        "Server, Port und Verschlüsselung prüfen." + tipp
    )


def sende(
    *,
    an: str,
    betreff: str,
    text: str,
    kopie_an: str | None = None,
    anhaenge: tuple[Anhang, ...] = (),
    html: str | None = None,
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
            html=html,
        )
    except EmailUngueltig as fehler:
        raise MailFehler(str(fehler)) from fehler
    if current_app.config.get("MAIL_TESTBETRIEB"):
        ausgang().append(nachricht)
    else:
        _sende_smtp(nachricht)
    return nachricht
