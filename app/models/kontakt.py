from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.stammdaten import anzeigename
from app.extensions import db


class Kontakt(db.Model):
    """Kunde und/oder Lieferant."""

    __tablename__ = "kontakt"
    __table_args__ = (
        CheckConstraint("art IN ('firma', 'person')", name="kontakt_art_gueltig"),
        CheckConstraint("ist_kunde OR ist_lieferant", name="kontakt_kunde_oder_lieferant"),
        CheckConstraint(
            "NOT ist_kunde OR kundennummer IS NOT NULL", name="kontakt_kunde_hat_nummer"
        ),
        CheckConstraint(
            "NOT ist_lieferant OR lieferantennummer IS NOT NULL",
            name="kontakt_lieferant_hat_nummer",
        ),
        CheckConstraint(
            "(art = 'firma' AND firmenname IS NOT NULL) "
            "OR (art = 'person' AND nachname IS NOT NULL)",
            name="kontakt_hat_namen",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    art: Mapped[str] = mapped_column(String(10))
    firmenname: Mapped[str | None] = mapped_column(String(200))
    anrede: Mapped[str | None] = mapped_column(String(30))
    vorname: Mapped[str | None] = mapped_column(String(100))
    nachname: Mapped[str | None] = mapped_column(String(100))
    ist_kunde: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    ist_lieferant: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    kundennummer: Mapped[int | None] = mapped_column(Integer, unique=True)
    lieferantennummer: Mapped[int | None] = mapped_column(Integer, unique=True)
    adresszusatz: Mapped[str | None] = mapped_column(String(200))
    strasse: Mapped[str | None] = mapped_column(String(200))
    plz: Mapped[str | None] = mapped_column(String(10))
    ort: Mapped[str | None] = mapped_column(String(100))
    land: Mapped[str] = mapped_column(String(100), server_default="Deutschland")
    email: Mapped[str | None] = mapped_column(String(254))
    telefon: Mapped[str | None] = mapped_column(String(50))
    steuernummer: Mapped[str | None] = mapped_column(String(30))
    # Leitweg-ID oder Käuferreferenz: Mit ihr wird die E-Rechnung zur XRechnung (Behörden)
    leitweg_id: Mapped[str | None] = mapped_column(String(46))
    ust_idnr: Mapped[str | None] = mapped_column(String(20))
    notiz: Mapped[str | None] = mapped_column(Text)
    archiviert: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    mahnsperre: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    FELDER = (
        "art",
        "firmenname",
        "anrede",
        "vorname",
        "nachname",
        "adresszusatz",
        "strasse",
        "plz",
        "ort",
        "land",
        "email",
        "telefon",
        "steuernummer",
        "ust_idnr",
        "leitweg_id",
        "notiz",
    )

    @property
    def name(self) -> str:
        return anzeigename(self.art, self.firmenname, self.vorname, self.nachname)

    @property
    def nummer(self) -> int | None:
        return self.kundennummer or self.lieferantennummer
