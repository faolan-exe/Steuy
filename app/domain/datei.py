"""Dateityp anhand des Inhalts erkennen, nicht anhand der Endung."""

TYPEN = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "application/xml": ".xml",
}


def erkenne_typ(inhalt: bytes) -> str | None:
    if inhalt.startswith(b"%PDF-"):
        return "application/pdf"
    if inhalt.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if inhalt.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    anfang = inhalt[:200].lstrip(b"\xef\xbb\xbf \t\r\n")
    if anfang.startswith(b"<?xml") or anfang.startswith(b"<"):
        return "application/xml"
    return None
