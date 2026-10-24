from sqlalchemy import Boolean, CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class Drucklayout(db.Model):
    """Aussehen von Rechnungen, Angeboten, Lieferscheinen, Mahnungen. Eine Zeile je Installation."""

    __tablename__ = "drucklayout"
    __table_args__ = (
        CheckConstraint("id = 1", name="drucklayout_nur_eine_zeile"),
        CheckConstraint("layout BETWEEN 1 AND 5", name="drucklayout_layout"),
        CheckConstraint("logo_prozent BETWEEN 30 AND 250", name="drucklayout_logo_prozent"),
        CheckConstraint(
            "logo_position IN ('auto', 'links', 'mitte', 'rechts')",
            name="drucklayout_logo_position",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    layout: Mapped[int] = mapped_column(Integer, server_default="1", default=1)
    akzent: Mapped[str] = mapped_column(String(7), server_default="#2e7d4f", default="#2e7d4f")
    schrift: Mapped[str] = mapped_column(String(20), server_default="sans", default="sans")
    schrift_text: Mapped[int] = mapped_column(Integer, server_default="10", default=10)
    schrift_titel: Mapped[int] = mapped_column(Integer, server_default="15", default=15)
    logo_sha256: Mapped[str | None] = mapped_column(String(64))
    logo_mime: Mapped[str | None] = mapped_column(String(30))
    logo_prozent: Mapped[int] = mapped_column(Integer, server_default="100", default=100)
    logo_position: Mapped[str] = mapped_column(String(10), server_default="auto", default="auto")
    zeige_firmenname: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True)
    zeige_absenderzeile: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True)
    zeige_pos: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True)
    gesamt_grau: Mapped[bool] = mapped_column(Boolean, server_default="false", default=False)
    zeige_fusszeile: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True)
    zeige_bank: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True)
    zeige_steuer: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True)
