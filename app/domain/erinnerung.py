"""Wöchentliche Zusammenfassung von „Zu prüfen“ (docs/domain/zahlungen-und-pruefung.md)."""

from datetime import UTC, datetime, time, timedelta

# Montags ab 6 Uhr UTC (7 bzw. 8 Uhr deutscher Zeit)
STUNDE_UTC = 6


def wochenbeginn(jetzt: datetime) -> datetime:
    """Montag dieser Woche, 6 Uhr UTC. Vor diesem Zeitpunkt zählt noch die Vorwoche."""
    jetzt = jetzt.astimezone(UTC)
    montag = (jetzt - timedelta(days=jetzt.weekday())).date()
    beginn = datetime.combine(montag, time(STUNDE_UTC), tzinfo=UTC)
    return beginn if jetzt >= beginn else beginn - timedelta(days=7)


def faellig(zuletzt: datetime | None, jetzt: datetime) -> bool:
    """Höchstens eine Mail je Woche, auch wenn der Zeitplan öfter läuft."""
    return zuletzt is None or zuletzt.astimezone(UTC) < wochenbeginn(jetzt)


def zeilen(punkte: list[tuple[int, str, str]]) -> list[str]:
    """(Anzahl, Einzahl, Mehrzahl) → „- 2 überfällige Rechnungen“, leere Punkte fallen weg."""
    return [f"- {n} {einzahl if n == 1 else mehrzahl}" for n, einzahl, mehrzahl in punkte if n]


def text(name: str, firma: str, punkte: list[str], link: str | None) -> str:
    teile = [
        f"Hallo {name},",
        "",
        f"in steuy wartet für {firma} diese Woche Folgendes auf dich:",
        "",
        *punkte,
        "",
    ]
    if link:
        teile += [f"Zur Übersicht: {link}", ""]
    teile += [
        "Du bekommst diese Mail montags, wenn unter „Zu prüfen“ etwas liegt. "
        "Abbestellen kannst du sie in steuy unter Profil → E-Mail.",
    ]
    return "\n".join(teile)
