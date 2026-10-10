# Public rules compendium

This directory contains Encounter+ modules made from game mechanics and
functional rules text that Paizo released under the Open RPG Creative (ORC)
License. It intentionally does not contain source PDFs, extracted page text,
watermarks, book art, maps, setting chapters, adventures, or creature lore.

The generated modules live in `packs/`. Each pack carries its own ORC and
Community Use notices so those terms and credits travel with an individual
`.module` file. The aggregate ORC notice is in
[ORC-NOTICE.md](ORC-NOTICE.md), and the upstream source and license review is
recorded in [sources.json](sources.json).

The separately licensed OGL module lives in `ogl-packs/rage-of-elements/`.
It carries the complete OGL 1.0a text and COPYRIGHT NOTICE in
`OGL-1.0a.txt`; it is not part of the ORC compendium and is not designated as
ORC Licensed Material.

## What is included

- actions, rules, traits, conditions, and afflictions
- ancestries, heritages, backgrounds, classes, archetypes, and feats
- spells and rituals
- equipment and other items
- mechanical creature, NPC, hazard, and vehicle statistics
- functional text required to use those game elements

## What is excluded

- all source-book art, maps, page images, fonts, and trade dress
- creature and ancestry lore, class introductions, setting prose, and
  background story prompts
- deity narrative and intercession lore (mechanical cleric fields are retained)
- private PDF extraction fields and source-site implementation identifiers
- OGL-only material inside the ORC packs

Names that identify Paizo game elements are descriptive references only and
remain Paizo property. See [COMMUNITY-USE-NOTICE.md](COMMUNITY-USE-NOTICE.md).

## Rebuilding and validation

The repository does not contain private source files. Given a separately
prepared structured staging directory, rebuild and validate with:

```sh
python3 tools/sync_aon_core_traits.py --staging /path/to/private/structured-modules --reference /path/to/aon-remaster.json
python3 tools/refresh_aon_rule_descriptions.py --staging /path/to/private/structured-modules --reference /path/to/aon-remaster.json
python3 tools/link_compendium_references.py --staging /path/to/private/structured-modules --foundry /path/to/foundry-pf2e/packs/pf2e --aon-reference /path/to/aon-remaster.json --write
python3 tools/build_public_orc_compendium.py --source /path/to/private/structured-modules
python3 tools/build_public_ogl_compendium.py --source /path/to/private/structured-modules/rage-of-elements
python3 tools/validate_public_orc_compendium.py
python3 tools/validate_public_ogl_compendium.py
```

The builder uses a fail-closed source allowlist. A new book is not included
until its ORC status, required attribution, and record types are reviewed.
The OGL builder is deliberately restricted to the separately reviewed
*Rage of Elements* module. The cross-link pass is read-only unless `--write`
is supplied. It restores source-authored Foundry/AoN references, adds only
context-disambiguated fallback links, and never processes Operations Center
pages. Validation rejects missing destinations and repeated links to the same
entry.
