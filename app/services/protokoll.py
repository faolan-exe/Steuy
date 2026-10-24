from typing import Any

from app.extensions import db
from app.models import Protokoll


def protokolliere(
    aktion: str,
    *,
    nutzer_id: int | None = None,
    objekt_typ: str | None = None,
    objekt_id: str | int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Fügt einen Protokolleintrag zur laufenden Transaktion hinzu. Committet nicht."""
    db.session.add(
        Protokoll(
            aktion=aktion,
            nutzer_id=nutzer_id,
            objekt_typ=objekt_typ,
            objekt_id=None if objekt_id is None else str(objekt_id),
            details=details,
        )
    )
