from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect, FlaskForm
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_message = "Bitte melde dich an, um diese Seite zu sehen."
csrf = CSRFProtect()

# Standardmeldungen von WTForms auf Deutsch („Keine gültige, ganze Zahl.“ statt „Not a valid
# integer value.“). Gilt für alle Formulare; dazu WTF_I18N_ENABLED = False in der Konfiguration.
FlaskForm.Meta.locales = ["de_DE", "de"]
