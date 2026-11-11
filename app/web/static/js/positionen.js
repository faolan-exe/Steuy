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
  // Positionen hinzugefügt oder entfernt: Summe neu
  document.addEventListener("positionen-geaendert", function (e) { rechne(e.target); });
})();

// Positionen hinzufügen und entfernen, ohne die Seite neu zu laden. Der Server liest die
// Positionen nach ihrem Index (pos-<n>-...), Lücken sind egal. Ohne JavaScript schicken die
// Knöpfe das Formular wie früher ab.
(function () {
  "use strict";

  function bereich(form) { return form.querySelector("[data-positionen]"); }

  function naechsterIndex(form) {
    let hoechster = -1;
    form.querySelectorAll('[name^="pos-"][name$="-typ"]').forEach(function (feld) {
      const n = parseInt(feld.name.split("-")[1], 10);
      if (n > hoechster) hoechster = n;
    });
    return hoechster + 1;
  }

  function nummerieren(form) {
    let nr = 0;
    bereich(form).querySelectorAll("[data-position]").forEach(function (zeile) {
      if (zeile.classList.contains("freitext")) return;
      nr += 1;
      zeile.querySelector(".positionsnr").textContent = nr;
    });
    form.dispatchEvent(new CustomEvent("positionen-geaendert", { bubbles: true }));
  }

  function neueZeile(form, art) {
    const vorlage = document.getElementById(art === "text" ? "vorlage-text" : "vorlage-artikel");
    const i = String(naechsterIndex(form));
    const html = vorlage.innerHTML.replace(/__I__/g, i);
    const huelle = document.createElement("div");
    huelle.innerHTML = html.trim();
    const zeile = huelle.firstElementChild;
    bereich(form).appendChild(zeile);
    nummerieren(form);
    return zeile;
  }

  function istLeer(zeile) {
    if (zeile.classList.contains("freitext")) return false;
    const wert = function (ende) {
      const f = zeile.querySelector('[name$="-' + ende + '"]');
      return f ? f.value.trim() : "";
    };
    return !wert("bezeichnung") && /^0*(,0*)?$/.test(wert("preis"));
  }

  function artikelEinfuegen(form) {
    const auswahl = form.querySelector('select[name="neuer_artikel"]');
    const liste = document.getElementById("artikelvorschlaege");
    if (!auswahl || !liste) return;
    const daten = Array.from(liste.options).find(function (o) { return o.dataset.id === auswahl.value; });
    if (!daten) return;
    // Wie auf dem Server: eine leere Position (z. B. die erste im neuen Entwurf) wird ersetzt
    const leer = Array.from(bereich(form).querySelectorAll("[data-position]")).find(istLeer);
    const zeile = leer || neueZeile(form, "artikel");
    const setze = function (ende, wert) {
      const f = zeile.querySelector('[name$="-' + ende + '"]');
      if (f) f.value = wert;
    };
    setze("bezeichnung", daten.value);
    setze("artikel_id", daten.dataset.id);
    setze("einheit", daten.dataset.einheit || "");
    setze("preis", daten.dataset.preis || "0,00");
    setze("beschreibung", daten.dataset.beschreibung || "");
    nummerieren(form);
    const menge = zeile.querySelector('[name$="-menge"]');
    if (menge) { menge.focus(); menge.select(); }
  }

  document.addEventListener("click", function (e) {
    const knopf = e.target.closest ? e.target.closest("[data-neue-position], [data-entfernen]") : null;
    if (!knopf || !knopf.form || !bereich(knopf.form)) return;
    e.preventDefault();
    const form = knopf.form;
    if (knopf.hasAttribute("data-entfernen")) {
      knopf.closest("[data-position]").remove();
      nummerieren(form);
      return;
    }
    const art = knopf.dataset.neuePosition;
    if (art === "artikel-aus-liste") { artikelEinfuegen(form); return; }
    const zeile = neueZeile(form, art);
    const erstes = zeile.querySelector('[name$="-bezeichnung"]');
    if (erstes) erstes.focus();
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

// Artikel beim Tippen in „Bezeichnung“ vorschlagen. Passt der Text genau zu einem Artikel,
// werden Einheit, Preis und Beschreibung übernommen (nur in leere Felder bzw. Preis 0).
(function () {
  "use strict";
  function uebernehmen(feld) {
    const liste = document.getElementById("artikelvorschlaege");
    if (!liste || !/-bezeichnung$/.test(feld.name || "")) return;
    const wahl = Array.from(liste.options).find(function (o) { return o.value === feld.value; });
    if (!wahl) return;
    const pre = feld.name.replace(/bezeichnung$/, "");
    const form = feld.form;
    const setze = function (name, wert, nurWennLeer) {
      const ziel = form.querySelector('[name="' + pre + name + '"]');
      if (!ziel || !wert) return;
      const leer = !ziel.value.trim() || (name === "preis" && /^0+(,0+)?$/.test(ziel.value.trim()));
      if (!nurWennLeer || leer) ziel.value = wert;
    };
    setze("artikel_id", wahl.dataset.id, false);
    setze("einheit", wahl.dataset.einheit, true);
    setze("preis", wahl.dataset.preis, true);
    setze("beschreibung", wahl.dataset.beschreibung, true);
    const menge = form.querySelector('[name="' + pre + 'menge"]');
    if (menge) menge.dispatchEvent(new Event("input", { bubbles: true }));
  }
  document.addEventListener("change", function (e) { uebernehmen(e.target); });
  document.addEventListener("input", function (e) {
    // Auswahl aus der Vorschlagsliste kommt in manchen Browsern nur als input-Ereignis
    if (e.inputType === undefined || e.inputType === "insertReplacementText") uebernehmen(e.target);
  });
})();
