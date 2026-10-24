#!/bin/sh
# Startpunkt im Container: Datenbank auf den neuesten Stand bringen, dann die App starten.
set -eu

flask db upgrade
exec gunicorn \
    --bind 0.0.0.0:8000 \
    --workers "${WEB_WORKER:-2}" \
    --timeout 120 \
    --access-logfile - \
    "app:create_app()"
