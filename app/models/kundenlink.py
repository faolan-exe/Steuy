from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class Kundenlink(db.Model):
    """Persönlicher Link, über den ein Kunde einen Beleg ansieht, herunterlädt und Angebote
    annimmt. Gespeichert ist nur der SHA-256 des Schlüssels (für die Suche) und der Schlüssel
    verschlüsselt (damit steuy den Link erneut anzeigen kann)."""

    __tablename__ = "kundenlink"

    id: Mapped[int] = mapped_column(primary_key=True)
    rechnung_id: Mapped[int] = mapped_column(
        ForeignKey("rechnung.id", ondelete="CASCADE"), index=True
    )
    schluessel_hash: Mapped[str] = mapped_column(String(64), unique=True)
    schluessel_geheim: Mapped[str] = mapped_column(Text)
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    gesperrt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    abrufe: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    zuletzt_abgerufen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # PLZ-Abfrage: Fehlversuche und Sperre gegen Durchprobieren
    fehlversuche: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    gesperrt_bis: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Entscheidung des Kunden zu einem Angebot
    entschieden_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entschieden_von: Mapped[str | None] = mapped_column(String(200))
    kommentar: Mapped[str | None] = mapped_column(Text)

    rechnung: Mapped["Rechnung"] = relationship()  # noqa: F821

    @property
    def aktiv(self) -> bool:
        return self.gesperrt_am is None
