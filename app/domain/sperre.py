"""Wann ist eine Anmeldung wegen zu vieler Fehlversuche gesperrt?"""

from datetime import datetime, timedelta

FENSTER = timedelta(minutes=15)
MAX_JE_KONTO = 5
MAX_JE_ADRESSE = 20


def gesperrt(
    fehlversuche_konto: list[datetime], fehlversuche_adresse: list[datetime], jetzt: datetime
) -> bool:
    """Fehlversuche seit der letzten erfolgreichen Anmeldung, jeweils im Zeitfenster."""
    grenze = jetzt - FENSTER
    konto = sum(1 for z in fehlversuche_konto if z >= grenze)
    adresse = sum(1 for z in fehlversuche_adresse if z >= grenze)
    return konto >= MAX_JE_KONTO or adresse >= MAX_JE_ADRESSE
