"""E-Mails zu Belegen: Vorlagen und Aufbau der Nachricht, ohne Versand."""

import re
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

ADRESSE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")

VORLAGEN = {
    "rechnung": (
        "Rechnung {nummer} von {firma}",
        "Guten Tag,\n\n"
        "anbei erhalten Sie die Rechnung {nummer} über {betrag}.\n"
        "Bitte überweisen Sie den Betrag bis zum {faellig}. Mit dem QR-Code auf der Rechnung "
        "geht das direkt aus der Banking-App.\n\n"
        "Vielen Dank für Ihren Auftrag!\n\n"
        "Viele Grüße\n{inhaber}\n{firma}",
    ),
    "korrektur": (
        "Rechnungskorrektur {nummer} von {firma}",
        "Guten Tag,\n\n"
        "anbei erhalten Sie die Rechnungskorrektur {nummer}. Sie hebt die genannte Rechnung "
        "auf, der Betrag ist nicht mehr fällig.\n\n"
        "Viele Grüße\n{inhaber}\n{firma}",
    ),
    "angebot": (
        "Angebot {nummer} von {firma}",
        "Guten Tag,\n\n"
        "vielen Dank für Ihre Anfrage. Anbei erhalten Sie unser Angebot {nummer} über "
        "{betrag}, gültig bis zum {gueltig}.\n\n"
        "Bei Fragen melden Sie sich gern.\n\n"
        "Viele Grüße\n{inhaber}\n{firma}",
    ),
    "lieferschein": (
        "Lieferschein {nummer} von {firma}",
        "Guten Tag,\n\n"
        "anbei erhalten Sie den Lieferschein {nummer} zu Ihrer Bestellung. Bitte prüfen Sie die "
        "Lieferung auf Vollständigkeit und melden Sie sich bei Fragen gern.\n\n"
        "Viele Grüße\n{inhaber}\n{firma}",
    ),
    "mahnung": (
        "{bezeichnung} zu Rechnung {nummer}",
        "Guten Tag,\n\n"
        "sicher ist es Ihnen nur entgangen: Für die Rechnung {nummer} ist noch {betrag} offen. "
        "Anbei erhalten Sie unsere {bezeichnung}. Bitte überweisen Sie den Betrag bis zum "
        "{frist}.\n\n"
        "Sollte sich Ihre Zahlung mit diesem Schreiben überschnitten haben, betrachten Sie "
        "es bitte als gegenstandslos.\n\n"
        "Viele Grüße\n{inhaber}\n{firma}",
    ),
}


class EmailUngueltig(ValueError):
    pass


@dataclass(frozen=True)
class Anhang:
    name: str
    inhalt: bytes
    mime: str = "application/pdf"


def pruefe_adresse(adresse: str | None, feld: str = "Empfänger") -> str:
    adresse = (adresse or "").strip()
    if not ADRESSE.match(adresse):
        raise EmailUngueltig(f"{feld}: Bitte eine gültige E-Mail-Adresse angeben.")
    return adresse


def vorlage(art: str, werte: dict[str, str]) -> tuple[str, str]:
    betreff, text = VORLAGEN[art]
    return betreff.format(**werte), text.format(**werte)


def baue_nachricht(
    *,
    absender: str,
    absender_name: str,
    an: str,
    betreff: str,
    text: str,
    kopie_an: str | None = None,
    antwort_an: str | None = None,
    anhaenge: tuple[Anhang, ...] = (),
) -> EmailMessage:
    betreff = " ".join((betreff or "").split())
    if not betreff:
        raise EmailUngueltig("Bitte einen Betreff angeben.")
    if not (text or "").strip():
        raise EmailUngueltig("Bitte einen Text angeben.")
    nachricht = EmailMessage()
    nachricht["From"] = formataddr((absender_name, pruefe_adresse(absender, "Absender")))
    nachricht["To"] = pruefe_adresse(an)
    if kopie_an:
        nachricht["Bcc"] = pruefe_adresse(kopie_an, "Kopie an")
    if antwort_an and antwort_an != absender:
        nachricht["Reply-To"] = pruefe_adresse(antwort_an, "Antwort an")
    nachricht["Subject"] = betreff[:200]
    nachricht["Message-ID"] = make_msgid(domain=absender.rsplit("@", 1)[-1])
    nachricht.set_content(text)
    for anhang in anhaenge:
        haupt, _, unter = anhang.mime.partition("/")
        nachricht.add_attachment(anhang.inhalt, maintype=haupt, subtype=unter, filename=anhang.name)
    return nachricht
