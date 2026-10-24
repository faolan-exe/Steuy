// Rechnungseditor: Live-Anzeige der Positionsbeträge und der Summe, Anschrift beim Kundenwechsel.
// Nur Anzeige: Maßgeblich ist die Berechnung beim Speichern auf dem Server. Gerechnet wird
// wie dort mit ganzen Zahlen (Cent), nie mit Kommazahlen.
(function () {
  "use strict";

  // "1.234,56", "12,5", "12.5", "7" → ganze Zahl in 10^-stellen oder null, wenn unklar
  function lies(text, stellen) {
    let t = (text || "").trim().replace(/\s|€|%/g, "");
    if (!t) return null;
    if (/^\d{1,3}(\.\d{3})+$/.test(t)) t = t.replace(/\./g, "");
    else if (t.includes(",")) {
      const vorne = t.slice(0, t.lastIndexOf(","));
      const hinten = t.slice(t.lastIndexOf(",") + 1);
      if (/\./.test(vorne) && !/^\d{1,3}(\.\d{3})+$/.test(vorne)) return null;
      t = vorne.replace(/\./g, "") + "." + hinten;
    }
    const m = /^(\d+)(?:\.(\d*))?$/.exec(t);
    if (!m) return null;
    const rest = m[2] || "";
    if (rest.length > stellen) return null;
    return BigInt(m[1]) * 10n ** BigInt(stellen) + BigInt((rest + "0".repeat(stellen)).slice(0, stellen) || "0");
  }

  function geteilt(zaehler, nenner) {
    // halbe Cent weg vom Nullpunkt, wie auf dem Server
    const vz = zaehler < 0n ? -1n : 1n;
    const a = zaehler < 0n ? -zaehler : zaehler;
    let ganz = a / nenner;
    if (2n * (a % nenner) >= nenner) ganz += 1n;
    return vz * ganz;
  }

  function euro(cent) {
    const neg = cent < 0n;
    const a = neg ? -cent : cent;
    const e = (a / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return (neg ? "-" : "") + e + "," + (a % 100n).toString().padStart(2, "0") + " €";
  }

  function betragDerPosition(zeile) {
    const feld = (ende) => zeile.querySelector('input[name$="' + ende + '"]');
    const menge = lies(feld("menge") && feld("menge").value, 3);
    const preis = lies(feld("preis") && feld("preis").value, 2);
    const rabattText = feld("rabatt") ? feld("rabatt").value : "";
    const rabatt = rabattText.trim() ? lies(rabattText, 2) : 0n;
    if (menge === null || preis === null || rabatt === null || rabatt > 10000n) return null;
    return geteilt(preis * menge * (10000n - rabatt), 10000000n);
  }

  function rechne(form) {
    let summe = 0n;
    let gueltig = true;
    form.querySelectorAll(".position:not(.freitext)").forEach(function (zeile) {
      const b = betragDerPosition(zeile);
      const anzeige = zeile.querySelector(".positionsbetrag");
      if (b === null) {
        gueltig = false;
        if (anzeige) anzeige.textContent = "–";
        return;
      }
      summe += b;
      if (anzeige) anzeige.textContent = euro(b);
    });
    const gesamt = form.querySelector(".summenleiste strong");
    if (gesamt) gesamt.textContent = gueltig ? euro(summe) : "–";
  }

  document.addEventListener("input", function (e) {
    if (!e.target.name || !/-(menge|preis|rabatt)$/.test(e.target.name)) return;
    const form = e.target.closest("form");
    if (form) rechne(form);
  });
})();

// Kunde gewählt: Anschrift sofort in die Felder eintragen (nicht erst beim Speichern)
(function () {
  "use strict";
  document.addEventListener("change", function (e) {
    if (e.target.id !== "kontakt_id") return;
    const option = e.target.selectedOptions[0];
    if (!option || !option.value) return;
    const felder = {
      empfaenger_name: "name",
      empfaenger_zusatz: "zusatz",
      empfaenger_strasse: "strasse",
      empfaenger_plz: "plz",
      empfaenger_ort: "ort",
      empfaenger_land: "land",
    };
    Object.keys(felder).forEach(function (feld) {
      const eingabe = document.getElementById(feld);
      if (eingabe) eingabe.value = option.dataset[felder[feld]] || "";
    });
  });
})();
