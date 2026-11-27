"""Leitweg-ID für E-Rechnungen an Behörden (Formatspezifikation Leitweg-ID der KoSIT).

Aufbau: Grobadressierung (2 bis 12 Ziffern), optional Feinadressierung (bis 30 Buchstaben
oder Ziffern), Prüfziffer (2 Ziffern), getrennt durch Bindestriche, z. B. 04011000-1234512345-06.
Die Prüfziffer folgt ISO 7064 MOD 97-10 wie bei der IBAN: Alles ohne Bindestriche, Buchstaben
als Zahlen (A = 10 … Z = 35), muss bei Division durch 97 den Rest 1 ergeben."""

import re

FORM = re.compile(r"^\d{2,12}(-[A-Z0-9]{1,30})?-\d{2}$")


def sieht_aus_wie_leitweg_id(text: str) -> bool:
    """Nur Ziffern, Buchstaben und Bindestriche mit einer Ziffer am Anfang: Dann ist eine
    Leitweg-ID gemeint, keine freie Käuferreferenz."""
    return bool(re.fullmatch(r"\d[\dA-Za-z-]*", text.strip())) and "-" in text


def leitweg_fehler(text: str | None) -> str | None:
    """Fehlermeldung oder None, wenn die Leitweg-ID stimmt."""
    wert = (text or "").strip().upper()
    if not FORM.match(wert):
        return (
            "Eine Leitweg-ID sieht so aus: 04011000-1234512345-06 (Ziffern, optional ein Teil "
            "mit Buchstaben, am Ende zwei Prüfziffern)."
        )
    zahl = "".join(str(int(z, 36)) for z in wert.replace("-", ""))
    if int(zahl) % 97 != 1:
        return "Die Prüfziffer der Leitweg-ID passt nicht. Bitte genau abschreiben."
    return None
