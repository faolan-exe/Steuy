// Kundenportal: IBAN, Betrag und Verwendungszweck mit einem Klick kopieren.
(function () {
  "use strict";
  document.addEventListener("click", function (e) {
    const feld = e.target.closest ? e.target.closest("[data-kopieren]") : null;
    if (!feld || !navigator.clipboard) return;
    const text = feld.textContent.replace(/\s+€$/, "").trim();
    navigator.clipboard.writeText(text).then(function () {
      let hinweis = feld.parentNode.querySelector(".k-kopiert");
      if (!hinweis) {
        hinweis = document.createElement("span");
        hinweis.className = "k-kopiert";
        feld.parentNode.appendChild(hinweis);
      }
      hinweis.textContent = "kopiert";
      setTimeout(function () { hinweis.textContent = ""; }, 1500);
    });
  });
})();
