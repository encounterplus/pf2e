(function () {
  "use strict";

  function render(picker, tables) {
    var level = picker.querySelector("[data-ops-level]").value;
    var stat = picker.querySelector("[data-ops-stat]");
    var table = tables[stat ? Number(stat.value) : 0];
    var row = table.rows.find(function (candidate) { return candidate[0] === level; });
    if (!row) return;

    var result = picker.querySelector("[data-ops-values]");
    result.replaceChildren();
    table.headers.slice(1).forEach(function (header, index) {
      var pair = document.createElement("div");
      pair.className = "ops-ref-row";
      var label = document.createElement("strong");
      label.textContent = header;
      var value = document.createElement("span");
      value.textContent = row[index + 1].replace(/\*\*/g, "");
      pair.append(label, value);
      result.appendChild(pair);
    });
    picker.querySelector("[data-ops-source]").textContent = table.source;
    var full = picker.querySelector("[data-ops-full]");
    full.href = "/table/" + table.slug;
    full.textContent = "Open full " + table.name + " table";
  }

  document.querySelectorAll("[data-ops-reference]").forEach(function (picker) {
    var tables = JSON.parse(picker.querySelector("[data-ops-payload]").textContent);
    picker.querySelector("[data-ops-level]").addEventListener("change", function () { render(picker, tables); });
    var stat = picker.querySelector("[data-ops-stat]");
    if (stat) stat.addEventListener("change", function () { render(picker, tables); });
  });
})();
