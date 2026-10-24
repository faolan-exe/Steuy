// Rundgang: hebt das Element des aktuellen Schritts hervor und blättert dorthin.
(function () {
  "use strict";
  const fenster = document.getElementById("rundgang");
  if (!fenster || !fenster.dataset.licht) return;
  const ziele = document.querySelectorAll(fenster.dataset.licht);
  ziele.forEach(function (el) { el.classList.add("rundgang-licht"); });
  if (ziele.length) ziele[0].scrollIntoView({ block: "center" });
})();
