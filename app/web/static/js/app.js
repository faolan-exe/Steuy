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
