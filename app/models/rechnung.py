from datetime import date, datetime
from typing import Any

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
    false,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

STATUS = ("entwurf", "offen", "teilbezahlt", "bezahlt", "storniert", "angenommen", "abgelehnt")
BELEGARTEN = {
    "rechnung": "Rechnung",
    "angebot": "Angebot",
    "korrektur": "Rechnungskorrektur",
    "lieferschein": "Lieferschein",
}
NUMMERNKREIS = {
    "rechnung": "rechnung",
    "angebot": "angebot",
    "korrektur": "korrektur",
    "lieferschein": "lieferschein",
}
LEISTUNG_ARTEN = {
    "lieferdatum": "Lieferdatum",
    "leistungsdatum": "Leistungsdatum",
    "leistungszeitraum": "Leistungszeitraum",
}


class Nummernkreis(db.Model):
    __tablename__ = "nummernkreis"

    belegart: Mapped[str] = mapped_column(String(30), primary_key=True)
    praefix: Mapped[str] = mapped_column(String(20))
    stellen: Mapped[int] = mapped_column(Integer)
    naechste_nummer: Mapped[int] = mapped_column(Integer)


class Rechnung(db.Model):
    """Ausgangsrechnung. Nach dem Finalisieren unveränderlich (DB-Trigger, ADR 0002)."""

    __tablename__ = "rechnung"
    __table_args__ = (
        CheckConstraint(
            "status IN ('entwurf', 'offen', 'teilbezahlt', 'bezahlt', 'storniert', "
            "'angenommen', 'abgelehnt')",
            name="rechnung_status",
        ),
        CheckConstraint(
            "belegart IN ('rechnung', 'angebot', 'korrektur', 'lieferschein')",
            name="rechnung_belegart",
        ),
        CheckConstraint(
            "belegart <> 'lieferschein' OR bezug_id IS NOT NULL", name="rechnung_lieferschein_bezug"
        ),
        CheckConstraint(
            "belegart <> 'korrektur' OR bezug_id IS NOT NULL", name="rechnung_korrektur_bezug"
        ),
        CheckConstraint(
            "leistung_art IN ('lieferdatum', 'leistungsdatum', 'leistungszeitraum')",
            name="rechnung_leistung_art",
        ),
        CheckConstraint(
            "(status = 'entwurf') = (finalisiert_am IS NULL)", name="rechnung_entwurf_ohne_final"
        ),
        CheckConstraint(
            "finalisiert_am IS NULL OR (nummer IS NOT NULL AND pdf_sha256 IS NOT NULL)",
            name="rechnung_final_vollstaendig",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    belegart: Mapped[str] = mapped_column(String(20), server_default="rechnung", default="rechnung")
    nummer: Mapped[str | None] = mapped_column(String(30), unique=True)
    # Angebot → daraus erstellte Rechnung, Rechnungskorrektur → stornierte Rechnung,
    # Lieferschein → Rechnung, zu der er gehört
    bezug_id: Mapped[int | None] = mapped_column(ForeignKey("rechnung.id", ondelete="RESTRICT"))
    # Aus welcher wiederkehrenden Rechnung diese Rechnung entstanden ist
    wiederkehrend_id: Mapped[int | None] = mapped_column(
        ForeignKey("wiederkehrende_rechnung.id", ondelete="RESTRICT")
    )
    gueltig_bis: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), server_default="entwurf", default="entwurf")
    kontakt_id: Mapped[int | None] = mapped_column(ForeignKey("kontakt.id", ondelete="RESTRICT"))

    empfaenger_name: Mapped[str | None] = mapped_column(String(200))
    empfaenger_zusatz: Mapped[str | None] = mapped_column(String(200))
    empfaenger_strasse: Mapped[str | None] = mapped_column(String(200))
    empfaenger_plz: Mapped[str | None] = mapped_column(String(10))
    empfaenger_ort: Mapped[str | None] = mapped_column(String(100))
    empfaenger_land: Mapped[str | None] = mapped_column(String(100))

    rechnungsdatum: Mapped[date] = mapped_column(Date)
    leistung_art: Mapped[str] = mapped_column(String(20), default="leistungsdatum")
    leistung_von: Mapped[date | None] = mapped_column(Date)
    leistung_bis: Mapped[date | None] = mapped_column(Date)

    titel: Mapped[str] = mapped_column(String(100), default="Rechnung")
    einleitung: Mapped[str | None] = mapped_column(Text)
    nachbemerkung: Mapped[str | None] = mapped_column(Text)
    hinweis_steuerbefreiung: Mapped[str | None] = mapped_column(Text)
    zahlungsziel_tage: Mapped[int] = mapped_column(Integer, default=14)
    faellig_am: Mapped[date | None] = mapped_column(Date)
    qr_ueberweisung: Mapped[bool] = mapped_column(Boolean, server_default=true(), default=True)
    summe_cent: Mapped[int] = mapped_column(BigInteger, default=0)

    absender: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    pdf_sha256: Mapped[str | None] = mapped_column(String(64))
    # Die E-Rechnung (CII-XML) dazu, falls erzeugt. Liegt auch im PDF eingebettet.
    xml_sha256: Mapped[str | None] = mapped_column(String(64))
    # Darf sich nach dem Finalisieren noch ändern (siehe Trigger), wie der Status.
    mahnsperre: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    mahnsperre_grund: Mapped[str | None] = mapped_column(String(200))
    finalisiert_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalisiert_von: Mapped[int | None] = mapped_column(ForeignKey("nutzer.id"))
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    positionen: Mapped[list["Rechnungsposition"]] = relationship(
        back_populates="rechnung",
        order_by="Rechnungsposition.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    kontakt = relationship("Kontakt")
    bezug: Mapped["Rechnung | None"] = relationship(remote_side=[id])
    zahlungen: Mapped[list["Zahlung"]] = relationship(  # noqa: F821
        back_populates="rechnung", order_by="Zahlung.id"
    )

    versand: Mapped[list["Versand"]] = relationship(  # noqa: F821
        order_by="Versand.gesendet_am.desc()", viewonly=True
    )
    mahnungen: Mapped[list["Mahnung"]] = relationship(  # noqa: F821
        back_populates="rechnung", order_by="Mahnung.stufe"
    )

    @property
    def gesperrt_fuer_mahnungen(self) -> bool:
        return self.mahnsperre or bool(self.kontakt and self.kontakt.mahnsperre)

    @property
    def bezahlt_cent(self) -> int:
        return sum(z.betrag_cent for z in self.zahlungen)

    @property
    def offen_cent(self) -> int:
        if not self.ist_rechnung or self.ist_entwurf or self.status == "storniert":
            return 0
        return self.summe_cent - self.bezahlt_cent

    @property
    def ist_entwurf(self) -> bool:
        return self.status == "entwurf"

    @property
    def anzeige_nummer(self) -> str:
        return self.nummer or "Entwurf"

    @property
    def belegname(self) -> str:
        return BELEGARTEN[self.belegart]

    @property
    def ist_rechnung(self) -> bool:
        return self.belegart == "rechnung"


class Rechnungsposition(db.Model):
    __tablename__ = "rechnungsposition"
    __table_args__ = (
        CheckConstraint("typ IN ('artikel', 'text')", name="position_typ"),
        CheckConstraint("rabatt_bp BETWEEN 0 AND 10000", name="position_rabatt"),
        CheckConstraint("typ = 'text' OR menge_tausendstel > 0", name="position_menge"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rechnung_id: Mapped[int] = mapped_column(ForeignKey("rechnung.id", ondelete="CASCADE"))
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

    rechnung: Mapped[Rechnung] = relationship(back_populates="positionen")
