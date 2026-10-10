(function (root, factory) {
  var api = factory();
  root.PF2EXPCalculator = api;
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  var STANDARD_XP = { "-4": 10, "-3": 15, "-2": 20, "-1": 30, "0": 40, "1": 60, "2": 80, "3": 120, "4": 160 };
  var SIMPLE_HAZARD_XP = { "-4": 2, "-3": 3, "-2": 4, "-1": 6, "0": 8, "1": 12, "2": 16, "3": 24, "4": 32 };
  var BASE_BUDGETS = { trivial: 40, low: 60, moderate: 80, severe: 120, extreme: 160 };
  var CHARACTER_ADJUSTMENTS = { trivial: 10, low: 20, moderate: 20, severe: 30, extreme: 40 };
  var THREATS = ["trivial", "low", "moderate", "severe", "extreme"];
  var STORAGE_KEY = "pf2e-remaster.encounter-xp-calculator.v1";

  function integer(value, fallback) {
    var parsed = Number(value);
    return Number.isFinite(parsed) ? Math.trunc(parsed) : fallback;
  }

  function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
  }

  function adjustedBudgets(partySize) {
    var size = clamp(integer(partySize, 4), 1, 12);
    var difference = size - 4;
    var result = {};
    THREATS.forEach(function (threat) {
      result[threat] = Math.max(0, BASE_BUDGETS[threat] + difference * CHARACTER_ADJUSTMENTS[threat]);
    });
    return result;
  }

  function xpFor(kind, levelDifference) {
    var table = kind === "simple-hazard" ? SIMPLE_HAZARD_XP : STANDARD_XP;
    var key = String(integer(levelDifference, 99));
    return Object.prototype.hasOwnProperty.call(table, key) ? table[key] : null;
  }

  function classifyThreat(total, budgets) {
    var xp = Math.max(0, integer(total, 0));
    if (xp <= 0) return "trivial";
    if (xp >= budgets.extreme) return "extreme";
    if (xp >= budgets.severe) return "severe";
    if (xp >= budgets.moderate) return "moderate";
    if (xp >= budgets.low) return "low";
    return "trivial";
  }

  function calculateEntry(entry, partyLevel) {
    var quantity = clamp(integer(entry.quantity, 1), 1, 99);
    var adjustment = clamp(integer(entry.adjustment, 0), -1, 1);
    var level = integer(entry.level, partyLevel);
    var effectiveLevel = level + adjustment;
    var difference = effectiveLevel - partyLevel;
    var overridePresent = entry.overrideXp !== "" && entry.overrideXp !== null && entry.overrideXp !== undefined;
    var override = overridePresent ? Number(entry.overrideXp) : null;
    var validOverride = overridePresent && Number.isFinite(override) && override >= 0;
    var automaticXp = xpFor(entry.kind, difference);
    var eachXp = validOverride ? Math.trunc(override) : automaticXp;
    return {
      name: entry.name || "",
      kind: entry.kind || "creature",
      level: level,
      adjustment: adjustment,
      effectiveLevel: effectiveLevel,
      levelDifference: difference,
      quantity: quantity,
      overrideXp: validOverride ? Math.trunc(override) : null,
      eachXp: eachXp,
      totalXp: eachXp === null ? 0 : eachXp * quantity,
      outOfRange: automaticXp === null && !validOverride,
      invalidOverride: overridePresent && !validOverride
    };
  }

  function calculateEncounter(input) {
    var partyLevel = clamp(integer(input.partyLevel, 1), 1, 20);
    var partySize = clamp(integer(input.partySize, 4), 1, 12);
    var additionalXp = Math.max(0, integer(input.additionalXp, 0));
    var entries = (input.entries || []).map(function (entry) {
      return calculateEntry(entry, partyLevel);
    });
    var encounterXp = entries.reduce(function (sum, entry) { return sum + entry.totalXp; }, 0);
    var budgets = adjustedBudgets(partySize);
    return {
      partyLevel: partyLevel,
      partySize: partySize,
      entries: entries,
      encounterXp: encounterXp,
      additionalXp: additionalXp,
      awardedXp: encounterXp + additionalXp,
      budgets: budgets,
      threat: classifyThreat(encounterXp, budgets),
      warnings: entries.filter(function (entry) { return entry.outOfRange || entry.invalidOverride; }).length
    };
  }

  function titleCase(value) {
    return value.charAt(0).toUpperCase() + value.slice(1);
  }

  function nativeAwardValue(result) {
    return String(Math.max(0, integer(result && result.awardedXp, 0)));
  }

  function copyText(value) {
    var text = String(value);
    if (typeof navigator !== "undefined" && navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      try {
        var input = document.createElement("textarea");
        input.value = text;
        input.setAttribute("readonly", "");
        input.style.position = "fixed";
        input.style.opacity = "0";
        document.body.appendChild(input);
        input.select();
        var copied = document.execCommand("copy");
        input.remove();
        if (copied) resolve();
        else reject(new Error("Copy was unavailable"));
      } catch (error) {
        reject(error);
      }
    });
  }

  function makeOption(value, label) {
    var option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    return option;
  }

  function makeNumberInput(className, value, minimum, maximum, placeholder) {
    var input = document.createElement("input");
    input.type = "number";
    input.className = className;
    input.value = value;
    input.min = String(minimum);
    if (maximum !== null) input.max = String(maximum);
    input.step = "1";
    if (placeholder) input.placeholder = placeholder;
    return input;
  }

  function createEntryRow(entry) {
    var row = document.createElement("tr");
    row.setAttribute("data-xp-entry", "");

    var nameCell = row.insertCell();
    nameCell.setAttribute("data-label", "Name");
    var name = document.createElement("input");
    name.type = "text";
    name.className = "xp-entry-name";
    name.placeholder = "Optional name";
    name.value = entry.name || "";
    nameCell.appendChild(name);

    var kindCell = row.insertCell();
    kindCell.setAttribute("data-label", "Type");
    var kind = document.createElement("select");
    kind.className = "xp-entry-kind";
    kind.appendChild(makeOption("creature", "Creature"));
    kind.appendChild(makeOption("complex-hazard", "Complex hazard"));
    kind.appendChild(makeOption("simple-hazard", "Simple hazard"));
    kind.value = entry.kind || "creature";
    kindCell.appendChild(kind);

    var levelCell = row.insertCell();
    levelCell.setAttribute("data-label", "Level");
    levelCell.appendChild(makeNumberInput("xp-entry-level", entry.level, -1, 25));

    var adjustmentCell = row.insertCell();
    adjustmentCell.setAttribute("data-label", "Adjustment");
    var adjustment = document.createElement("select");
    adjustment.className = "xp-entry-adjustment";
    adjustment.appendChild(makeOption("-1", "Weak (−1)"));
    adjustment.appendChild(makeOption("0", "Normal"));
    adjustment.appendChild(makeOption("1", "Elite (+1)"));
    adjustment.value = String(entry.adjustment || 0);
    adjustmentCell.appendChild(adjustment);

    var quantityCell = row.insertCell();
    quantityCell.setAttribute("data-label", "Quantity");
    quantityCell.appendChild(makeNumberInput("xp-entry-quantity", entry.quantity || 1, 1, 99));

    var overrideCell = row.insertCell();
    overrideCell.setAttribute("data-label", "XP override");
    overrideCell.appendChild(makeNumberInput("xp-entry-override", entry.overrideXp == null ? "" : entry.overrideXp, 0, null, "Auto"));

    var eachCell = row.insertCell();
    eachCell.setAttribute("data-label", "XP each");
    eachCell.className = "xp-entry-each";
    eachCell.textContent = "—";

    var totalCell = row.insertCell();
    totalCell.setAttribute("data-label", "Total XP");
    totalCell.className = "xp-entry-total";
    totalCell.textContent = "—";

    var removeCell = row.insertCell();
    removeCell.className = "xp-entry-remove-cell";
    var remove = document.createElement("button");
    remove.type = "button";
    remove.className = "xp-remove";
    remove.setAttribute("aria-label", "Remove entry");
    remove.textContent = "×";
    removeCell.appendChild(remove);
    return row;
  }

  function readEntry(row) {
    return {
      name: row.querySelector(".xp-entry-name").value,
      kind: row.querySelector(".xp-entry-kind").value,
      level: row.querySelector(".xp-entry-level").value,
      adjustment: row.querySelector(".xp-entry-adjustment").value,
      quantity: row.querySelector(".xp-entry-quantity").value,
      overrideXp: row.querySelector(".xp-entry-override").value
    };
  }

  function initialState(partyLevel) {
    return {
      partyLevel: partyLevel || 1,
      partySize: 4,
      additionalXp: 0,
      entries: [{ name: "", kind: "creature", level: partyLevel || 1, adjustment: 0, quantity: 1, overrideXp: "" }]
    };
  }

  function loadState() {
    try {
      var saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
      return saved && Array.isArray(saved.entries) ? saved : null;
    } catch (error) {
      return null;
    }
  }

  function saveState(state) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (error) { /* storage is optional */ }
  }

  function initialize(container) {
    var partyLevelInput = container.querySelector("[data-xp-party-level]");
    var partySizeInput = container.querySelector("[data-xp-party-size]");
    var additionalInput = container.querySelector("[data-xp-additional]");
    var entriesBody = container.querySelector("[data-xp-entries]");
    var state = loadState() || initialState(1);

    function addRow(entry) {
      entriesBody.appendChild(createEntryRow(entry));
    }

    function readState() {
      return {
        partyLevel: partyLevelInput.value,
        partySize: partySizeInput.value,
        additionalXp: additionalInput.value,
        entries: Array.prototype.map.call(entriesBody.querySelectorAll("[data-xp-entry]"), readEntry)
      };
    }

    function render() {
      var raw = readState();
      var result = calculateEncounter(raw);
      container.querySelector("[data-xp-total]").textContent = String(result.encounterXp);
      container.querySelector("[data-xp-threat]").textContent = titleCase(result.threat);
      container.querySelector("[data-xp-award]").textContent = String(result.awardedXp);
      var copyButton = container.querySelector("[data-xp-copy-native]");
      var awardValue = nativeAwardValue(result);
      copyButton.setAttribute("data-copy-value", awardValue);
      copyButton.textContent = "Copy " + awardValue + " XP";
      container.querySelector("[data-xp-threat-card]").setAttribute("data-threat", result.threat);

      THREATS.forEach(function (threat) {
        var cell = container.querySelector('[data-xp-budget="' + threat + '"]');
        cell.textContent = String(result.budgets[threat]);
        cell.classList.toggle("is-current", result.threat === threat);
      });

      var rows = entriesBody.querySelectorAll("[data-xp-entry]");
      result.entries.forEach(function (entry, index) {
        var row = rows[index];
        row.classList.toggle("has-warning", entry.outOfRange || entry.invalidOverride);
        row.querySelector(".xp-entry-each").textContent = entry.eachXp === null ? "Out of range" : String(entry.eachXp);
        row.querySelector(".xp-entry-total").textContent = entry.eachXp === null ? "—" : String(entry.totalXp);
      });

      var warning = container.querySelector("[data-xp-warning]");
      warning.hidden = result.warnings === 0;
      warning.textContent = result.warnings ? "One or more entries are outside the normal party level −4 to +4 range, or have an invalid override. Enter a nonnegative XP override to include them." : "";
      container.querySelector("[data-xp-interpretation]").textContent = result.encounterXp + " XP compared with the " + result.budgets[result.threat] + " XP " + titleCase(result.threat) + " target for " + result.partySize + " PC" + (result.partySize === 1 ? "" : "s") + ".";
      saveState(raw);
    }

    partyLevelInput.value = clamp(integer(state.partyLevel, 1), 1, 20);
    partySizeInput.value = clamp(integer(state.partySize, 4), 1, 12);
    additionalInput.value = Math.max(0, integer(state.additionalXp, 0));
    (state.entries.length ? state.entries : initialState(partyLevelInput.value).entries).forEach(addRow);

    container.addEventListener("input", render);
    container.addEventListener("change", render);
    container.querySelector("[data-xp-add-entry]").addEventListener("click", function () {
      addRow(initialState(integer(partyLevelInput.value, 1)).entries[0]);
      render();
    });
    container.addEventListener("click", function (event) {
      if (!event.target.classList.contains("xp-remove")) return;
      event.target.closest("tr").remove();
      if (!entriesBody.children.length) addRow(initialState(integer(partyLevelInput.value, 1)).entries[0]);
      render();
    });
    container.querySelector("[data-xp-reset]").addEventListener("click", function () {
      var fresh = initialState(1);
      partyLevelInput.value = fresh.partyLevel;
      partySizeInput.value = fresh.partySize;
      additionalInput.value = fresh.additionalXp;
      entriesBody.textContent = "";
      fresh.entries.forEach(addRow);
      render();
    });
    container.querySelector("[data-xp-copy-native]").addEventListener("click", function (event) {
      var button = event.currentTarget;
      var status = container.querySelector("[data-xp-copy-status]");
      copyText(button.getAttribute("data-copy-value")).then(function () {
        status.textContent = "Copied. Paste this into Encounter+'s Total Experience field.";
      }).catch(function () {
        status.textContent = "Copy was blocked. Enter the displayed Native award total manually.";
      });
    });
    render();
  }

  function initializeAll() {
    var containers = document.querySelectorAll("[data-xp-calculator]");
    Array.prototype.forEach.call(containers, initialize);
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initializeAll);
    else initializeAll();
  }

  return {
    STANDARD_XP: STANDARD_XP,
    SIMPLE_HAZARD_XP: SIMPLE_HAZARD_XP,
    BASE_BUDGETS: BASE_BUDGETS,
    CHARACTER_ADJUSTMENTS: CHARACTER_ADJUSTMENTS,
    adjustedBudgets: adjustedBudgets,
    xpFor: xpFor,
    classifyThreat: classifyThreat,
    calculateEntry: calculateEntry,
    calculateEncounter: calculateEncounter,
    nativeAwardValue: nativeAwardValue
  };
});
