from datetime import date, datetime

from flask_login import UserMixin
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
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.rollen import Rolle
from app.extensions import db

_ROLLEN_SQL = ", ".join(f"'{r.value}'" for r in Rolle)


class Nutzer(UserMixin, db.Model):
    __tablename__ = "nutzer"
    __table_args__ = (
        CheckConstraint(f"rolle IN ({_ROLLEN_SQL})", name="nutzer_rolle_gueltig"),
        CheckConstraint("zwei_faktor_art IN ('app', 'mail')", name="nutzer_zwei_faktor_art"),
        CheckConstraint(
            "erfahrung IN ('anfaenger', 'erfahren', 'experte')", name="nutzer_erfahrung"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    passwort_hash: Mapped[str] = mapped_column(String(255))
    rolle: Mapped[str] = mapped_column(String(20))
    aktiv: Mapped[bool] = mapped_column(Boolean, server_default=true(), default=True)
    # Letzter Tag mit Zugang, z. B. für einen befristeten Steuerberater-Zugang.
    zugang_bis: Mapped[date | None] = mapped_column(Date)
    # Zwei-Faktor-Anmeldung: Schlüssel verschlüsselt, letzter Zeitschritt gegen Wiederverwendung
    totp_geheimnis: Mapped[str | None] = mapped_column(Text)
    totp_aktiv: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    hilfe_anzeigen: Mapped[bool] = mapped_column(Boolean, server_default=true(), default=True)
    # Rundgang: Vorkenntnisse (Buchhaltung), schon mit steuy gearbeitet, aktueller Schritt
    erfahrung: Mapped[str | None] = mapped_column(String(12))
    kennt_steuy: Mapped[bool | None] = mapped_column(Boolean)
    rundgang_schritt: Mapped[int | None] = mapped_column(Integer)
    rundgang_fertig: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    wochenmail: Mapped[bool] = mapped_column(Boolean, server_default=true(), default=True)
    wochenmail_gesendet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    totp_letzter_schritt: Mapped[int | None] = mapped_column(BigInteger)
    # „app“ (Authenticator, TOTP) oder „mail“ (Code per E-Mail). Aktiv ist 2FA über totp_aktiv.
    zwei_faktor_art: Mapped[str] = mapped_column(String(5), server_default="app", default="app")
    mail_code_hash: Mapped[str | None] = mapped_column(String(255))
    mail_code_bis: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mail_code_gesendet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    @property
    def abgelaufen(self) -> bool:
        return self.zugang_bis is not None and self.zugang_bis < date.today()

    @property
    def is_active(self) -> bool:
        return self.aktiv and not self.abgelaufen

    @property
    def ist_admin(self) -> bool:
        return self.rolle == Rolle.ADMIN


class Wiederherstellungscode(db.Model):
    """Einmalcodes für den Notfall, nur als Hash gespeichert."""

    __tablename__ = "wiederherstellungscode"

    id: Mapped[int] = mapped_column(primary_key=True)
    nutzer_id: Mapped[int] = mapped_column(ForeignKey("nutzer.id", ondelete="CASCADE"))
    code_hash: Mapped[str] = mapped_column(String(255))
    benutzt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
