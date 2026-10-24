from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class Protokoll(db.Model):
    """Änderungsprotokoll. Append-only, ein DB-Trigger verbietet UPDATE und DELETE (ADR 0002)."""

    __tablename__ = "protokoll"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    nutzer_id: Mapped[int | None] = mapped_column(ForeignKey("nutzer.id", ondelete="RESTRICT"))
    aktion: Mapped[str] = mapped_column(String(60))
    objekt_typ: Mapped[str | None] = mapped_column(String(60))
    objekt_id: Mapped[str | None] = mapped_column(String(60))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
