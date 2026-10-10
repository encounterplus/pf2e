#!/usr/bin/env python3
"""Build deterministic creature metadata omitted by the original converter."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from build_creature_ability_glossary import html_to_markdown
from foundry_markup import replace_foundry_directives


REPO = Path(__file__).resolve().parents[1]
DEFAULT_STAGING = REPO.parent / "structured-modules"
DEFAULT_FOUNDRY = REPO.parent / "foundry-pf2e" / "packs" / "pf2e"
DEFAULT_OUTPUT = REPO / "tools" / "creature-metadata.json"

SENSE_NAMES = {
    "greater-darkvision": "Greater Darkvision",
    "low-light-vision": "Low-Light Vision",
    "motion-sense": "Motion Sense",
    "see-invisibility": "See Invisibility",
}

# Foundry intentionally stores these in the trait rather than repeating them
# on every actor. A printed stat block still needs the complete list.
TRAIT_IMMUNITIES = {
    "mindless": {"mental"},
    "swarm": {"grabbed", "prone", "restrained"},
    "construct": {
        "bleed", "death-effects", "disease", "doomed", "drained",
        "fatigued", "healing", "mental", "nonlethal-attacks", "paralyzed",
        "poison", "sickened", "spirit", "unconscious", "vitality", "void",
    },
}

# The current Foundry Monster Core actors omit the physical resistance printed
# for adamantine dragons. Keep this small published-stat correction explicit so
# regenerating the catalog does not silently remove an important defense.
PUBLISHED_OVERRIDES = {
    "adamantine-dragon-young-monster-core": {"resistances": {"physical": "10 (except adamantine)"}},
    "adamantine-dragon-young-spellcaster-monster-core": {"resistances": {"physical": "10 (except adamantine)"}},
    "adamantine-dragon-adult-monster-core": {"resistances": {"physical": "15 (except adamantine)"}},
    "adamantine-dragon-adult-spellcaster-monster-core": {"resistances": {"physical": "15 (except adamantine)"}},
    "adamantine-dragon-ancient-monster-core": {"resistances": {"physical": "20 (except adamantine)"}},
    "adamantine-dragon-ancient-spellcaster-monster-core": {"resistances": {"physical": "20 (except adamantine)"}},
}

TRUNCATED_RECHARGE_TEXT = re.compile(r"\bdeals\s+1d4 rounds\b", re.I)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, default=DEFAULT_STAGING)
    parser.add_argument("--foundry", type=Path, default=DEFAULT_FOUNDRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def title(value: str) -> str:
    return " ".join(part.capitalize() for part in value.replace("_", "-").split("-"))


def clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"<[^>]+>", "", value)
    text = re.sub(r"@UUID\[[^]]+\]\{([^}]+)\}", r"\1", text)
    text = re.sub(r"@\w+\[[^]]+\](?:\{([^}]+)\})?", lambda m: m.group(1) or "", text)
    return " ".join(text.replace("&nbsp;", " ").split()).strip(" ;")


def normalized_name(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def display_trait(value: str) -> str:
    """Normalize a printed creature Strike trait without losing its parameter."""
    code = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    code = re.sub(r"^(deadly|fatal|two-hand)-1d", r"\1-d", code)
    code = re.sub(r"^(scatter|volley)-(\d+)-feet$", r"\1-\2", code)
    code = re.sub(r"^two-handed-", "two-hand-", code)
    if code == "reach-5" or code == "reach-5-feet":
        return "reach"
    match = re.fullmatch(r"(reach|range-increment|thrown)-(\d+)(?:-feet)?", code)
    return f"{match.group(1)}-{match.group(2)}" if match else code


def source_attack_metadata(raw: str) -> list[dict[str, Any]]:
    """Read the printed Strike type and traits from a staged stat block."""
    flat = " ".join(str(raw or "").split())
    pattern = re.compile(
        r"\b(Melee|Ranged)\s+\[[^]]+\]\s+(.+?)\s+([+-]\d+)\s*"
        r"(?:\((.*?)\))?,\s*Damage\b",
        flags=re.I,
    )
    result: list[dict[str, Any]] = []
    for match in pattern.finditer(flat):
        traits = [
            display_trait(value)
            for value in (match.group(4) or "").split(",")
            if display_trait(value) and display_trait(value) != "unarmed"
        ]
        result.append({
            "name": match.group(2).strip(),
            "type": match.group(1).casefold(),
            "traits": list(dict.fromkeys(traits)),
        })
    return result


def source_movement(raw: str) -> dict[str, int]:
    """Read printed Speeds, which can be more precise than actor automation."""
    match = re.search(r"(?m)^Speed\s+([^\n]+)", str(raw or ""), flags=re.I)
    if not match:
        return {}
    movement: dict[str, int] = {}
    for kind, value in re.findall(
        r"(?:(walk|burrow|climb|fly|swim)\s+)?(\d+)\s+feet",
        match.group(1).split(";", 1)[0],
        flags=re.I,
    ):
        movement[(kind or "walk").casefold()] = int(value)
    return movement


def source_ability_categories(raw: str, names: list[str]) -> dict[str, str]:
    """Place abilities according to their printed stat-block section."""
    text = str(raw or "")
    ac = re.search(r"(?m)^AC\b", text)
    speed = re.search(r"(?m)^Speed\b", text)
    if not ac or not speed:
        return {}
    result: dict[str, str] = {}
    for name in names:
        marker = re.search(
            rf"(?m)^{re.escape(name)}(?:\s+\[[^]]+\]|\s+\(|\s+[A-Z])",
            text,
            flags=re.I,
        )
        if not marker:
            continue
        result[name] = (
            "interaction"
            if marker.start() < ac.start()
            else ("defensive" if marker.start() < speed.start() else "offensive")
        )
    return result


def attack_metadata_matches(
    attacks: list[dict[str, Any]], supplied: list[dict[str, Any]]
) -> bool:
    """Avoid cataloguing source fields the staging converter already retained."""
    if len(attacks) != len(supplied):
        return False
    available: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attack in supplied:
        available[normalized_name(str(attack.get("name") or ""))].append(attack)
    for attack in attacks:
        matches = available.get(normalized_name(str(attack.get("name") or ""))) or []
        if not matches:
            return False
        source = matches.pop(0)
        traits = [str(value) for value in attack.get("traits") or [] if value != "unarmed"]
        attack_type = str(attack.get("type") or "melee")
        if any(value.startswith(("thrown-", "range-increment-")) for value in traits):
            attack_type = "ranged"
        if attack_type != source.get("type") or traits != source.get("traits"):
            return False
    return not any(available.values())


def item_route_index(staging: Path) -> dict[str, str]:
    candidates: dict[str, list[tuple[int, str]]] = defaultdict(list)
    preferred = {"player-core": 4, "gm-core": 3, "player-core-2": 2}
    for path in sorted(staging.glob("*/items.json")):
        source = path.parent.name
        for record in json.loads(path.read_text(encoding="utf-8")):
            name = str(record.get("name") or "")
            slug = str(record.get("slug") or "")
            if name and slug:
                candidates[normalized_name(name)].append(
                    (preferred.get(source, 1), f"/item/{slug}")
                )
    return {
        key: max(values, key=lambda value: (value[0], value[1]))[1]
        for key, values in candidates.items()
    }


def format_sense(sense: dict[str, Any]) -> str:
    kind = str(sense.get("type") or "")
    value = SENSE_NAMES.get(kind, title(kind))
    acuity = str(sense.get("acuity") or "")
    if acuity:
        value += f" ({acuity})"
    distance = sense.get("range")
    if distance:
        value += f" {distance} feet"
    return value


def format_defense(entry: dict[str, Any], include_value: bool) -> tuple[str, int | str]:
    kind = str(entry.get("type") or "")
    value: int | str = int(entry.get("value") or 0) if include_value else title(kind)
    qualifiers: list[str] = []
    exceptions = entry.get("exceptions") or []
    if exceptions:
        qualifiers.append("except " + ", ".join(title(str(item)) for item in exceptions))
    double_vs = entry.get("doubleVs") or []
    if double_vs:
        qualifiers.append("double vs. " + ", ".join(title(str(item)) for item in double_vs))
    if include_value and qualifiers:
        value = f"{value} ({'; '.join(qualifiers)})"
    elif not include_value and qualifiers:
        value = f"{value} ({'; '.join(qualifiers)})"
    return kind, value


def actor_metadata(
    actor: dict[str, Any], creature: dict[str, Any], item_routes: dict[str, str]
) -> dict[str, Any]:
    system = actor.get("system", {})
    perception = system.get("perception", {}) if isinstance(system.get("perception"), dict) else {}
    attributes = system.get("attributes", {}) if isinstance(system.get("attributes"), dict) else {}
    details = system.get("details", {}) if isinstance(system.get("details"), dict) else {}
    traits_data = system.get("traits", {}) if isinstance(system.get("traits"), dict) else {}
    traits = {str(value) for value in traits_data.get("value", [])}

    senses = [format_sense(value) for value in perception.get("senses", []) if isinstance(value, dict)]
    perception_details = clean_text(perception.get("details"))
    if perception_details:
        senses.append(perception_details)

    explicit: list[str] = []
    for value in attributes.get("immunities") or []:
        if isinstance(value, dict) and value.get("type"):
            _, rendered = format_defense(value, False)
            explicit.append(str(rendered))
    for trait in traits:
        explicit.extend(title(value) for value in TRAIT_IMMUNITIES.get(trait, set()))

    saves = system.get("saves", {}) if isinstance(system.get("saves"), dict) else {}
    save_details = []
    for key, label in (("fortitude", "Fortitude"), ("reflex", "Reflex"), ("will", "Will")):
        save = saves.get(key, {}) if isinstance(saves.get(key), dict) else {}
        value = clean_text(save.get("saveDetail"))
        if value:
            save_details.append(f"{label} {value}")

    languages = details.get("languages", {}) if isinstance(details.get("languages"), dict) else {}
    speed = attributes.get("speed", {}) if isinstance(attributes.get("speed"), dict) else {}
    hardness = attributes.get("hardness")
    hardness_value = hardness.get("value") if isinstance(hardness, dict) else None

    attack_effects: dict[str, list[str]] = {}
    attack_metadata: list[dict[str, Any]] = []
    lore_skills: list[dict[str, Any]] = []
    actor_abilities: dict[str, str] = {}
    carried_items: list[str] = []
    for item in actor.get("items") or []:
        if not isinstance(item, dict):
            continue
        item_system = item.get("system") or {}
        item_name = str(item.get("name") or "")
        if item.get("type") == "melee":
            effects = (item_system.get("attackEffects") or {}).get("value") or []
            if effects:
                attack_effects[item_name.casefold()] = [str(value) for value in effects]
            attack_traits = [
                str(value)
                for value in (item_system.get("traits") or {}).get("value", [])
                if str(value) != "unarmed"
            ]
            attack_range = item_system.get("range") or {}
            increment = attack_range.get("increment") if isinstance(attack_range, dict) else None
            if increment:
                attack_traits.append(f"range-increment-{int(increment)}")
            attack_metadata.append({
                "name": item_name,
                "type": (
                    "ranged"
                    if increment or any(value.startswith("thrown-") for value in attack_traits)
                    else "melee"
                ),
                "traits": list(dict.fromkeys(attack_traits)),
            })
        elif item.get("type") == "lore":
            modifier = (item_system.get("mod") or {}).get("value")
            if item_name and modifier is not None:
                lore_skills.append({"name": item_name, "value": int(modifier)})
        elif item.get("type") == "action":
            description = (item_system.get("description") or {}).get("value")
            if item_name and description:
                actor_abilities[item_name.casefold()] = html_to_markdown(
                    replace_foundry_directives(str(description))
                )
        elif item.get("type") in {
            "armor", "backpack", "consumable", "equipment", "treasure", "weapon"
        }:
            route = item_routes.get(normalized_name(item_name), "")
            label = f"[{item_name}]({route})" if route else item_name
            quantity = item_system.get("quantity", 1)
            if isinstance(quantity, dict):
                quantity = quantity.get("value", 1)
            try:
                count = int(quantity or 1)
            except (TypeError, ValueError):
                count = 1
            if count > 1:
                label += f" ({count})"
            carried_items.append(label)

    ability_text: dict[str, str] = {}
    creature_abilities = (creature.get("data") or {}).get("abilities") or {}
    for entries in creature_abilities.values():
        for ability in entries or []:
            if not isinstance(ability, dict):
                continue
            original = str(ability.get("text") or "")
            corrected = actor_abilities.get(str(ability.get("name") or "").casefold(), "")
            if corrected and TRUNCATED_RECHARGE_TEXT.search(original):
                ability_text[str(ability.get("name") or "")] = corrected

    creature_data = creature.get("data") or {}
    raw_text = str(creature_data.get("rawText") or "")
    printed_attacks = source_attack_metadata(raw_text)
    if printed_attacks:
        attack_metadata = printed_attacks
    actor_movement = {"walk": int(speed.get("value") or 0)} if speed.get("value") else {}
    for entry in speed.get("otherSpeeds") or []:
        if isinstance(entry, dict) and entry.get("type") and entry.get("value"):
            actor_movement[str(entry["type"])] = int(entry["value"])
    movement = source_movement(raw_text) or actor_movement
    ability_names = [
        str(ability.get("name") or "")
        for entries in creature_abilities.values()
        for ability in entries or []
        if isinstance(ability, dict) and ability.get("name")
    ]
    if attack_metadata_matches(creature_data.get("attacks") or [], attack_metadata):
        attack_metadata = []
    current_movement = creature_data.get("movement") or {}
    if movement and all(current_movement.get(key) == value for key, value in movement.items()):
        movement = {}
    ability_categories = source_ability_categories(raw_text, ability_names)
    current_categories = {
        str(ability.get("name") or ""): category
        for category, entries in creature_abilities.items()
        for ability in entries or []
        if isinstance(ability, dict)
    }
    ability_categories = {
        name: category
        for name, category in ability_categories.items()
        if current_categories.get(name) != category
    }

    result: dict[str, Any] = {
        "senses": ", ".join(dict.fromkeys(filter(None, senses))),
        "languages": list(dict.fromkeys(str(value) for value in languages.get("value", []))),
        "languagesDetails": clean_text(languages.get("details")),
        "acDetails": clean_text((attributes.get("ac") or {}).get("details")) if isinstance(attributes.get("ac"), dict) else "",
        "hpDetails": clean_text((attributes.get("hp") or {}).get("details")) if isinstance(attributes.get("hp"), dict) else "",
        "savesDetails": "; ".join(save_details),
        "immunities": sorted(dict.fromkeys(explicit), key=str.casefold),
        "weaknesses": {},
        "resistances": {},
        "movementOther": clean_text(speed.get("details")),
        "attackEffects": attack_effects,
        "attacks": attack_metadata,
        "loreSkills": lore_skills,
        "abilityText": ability_text,
        "abilityCategories": ability_categories,
        "items": ", ".join(carried_items),
        "movement": movement,
    }
    if hardness_value:
        result["hardness"] = int(hardness_value)
    for field in ("weaknesses", "resistances"):
        for entry in attributes.get(field) or []:
            if not isinstance(entry, dict) or not entry.get("type"):
                continue
            key, value = format_defense(entry, True)
            result[field][key] = value
    return {
        key: value
        for key, value in result.items()
        if key == "languages" or value not in (None, "", [], {})
    }


def actor_index(foundry: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(foundry.rglob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and value.get("type") == "npc" and value.get("_id"):
            result[str(value["_id"])].append(value)
    return result


def staging_creatures(staging: Path) -> Iterable[dict[str, Any]]:
    for path in sorted(staging.glob("*/creatures.json")):
        yield from json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    actors = actor_index(args.foundry)
    item_routes = item_route_index(args.staging)
    catalog: dict[str, dict[str, Any]] = {}
    for creature in staging_creatures(args.staging):
        foundry_id = str(creature.get("attributes", {}).get("foundryId") or "")
        slug = str(creature["slug"])
        candidates = actors.get(foundry_id, [])
        metadata: dict[str, Any] = {}
        if candidates:
            actor = next(
                (value for value in candidates if value.get("name") == creature.get("name")),
                candidates[0],
            )
            metadata = actor_metadata(actor, creature, item_routes)
        for field, supplied in PUBLISHED_OVERRIDES.get(slug, {}).items():
            if isinstance(supplied, dict):
                metadata.setdefault(field, {}).update(supplied)
            else:
                metadata[field] = supplied
        if metadata:
            catalog[slug] = metadata
    payload = {"stats": {"creatures": len(catalog)}, "creatures": dict(sorted(catalog.items()))}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["stats"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
