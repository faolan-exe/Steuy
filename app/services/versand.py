"""Rechnungen, Angebote und Mahnungen per E-Mail verschicken, mit Verlauf."""

from datetime import date

from app.domain.geld import cent_zu_euro
from app.domain.mail import Anhang, vorlage
from app.extensions import db
from app.models import Mahnung, Rechnung, Versand
from app.services import ablage
from app.services.einrichtung import aktuelles_gewerbe
from app.services.mail import MailFehler, sende
from app.services.protokoll import protokolliere


def _datum(wert: date | None) -> str:
    return wert.strftime("%d.%m.%Y") if wert else ""


def dateiname(rechnung: Rechnung, mahnung: Mahnung | None = None) -> str:
    if mahnung:
        return f"{mahnung.bezeichnung}-{rechnung.nummer}.pdf".replace(" ", "-")
    return f"{rechnung.titel}-{rechnung.anzeige_nummer}.pdf".replace(" ", "-")


def vorschlag(rechnung: Rechnung, mahnung: Mahnung | None = None) -> dict[str, str]:
    """Empfänger, Betreff und Text zum Bearbeiten vor dem Senden."""
    gewerbe = aktuelles_gewerbe()
    werte = {
        "nummer": rechnung.anzeige_nummer,
        "firma": gewerbe.name,
        "inhaber": gewerbe.inhaber,
        "betrag": cent_zu_euro(mahnung.offen_cent if mahnung else rechnung.summe_cent),
        "faellig": _datum(rechnung.faellig_am),
        "gueltig": _datum(rechnung.gueltig_bis),
        "bezeichnung": mahnung.bezeichnung if mahnung else "",
        "frist": _datum(mahnung.frist_bis) if mahnung else "",
    }
    art = "mahnung" if mahnung else rechnung.belegart
    betreff, text = vorlage(art, werte)
    an = rechnung.kontakt.email if rechnung.kontakt and rechnung.kontakt.email else ""
    return {"an": an, "betreff": betreff, "text": text}


def sende_beleg(
    rechnung: Rechnung,
    *,
    an: str,
    betreff: str,
    text: str,
    nutzer_id: int,
    mahnung: Mahnung | None = None,
    kopie_an: str | None = None,
) -> Versand:
    """Schickt das unveränderte PDF. Auch ein Fehlversuch landet im Verlauf."""
    sha = mahnung.pdf_sha256 if mahnung else rechnung.pdf_sha256
    if not sha:
        raise MailFehler("Nur finalisierte Belege lassen sich verschicken.")
    name = dateiname(rechnung, mahnung)
    versand = Versand(
        rechnung_id=rechnung.id,
        mahnung_id=mahnung.id if mahnung else None,
        an=(an or "").strip()[:254],
        kopie_an=(kopie_an or "").strip()[:254] or None,
        betreff=" ".join((betreff or "").split())[:200],
        text=text or "",
        anhang=name,
        gesendet_von=nutzer_id,
    )
    try:
        sende(
            an=an,
            betreff=betreff,
            text=text,
            kopie_an=kopie_an or None,
            anhaenge=(Anhang(name, ablage.lies(sha)),),
        )
    except MailFehler as fehler:
        versand.erfolgreich = False
        versand.fehler = str(fehler)
        if versand.an:
            db.session.add(versand)
            db.session.commit()
        raise
    versand.erfolgreich = True
    db.session.add(versand)
    db.session.flush()
    protokolliere(
        "beleg_versendet",
        nutzer_id=nutzer_id,
        objekt_typ="rechnung",
        objekt_id=rechnung.id,
        details={"versand_id": versand.id, "an": versand.an, "mahnung_id": versand.mahnung_id},
    )
    db.session.commit()
    return versand
