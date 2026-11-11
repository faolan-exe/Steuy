"""Antwort auf Schalter, die sofort speichern (Profil, Nutzer, Update, Mahnwesen).

Im Browser speichert app.js per fetch im Hintergrund und zeigt die Meldung kurz an, ohne die
Seite neu zu laden. Ohne JavaScript gibt es wie früher Meldung und Weiterleitung.
"""

from flask import flash, jsonify, redirect, request


def schalter_antwort(meldung: str, ziel: str):
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True, meldung=meldung)
    flash(meldung)
    return redirect(ziel)
