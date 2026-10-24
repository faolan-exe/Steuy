from sqlalchemy import delete, select

from app.domain.rollen import EINSTELLBAR, EINSTELLBARE_ROLLEN, Recht, Rolle, hat_recht
from app.extensions import db
from app.models import Nutzer, Rollenrecht
from app.services.protokoll import protokolliere


class UngueltigesRecht(ValueError):
    pass


def rechte_matrix() -> dict[Rolle, set[Recht]]:
    matrix: dict[Rolle, set[Recht]] = {rolle: set() for rolle in EINSTELLBARE_ROLLEN}
    for zeile in db.session.execute(select(Rollenrecht)).scalars():
        matrix[Rolle(zeile.rolle)].add(Recht(zeile.recht))
    return matrix


def darf(nutzer: Nutzer, recht: Recht) -> bool:
    if not nutzer.is_active:
        return False
    rolle = Rolle(nutzer.rolle)
    if rolle == Rolle.ADMIN:
        return True
    vergeben = set(
        db.session.execute(
            select(Rollenrecht.recht).where(Rollenrecht.rolle == rolle.value)
        ).scalars()
    )
    return hat_recht(rolle, recht, {Recht(r) for r in vergeben})


def setze_rechte(neu: dict[Rolle, set[Recht]], admin_id: int) -> dict:
    """Ersetzt die Rechte der einstellbaren Rollen und protokolliert die Unterschiede."""
    for rolle, rechte in neu.items():
        if rolle not in EINSTELLBARE_ROLLEN:
            raise UngueltigesRecht(f"Die Rechte der Rolle {rolle} sind nicht einstellbar.")
        unerlaubt = set(rechte) - set(EINSTELLBAR)
        if unerlaubt:
            raise UngueltigesRecht(f"Nicht vergebbar: {', '.join(sorted(unerlaubt))}")

    alt = rechte_matrix()
    aenderungen = {}
    for rolle in EINSTELLBARE_ROLLEN:
        rechte = set(neu.get(rolle, alt[rolle]))
        hinzu, weg = rechte - alt[rolle], alt[rolle] - rechte
        if hinzu or weg:
            aenderungen[rolle.value] = {
                "hinzugefuegt": sorted(r.value for r in hinzu),
                "entfernt": sorted(r.value for r in weg),
            }
        db.session.execute(delete(Rollenrecht).where(Rollenrecht.rolle == rolle.value))
        db.session.add_all(Rollenrecht(rolle=rolle.value, recht=r.value) for r in rechte)

    if aenderungen:
        protokolliere("rechte_geaendert", nutzer_id=admin_id, details=aenderungen)
    db.session.commit()
    return aenderungen
