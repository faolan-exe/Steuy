from flask import Flask

from app.config import Config
from app.extensions import csrf, db, login_manager, migrate


def create_app(config: type[Config] = Config) -> Flask:
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    app.config.from_object(config)
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY fehlt. Bitte in der .env setzen (Vorlage: .env.example).")

    # Hinter einem Reverse Proxy die echte Client-Adresse übernehmen (für die Anmeldesperre)
    if app.config.get("PROXY_ANZAHL"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=app.config["PROXY_ANZAHL"], x_proto=1)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app import models  # noqa: F401  Modelle für Alembic registrieren
    from app.web import (
        allgemein,
        anlagen,
        artikel,
        auswertung,
        auth,
        belege,
        einrichtung,
        einstellungen,
        importieren,
        kontakte,
        profil,
        rechnungen,
        rundgang,
        shop,
    )
    from app.web.filter import registriere_filter
    from app.web.zugang import registriere_zugang

    app.register_blueprint(allgemein.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(einrichtung.bp)
    app.register_blueprint(einstellungen.bp)
    app.register_blueprint(kontakte.bp)
    app.register_blueprint(artikel.bp)
    app.register_blueprint(rechnungen.bp)
    app.register_blueprint(rechnungen.angebote_bp)
    app.register_blueprint(belege.bp)
    app.register_blueprint(auswertung.bp)
    app.register_blueprint(profil.bp)
    app.register_blueprint(shop.bp)
    app.register_blueprint(importieren.bp)
    app.register_blueprint(anlagen.bp)
    app.register_blueprint(rundgang.bp)
    registriere_filter(app)

    from app.web.hilfe import registriere as registriere_hilfe

    registriere_hilfe(app)
    registriere_zugang(app)

    from app.web.fehler import registriere as registriere_fehlerseiten

    registriere_fehlerseiten(app)


    @app.cli.command("erinnerungen")
    def erinnerungen():
        """Wöchentliche Zusammenfassung verschicken (für Cron oder den Zeitplan-Dienst)."""
        from app.services.erinnerung import sende_wochenmails

        print(f"Wochenmails verschickt: {sende_wochenmails()}")

    @app.cli.command("mahnlauf")
    def mahnlauf():
        """Fällige Mahnungen erstellen und verschicken, wenn die Automatik eingeschaltet ist."""
        from sqlalchemy import select

        from app.models import Nutzer
        from app.services.mahnwesen import automatischer_mahnlauf

        admin = (
            db.session.execute(
                select(Nutzer).where(Nutzer.rolle == "admin", Nutzer.aktiv).order_by(Nutzer.id)
            )
            .scalars()
            .first()
        )
        if admin is None:
            print("Kein aktiver Admin.")
            return
        lauf = automatischer_mahnlauf(admin.id)
        print(f"Mahnungen erstellt: {lauf.erstellt}, verschickt: {lauf.verschickt}")
        for zeile in lauf.nicht_verschickt:
            print(f"Nicht verschickt: {zeile}")

    @app.cli.command("shop-abruf")
    def shop_abruf():
        """Bestellungen aus WooCommerce abrufen (für Cron oder den Zeitplan-Dienst)."""
        from sqlalchemy import select

        from app.models import Nutzer
        from app.services.shop import ShopFehler, eingerichtet, synchronisiere

        if not eingerichtet():
            print("Kein Shop verbunden.")
            return
        # Automatische Abrufe laufen im Namen des ersten aktiven Admins (für das Protokoll)
        admin = next(
            n
            for n in db.session.execute(
                select(Nutzer).where(Nutzer.rolle == "admin").order_by(Nutzer.id)
            ).scalars()
            if n.is_active
        )
        try:
            print(synchronisiere(admin.id).text())
        except ShopFehler as fehler:
            print(f"Shop-Abruf fehlgeschlagen: {fehler}")

    return app
