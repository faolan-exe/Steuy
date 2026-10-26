"""Wer darf welche Seite sehen: erst Einrichtung, dann nur noch angemeldet."""

from flask import Flask, flash, redirect, request, session, url_for
from flask_login import current_user

from app.domain.rollen import Recht
from app.extensions import db, login_manager
from app.models import Nutzer
from app.services.einrichtung import aktuelles_gewerbe
from app.services.rechte import darf

OFFEN = {"static", "allgemein.gesund"}
NUR_OHNE_EINRICHTUNG = {"einrichtung.einrichten"}
OHNE_ANMELDUNG = {
    "auth.anmelden",
    "auth.zweiter_faktor",
    "auth.code_neu_senden",
    "auth.passkey_optionen",
    "auth.passkey_anmelden",
}
# Erreichbar, solange eine verpflichtende 2FA noch nicht eingerichtet ist
WAEHREND_2FA_PFLICHT = {
    "profil.zwei_faktor",
    "profil.zwei_faktor_mail",
    "auth.abmelden",
    "static",
}


@login_manager.user_loader
def lade_nutzer(nutzer_id: str) -> Nutzer | None:
    # Deaktivierte oder abgelaufene Konten verlieren auch laufende Sitzungen.
    nutzer = db.session.get(Nutzer, int(nutzer_id))
    return nutzer if nutzer and nutzer.is_active else None


def registriere_zugang(app: Flask) -> None:
    login_manager.login_view = "auth.anmelden"

    @app.before_request
    def zugang_pruefen():
        endpunkt = request.endpoint
        if endpunkt in OFFEN or endpunkt is None:
            return None
        if aktuelles_gewerbe() is None:
            if endpunkt in NUR_OHNE_EINRICHTUNG:
                return None
            return redirect(url_for("einrichtung.einrichten"))
        if endpunkt in NUR_OHNE_EINRICHTUNG:
            return None  # die Route selbst antwortet mit 404
        if endpunkt in OHNE_ANMELDUNG:
            return None
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        gewerbe = aktuelles_gewerbe()
        if (
            gewerbe.zwei_faktor_pflicht
            and not current_user.totp_aktiv
            and not session.get("passkey_anmeldung")  # Passkey mit Nutzerprüfung zählt als 2FA
            and endpunkt not in WAEHREND_2FA_PFLICHT
        ):
            flash("Bitte richte zuerst die Zwei-Faktor-Anmeldung ein.")
            return redirect(url_for("profil.zwei_faktor"))
        return None

    @app.context_processor
    def fuer_templates():
        def darf_ich(recht: str) -> bool:
            return current_user.is_authenticated and darf(current_user, Recht(recht))

        daten = {"gewerbe": aktuelles_gewerbe(), "darf": darf_ich}
        angemeldet = bool(current_user) and current_user.is_authenticated
        if angemeldet and current_user.rundgang_schritt is not None:
            from app.domain.rundgang import absaetze
            from app.services.rundgang import aktueller_schritt

            ziel = aktueller_schritt(current_user)
            if ziel:
                schritt, nummer, anzahl = ziel
                daten["rundgang"] = {
                    "schritt": schritt,
                    "nummer": nummer,
                    "anzahl": anzahl,
                    "absaetze": absaetze(schritt, current_user.erfahrung),
                    "erster": nummer == 1,
                    "letzter": nummer == anzahl,
                }
        return daten
