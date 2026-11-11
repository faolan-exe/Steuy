"""E-Mails zu Belegen: Vorlagen und Aufbau der Nachricht, ohne Versand."""

import re
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from html import escape

ADRESSE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")

VORLAGEN = {
    "rechnung": (
        "Rechnung {nummer} von {firma}",
        "Guten Tag,\n\n"
        "anbei erhalten Sie die Rechnung {nummer} über {betrag}.\n"
        "Bitte überweisen Sie den Betrag bis zum {faellig}. Mit dem QR-Code auf der Rechnung "
        "geht das direkt aus der Banking-App.\n\n"
        "{link}"
        "Vielen Dank für Ihren Auftrag!\n\n"
        "Viele Grüße\n{inhaber}\n{firma}",
    ),
    "korrektur": (
        "Rechnungskorrektur {nummer} von {firma}",
        "Guten Tag,\n\n"
        "anbei erhalten Sie die Rechnungskorrektur {nummer}. Sie hebt die genannte Rechnung "
        "auf, der Betrag ist nicht mehr fällig.\n\n"
        "{link}"
        "Viele Grüße\n{inhaber}\n{firma}",
    ),
    "angebot": (
        "Angebot {nummer} von {firma}",
        "Guten Tag,\n\n"
        "vielen Dank für Ihre Anfrage. Anbei erhalten Sie unser Angebot {nummer} über "
        "{betrag}, gültig bis zum {gueltig}.\n\n"
        "{link}"
        "Bei Fragen melden Sie sich gern.\n\n"
        "Viele Grüße\n{inhaber}\n{firma}",
    ),
    "lieferschein": (
        "Lieferschein {nummer} von {firma}",
        "Guten Tag,\n\n"
        "anbei erhalten Sie den Lieferschein {nummer} zu Ihrer Bestellung. Bitte prüfen Sie die "
        "Lieferung auf Vollständigkeit und melden Sie sich bei Fragen gern.\n\n"
        "{link}"
        "Viele Grüße\n{inhaber}\n{firma}",
    ),
    "mahnung": (
        "{bezeichnung} zu Rechnung {nummer}",
        "Guten Tag,\n\n"
        "sicher ist es Ihnen nur entgangen: Für die Rechnung {nummer} ist noch {betrag} offen. "
        "Anbei erhalten Sie unsere {bezeichnung}. Bitte überweisen Sie den Betrag bis zum "
        "{frist}.\n\n"
        "{link}"
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


# Absatz mit dem Link ins Kundenportal, je Belegart
LINK_TEXTE = {
    "rechnung": "Online ansehen, herunterladen und bezahlen:",
    "korrektur": "Online ansehen und herunterladen:",
    "angebot": "Hier können Sie das Angebot online ansehen und mit einem Klick annehmen:",
    "lieferschein": "Online ansehen und herunterladen:",
    "mahnung": "Rechnung und Zahlungsdaten online:",
}
KNOPF_TEXTE = {
    "rechnung": "Rechnung ansehen",
    "korrektur": "Rechnungskorrektur ansehen",
    "angebot": "Angebot ansehen und annehmen",
    "lieferschein": "Lieferschein ansehen",
    "mahnung": "Rechnung ansehen",
}


def vorlage(art: str, werte: dict[str, str]) -> tuple[str, str]:
    betreff, text = VORLAGEN[art]
    link = werte.get("link")
    werte = {**werte, "link": f"{LINK_TEXTE[art]}\n{link}\n\n" if link else ""}
    return betreff.format(**werte), text.format(**werte)


def als_html(text: str, link: str | None = None, knopf: str = "Ansehen") -> str:
    """HTML-Fassung einer Text-Mail: gleicher Text, Links klickbar, der Portal-Link als Knopf.
    Der Text wurde vorher im Formular bearbeitet, deshalb wird alles maskiert."""
    absaetze = []
    for absatz in re.split(r"\n\s*\n", text.strip()):
        zeilen = absatz.split("\n")
        if link and link in absatz:
            vorher = [z for z in zeilen if z.strip() != link]
            if vorher:
                absaetze.append(f"<p>{'<br>'.join(escape(z) for z in vorher)}</p>")
            stil = (
                "background:#0f7c80;color:#ffffff;text-decoration:none;padding:12px 22px;"
                "border-radius:6px;font-weight:600;display:inline-block"
            )
            absaetze.append(
                f'<p style="margin:24px 0"><a href="{escape(link)}" style="{stil}">'
                f"{escape(knopf)}</a></p>"
            )
            continue
        absaetze.append(f"<p>{'<br>'.join(_verlinke(escape(z)) for z in zeilen)}</p>")
    return (
        '<!doctype html><html lang="de"><head><meta charset="utf-8"></head>'
        '<body style="margin:0;padding:24px;background:#f4f6f7">'
        '<div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:8px;'
        'padding:28px;font:15px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2529">'
        + "".join(absaetze)
        + "</div></body></html>"
    )


def _verlinke(zeile: str) -> str:
    return re.sub(r"(https?://[^\s<>&\"]+)", r'<a href="\1" style="color:#0f7c80">\1</a>', zeile)


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
    html: str | None = None,
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
    if html:
        nachricht.add_alternative(html, subtype="html")
    for anhang in anhaenge:
        haupt, _, unter = anhang.mime.partition("/")
        nachricht.add_attachment(anhang.inhalt, maintype=haupt, subtype=unter, filename=anhang.name)
    return nachricht
