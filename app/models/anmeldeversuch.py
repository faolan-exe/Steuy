from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class Anmeldeversuch(db.Model):
    """Für die Begrenzung von Anmeldeversuchen. E-Mail und IP nur als Hash (keine Klartextdaten).

    Kein Teil der Buchhaltung: alte Einträge werden nach einem Tag gelöscht.
    """

    __tablename__ = "anmeldeversuch"
    __table_args__ = (
        Index("anmeldeversuch_email", "email_hash", "zeitpunkt"),
        Index("anmeldeversuch_ip", "ip_hash", "zeitpunkt"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    email_hash: Mapped[str] = mapped_column(String(64))
    ip_hash: Mapped[str] = mapped_column(String(64))
    erfolgreich: Mapped[bool] = mapped_column(Boolean)
