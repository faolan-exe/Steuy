from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class Rollenrecht(db.Model):
    """Ein vergebenes Recht einer Rolle. Admin hat immer alle Rechte und steht hier nicht drin."""

    __tablename__ = "rollenrecht"
    __table_args__ = (
        CheckConstraint(
            "rolle IN ('buchhalter', 'mitarbeiter', 'steuerberater')",
            name="rollenrecht_rolle_einstellbar",
        ),
    )

    rolle: Mapped[str] = mapped_column(String(20), primary_key=True)
    recht: Mapped[str] = mapped_column(String(40), primary_key=True)
