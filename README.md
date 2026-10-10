# PF2E editors, GM tools, and reviewed content

This contribution extends the existing **PF2E Remaster system** in
[encounterplus/pf2e](https://github.com/encounterplus/pf2e). The official system's
current display name is Pathfinder 2E; this work adds editor, presentation,
reference, and GM-tool functionality to that Remaster baseline.

The tested candidate keeps the separate `pf2e-remaster` identity and version
`0.9.02`. Adopting the official `pf2e` identity, update channel, and existing
campaign migration path needs a separate integration decision. See
[the review and testing guide](REVIEWING.md).

## Included changes

- Four-tab creature and character editors with structured skills/Lore, Recall
  Knowledge, senses, inventory references, attacks, abilities, and spellcasting.
- Editable item categories, craft requirements, additional details, activations,
  and variants, with corresponding native previews and statblocks.
- Variable-action spell casting, printed casting/range/defense/duration fields,
  map area templates, and native timed, turn-relative, or manual token effects.
- Editable hazard, vehicle, deity, and ritual mechanics with internal rule links.
- A bookmarkable Operations Center and an Encounter XP Planner using native
  experience-award and reference-opening routes.
- 24 reference tables and 30 native roll tables. The single installer contains
  18,041 records: 17,359 ORC records, 681 separately identified Rage of Elements
  OGL records, and one project-authored GM Tool record.

## Build and check

Use Python 3.12+ and Node.js 22+:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python tools/eplus_dev.py check --json
.venv/bin/python tools/package_public_release.py
.venv/bin/python tools/eplus_dev.py inspect-release --json
```

The builder produces `dist/pf2e-remaster.system`, a manifest, a record-count
summary, and checksums. CI runs these same checks and packaging steps.
Compendium JSON is generated output. Its converters, catalogs, source
supplements, and regressions live under `tools/`; full regeneration uses the
source tree supplied with `--source` (default: `../structured-modules`).
The checked-in packs are sufficient for CI validation and packaging.

## Native test installation

The [published 0.9.02 candidate](https://github.com/Saharory/pf2e_remasterd/releases/tag/v0.9.02)
contains the same runtime and content as this review branch, apart from a
whitespace-only cleanup in `types.json`.

1. Download `pf2e-remaster.system`, or build it using the commands above.
2. In Encounter+, open **Settings → Import** and select the system file.
3. Open **Settings → Systems** and select **Pathfinder 2E Remaster**.
4. Use a temporary campaign for the checks in [REVIEWING.md](REVIEWING.md).

To open the Operations Center during play, find its home page under
**Library → System → Content → PF2E Operations Center**, bookmark that page with
the ribbon button, then open it from **Bookmarks** on the game screen.

## Attribution

ORC and OGL records retain separate license markers and notices. See
[CONTENT-LICENSES.md](CONTENT-LICENSES.md), [LEGAL-REVIEW.md](LEGAL-REVIEW.md),
and the notices under `compendium/`. Existing official assets and added content
retain their documented attribution. Official distribution clearance remains
with the upstream maintainer.
