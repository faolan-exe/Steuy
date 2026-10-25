# Samba-Freigabe für den Scan-Eingang (docs/scanner.md). Läuft nur, wenn sie in steuy
# unter Einstellungen → Scanner eingeschaltet ist.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends samba \
    && rm -rf /var/lib/apt/lists/* \
    # gleiche Benutzernummer wie in der App, damit beide Seiten alle Dateien lesen und verschieben
    && useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin steuy \
    && useradd --no-create-home --shell /usr/sbin/nologin scanner \
    && mkdir -p /scan /freigabe \
    && chown 1000:1000 /scan

COPY smb.conf /etc/samba/smb.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 445
CMD ["/entrypoint.sh"]
