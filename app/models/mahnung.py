from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    false,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.mahnung import Stufe
from app.extensions import db


class Mahnstufe(db.Model):
    __tablename__ = "mahnstufe"
    __table_args__ = (
        CheckConstraint("nummer BETWEEN 1 AND 3", name="mahnstufe_nummer"),
        CheckConstraint("tage_nach >= 0 AND frist_tage >= 0", name="mahnstufe_tage"),
    )

    nummer: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    bezeichnung: Mapped[str] = mapped_column(String(60))
    tage_nach: Mapped[int] = mapped_column(Integer)
    frist_tage: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)

    def als_stufe(self) -> Stufe:
        return Stufe(self.nummer, self.bezeichnung, self.tage_nach, self.frist_tage)


class Mahnung(db.Model):
    """Erstellte Zahlungserinnerung oder Mahnung. Inhalt unveränderlich (Trigger).

    Eine nie verschickte Mahnung darf gelöscht werden, eine verschickte nur zurückgezogen:
    Sie bleibt mit PDF und Versand erhalten, zählt aber nicht mehr für die Mahnstufen."""

    __tablename__ = "mahnung"
    __table_args__ = (
        Index(
            "mahnung_stufe_einmal",
            "rechnung_id",
            "stufe",
            unique=True,
            postgresql_where=text("zurueckgezogen_am IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rechnung_id: Mapped[int] = mapped_column(ForeignKey("rechnung.id", ondelete="RESTRICT"))
    stufe: Mapped[int] = mapped_column(Integer)
    bezeichnung: Mapped[str] = mapped_column(String(60))
    datum: Mapped[date] = mapped_column(Date)
    offen_cent: Mapped[int] = mapped_column(BigInteger)
    frist_bis: Mapped[date] = mapped_column(Date)
    # Verzugspauschale auf dem Schreiben, kommt zum offenen Rechnungsbetrag dazu
    pauschale_cent: Mapped[int] = mapped_column(BigInteger, server_default="0", default=0)
    pdf_sha256: Mapped[str] = mapped_column(String(64))
    automatisch: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    zurueckgezogen_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    zurueckgezogen_von: Mapped[int | None] = mapped_column(ForeignKey("nutzer.id"))
    zurueckgezogen_grund: Mapped[str | None] = mapped_column(String(200))
    erstellt_von: Mapped[int] = mapped_column(ForeignKey("nutzer.id"))
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    rechnung = relationship("Rechnung", back_populates="mahnungen")

    @property
    def aktiv(self) -> bool:
        return self.zurueckgezogen_am is None

    @property
    def gesamt_cent(self) -> int:
        return self.offen_cent + self.pauschale_cent


class Mahnvorlage(db.Model):
    """Selbst gespeicherter Brieftext für Mahnungen, mit Platzhaltern."""

    __tablename__ = "mahnvorlage"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    text: Mapped[str] = mapped_column(Text)
