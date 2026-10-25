# steuy als Container: App mit Gunicorn, PDF (WeasyPrint) und Texterkennung (Tesseract).
# Start mit docker compose, siehe docs/betrieb.md.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    FLASK_APP=app \
    ABLAGE_VERZEICHNIS=/daten/ablage

# Systembibliotheken für PDF/A (ADR 0008), Schrift und deutsche Texterkennung
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core fonts-liberation2 \
        tesseract-ocr tesseract-ocr-deu \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /bin/uv

WORKDIR /app
# Erst nur die Abhängigkeiten, damit dieser Schritt im Cache bleibt
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY app ./app
COPY migrations ./migrations
COPY scripts/docker-start.sh ./scripts/docker-start.sh

RUN useradd --create-home --uid 1000 steuy \
    && mkdir -p /daten/ablage /daten/scan-eingang /daten/freigabe \
    && chown -R steuy:steuy /daten
USER steuy

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/gesund', timeout=4).status != 200)"

CMD ["scripts/docker-start.sh"]
