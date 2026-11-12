"""Von außen nur über HTTPS, im eigenen Netz auch ohne.

Wie bei Nextcloud: Wer aus dem Internet kommt, bekommt steuy nur verschlüsselt. Eine Anfrage
über http:// von einer öffentlichen Adresse wird nicht beantwortet. Ist eine öffentliche
https-Adresse eingetragen (BASIS_URL), leitet steuy Seitenaufrufe dorthin um, alles andere
(z. B. abgeschickte Formulare) wird mit 403 abgelehnt. So geht nie ein Passwort, ein
Kundenlink oder eine Rechnung unverschlüsselt durchs Internet.

„Eigenes Netz“ sind die privaten Adressbereiche (Heimnetz, Docker, localhost), dazu der Bereich
100.64.0.0/10, den Tailscale und andere VPNs nutzen. Weitere Netze, z. B. ein eigenes VPN mit
öffentlichen Adressen, nennt INTERNE_NETZE. Abschalten (nicht empfohlen): NUR_HTTPS_VON_AUSSEN=0.

Damit die Adresse des Besuchers stimmt, muss PROXY_ANZAHL zum Aufbau passen (docs/betrieb.md):
Hinter einem Reverse Proxy sieht steuy sonst nur dessen interne Adresse.
"""

import ipaddress
from functools import lru_cache

from flask import Flask, current_app, redirect, request

# Private und lokale Bereiche (RFC 1918, Loopback, Link-Local, IPv6 ULA) und CGNAT (VPNs)
STANDARD_NETZE = (
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "100.64.0.0/10",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
)


@lru_cache(maxsize=8)
def _netze(zusatz: str) -> tuple:
    netze = [ipaddress.ip_network(n) for n in STANDARD_NETZE]
    for teil in zusatz.replace(";", ",").split(","):
        if teil.strip():
            netze.append(ipaddress.ip_network(teil.strip(), strict=False))
    return tuple(netze)


def ist_intern(adresse: str | None, zusatz: str = "") -> bool:
    """True für Adressen aus dem eigenen Netz. Unlesbare Adressen gelten als extern."""
    try:
        ip = ipaddress.ip_address((adresse or "").split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return any(ip.version == netz.version and ip in netz for netz in _netze(zusatz))


def pruefe_zugang():
    if request.is_secure or not current_app.config.get("NUR_HTTPS_VON_AUSSEN", True):
        return None
    if ist_intern(request.remote_addr, current_app.config.get("INTERNE_NETZE", "")):
        return None
    basis = current_app.config.get("BASIS_URL", "")
    if request.method in ("GET", "HEAD") and basis.startswith("https://"):
        # Gleicher Pfad unter der https-Adresse. Die Abfrage bleibt dran (z. B. ?seite=2).
        ziel = basis + request.path
        if request.query_string:
            ziel += "?" + request.query_string.decode("latin-1")
        return redirect(ziel, code=308)
    # Eigene schlichte Seite statt der normalen Vorlage: Sie zeigt weder Menü noch Namen,
    # denn über eine unverschlüsselte Verbindung soll gar nichts aus steuy hinausgehen.
    return SEITE, 403, {"Cache-Control": "no-store"}


def registriere(app: Flask) -> None:
    # Als erste Prüfung, noch vor Anmeldung und Demo-Konto
    app.before_request_funcs.setdefault(None, []).insert(0, pruefe_zugang)


SEITE = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Nur über HTTPS – steuy</title>
<style>body{font:16px/1.55 system-ui,sans-serif;max-width:36rem;margin:14vh auto;padding:0 1rem;
color:#1d2529;background:#f2f5f6}h1{font-size:1.5rem}code{background:#e3e8ea;padding:.1rem .3rem;
border-radius:3px}@media (prefers-color-scheme:dark){body{color:#e2e9eb;background:#0e1417}
code{background:#23323a}}</style></head><body>
<h1>steuy ist von außen nur verschlüsselt erreichbar</h1>
<p>Du rufst steuy aus dem Internet über eine unverschlüsselte Verbindung (<code>http://</code>) auf.
Damit Passwörter, Rechnungen und Kundendaten nicht mitgelesen werden können, antwortet steuy
darauf nicht.</p>
<p><strong>Im eigenen Netz</strong> (zu Hause, im Büro, per VPN) geht es weiter wie gewohnt.
<strong>Von unterwegs</strong> braucht steuy eine Adresse mit <code>https://</code>. Wie das
eingerichtet wird, steht in der Anleitung unter „Von unterwegs erreichen“.</p>
</body></html>"""
