#!/usr/bin/env python3
"""Validate the complete linked creature spellcasting catalog."""

from __future__ import annotations

import json
from pathlib import Path

import json5

from creature_spellcasting import CATALOG_STATS, CREATURE_SPELLCASTING


REPO = Path(__file__).resolve().parents[1]
EXPECTED_UNRESOLVED = {
    ("crystal-strider-rage-of-elements", "Chromatic Ray (Release Light)"),
    ("jann-shuyookh-rage-of-elements", "Wall of Water"),
    ("stone-lion-cub-monster-core-2", "Detect Alignment (At Will) (Evil Only)"),
    ("tantriog-rage-of-elements", "Wall of Water"),
    ("urdefhan-tormentor-monster-core-2", "Daemonic Pact"),
    ("wood-scamp-rage-of-elements", "Verdant Sprout"),
}


def records(base: Path, name: str) -> list[dict]:
    result: list[dict] = []
    for path in base.glob(f"**/{name}"):
        result.extend(json.loads(path.read_text(encoding="utf-8")))
    return result


def main() -> int:
    creatures = records(REPO / "compendium" / "packs", "creatures.json")
    creatures += records(REPO / "compendium" / "ogl-packs", "creatures.json")
    by_slug = {record.get("slug"): record for record in creatures}
    spells = records(REPO / "compendium" / "packs", "spells.json")
    spells += records(REPO / "compendium" / "ogl-packs", "spells.json")
    rituals = records(REPO / "compendium" / "packs", "rituals.json")
    rituals += records(REPO / "compendium" / "ogl-packs", "rituals.json")
    routes = {f"/spell/{record['slug']}" for record in spells}
    routes.update(f"/ritual/{record['slug']}" for record in rituals)

    if len(CREATURE_SPELLCASTING) < 680:
        raise SystemExit("creature spellcasting catalog is unexpectedly incomplete")
    if CATALOG_STATS.get("spells", 0) < 6000 or CATALOG_STATS.get("rituals", 0) < 140:
        raise SystemExit("creature spell or ritual totals are unexpectedly incomplete")

    unresolved: set[tuple[str, str]] = set()
    linked = 0
    at_will = 0
    spell_count = 0
    ritual_count = 0
    for slug, configured in CREATURE_SPELLCASTING.items():
        creature = by_slug.get(slug)
        if creature is None:
            raise SystemExit(f"spellcasting catalog references missing creature: {slug}")
        data = creature.get("data", {})
        if configured.get("spellcasting") != data.get("spellcasting"):
            raise SystemExit(f"published spellcasting does not match catalog: {slug}")
        if configured.get("rituals") != data.get("rituals"):
            raise SystemExit(f"published rituals do not match catalog: {slug}")

        entries = [
            spell
            for casting in configured.get("spellcasting", [])
            for group in casting.get("spellGroups", [])
            for spell in group.get("spells", [])
        ]
        spell_count += len(entries)
        for casting in configured.get("spellcasting", []):
            for group in casting.get("spellGroups", []):
                identities = [
                    (
                        spell.get("name"),
                        spell.get("rank"),
                        spell.get("reference"),
                        bool(spell.get("atWill")),
                        spell.get("details"),
                    )
                    for spell in group.get("spells", [])
                ]
                if len(identities) != len(set(identities)):
                    raise SystemExit(
                        f"duplicate creature spell entry was not compacted: {slug}: {group.get('label')}"
                    )
        for entry in entries:
            if entry.get("atWill"):
                at_will += 1
                if "at will" in str(entry.get("details") or "").casefold():
                    raise SystemExit(f"at-will spell duplicates its display label: {slug}: {entry['name']}")
            reference = entry.get("reference")
            if not reference:
                unresolved.add((slug, entry["name"]))
            elif reference not in routes:
                raise SystemExit(f"unresolved creature reference: {slug}: {reference}")
            else:
                linked += 1

        ritual_entries = [
            ritual
            for group in configured.get("rituals", {}).get("ritualGroups", [])
            for ritual in group.get("rituals", [])
        ]
        ritual_count += len(ritual_entries)
        seen_rituals: set[tuple[int, str, str]] = set()
        for ritual in ritual_entries:
            identity = (
                int(ritual.get("rank") or 0),
                str(ritual.get("name") or ""),
                str(ritual.get("reference") or ""),
            )
            if identity in seen_rituals:
                raise SystemExit(f"duplicate creature ritual: {slug}: {identity[1]}")
            seen_rituals.add(identity)
            reference = ritual.get("reference")
            if not reference:
                unresolved.add((slug, ritual["name"]))
            elif not reference.startswith("/ritual/") or reference not in routes:
                raise SystemExit(f"unresolved creature ritual reference: {slug}: {reference}")
            else:
                linked += 1

    if unresolved != EXPECTED_UNRESOLVED:
        raise SystemExit(
            "unexpected unlinked legacy creature spells: "
            + json.dumps(sorted(unresolved), ensure_ascii=False)
        )
    actual_stats = {
        "creatures": len(CREATURE_SPELLCASTING),
        "linked": linked,
        "rituals": ritual_count,
        "spells": spell_count,
        "unresolved": len(unresolved),
    }
    if actual_stats != CATALOG_STATS:
        raise SystemExit(
            "creature spellcasting catalog totals are stale: "
            + json.dumps(actual_stats, sort_keys=True)
        )

    goblin = by_slug["goblin-war-chanter-monster-core"]
    casting = goblin["data"]["spellcasting"][0]
    if casting.get("spellDC") != 17 or casting.get("spellAttack") != 7:
        raise SystemExit("Goblin War Chanter sanity check failed")
    # Native regression: the parent preview showed Astradaemon's numeric
    # DC/attack while inherited text controls displayed None in the entry.
    astradaemon_casting = by_slug["astradaemon-monster-core"]["data"]["spellcasting"][0]
    if astradaemon_casting.get("spellDC") != 37 or astradaemon_casting.get("spellAttack") != 29:
        raise SystemExit("Astradaemon numeric spellcasting fixture changed")
    casting_form = json5.loads(
        (REPO / "forms/partials/spellcasting.json").read_text(encoding="utf-8")
    )
    casting_fields = {
        field.get("attribute"): field
        for section in casting_form.get("sections", [])
        for field in section.get("fields", [])
    }
    for attribute in ("spellDC", "spellAttack", "focusPoints"):
        if casting_fields.get(attribute, {}).get("type") != "number":
            raise SystemExit(f"{attribute}: numeric casting data must use a native number control")
    casting_groups = next(section for section in casting_form["sections"]
                          if section.get("attribute") == "spellGroups")
    if casting_groups.get("type") != "list" or casting_groups.get("form", {}).get("partial") != "spellcasting-group":
        raise SystemExit("numeric casting control repair changed the structured rank-group editor")
    if at_will < 500:
        raise SystemExit("creature at-will spell markers are unexpectedly incomplete")
    for creature in creatures:
        if any(
            spell.get("atWill")
            for casting in creature.get("data", {}).get("spellcasting", [])
            for group in casting.get("spellGroups", [])
            for spell in group.get("spells", [])
        ):
            ability_names = {
                ability.get("name")
                for entries in creature.get("data", {}).get("abilities", {}).values()
                for ability in entries or []
            }
            if "At-Will Spells" in ability_names:
                raise SystemExit(f"creature repeats at-will casting as an ability: {creature['slug']}")

    group_form = json.loads(
        (REPO / "forms/partials/spellcasting-group.json").read_text(encoding="utf-8")
    )
    ritual_form = json.loads(
        (REPO / "forms/partials/ritual-group.json").read_text(encoding="utf-8")
    )
    if group_form["sections"][1].get("attributeType") != "Spell":
        raise SystemExit("spellcasting group must use Encounter+'s Spell picker")
    if ritual_form["sections"][1].get("attributeType") != "Ritual":
        raise SystemExit("ritual group must use Encounter+'s Ritual picker")

    views = [
        (REPO / "views/partials/spellcasting.md").read_text(encoding="utf-8"),
        (REPO / "views/partials/creature-tertiary.md").read_text(encoding="utf-8"),
    ]
    if any("{% elsif" in view or "{% elseif" in view for view in views):
        raise SystemExit("creature views use a template tag unsupported by Encounter+")
    if "[at will](/action/at-will-spells-monster-core)" not in views[0]:
        raise SystemExit("at-will spell labels do not link to their shared rule")

    spell_form = json.loads(
        (REPO / "forms/partials/spellcasting-spell.json").read_text(encoding="utf-8")
    )
    spell_form_attributes = {
        field.get("attribute")
        for section in spell_form.get("sections", [])
        for field in section.get("fields", [])
    }
    if not {"atWill", "details"}.issubset(spell_form_attributes):
        raise SystemExit("at-will and repeated-spell details must remain editable")

    print(
        f"Validated {linked} linked spell/ritual references on "
        f"{len(CREATURE_SPELLCASTING)} creatures, {at_will} at-will spells; "
        f"{len(unresolved)} legacy references remain display-only"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
