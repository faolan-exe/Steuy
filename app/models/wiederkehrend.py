from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.wiederkehrend import INTERVALLE, VERSAND_ARTEN
from app.extensions import db

_INTERVALLE_SQL = ", ".join(f"'{i}'" for i in INTERVALLE)
_VERSAND_SQL = ", ".join(f"'{v}'" for v in VERSAND_ARTEN)


class WiederkehrendeRechnung(db.Model):
    """Vorlage für Rechnungen, die in festen Abständen entstehen (Abo, Wartung, Miete)."""

    __tablename__ = "wiederkehrende_rechnung"
    __table_args__ = (
        CheckConstraint(f"intervall IN ({_INTERVALLE_SQL})", name="wiederkehrend_intervall"),
        CheckConstraint(f"versand IN ({_VERSAND_SQL})", name="wiederkehrend_versand"),
        CheckConstraint("anker_tag BETWEEN 1 AND 31", name="wiederkehrend_anker"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kontakt_id: Mapped[int | None] = mapped_column(ForeignKey("kontakt.id", ondelete="RESTRICT"))

    empfaenger_name: Mapped[str | None] = mapped_column(String(200))
    empfaenger_zusatz: Mapped[str | None] = mapped_column(String(200))
    empfaenger_strasse: Mapped[str | None] = mapped_column(String(200))
    empfaenger_plz: Mapped[str | None] = mapped_column(String(10))
    empfaenger_ort: Mapped[str | None] = mapped_column(String(100))
    empfaenger_land: Mapped[str | None] = mapped_column(String(100))

    titel: Mapped[str] = mapped_column(String(100), default="Rechnung")
    einleitung: Mapped[str | None] = mapped_column(Text)
    nachbemerkung: Mapped[str | None] = mapped_column(Text)
    hinweis_steuerbefreiung: Mapped[str | None] = mapped_column(Text)
    zahlungsziel_tage: Mapped[int] = mapped_column(Integer, default=14)
    qr_ueberweisung: Mapped[bool] = mapped_column(Boolean, server_default=true(), default=True)
    summe_cent: Mapped[int] = mapped_column(BigInteger, default=0)

    intervall: Mapped[str] = mapped_column(String(20), default="monatlich")
    anker_tag: Mapped[int] = mapped_column(Integer, default=1)
    naechste_am: Mapped[date] = mapped_column(Date)
    ende_am: Mapped[date | None] = mapped_column(Date)
    aktiv: Mapped[bool] = mapped_column(Boolean, server_default=true(), default=True)
    versand: Mapped[str] = mapped_column(String(20), server_default="entwurf", default="entwurf")

    erzeugt_anzahl: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    letzter_lauf_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    letzte_meldung: Mapped[str | None] = mapped_column(Text)
    erstellt_von: Mapped[int] = mapped_column(ForeignKey("nutzer.id"))
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    positionen: Mapped[list["WiederkehrendePosition"]] = relationship(
        back_populates="vorlage",
        order_by="WiederkehrendePosition.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    kontakt = relationship("Kontakt")

    # Der Rechnungseditor liest diese Felder wie bei einer Rechnung
    belegart = "vorlage"
    belegname = "Wiederkehrende Rechnung"
    nummer = None
    rechnungsdatum = None
    leistung_art = "leistungszeitraum"
    leistung_von = None
    leistung_bis = None
    ist_rechnung = True

    @property
    def beendet(self) -> bool:
        return self.ende_am is not None and self.naechste_am > self.ende_am


class WiederkehrendePosition(db.Model):
    __tablename__ = "wiederkehrende_position"
    __table_args__ = (
        CheckConstraint("typ IN ('artikel', 'text')", name="wiederkehrend_position_typ"),
        CheckConstraint("rabatt_bp BETWEEN 0 AND 10000", name="wiederkehrend_position_rabatt"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vorlage_id: Mapped[int] = mapped_column(
        ForeignKey("wiederkehrende_rechnung.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    typ: Mapped[str] = mapped_column(String(10), default="artikel")
    artikel_id: Mapped[int | None] = mapped_column(ForeignKey("artikel.id", ondelete="SET NULL"))
    bezeichnung: Mapped[str] = mapped_column(String(200), default="")
    beschreibung: Mapped[str | None] = mapped_column(Text)
    menge_tausendstel: Mapped[int] = mapped_column(BigInteger, default=1000)
    einheit: Mapped[str | None] = mapped_column(String(30))
    einzelpreis_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    rabatt_bp: Mapped[int] = mapped_column(Integer, default=0)
    betrag_cent: Mapped[int] = mapped_column(BigInteger, default=0)

    vorlage: Mapped[WiederkehrendeRechnung] = relationship(back_populates="positionen")
