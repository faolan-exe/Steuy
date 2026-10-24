"""Passwörter hashen und prüfen (Argon2id)."""

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MINDESTLAENGE = 10

_hasher = PasswordHasher()
# Wird geprüft, wenn es den Nutzer nicht gibt, damit die Antwortzeit nichts verrät.
_ATTRAPPE = _hasher.hash("keine-echte-anmeldung")


class PasswortZuKurz(ValueError):
    pass


# Häufige Passwörter (klein geschrieben). Ziffern und Satzzeichen am Ende werden vor dem
# Vergleich abgeschnitten, damit auch „Passwort2026!“ auffällt.
HAEUFIGE = frozenset(
    """
    passwort password passwort1 geheim geheim123 hallo hallo123 willkommen welcome login admin
    administrator administrator1 qwertz qwerty qwertzuiop qwertyuiop asdfgh asdfghjkl yxcvbn
    abc123 abcdef abcdefgh abcdefghij letmein iloveyou monkey dragon master sunshine princess
    football fussball bayern bundesliga schalke dortmund hamburg berlin muenchen sommer winter
    frühling herbst sonne mond schatz schatzi liebe liebling hund katze mausi mäuschen
    superman batman michael daniel thomas andreas stefan sabine julia lisa maria lena
    computer internet test testtest test123 default changeme trustno1 000000 123456 12345678
    123456789 1234567890 0123456789 654321 111111 121212 123123 987654321 passw0rd p@ssw0rd
    p@ssword steuy buchhaltung rechnung firma geschaeft geschäft kunde mustermann musterfirma
    """.split()  # noqa: SIM905
)
TASTATURREIHEN = (
    "qwertzuiopü",
    "qwertyuiop",
    "asdfghjklöä",
    "yxcvbnm",
    "zxcvbnm",
    "1234567890",
    "abcdefghijklmnopqrstuvwxyz",
)


def schwaches_passwort(passwort: str, persoenlich: tuple[str, ...] = ()) -> str | None:
    """Gibt den Grund zurück, warum das Passwort zu leicht zu erraten ist, sonst None.

    Bewusst keine Pflicht für Sonderzeichen oder Großbuchstaben: Länge und Unvorhersehbarkeit
    zählen. `persoenlich` sind Namen und E-Mail-Adressen, die nicht im Passwort stehen sollen."""
    klein = passwort.lower()
    kern = klein.rstrip("0123456789!?.,;:-_#+*~ ")
    if klein in HAEUFIGE or kern in HAEUFIGE:
        return "Dieses Passwort ist sehr häufig und wird zuerst ausprobiert."
    if len(set(klein)) <= 3:
        return "Das Passwort besteht fast nur aus gleichen Zeichen."
    for reihe in TASTATURREIHEN:
        if len(klein) >= 6 and (klein in reihe or klein in reihe[::-1]):
            return "Das Passwort ist eine Tastatur- oder Zahlenreihe."
    for text in persoenlich:
        for teil in re.split(r"[^0-9a-zäöüß]+", (text or "").lower()):
            if len(teil) >= 4 and teil in klein:
                return "Das Passwort enthält deinen Namen oder deine E-Mail-Adresse."
    return None


def hash_passwort(passwort: str) -> str:
    if len(passwort) < MINDESTLAENGE:
        raise PasswortZuKurz(f"Das Passwort braucht mindestens {MINDESTLAENGE} Zeichen.")
    return _hasher.hash(passwort)


def hash_einmalcode(code: str) -> str:
    """Für kurze Einmalcodes (z. B. 6 Ziffern per Mail): ohne Mindestlänge, Schutz über
    kurze Gültigkeit, Einmalnutzung und die Anmeldesperre."""
    return _hasher.hash(code)


def pruefe_passwort(passwort_hash: str | None, passwort: str) -> bool:
    try:
        return _hasher.verify(passwort_hash or _ATTRAPPE, passwort) and passwort_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def normalisiere_email(email: str) -> str:
    return email.strip().lower()
