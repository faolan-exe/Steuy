"""Wann ist eine Anmeldung wegen zu vieler Fehlversuche gesperrt?

Gesperrt wird je Konto und Absender-Adresse, nicht je Konto allein: Sonst könnte ein Fremder
mit fünf falschen Passwörtern den Inhaber aussperren (OWASP: Sperren dürfen keinen
Denial-of-Service ermöglichen). Gegen verteiltes Raten von vielen Adressen aus gilt
zusätzlich eine hohe Grenze je Konto, gegen Raten vieler Konten eine Grenze je Adresse."""

from datetime import datetime, timedelta

FENSTER = timedelta(minutes=15)
MAX_JE_KONTO_UND_ADRESSE = 5
MAX_JE_ADRESSE = 20
MAX_JE_KONTO = 50


def gesperrt(
    fehlversuche_konto_adresse: list[datetime],
    fehlversuche_adresse: list[datetime],
    jetzt: datetime,
    fehlversuche_konto: list[datetime] | None = None,
) -> bool:
    """Fehlversuche seit der letzten erfolgreichen Anmeldung, jeweils im Zeitfenster."""
    grenze = jetzt - FENSTER

    def zaehle(liste):
        return sum(1 for z in liste or [] if z >= grenze)

    return (
        zaehle(fehlversuche_konto_adresse) >= MAX_JE_KONTO_UND_ADRESSE
        or zaehle(fehlversuche_adresse) >= MAX_JE_ADRESSE
        or zaehle(fehlversuche_konto) >= MAX_JE_KONTO
    )
