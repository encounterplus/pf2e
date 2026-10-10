/**
 * Compact semantic Encounter+ UI actions for Codex Computer Use.
 *
 * Import this module inside the persistent node_repl and pass the existing
 * `sky` instance to `createEncounterPlusHelper`. The helper returns small
 * objects instead of accessibility-tree dumps and never uses coordinates.
 * Destructive content deletion is deliberately not implemented here.
 */

const ENCOUNTER_APP = "sk.qbit.tracker";
const FINDER_APP = "com.apple.finder";
const LOWER_COLLECTIONS = new Set([
  "Actions",
  "Conditions & Effects",
  "Hazards",
  "Vehicles",
  "Afflictions",
  "Deities",
  "Domains",
  "Languages",
  "GM Tools",
]);

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function elementLines(text) {
  return text
    .split("\n")
    .map((line) => {
      const match = line.trim().match(/^(\d+)\s+(.*)$/);
      return match ? { index: Number(match[1]), text: match[2] } : null;
    })
    .filter(Boolean);
}

function findElement(text, pattern, { last = false } = {}) {
  const matches = elementLines(text).filter((entry) => pattern.test(entry.text));
  return matches.length ? (last ? matches.at(-1) : matches[0]) : null;
}

function descriptionPattern(description, kind = "(?:text|button|heading|link)") {
  return new RegExp(`^${kind}.*Description: ${escapeRegex(description)}(?:,|$)`);
}

export function createEncounterPlusHelper(sky, options = {}) {
  const encounterApp = options.encounterApp ?? ENCOUNTER_APP;
  const finderApp = options.finderApp ?? FINDER_APP;
  const pause = options.pause ?? 250;

  async function state(app = encounterApp) {
    return sky.get_app_state({ app, disableDiff: true });
  }

  async function settle() {
    await new Promise((resolve) => setTimeout(resolve, pause));
    return state();
  }

  async function ensureLibrary() {
    let current = await state();
    if (/^Window: "Library"/.test(current.text)) return current;

    const libraryButton = findElement(
      current.text,
      /^button Library, Help: Show library window/,
    );
    if (libraryButton) {
      await sky.click({ app: encounterApp, element_index: libraryButton.index });
      current = await settle();
      if (/^Window: "Library"/.test(current.text)) return current;
    }

    const windowMenu = findElement(current.text, /^Window, ID: com\.apple\.menu\.window$/);
    if (!windowMenu) throw new Error("Encounter+ Window menu is not visible");
    await sky.click({ app: encounterApp, element_index: windowMenu.index });
    current = await settle();

    const library = findElement(current.text, /^Library, ID: makeKeyAndOrderFront:$/);
    if (!library) throw new Error("Encounter+ Library window is not open");
    await sky.click({ app: encounterApp, element_index: library.index });
    return settle();
  }

  async function clickMatch(pattern, { last = false } = {}) {
    const current = await state();
    const element = findElement(current.text, pattern, { last });
    if (!element) throw new Error(`Encounter+ control not found: ${pattern}`);
    await sky.click({ app: encounterApp, element_index: element.index });
    return settle();
  }

  async function closeSheetIfPresent() {
    const current = await state();
    const stop = findElement(current.text, descriptionPattern("Stop", "button"));
    if (!stop) return false;
    await sky.click({ app: encounterApp, element_index: stop.index });
    await settle();
    return true;
  }

  async function revealCollection(name) {
    let current = await state();
    let collection = findElement(current.text, descriptionPattern(name, "text"), {
      last: true,
    });
    if (collection) return { current, collection };

    const action = LOWER_COLLECTIONS.has(name) ? "Scroll Down" : "Scroll Up";
    for (let attempt = 0; attempt < 4 && !collection; attempt += 1) {
      const scrollables = elementLines(current.text).filter((entry) =>
        /^container Secondary Actions:.*Scroll Down.*Scroll Up/.test(entry.text),
      );
      const sidebar = scrollables.at(-1);
      if (!sidebar) break;
      await sky.perform_secondary_action({
        app: encounterApp,
        element_index: sidebar.index,
        action,
      });
      current = await settle();
      collection = findElement(current.text, descriptionPattern(name, "text"), {
        last: true,
      });
    }
    return { current, collection };
  }

  async function reloadSystem() {
    let current = await ensureLibrary();

    let reload = findElement(current.text, /^Reload System, ID: reload_system$/);
    if (!reload) {
      await closeSheetIfPresent();
      current = await state();

      const systemSection = findElement(
        current.text,
        descriptionPattern("System", "text"),
        { last: true },
      );
      if (!systemSection) throw new Error("System section is not visible");
      await sky.click({ app: encounterApp, element_index: systemSection.index });
      current = await settle();

      const systemRow = findElement(
        current.text,
        /^text.*Description: PF2E Remaster, Value: v\d+\.\d+\.\d+/,
      );
      if (!systemRow) throw new Error("PF2E Remaster system row is not visible");
      await sky.click({ app: encounterApp, element_index: systemRow.index });
      current = await settle();

      const actions = findElement(current.text, /^pop up button(?: |$)/);
      if (!actions) throw new Error("System actions menu is not visible");
      await sky.click({ app: encounterApp, element_index: actions.index });
      current = await settle();
      reload = findElement(current.text, /^Reload System, ID: reload_system$/);
    }

    if (!reload) throw new Error("Reload System action is not visible");
    await sky.click({ app: encounterApp, element_index: reload.index });
    current = await settle();
    return {
      ok: true,
      action: "reload-system",
      window: current.text.match(/^Window: "([^"]+)"/)?.[1] ?? null,
    };
  }

  async function openCollection(name) {
    await ensureLibrary();
    await closeSheetIfPresent();
    const { collection } = await revealCollection(name);
    if (!collection) throw new Error(`Encounter+ collection is not visible: ${name}`);
    await sky.click({ app: encounterApp, element_index: collection.index });
    const opened = await settle();
    const count = opened.text.match(/text Description: ([\d,]+) entries/)?.[1] ?? null;
    return {
      ok: true,
      collection: name,
      count: count === null ? null : Number(count.replaceAll(",", "")),
    };
  }

  async function openEntry(collection, name) {
    await openCollection(collection);
    let current = await state();
    const search = findElement(current.text, /^search text field/);
    if (!search) throw new Error(`Search field not visible in ${collection}`);
    await sky.set_value({ app: encounterApp, element_index: search.index, value: name });
    current = await settle();

    const entry = findElement(current.text, descriptionPattern(name, "text"));
    if (!entry) throw new Error(`Entry not found in ${collection}: ${name}`);
    await sky.click({ app: encounterApp, element_index: entry.index });
    current = await settle();

    const view = elementLines(current.text).find((line) =>
      /URL: encounterplus:\/\/local\/views\//.test(line.text),
    );
    const headings = elementLines(current.text)
      .filter((line) => line.text.startsWith("heading Description:"))
      .map((line) => line.text.match(/Description: ([^,]+)/)?.[1])
      .filter(Boolean)
      .slice(0, 8);
    return { ok: true, collection, entry: name, view: view?.text ?? null, headings };
  }

  async function auditCollections(names) {
    const results = [];
    for (const name of names) results.push(await openCollection(name));
    return { ok: true, collections: results };
  }

  async function visibleSummary() {
    const current = await state();
    const lines = elementLines(current.text);
    return {
      window: current.text.match(/^Window: "([^"]+)"/)?.[1] ?? null,
      selected: lines
        .filter((line) => /\(selected\).*Description:/.test(line.text))
        .map((line) => line.text.match(/Description: ([^,]+)/)?.[1])
        .filter(Boolean),
      headings: lines
        .filter((line) => line.text.startsWith("heading Description:"))
        .map((line) => line.text.match(/Description: ([^,]+)/)?.[1])
        .filter(Boolean)
        .slice(0, 10),
    };
  }

  async function importVisibleFinderPackage(fileName) {
    const finder = await state(finderApp);
    const file = findElement(
      finder.text,
      new RegExp(
        `^image(?: \\([^)]*\\))? ${escapeRegex(fileName)},.*Secondary Actions:.*open`,
      ),
    );
    if (!file) throw new Error(`Finder item is not visible: ${fileName}`);
    await sky.perform_secondary_action({
      app: finderApp,
      element_index: file.index,
      action: "open",
    });

    let current;
    let importButton;
    for (let attempt = 0; attempt < 40 && !importButton; attempt += 1) {
      current = await settle();
      importButton = findElement(
        current.text,
        descriptionPattern("IMPORT", "button"),
      );
    }
    if (!importButton) throw new Error(`Import sheet did not open for ${fileName}`);
    await sky.click({ app: encounterApp, element_index: importButton.index });
    for (let attempt = 0; attempt < 120; attempt += 1) {
      current = await settle();
      if (/Description: Success(?:,|$)/m.test(current.text)) break;
      if (/Description: (?:Failure|Error)(?:,|$)/m.test(current.text)) {
        throw new Error(`Encounter+ reported an import error for ${fileName}`);
      }
    }
    if (!/Description: Success(?:,|$)/m.test(current.text)) {
      throw new Error(`Timed out waiting for Encounter+ to import ${fileName}`);
    }
    const close = findElement(current.text, descriptionPattern("Close", "button"));
    if (close) await sky.click({ app: encounterApp, element_index: close.index });
    return { ok: true, file: fileName, status: "installed" };
  }

  return {
    state,
    ensureLibrary,
    reloadSystem,
    openCollection,
    openEntry,
    auditCollections,
    visibleSummary,
    importVisibleFinderPackage,
  };
}
