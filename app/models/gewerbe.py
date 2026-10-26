from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db

HINWEIS_STANDARD = "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet."


class Gewerbe(db.Model):
    """Firmendaten. Genau eine Zeile je Installation (ADR 0007)."""

    __tablename__ = "gewerbe"
    __table_args__ = (
        CheckConstraint("id = 1", name="gewerbe_nur_eine_zeile"),
        CheckConstraint("ziel_art IN ('auftraege', 'umsatz', 'gewinn')", name="gewerbe_ziel_art"),
        CheckConstraint(
            "(ziel_art IS NULL) = (ziel_wert IS NULL) AND (ziel_wert IS NULL OR ziel_wert > 0)",
            name="gewerbe_ziel_wert",
        ),
        CheckConstraint(
            "smtp_verschluesselung IN ('starttls', 'ssl', 'keine')", name="gewerbe_smtp_art"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(200))
    inhaber: Mapped[str] = mapped_column(String(200))
    strasse: Mapped[str] = mapped_column(String(200))
    plz: Mapped[str] = mapped_column(String(10))
    ort: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254))
    telefon: Mapped[str | None] = mapped_column(String(50))
    steuernummer: Mapped[str | None] = mapped_column(String(30))
    ust_idnr: Mapped[str | None] = mapped_column(String(20))
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Bankverbindung für Rechnungen und QR-Code
    kontoinhaber: Mapped[str | None] = mapped_column(String(70))
    iban: Mapped[str | None] = mapped_column(String(34))
    bic: Mapped[str | None] = mapped_column(String(11))
    bank: Mapped[str | None] = mapped_column(String(100))

    # Vorgaben für neue Rechnungen
    zahlungsziel_tage: Mapped[int] = mapped_column(Integer, server_default="14", default=14)
    angebot_gueltig_tage: Mapped[int] = mapped_column(Integer, server_default="30", default=30)
    # Dashboard-Ziel für das gewählte Jahr: Anzahl (auftraege) oder Cent (umsatz, gewinn)
    # Mahnungen automatisch erstellen und per E-Mail schicken (Standard: aus)
    auto_mahnen: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    update_uebersprungen: Mapped[str | None] = mapped_column(String(20))
    ziel_art: Mapped[str | None] = mapped_column(String(20))
    ziel_wert: Mapped[int | None] = mapped_column(BigInteger)
    zwei_faktor_pflicht: Mapped[bool] = mapped_column(
        Boolean, server_default=false(), default=False
    )
    hinweis_steuerbefreiung: Mapped[str] = mapped_column(
        Text,
        server_default=HINWEIS_STANDARD,
        default=HINWEIS_STANDARD,
    )
    rechnung_einleitung: Mapped[str | None] = mapped_column(Text)
    rechnung_nachbemerkung: Mapped[str | None] = mapped_column(Text)
    # E-Mail-Versand (SMTP). Passwort verschlüsselt (app/services/geheimnis.py).
    smtp_server: Mapped[str | None] = mapped_column(String(200))
    smtp_port: Mapped[int] = mapped_column(Integer, server_default="587", default=587)
    smtp_verschluesselung: Mapped[str] = mapped_column(
        String(10), server_default="starttls", default="starttls"
    )
    smtp_benutzer: Mapped[str | None] = mapped_column(String(200))
    smtp_passwort: Mapped[str | None] = mapped_column(Text)
    mail_absender: Mapped[str | None] = mapped_column(String(254))
    # E-Rechnung: Rechnungen als ZUGFeRD-PDF (mit eingebettetem XML) festschreiben
    e_rechnung: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    # Scan-Eingang: Belege aus einem Ordner übernehmen, in den der Scanner speichert
    scan_aktiv: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    scan_letzter_lauf: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Netzwerkfreigabe (Samba-Container) für den Scanner, Passwort verschlüsselt
    scan_freigabe: Mapped[bool] = mapped_column(Boolean, server_default=true(), default=True)
    scan_kompatibel: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    scan_passwort: Mapped[str | None] = mapped_column(Text)
    # WooCommerce (docs/domain/woocommerce.md). Schlüssel verschlüsselt.
    shop_url: Mapped[str | None] = mapped_column(String(300))
    shop_schluessel: Mapped[str | None] = mapped_column(Text)
    shop_geheimnis: Mapped[str | None] = mapped_column(Text)
    shop_auto_versand: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    shop_letzter_abruf: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    FELDER = (
        "name",
        "inhaber",
        "strasse",
        "plz",
        "ort",
        "email",
        "telefon",
        "steuernummer",
        "ust_idnr",
    )
