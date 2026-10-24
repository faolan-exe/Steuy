"""Inhalt des GiroCode-QR-Codes nach EPC069-12, Version 002 (SEPA-Überweisung)."""

from app.domain.geld import cent_zu_dezimal

MAX_BETRAG_CENT = 99_999_999_999  # 999.999.999,99 €


class EpcFehler(ValueError):
    pass


def epc_payload(
    *, name: str, iban: str, bic: str | None, betrag_cent: int, verwendungszweck: str
) -> str:
    if not 1 <= betrag_cent <= MAX_BETRAG_CENT:
        raise EpcFehler(
            "Ein QR-Code ist nur für Beträge zwischen 0,01 € und 999.999.999,99 € möglich."
        )
    zeilen = [
        "BCD",  # Service Tag
        "002",  # Version, BIC optional
        "1",  # Zeichensatz UTF-8
        "SCT",  # SEPA Credit Transfer
        (bic or "").strip(),
        name.strip()[:70],
        iban,
        f"EUR{cent_zu_dezimal(betrag_cent)}",
        "",  # Purpose Code
        "",  # strukturierte Referenz (nicht zusammen mit Freitext)
        verwendungszweck.strip()[:140],
    ]
    return "\n".join(zeilen)
