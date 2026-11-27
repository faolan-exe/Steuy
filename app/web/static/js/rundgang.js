// Rundgang: hebt das Element des aktuellen Schritts hervor und blättert dorthin.
// Der Kasten lässt sich einklappen, damit er keine Knöpfe verdeckt; das bleibt beim Blättern so.
(function () {
  "use strict";
  const fenster = document.getElementById("rundgang");
  if (!fenster) return;

  const klapp = fenster.querySelector(".rundgang-klapp");
  const SCHLUESSEL = "steuy-rundgang-eingeklappt";
  function setze(zu) {
    fenster.classList.toggle("eingeklappt", zu);
    if (klapp) {
      klapp.textContent = zu ? "+" : "–";
      klapp.setAttribute("aria-expanded", zu ? "false" : "true");
      klapp.title = zu ? "Aufklappen" : "Einklappen";
      klapp.setAttribute("aria-label", zu ? "Rundgang aufklappen" : "Rundgang einklappen");
    }
    try {
      if (zu) localStorage.setItem(SCHLUESSEL, "1");
      else localStorage.removeItem(SCHLUESSEL);
    } catch (e) {
      /* ohne Speicher bleibt es nur auf dieser Seite eingeklappt */
    }
  }
  let zu = false;
  try {
    zu = localStorage.getItem(SCHLUESSEL) === "1";
  } catch (e) {
    zu = false;
  }
  setze(zu);
  if (klapp) {
    klapp.addEventListener("click", function (e) {
      e.stopPropagation();
      setze(!fenster.classList.contains("eingeklappt"));
    });
  }
  // Eingeklappt: Klick auf die Zeile klappt wieder auf
  fenster.addEventListener("click", function () {
    if (fenster.classList.contains("eingeklappt")) setze(false);
  });

  if (!fenster.dataset.licht) return;
  const ziele = document.querySelectorAll(fenster.dataset.licht);
  ziele.forEach(function (el) { el.classList.add("rundgang-licht"); });
  if (ziele.length) ziele[0].scrollIntoView({ block: "center" });
})();
