from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.kleinunternehmer import Grenze
from app.extensions import db


class Kleinunternehmergrenze(db.Model):
    """Grenzen nach § 19 UStG je Gültigkeitsjahr. Neue Werte kommen per Migration."""

    __tablename__ = "kleinunternehmergrenze"

    gueltig_ab_jahr: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    vorjahr_cent: Mapped[int] = mapped_column(BigInteger)
    laufendes_jahr_cent: Mapped[int] = mapped_column(BigInteger)

    def als_grenze(self) -> Grenze:
        return Grenze(self.gueltig_ab_jahr, self.vorjahr_cent, self.laufendes_jahr_cent)
