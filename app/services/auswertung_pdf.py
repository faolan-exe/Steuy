from datetime import date

from flask import current_app, render_template
from weasyprint import HTML

from app.domain.euer import Ergebnis
from app.services.einrichtung import aktuelles_gewerbe


def euer_pdf(ergebnis: Ergebnis) -> bytes:
    html = render_template(
        "pdf/euer.html", e=ergebnis, gewerbe=aktuelles_gewerbe(), heute=date.today()
    )
    return HTML(string=html, base_url=current_app.root_path).write_pdf()
