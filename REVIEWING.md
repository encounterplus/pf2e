# Review and testing guide

## Scope and commit map

This is an expansion of the official system's existing Remaster implementation.
The review branch consolidates the released candidate's development history
into five commits with explanatory bodies:

1. **Native system and sheets:** entity/type/configuration contracts, native
   JSON/JSON5 forms, Stencil/HTML views, localization, styles, assets, and
   existing candidate migrations.
2. **GM tools:** Operations Center pages/navigation, XP Planner, native handoff
   routes, and the builders/data for sourced reference tables.
3. **Build and regression tooling:** deterministic converters, content-source
   supplements, packaging, validators, regression suites, CI, and attribution
   documents.
4. **Generated content:** the ORC/OGL packs and their notices, inventories, and
   summaries. Review these separately from the handwritten implementation.
5. **Review documentation:** this guide and the README.

The initial editor commit is not a complete installer by itself. The native
sheets, tooling, and content references are checked together at the final PR
head. Original fork history and the published `v0.9.02` tag are preserved outside
this cleaned review history.

## Integration boundary

The candidate deliberately retains the tested `pf2e-remaster` namespace,
package/update URLs, and `0.9.02` version. Those identify the independent test
installation. The maintainer should choose the official version and update
channel, coordinate the `pf2e` namespace across package metadata and records,
and verify existing-campaign migrations before adopting it as an official
update. The current PR does not demonstrate an in-place upgrade of an existing
official `pf2e` campaign.

Forms and views use Encounter+'s existing definitions and templates. Rolls,
reference opening, map loading, token expiry, and experience awards use native
routes. Custom browser JavaScript is confined to the calculator/reference
panels. Printed spell duration and token expiry remain separate editable data.

## Automated checks

Run the three commands under **Build and check** in the README. The source
check covers 83 definitions and nine maintained validator groups, including
content conversion, creature editability/spellcasting, hazard/vehicle
mechanics, references, spell areas/durations, and four UI regression files.
Archive inspection checks record counts, license/source markers, packaged
references, metadata, and ZIP integrity. CI checks the same final snapshot.

The packaged definitions can be compared with the checkout using
`system_source_files()` from `tools/package_public_release.py`; each yielded
file should have identical bytes in the installer, except the GM Tool collection,
which the builder normalizes and stamps with the system version. Generated content should
be rebuilt through its owning converter/catalog, not edited directly in the
published packs. Full content regeneration also needs the corresponding
`--source` input tree; CI validation and packaging use the checked-in packs.

## Focused native checks

Install the candidate into a temporary campaign. These are smoke checks for a
reviewer; prior user-performed checks of the available flows are recorded below.

| Area | Check | Expected result |
| --- | --- | --- |
| Creatures/characters | Visit all four tabs; add, edit, remove and save/reopen a Skill/Lore entry, sense, inventory reference, attack and ability. Change a Recall Knowledge DC and an ability/attack-effect reference. | Structured values persist and the statblock reflects them; reference links open the selected entry. |
| Spellcasting/rituals | Open an existing creature spell link; add a spell and ritual using their group choosers; change the reference and save/reopen. | Name/rank/reference remain editable and the destination follows the saved reference. |
| Items | Switch category on an empty item; edit Craft Requirements, additional details, primary/named activations, and variants; clear fields and save/reopen. | Relevant controls appear, values persist, and clearing removes the rendered field without changing another activation. |
| Spell fields | Edit Cast actions, casting details, Range, Defense, and printed Duration. | The selected actions/icons and printed mechanics survive save/reopen independently of token expiry. |
| Map templates | Load Fireball and Detect Magic without a token; test an edited fractional cone, then remove it. | Native placement/load/removal and configured geometry work. |
| Token expiry | Test Haste's timer, Shield at source-turn start, Command at target-turn end, and a manual Heal/Mystic Armor reminder. Repeat with different Source and Target tokens. | Each expiry follows its configured source/target; manual reminders persist until removed. |
| Hazards/vehicles | Populate, add, edit, remove and save/reopen immunity/mechanics entries. | The native form and statblock agree, including after clearing. |
| Deities | Edit/clear directives and custom description, Any attribute notes, sanctification text, weapon/domains and cleric-spell links; Erastil is a reference fixture. | Editable mechanics render accurately and links open their intended rules. |
| GM tools/tables | Bookmark the Operations Center; navigate back and follow references; use XP party budgets/weak-elite/hazards and the native award handoff; roll a native roll table. | Compact navigation works, calculations respond, and handoffs open Encounter+'s native screens. |

## Evidence and remaining checks

The candidate's source checks and package inspection passed before this cleanup.
The user reports the available Mac native editor/reference checks passed,
including save/reopen, structured list editing, direct reference opening,
spell placement, and supported expiry flows. App 5.0.9 resolved the previously
reported nested-form refresh cases. The app-level small-name-edit saving issue
was explicitly excluded from system work.

Older saved-character and custom-spell native fixtures were unavailable.
The duration migration has automated published-spell fixtures and idempotence
checks, but a native existing-campaign upgrade is not claimed. Essence Dancers
sanctification and conflicting Rokoga Gin source material remain documented
content questions; they were not silently changed for this review cleanup.
