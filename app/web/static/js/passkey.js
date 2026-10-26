// Passkeys: Registrierung (Profil) und Anmeldung. Der Browser fragt nach Fingerabdruck, Gesicht
// oder PIN, steuy bekommt nur den öffentlichen Schlüssel und eine Signatur.
(function () {
  "use strict";

  function zuPuffer(b64u) {
    const b64 = b64u.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(b64u.length / 4) * 4, "=");
    const bin = atob(b64);
    const puffer = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) puffer[i] = bin.charCodeAt(i);
    return puffer.buffer;
  }

  function zuB64u(puffer) {
    const bytes = new Uint8Array(puffer);
    let bin = "";
    for (const b of bytes) bin += String.fromCharCode(b);
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function csrf() {
    const feld = document.querySelector('input[name="csrf_token"]');
    return feld ? feld.value : "";
  }

  async function senden(adresse, daten) {
    const antwort = await fetch(adresse, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(daten || {}),
    });
    let inhalt = {};
    try { inhalt = await antwort.json(); } catch (e) { /* keine JSON-Antwort */ }
    if (!antwort.ok) throw new Error(inhalt.fehler || "Das hat nicht geklappt.");
    return inhalt;
  }

  function meldung(ort, text, fehler) {
    if (!ort) return;
    ort.textContent = text;
    ort.hidden = !text;
    ort.className = fehler ? "fehlermeldung" : "hinweis";
  }

  function fehlertext(fehler) {
    if (fehler && fehler.name === "NotAllowedError") return "Abgebrochen oder nicht erlaubt.";
    if (fehler && fehler.name === "InvalidStateError") return "Dieser Passkey ist schon eingerichtet.";
    return (fehler && fehler.message) || "Das hat nicht geklappt.";
  }

  async function registrieren(knopf) {
    const ausgabe = document.getElementById("passkey-meldung");
    const name = (document.getElementById("passkey-name") || {}).value || "";
    try {
      meldung(ausgabe, "", false);
      const optionen = await senden(knopf.dataset.optionen);
      const pk = optionen;
      pk.challenge = zuPuffer(pk.challenge);
      pk.user.id = zuPuffer(pk.user.id);
      (pk.excludeCredentials || []).forEach((c) => (c.id = zuPuffer(c.id)));
      const cred = await navigator.credentials.create({ publicKey: pk });
      const antwort = cred.response;
      await senden(knopf.dataset.ziel, {
        name: name,
        credential: {
          id: cred.id,
          rawId: zuB64u(cred.rawId),
          type: cred.type,
          response: {
            clientDataJSON: zuB64u(antwort.clientDataJSON),
            attestationObject: zuB64u(antwort.attestationObject),
            transports: antwort.getTransports ? antwort.getTransports() : [],
          },
          clientExtensionResults: cred.getClientExtensionResults(),
          authenticatorAttachment: cred.authenticatorAttachment || undefined,
        },
      });
      window.location.reload();
    } catch (e) {
      meldung(ausgabe, fehlertext(e), true);
    }
  }

  async function anmelden(knopf) {
    const ausgabe = document.getElementById("passkey-meldung");
    try {
      meldung(ausgabe, "", false);
      const pk = await senden(knopf.dataset.optionen);
      pk.challenge = zuPuffer(pk.challenge);
      (pk.allowCredentials || []).forEach((c) => (c.id = zuPuffer(c.id)));
      const cred = await navigator.credentials.get({ publicKey: pk });
      const antwort = cred.response;
      const ergebnis = await senden(knopf.dataset.ziel, {
        credential: {
          id: cred.id,
          rawId: zuB64u(cred.rawId),
          type: cred.type,
          response: {
            clientDataJSON: zuB64u(antwort.clientDataJSON),
            authenticatorData: zuB64u(antwort.authenticatorData),
            signature: zuB64u(antwort.signature),
            userHandle: antwort.userHandle ? zuB64u(antwort.userHandle) : undefined,
          },
          clientExtensionResults: cred.getClientExtensionResults(),
          authenticatorAttachment: cred.authenticatorAttachment || undefined,
        },
        ziel: new URLSearchParams(window.location.search).get("next") || "",
      });
      window.location.href = ergebnis.ziel || "/";
    } catch (e) {
      meldung(ausgabe, fehlertext(e), true);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    const unterstuetzt = !!(window.PublicKeyCredential && navigator.credentials);
    document.querySelectorAll("[data-passkey]").forEach(function (knopf) {
      if (!unterstuetzt) {
        const hinweis = document.getElementById("passkey-meldung");
        meldung(hinweis, "Dieser Browser unterstützt keine Passkeys.", true);
        knopf.disabled = true;
        return;
      }
      knopf.hidden = false;
      knopf.addEventListener("click", function (ereignis) {
        ereignis.preventDefault();
        if (knopf.dataset.passkey === "registrieren") registrieren(knopf);
        else anmelden(knopf);
      });
    });
  });
})();
