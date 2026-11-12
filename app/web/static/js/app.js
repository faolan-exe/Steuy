// Eigene Sicherheitsabfrage statt confirm(): Manche Browser und eingebettete Ansichten
// unterdrücken confirm() still, dann passierte beim Klick nichts.
(function () {
  "use strict";

  let dialog;

  function baueDialog() {
    dialog = document.createElement("dialog");
    dialog.className = "bestaetigung";
    dialog.innerHTML =
      '<form method="dialog">' +
      '<p class="bestaetigung-text"></p>' +
      '<div class="formular-fuss">' +
      '<button class="knopf knopf-text" value="nein">Abbrechen</button>' +
      '<button class="knopf knopf-primaer" value="ja"></button>' +
      "</div></form>";
    document.body.appendChild(dialog);
  }

  document.addEventListener("submit", function (ereignis) {
    const formular = ereignis.target;
    const frage = formular.dataset && formular.dataset.bestaetigen;
    if (!frage || formular.dataset.bestaetigt === "ja") return;
    ereignis.preventDefault();
    if (!dialog) baueDialog();
    dialog.querySelector(".bestaetigung-text").textContent = frage;
    dialog.querySelector('[value="ja"]').textContent =
      formular.dataset.bestaetigenKnopf || "Ja, fortfahren";
    dialog.onclose = function () {
      if (dialog.returnValue !== "ja") return;
      formular.dataset.bestaetigt = "ja";
      formular.requestSubmit(ereignis.submitter || undefined);
    };
    dialog.returnValue = "";
    dialog.showModal();
    dialog.querySelector('[value="nein"]').focus();
  });
})();

// Hilfe-Fragezeichen: Erklärung als Sprechblase bei Hover, Fokus oder Antippen.
(function () {
  "use strict";

  let blase;
  let aktiv = null;

  function zeige(ziel) {
    if (!blase) {
      blase = document.createElement("div");
      blase.className = "hilfeblase";
      blase.setAttribute("role", "tooltip");
      blase.id = "hilfeblase";
      document.body.appendChild(blase);
    }
    aktiv = ziel;
    blase.textContent = ziel.dataset.hilfe;
    blase.hidden = false;
    ziel.setAttribute("aria-expanded", "true");
    ziel.setAttribute("aria-describedby", "hilfeblase");
    const r = ziel.getBoundingClientRect();
    const b = blase.getBoundingClientRect();
    let links = r.left + r.width / 2 - b.width / 2;
    links = Math.max(8, Math.min(links, window.innerWidth - b.width - 8));
    let oben = r.bottom + 8;
    if (oben + b.height > window.innerHeight - 8) oben = r.top - b.height - 8;
    blase.style.left = links + "px";
    blase.style.top = Math.max(8, oben) + "px";
  }

  function verstecke() {
    if (!blase || !aktiv) return;
    blase.hidden = true;
    aktiv.removeAttribute("aria-expanded");
    aktiv.removeAttribute("aria-describedby");
    aktiv = null;
  }

  function hilfeVon(element) {
    return element && element.closest ? element.closest(".hilfe[data-hilfe]") : null;
  }

  document.addEventListener("DOMContentLoaded", function () {
    // Das title-Attribut ist nur der Ersatz ohne JavaScript
    document.querySelectorAll(".hilfe[title]").forEach(function (h) {
      h.removeAttribute("title");
    });
  });
  document.addEventListener("mouseover", function (e) {
    const h = hilfeVon(e.target);
    if (h && h !== aktiv) zeige(h);
  });
  document.addEventListener("mouseout", function (e) {
    const h = hilfeVon(e.target);
    if (h && h === aktiv && document.activeElement !== h) verstecke();
  });
  document.addEventListener("focusin", function (e) {
    const h = hilfeVon(e.target);
    if (h) zeige(h);
  });
  document.addEventListener("focusout", function (e) {
    if (hilfeVon(e.target)) verstecke();
  });
  document.addEventListener("click", function (e) {
    const h = hilfeVon(e.target);
    if (h) {
      // Nicht das Eingabefeld des Labels fokussieren, sondern nur erklären
      e.preventDefault();
      zeige(h);
    } else {
      verstecke();
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") verstecke();
  });
  window.addEventListener("scroll", verstecke, { passive: true });
})();

// Formulare, die beim Ändern sofort speichern (Schalter, Jahreswahl, Datei-Auswahl), und
// Druck-Knöpfe. Ohne Inline-Handler, damit die Content-Security-Policy keine braucht.
(function () {
  "use strict";
  let toast;
  function zeigeMeldung(text, fehler) {
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "toast";
      toast.setAttribute("role", "status");
      document.body.appendChild(toast);
    }
    toast.textContent = text;
    toast.classList.toggle("toast-fehler", !!fehler);
    toast.classList.add("sichtbar");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(function () { toast.classList.remove("sichtbar"); }, 2500);
  }

  // Schalter speichern im Hintergrund, die Seite bleibt stehen. Auswahllisten und Dateien
  // (z. B. Jahreswahl, Beleg-Upload) laden dagegen neuen Inhalt und schicken das Formular ab.
  function imHintergrund(feld) {
    const form = feld.form;
    const daten = new FormData(form); // vor dem Sperren lesen: gesperrte Felder fehlen sonst
    feld.disabled = true;
    fetch(form.action, {
      method: "POST",
      body: daten,
      headers: { "X-Requested-With": "fetch" },
      credentials: "same-origin",
    })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (antwort) { zeigeMeldung(antwort.meldung || "Gespeichert."); })
      .catch(function () {
        if (feld.type === "checkbox") feld.checked = !feld.checked;
        zeigeMeldung("Das konnte nicht gespeichert werden. Bitte erneut versuchen.", true);
      })
      .finally(function () { feld.disabled = false; });
  }

  document.addEventListener("change", function (e) {
    const feld = e.target.closest ? e.target.closest("[data-sofort-senden]") : null;
    if (!feld || !feld.form) return;
    if ((feld.type === "checkbox" || feld.type === "radio") && window.fetch && window.FormData) {
      imHintergrund(feld);
      return;
    }
    if (feld.form.requestSubmit) feld.form.requestSubmit();
    else feld.form.submit();
  });
  document.addEventListener("click", function (e) {
    if (e.target.closest && e.target.closest("[data-drucken]")) window.print();
    // „Zurück“ auf Fehlerseiten: ohne Verlauf (neuer Tab) führt der Link zur Übersicht
    if (e.target.closest && e.target.closest("[data-zurueck]") && window.history.length > 1) {
      e.preventDefault();
      window.history.back();
    }
  });
})();

// Text aus einem Feld kopieren (z. B. Kundenlink)
(function () {
  "use strict";
  document.addEventListener("click", function (e) {
    const knopf = e.target.closest ? e.target.closest("[data-kopieren-aus]") : null;
    if (!knopf) return;
    const feld = document.querySelector(knopf.dataset.kopierenAus);
    if (!feld) return;
    feld.select();
    const fertig = function () {
      const alt = knopf.textContent;
      knopf.textContent = "Kopiert";
      setTimeout(function () { knopf.textContent = alt; }, 1500);
    };
    if (navigator.clipboard) navigator.clipboard.writeText(feld.value).then(fertig);
    else { document.execCommand("copy"); fertig(); }
  });
})();

// Hell oder dunkel: sofort umschalten, im Hintergrund speichern. „auto“ heißt wie das System.
(function () {
  "use strict";
  const system = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  const wurzel = document.documentElement;

  function systemDunkel() { return !!(system && system.matches); }
  function istDunkel() {
    const fest = wurzel.dataset.farbschema;
    return fest ? fest === "dunkel" : systemDunkel();
  }
  function setze(wert) {
    if (wert === "hell" || wert === "dunkel") wurzel.dataset.farbschema = wert;
    else delete wurzel.dataset.farbschema;
  }

  document.addEventListener("submit", function (e) {
    const form = e.target.closest ? e.target.closest("[data-farbschema-schalter]") : null;
    if (!form || !window.fetch || !window.FormData) return;
    e.preventDefault();
    const ziel = istDunkel() ? "hell" : "dunkel";
    // Landet der Klick wieder beim System, folgt steuy ihm ab jetzt wieder
    const wert = (ziel === "dunkel") === systemDunkel() ? "auto" : ziel;
    const vorher = wurzel.dataset.farbschema || "auto";
    setze(wert);
    const daten = new FormData(form);
    daten.set("farbschema", wert);
    fetch(form.action, {
      method: "POST",
      body: daten,
      headers: { "X-Requested-With": "fetch" },
      credentials: "same-origin",
    })
      .then(function (r) { if (!r.ok) throw new Error(r.status); })
      .then(function () {
        const wahl = document.querySelector('input[name="farbschema"][value="' + wert + '"]');
        if (wahl && wahl.type === "radio") wahl.checked = true;
      })
      .catch(function () { setze(vorher); });
  });

  document.addEventListener("change", function (e) {
    const feld = e.target;
    if (feld && feld.name === "farbschema" && feld.type === "radio" && feld.checked) setze(feld.value);
  });
})();
