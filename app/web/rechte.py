from functools import wraps

from flask import abort
from flask_login import current_user

from app.domain.rollen import Recht
from app.services.rechte import darf


def braucht_recht(recht: Recht):
    """Route nur für Nutzer mit diesem Recht, sonst 403."""

    def dekorator(funktion):
        @wraps(funktion)
        def pruefen(*args, **kwargs):
            if not current_user.is_authenticated or not darf(current_user, recht):
                abort(403)
            return funktion(*args, **kwargs)

        return pruefen

    return dekorator
