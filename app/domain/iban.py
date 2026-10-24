"""IBAN prüfen (ISO 13616, Prüfziffer nach Modulo 97)."""

import re

_FORMAT = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
_LAENGEN = {
    "DE": 22,
    "AT": 20,
    "CH": 21,
    "NL": 18,
    "BE": 16,
    "FR": 27,
    "IT": 27,
    "ES": 24,
    "LU": 20,
}


class IbanFehler(ValueError):
    pass


def pruefe_iban(text: str) -> str:
    """Gibt die IBAN ohne Leerzeichen in Großbuchstaben zurück oder wirft IbanFehler."""
    iban = (text or "").replace(" ", "").upper()
    if not _FORMAT.match(iban):
        raise IbanFehler("Ungültige IBAN.")
    if iban[:2] in _LAENGEN and len(iban) != _LAENGEN[iban[:2]]:
        raise IbanFehler(f"Eine IBAN aus {iban[:2]} hat {_LAENGEN[iban[:2]]} Zeichen.")
    umgestellt = iban[4:] + iban[:4]
    zahl = "".join(str(int(z, 36)) for z in umgestellt)
    if int(zahl) % 97 != 1:
        raise IbanFehler(
            "Die IBAN ist ungültig (Prüfziffer stimmt nicht). Bitte Tippfehler prüfen."
        )
    return iban


def formatiere_iban(iban: str) -> str:
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))
