from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class Passkey(db.Model):
    """Ein Passkey (WebAuthn-Zugangsdaten) einer Person. Der private Schlüssel bleibt im Gerät."""

    __tablename__ = "passkey"

    id: Mapped[int] = mapped_column(primary_key=True)
    nutzer_id: Mapped[int] = mapped_column(ForeignKey("nutzer.id", ondelete="CASCADE"), index=True)
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(BigInteger, default=0)
    name: Mapped[str] = mapped_column(String(80))
    transports: Mapped[list[str] | None] = mapped_column(JSONB)
    geraetetyp: Mapped[str] = mapped_column(String(20), default="single_device")
    gesichert: Mapped[bool] = mapped_column(Boolean, default=False)
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    zuletzt_benutzt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    nutzer = relationship("Nutzer", back_populates="passkeys")

    def als_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name}
