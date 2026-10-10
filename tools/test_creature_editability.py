#!/usr/bin/env python3
"""Validate creature ability text and editable spell/ritual summaries."""

from __future__ import annotations

import json
import re
from pathlib import Path

import json5

from build_public_orc_compendium import parameterized_trait_family
from build_creature_metadata import PUBLISHED_OVERRIDES
from creature_ability_glossary import GLOSSARY, GLOSSARY_ROUTES
from creature_metadata import CREATURE_IDENTIFICATION_SKILLS
from creature_senses import SENSE_ROUTES, link_shared_senses
from creature_editor_data import (
    parse_ability_editor_fields,
    parse_item_entries,
    parse_defense_entries,
    parse_reference_entry,
    parse_sense_entries,
    render_ability_editor_fields,
    render_item_entries,
    render_defense_entries,
    render_reference_entry,
    render_sense_entries,
)


REPO = Path(__file__).resolve().parents[1]
SEPARATOR = re.compile(r"\n\s*---\s*\n")


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def content_tokens(value: str) -> list[str]:
    """Compare visible/editor content without treating punctuation as data."""
    return sorted(re.findall(r"[a-z0-9]+", value.casefold()))


def linked_labels(values: list) -> set[str]:
    return {
        re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", str(value)).casefold()
        for value in values
    }


def visible_label(value: object) -> str:
    return re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", str(value)).casefold()


def recall_entries(subjects: list[str]) -> list[dict]:
    return [
        {
            "subject": subject,
            "skills": list(CREATURE_IDENTIFICATION_SKILLS[subject]),
        }
        for subject in subjects
    ]


def records(name: str) -> list[dict]:
    result: list[dict] = []
    for base in (REPO / "compendium" / "packs", REPO / "compendium" / "ogl-packs"):
        for path in base.glob(f"**/{name}"):
            result.extend(json.loads(path.read_text(encoding="utf-8")))
    return result


def field_attributes(partial: dict) -> set[str]:
    return {
        str(field.get("attribute"))
        for section in partial.get("sections", [])
        for field in section.get("fields", [])
        if field.get("attribute")
    }


def form(name: str) -> dict:
    return json5.loads(
        (REPO / "forms" / name).read_text(encoding="utf-8"),
        allow_duplicate_keys=False,
    )


def form_nodes(definition: dict):
    """Walk inline definitions without changing their binding context."""
    yield definition
    for key in ("tabs", "sections", "fields"):
        for child in definition.get(key, []):
            yield from form_nodes(child)
    if isinstance(definition.get("form"), dict):
        yield from form_nodes(definition["form"])


def validate_form_refresh_bindings() -> None:
    """Protect the entity-context pattern verified on Mac in Encounter+.

    Entry forms still receive their list row. Object lists retain explicit
    context-preserving pages; scalar string lists use native field controls.
    """
    def walk(node: dict, role: str, location: str, row: bool, nested: bool) -> None:
        kind = node.get("type")
        attribute = node.get("attribute")
        if kind == "form" and attribute:
            raise SystemExit(f"{location}: nested form loses its parent context")
        if role == "field" and kind == "list" and node.get("form"):
            raise SystemExit(f"{location}: object lists need an explicit context-preserving list page")
        if role == "section" and kind == "list" and not node.get("form"):
            raise SystemExit(f"{location}: scalar lists need a native field-level list control")
        if kind == "form" and not node.get("text"):
            raise SystemExit(f"{location}: context-preserving form needs an explicit summary")
        if nested and not row and attribute and not attribute.startswith("data."):
            raise SystemExit(f"{location}: nested entity binding is not fully qualified: {attribute}")
        for key, child_role in (("tabs", "form"), ("sections", "section"), ("fields", "field")):
            for index, child in enumerate(node.get(key, [])):
                walk(child, child_role, f"{location}.{key}[{index}]", row, nested)
        child_form = node.get("form")
        if isinstance(child_form, dict):
            if child_form.get("partial"):
                child_form = form(f"partials/{child_form['partial']}.json")
            walk(child_form, "form", f"{location}.form", row or kind == "list", True)

    for path in sorted((REPO / "forms").glob("*.json")):
        walk(form(path.name), "form", path.name, False, False)


def main() -> int:
    validate_form_refresh_bindings()
    source_generation_examples = {
        "murajau-rage-of-elements",
        "lithic-locus-rage-of-elements",
        "solar-crow-rage-of-elements",
        "vault-builder-rage-of-elements",
        "adult-executor-dragon-draconic-codex-creature-creature-4139",
    }
    if source_generation_examples.intersection(PUBLISHED_OVERRIDES):
        raise SystemExit("audited creatures must be generated from source, not patched by slug")
    if len(GLOSSARY) != 55:
        raise SystemExit("shared monster ability glossary is incomplete")
    glossary_keys = {normalize(code) for code in GLOSSARY}

    creatures = records("creatures.json")
    by_slug = {record["slug"]: record for record in creatures}
    ability_count = 0
    shared_reference_count = 0
    sense_reference_count = 0
    item_editor_count = 0
    immunity_editor_count = 0
    ritual_editor_count = 0
    trigger_action_counts: dict[str, int] = {}
    for creature in creatures:
        data = creature.get("data", {})
        senses = str(data.get("senses") or "")
        if re.search(r"(?:^|;\s*)(?:Recall Knowledge|Languages)\b", senses, re.I):
            raise SystemExit(f"creature metadata remains embedded in senses: {creature['slug']}")
        if link_shared_senses(senses) != senses:
            raise SystemExit(f"creature shared sense is not linked: {creature['slug']}")
        sense_reference_count += sum(
            int(route in senses) for _, route in SENSE_ROUTES
        )
        if senses:
            expected_senses = parse_sense_entries(senses)
            if data.get("senseEntries") != expected_senses:
                raise SystemExit(f"creature sense editor is out of sync: {creature['slug']}")
            if render_sense_entries(expected_senses) != senses:
                raise SystemExit(f"creature sense editor changes rendered text: {creature['slug']}")
        items = str(data.get("items") or "")
        if items:
            item_editor_count += 1
            expected_items = parse_item_entries(items)
            if data.get("itemEntries") != expected_items:
                raise SystemExit(f"creature item editor is out of sync: {creature['slug']}")
            if render_item_entries(expected_items) != items:
                raise SystemExit(f"creature item editor changes rendered text: {creature['slug']}")
        immunities = data.get("immunities") or []
        if immunities:
            immunity_editor_count += 1
            expected_immunities = [parse_reference_entry(str(value)) for value in immunities]
            if data.get("immunityEditor", {}).get("entries") != expected_immunities:
                raise SystemExit(f"creature immunity editor is out of sync: {creature['slug']}")
            if [render_reference_entry(entry) for entry in expected_immunities] != immunities:
                raise SystemExit(f"creature immunity editor changes rendered text: {creature['slug']}")
        rituals = data.get("rituals")
        if isinstance(rituals, dict) and any(rituals.values()):
            ritual_editor_count += 1
            if data.get("ritualcasting") != [rituals]:
                raise SystemExit(f"creature ritual editor is out of sync: {creature['slug']}")
        skills = data.get("skills")
        lore_skills = data.get("loreSkills")
        if isinstance(skills, dict) or isinstance(lore_skills, list):
            expected_skills_editor = {
                "skills": skills if isinstance(skills, dict) else {},
                "loreSkills": lore_skills if isinstance(lore_skills, list) else [],
            }
            if data.get("skillsEditor") != expected_skills_editor:
                raise SystemExit(f"creature Skills editor is out of sync: {creature['slug']}")
        for source, target in (
            ("weaknesses", "weaknessEntries"),
            ("resistances", "resistanceEntries"),
        ):
            defenses = data.get(source)
            if isinstance(defenses, dict) and defenses:
                expected_defenses = parse_defense_entries(defenses)
                if data.get(target) != expected_defenses:
                    raise SystemExit(f"creature defense editor is out of sync: {creature['slug']}: {source}")
                if render_defense_entries(expected_defenses) != defenses:
                    raise SystemExit(f"creature defense editor changes data: {creature['slug']}: {source}")
        for entries in creature.get("data", {}).get("abilities", {}).values():
            for ability in entries or []:
                ability_count += 1
                text = str(ability.get("text") or "")
                expected_editor_fields = parse_ability_editor_fields(text)
                actual_editor_fields = {
                    key: ability[key]
                    for key in expected_editor_fields
                    if key in ability
                }
                if actual_editor_fields != expected_editor_fields:
                    raise SystemExit(
                        f"creature ability editor is out of sync: {creature['slug']}: {ability.get('name')}"
                    )
                if content_tokens(render_ability_editor_fields(expected_editor_fields)) != content_tokens(text):
                    raise SystemExit(
                        f"creature ability editor changes visible content: {creature['slug']}: {ability.get('name')}"
                    )
                if expected_editor_fields.get("trigger"):
                    action = str(ability.get("actions") or "none")
                    trigger_action_counts[action] = trigger_action_counts.get(action, 0) + 1
                shared_reference_count += int(bool(ability.get("reference")))
                name = str(ability.get("name") or "")
                if SEPARATOR.search(text):
                    raise SystemExit(f"creature ability retains artificial divider: {creature['slug']}: {name}")
                if normalize(text) in glossary_keys:
                    raise SystemExit(f"creature ability retains a glossary token: {creature['slug']}: {name}")
                tail = text.split("\n\n")[-1]
                if normalize(tail) in {normalize(name), normalize("Effect " + name)}:
                    raise SystemExit(f"creature ability retains a duplicate reference label: {creature['slug']}: {name}")
                for code in GLOSSARY_ROUTES:
                    if GLOSSARY[code] and GLOSSARY[code] in text:
                        raise SystemExit(
                            f"creature repeats linked shared rule {code}: {creature['slug']}: {name}"
                        )
                if re.search(r"\n\n\u2003\*\*(?:Critical Success|Success|Failure|Critical Failure)\*\*", text):
                    raise SystemExit(
                        f"creature outcome starts a detached paragraph: {creature['slug']}: {name}"
                    )
        for attack in creature.get("data", {}).get("attacks", []):
            shared_reference_count += sum(
                int(bool(effect.get("reference")))
                for effect in attack.get("effects", [])
                if isinstance(effect, dict)
            )

    if shared_reference_count < 1500:
        raise SystemExit("creature shared-rule references are unexpectedly incomplete")
    if not trigger_action_counts.get("reaction") or not trigger_action_counts.get("free"):
        raise SystemExit("Trigger was incorrectly treated as reaction-only")

    moon_hag = by_slug["moon-hag-monster-core-2"]
    if moon_hag["data"].get("senses") != "[Darkvision](/action/darkvision-monster-core)":
        raise SystemExit("Moon Hag senses are not separated and linked")
    abilities = {
        ability["name"]: ability
        for entries in moon_hag["data"]["abilities"].values()
        for ability in entries
    }
    required_phrases = {
        "Coven": "[Spirit Blast](/spell/spirit-blast-player-core) to their coven's spells.",
        "Rend": "Claw",
        "Change Shape": "The moon hag can take on the appearance",
        "Dreadful Prediction": "once per round; **Effect** The moon hag",
        "Moonlight's Kiss": "[Quickened](/condition/quickened-player-core)",
        "Ride the Moonbeams": "[fly Speed](/rule/fly-speed-rules-2350)",
    }
    for name, phrase in required_phrases.items():
        if phrase not in str(abilities.get(name, {}).get("text") or ""):
            raise SystemExit(f"Moon Hag ability is incomplete: {name}")

    required_references = {
        "Coven": "/action/coven-monster-core",
        "Ferocity": "/action/ferocity-monster-core",
        "Rend": "/action/rend-monster-core",
        "Change Shape": "/action/change-shape-monster-core",
    }
    for name, reference in required_references.items():
        if abilities.get(name, {}).get("reference") != reference:
            raise SystemExit(f"Moon Hag shared ability name is not linked: {name}")

    if "At-Will Spells" in abilities:
        raise SystemExit("Moon Hag repeats at-will casting as a separate ability")
    if "form a coven" in abilities["Coven"]["text"] or "A Rend entry lists" in abilities["Rend"]["text"]:
        raise SystemExit("Moon Hag repeats a linked shared ability")
    if "\n\n**Effect**" in abilities["Dreadful Prediction"]["text"]:
        raise SystemExit("Moon Hag separates Effect from its ability metadata")
    for expected in (
        "[Stride](/action/stride-player-core)",
        "[Strike](/action/strike-player-core)",
        "[Fly](/action/fly-player-core)",
    ):
        if expected not in abilities["Moonlight's Kiss"]["text"]:
            raise SystemExit(f"Moon Hag is missing AoN-style inline reference: {expected}")

    murajau = by_slug["murajau-rage-of-elements"]
    murajau_data = murajau["data"]
    expected_items = "[Spear](/item/spear-player-core) (3), [Mesmerizing Opal](/item/mesmerizing-opal-gm-core), [Potency Crystal](/item/potency-crystal-gm-core), [Shark Tooth Charm](/item/shark-tooth-charm-gm-core)"
    if murajau_data.get("items") != expected_items:
        raise SystemExit("Murajau item links or quantities are incomplete")
    if murajau_data["attacks"][2].get("type") != "ranged":
        raise SystemExit("Murajau thrown spear is not a ranged Strike")
    if any(ability.get("name") == "Retract" for ability in murajau_data["abilities"]["defensive"]):
        raise SystemExit("Murajau Retract is still classified as defensive")
    if not any(ability.get("name") == "Retract" for ability in murajau_data["abilities"]["offensive"]):
        raise SystemExit("Murajau Retract is missing from its active abilities")
    if murajau_data.get("recallKnowledge", {}).get("subjects") != ["humanoid"]:
        raise SystemExit("Murajau is missing its Humanoid Recall Knowledge subject")
    retract = next(
        ability
        for ability in murajau_data["abilities"]["offensive"]
        if ability.get("name") == "Retract"
    )
    for expected in ("[auditory](/trait/auditory)", "[move](/trait/move) actions"):
        if expected not in str(retract.get("text") or ""):
            raise SystemExit(f"Murajau Retract is missing its inline rule link: {expected}")

    lithic = by_slug["lithic-locus-rage-of-elements"]
    lithic_spells = {
        spell["name"]
        for casting in lithic["data"].get("spellcasting", [])
        for group in casting.get("spellGroups", [])
        for spell in group.get("spells", [])
    }
    if lithic_spells != {"One with Stone", "Daze"}:
        raise SystemExit("Lithic Locus repeats Echo the Past spells in innate spellcasting")
    if any(
        ability.get("name", "").startswith("Tremorsense")
        for ability in lithic["data"]["abilities"]["interaction"]
    ):
        raise SystemExit("Lithic Locus repeats Tremorsense as an interaction ability")
    lithic_recall = lithic["data"].get("recallKnowledge") or {}
    if lithic_recall.get("entries") != recall_entries(["construct", "elemental", "spirit"]):
        raise SystemExit("Lithic Locus does not pair each Recall Knowledge subject with its skills")
    lithic_bury = next(
        ability
        for ability in lithic["data"]["abilities"]["offensive"]
        if ability.get("name") == "Bury"
    )
    if "[Escape](/action/escape-player-core) DC 34" not in str(lithic_bury.get("text") or ""):
        raise SystemExit("Lithic Locus Bury is missing its Escape DC")

    solar = by_slug["solar-crow-rage-of-elements"]
    solar_abilities = {
        ability["name"]: ability
        for entries in solar["data"]["abilities"].values()
        for ability in entries
    }
    if "[concealment](/condition/concealed-player-core)" not in solar_abilities["Glinting Wing"]["text"]:
        raise SystemExit("Solar Crow Glinting Wing is missing its concealment link")
    if solar["data"].get("recallKnowledge") != {
        "dc": 27,
        "entries": recall_entries(["elemental"]),
        "subjects": ["elemental"],
        "skills": ["arcana", "nature"],
    }:
        raise SystemExit("Solar Crow has the wrong elemental Recall Knowledge skills")
    if [attack.get("traits") for attack in solar["data"].get("attacks", [])] != [
        ["finesse"],
        ["agile", "finesse"],
    ]:
        raise SystemExit("Solar Crow natural Strikes retain the incorrect unarmed trait")
    solar_outcomes = str(solar_abilities["Blinding Heat"].get("text") or "")
    for label in ("Critical Success", "Success", "Failure", "Critical Failure"):
        if f"\u2003**{label}**" not in solar_outcomes:
            raise SystemExit(f"Solar Crow outcome is not grouped under Blinding Heat: {label}")

    vault = by_slug["vault-builder-rage-of-elements"]
    vault_data = vault["data"]
    vault_abilities = {
        ability["name"]: ability
        for entries in vault_data["abilities"].values()
        for ability in entries
    }
    if vault_data.get("movement", {}).get("burrow") != 25:
        raise SystemExit("Vault Builder has the wrong burrow Speed")
    if vault_data.get("recallKnowledge") != {
        "dc": 51,
        "entries": recall_entries(["elemental"]),
        "subjects": ["elemental"],
        "skills": ["arcana", "nature"],
    }:
        raise SystemExit("Vault Builder has the wrong elemental Recall Knowledge skills")
    if vault_data.get("languagesDetails") != "[Telepathy](/action/telepathy-monster-core) 300 feet":
        raise SystemExit("Vault Builder telepathy is not linked to its internal rule")
    expected_resistance = "20 (except [Adamantine](/item/adamantine-weapon-gm-core))"
    if vault_data.get("resistances", {}).get("physical") != expected_resistance:
        raise SystemExit("Vault Builder physical resistance lacks its adamantine exception link")
    if vault_abilities.get("Reactive Strike", {}).get("reference") != "/action/reactive-strike-monster-core":
        raise SystemExit("Vault Builder does not use the remastered Reactive Strike reference")
    craft_text = str(vault_abilities.get("Craft Crystal Wand", {}).get("text") or "")
    for expected in (
        "[earth](/trait/earth)",
        "[greater striking](/item/striking-greater-gm-core)",
    ):
        if expected not in craft_text:
            raise SystemExit(f"Vault Builder Craft Crystal Wand is missing: {expected}")
    shard = next(attack for attack in vault_data["attacks"] if attack["name"] == "Crystal Shard")
    if shard.get("traits") != ["earth", "finesse", "magical", "range-increment-100"]:
        raise SystemExit("Vault Builder crystal shard is missing finesse or its range increment")
    prepared = vault_data["spellcasting"][0]["spellGroups"]
    prepared_spells = {
        (spell["name"], spell.get("details"))
        for group in prepared
        for spell in group["spells"]
    }
    for repeated in (("Disintegrate", "×2"), ("Earthquake", "×2"), ("Haste", "×2")):
        if repeated not in prepared_spells:
            raise SystemExit(f"Vault Builder prepared spell is not compacted: {repeated[0]}")
    if "+1 Status to All Saves vs. Magic" in vault_abilities or "+4 Status to All Saves vs. Earth" in vault_abilities:
        raise SystemExit("Vault Builder repeats save details as empty abilities")

    executor = by_slug["adult-executor-dragon-draconic-codex-creature-creature-4139"]
    executor_abilities = {
        ability["name"]: ability
        for entries in executor["data"]["abilities"].values()
        for ability in entries
    }
    aura = executor_abilities.get("Aura of Authority", {})
    if "temporarily immune" not in aura.get("text", "") or aura.get("traits") != ["aura", "emotion", "mental"]:
        raise SystemExit("Adult Executor Dragon Aura of Authority is incomplete")
    expected_executor_traits = {
        "Rage of the Divine": ["divine", "sanctified", "spirit"],
        "Change Shape": ["concentrate", "divine", "polymorph"],
        "Divine Utterance": ["divine", "sonic"],
    }
    for name, traits in expected_executor_traits.items():
        ability = executor_abilities.get(name, {})
        if ability.get("traits") != traits or re.match(
            r"\*\*(?:Reaction|Single Action|Two Actions)\*\*",
            ability.get("text", ""),
            re.I,
        ):
            raise SystemExit(f"Adult Executor Dragon action metadata is not structured: {name}")
    executor_data = executor["data"]
    sanctification = str(executor_abilities["Divine Sanctification"].get("text") or "")
    if "[holy](/trait/holy)" not in sanctification or "[unholy](/trait/unholy)" not in sanctification:
        raise SystemExit("Adult Executor Dragon sanctification choices are not linked")
    if executor_data.get("saves", {}).get("details") != "+2 status to all saves vs. [divine](/trait/divine)":
        raise SystemExit("Adult Executor Dragon is missing its divine save bonus")
    if executor_data.get("weaknesses", {}).get("divine-sanctification") != 10:
        raise SystemExit("Adult Executor Dragon is missing its opposing sanctification weakness")
    if executor_data.get("recallKnowledge", {}).get("subjects") != ["dragon"]:
        raise SystemExit("Adult Executor Dragon is missing its Dragon Recall Knowledge subject")
    if by_slug["wyrmwraith-draconic-codex-creature-creature-4210"]["data"].get("recallKnowledge", {}).get("subjects") != ["dragon", "undead"]:
        raise SystemExit("Wyrmwraith is missing one of its Recall Knowledge subjects")
    executor_attacks = {attack["name"]: attack for attack in executor_data["attacks"]}
    if "reach-10" not in executor_attacks["jaws"]["traits"] or "reach-15" not in executor_attacks["tail"]["traits"]:
        raise SystemExit("Adult Executor Dragon reach values are incomplete")

    army_ants = by_slug["army-ant-swarm-monster-core"]
    if "[Scent](/action/scent-monster-core) ([imprecise](/rule/imprecise-senses-rules-2407)) 30 feet" not in army_ants["data"]["senses"]:
        raise SystemExit("Army Ant Swarm is missing its scent acuity")
    if not {"grabbed", "precision", "prone", "restrained", "swarm mind"}.issubset(
        linked_labels(army_ants["data"].get("immunities") or [])
    ):
        raise SystemExit("Army Ant Swarm is missing explicit or swarm immunities")

    bone_prophet = by_slug["bone-prophet-monster-core"]
    if "([imprecise](/rule/imprecise-senses-rules-2407)) 30 feet" not in bone_prophet["data"].get("senses", ""):
        raise SystemExit("Bone Prophet is missing its scent acuity")
    if bone_prophet["data"].get("languagesDetails") != "[Telepathy](/action/telepathy-monster-core) 100 feet":
        raise SystemExit("Bone Prophet is missing its language details")

    adamantine_dragon = by_slug["adamantine-dragon-young-monster-core"]
    dragon_data = adamantine_dragon["data"]
    dragon_senses = dragon_data.get("senses", "")
    if "[Scent](/action/scent-monster-core) ([imprecise](/rule/imprecise-senses-rules-2407)) 60 feet" not in dragon_senses or "[Tremorsense](/action/tremorsense-monster-core) ([imprecise](/rule/imprecise-senses-rules-2407)) 60 feet" not in dragon_senses:
        raise SystemExit("Adamantine Dragon is missing structured sense acuity")
    if any(
        ability.get("name", "").startswith("Tremorsense")
        for ability in dragon_data["abilities"]["interaction"]
    ):
        raise SystemExit("Adamantine Dragon repeats Tremorsense as an interaction ability")
    if dragon_data.get("resistances", {}).get("physical") != "10 (except [adamantine](/item/adamantine-weapon-gm-core))":
        raise SystemExit("Adamantine Dragon is missing its printed physical resistance")
    dragon_abilities = {
        ability["name"]: ability
        for entries in dragon_data["abilities"].values()
        for ability in entries
    }
    avalanche = str(dragon_abilities.get("Avalanche Breath", {}).get("text") or "")
    for phrase in ("8d8 bludgeoning", "30-foot [cone]", "DC 28 [basic Reflex save]", "1d4 rounds"):
        if phrase not in avalanche:
            raise SystemExit(f"Adamantine Dragon Avalanche Breath is incomplete: {phrase}")
    attacks = {attack["name"]: attack for attack in dragon_data["attacks"]}
    if attacks["Jaws"].get("effects") != [{"name": "Grab", "reference": "/action/grab-monster-core"}]:
        raise SystemExit("Adamantine Dragon Grab is not attached to its jaws Strike")
    if attacks["Claw"].get("effects") != [{"name": "Knockdown", "reference": "/action/knockdown-monster-core"}]:
        raise SystemExit("Adamantine Dragon Knockdown is not attached to its claw Strike")
    if "Grab" in dragon_abilities or "Knockdown" in dragon_abilities:
        raise SystemExit("Adamantine Dragon repeats its Strike effects as separate abilities")
    if dragon_data.get("loreSkills") != [{"name": "Mining Lore", "value": 16}]:
        raise SystemExit("Adamantine Dragon is missing its named Lore skill")

    animated_armor = by_slug["animated-armor-monster-core"]
    if animated_armor["data"].get("hardness") != 9:
        raise SystemExit("Animated Armor is missing Hardness")
    if not {"mental", "vitality", "void"}.issubset(linked_labels(animated_armor["data"].get("immunities") or [])):
        raise SystemExit("Animated Armor is missing construct immunities")

    zombie = by_slug["zombie-shambler-monster-core"]
    if "mental" not in linked_labels(zombie["data"].get("immunities", [])):
        raise SystemExit("Zombie Shambler is missing its mindless immunity")

    for creature in creatures:
        data = creature.get("data", {})
        traits = set(data.get("traits") or [])
        expected_subjects = list(dict.fromkeys(
            trait
            for trait in data.get("traits") or []
            if trait in CREATURE_IDENTIFICATION_SKILLS
        ))
        recall = data.get("recallKnowledge") or {}
        if "subject" in recall:
            raise SystemExit(f"creature retains the obsolete singular subject: {creature['slug']}")
        if expected_subjects and recall.get("subjects") != expected_subjects:
            raise SystemExit(f"creature is missing Recall Knowledge subjects: {creature['slug']}")
        expected_skills = {
            skill
            for subject in expected_subjects
            for skill in CREATURE_IDENTIFICATION_SKILLS[subject]
        }
        if expected_skills.difference(recall.get("skills") or []):
            raise SystemExit(f"creature is missing Recall Knowledge skills: {creature['slug']}")
        if expected_subjects and recall.get("entries") != recall_entries(expected_subjects):
            raise SystemExit(f"creature does not pair Recall subjects and skills: {creature['slug']}")
        for attack in data.get("attacks") or []:
            attack_traits = [str(trait) for trait in attack.get("traits") or []]
            if "unarmed" in attack_traits:
                raise SystemExit(f"creature exposes an actor-only unarmed trait: {creature['slug']}")
            if any(
                trait.startswith(("thrown-", "range-increment-"))
                for trait in attack_traits
            ) and attack.get("type") != "ranged":
                raise SystemExit(f"creature has a ranged Strike rendered as melee: {creature['slug']}")
        for entries in data.get("abilities", {}).values():
            for ability in entries or []:
                if (
                    not str(ability.get("text") or "").strip()
                    and re.match(r"^[+-]\d+\s+", str(ability.get("name") or ""))
                ):
                    raise SystemExit(f"creature exposes an empty rule element: {creature['slug']}")
        immunities = linked_labels(data.get("immunities") or [])
        immunity_values = data.get("immunities") or []
        if immunity_values != sorted(immunity_values, key=visible_label):
            raise SystemExit(f"creature immunities are not alphabetical: {creature['slug']}")
        if "mindless" in traits and "mental" not in immunities:
            raise SystemExit(f"mindless creature is missing Mental immunity: {creature['slug']}")
        if "swarm" in traits and not {"grabbed", "prone", "restrained"}.issubset(immunities):
            raise SystemExit(f"swarm creature is missing condition immunities: {creature['slug']}")

    bibliodaemon = by_slug["bibliodaemon-shining-kingdoms"]
    thoughtsense = next(
        ability
        for entries in bibliodaemon["data"]["abilities"].values()
        for ability in entries
        if ability["name"] == "Thoughtsense"
    )
    if "Thoughtsense allows" in thoughtsense["text"]:
        raise SystemExit("creature-specific Thoughtsense repeats its glossary definition")

    actions = {record["slug"]: record for record in records("actions.json")}
    for slug in ("at-will-spells-monster-core", "ferocity-monster-core", "rend-monster-core"):
        description = str(actions.get(slug, {}).get("descr") or "")
        if not description or normalize(description) in glossary_keys:
            raise SystemExit(f"shared monster action is incomplete: {slug}")

    action_slugs = {record["slug"] for record in actions.values()}
    for route in GLOSSARY_ROUTES.values():
        if route.rsplit("/", 1)[-1] not in action_slugs:
            raise SystemExit(f"shared monster ability link is missing: {route}")

    ability_form = form("partials/ability.json")
    if field_attributes(ability_form) != {
        "name", "actions", "traits", "description", "trigger", "effect", "reference"
    }:
        raise SystemExit("ability form does not expose every rendered ability field")

    ability_view = (REPO / "views/partials/ability.md").read_text(encoding="utf-8")
    attack_view = (REPO / "views/partials/attack.md").read_text(encoding="utf-8")
    creature_view = (REPO / "views/partials/creature-primary.md").read_text(encoding="utf-8")
    # The native reference picker includes a source suffix, e.g.
    # /item/chest-player-core/player core. A bare Markdown destination treats
    # its space as a separator and displays the entire link as literal text.
    # Angle destinations preserve both the path and source in the link.
    reference_templates = {
        "creature-primary.md": {"item.reference", "sense.reference", "sense.acuityReference"},
        "creature-secondary.md": {"immunity.reference"},
        "creature-tertiary.md": {"ritual.reference"},
        "ability.md": {"ability.reference"},
        "item-activation.md": {"activation.reference"},
        "attack.md": {"effect.reference"},
        "spellcasting.md": {"spell.reference"},
    }
    for filename, expected_references in reference_templates.items():
        template = (REPO / "views/partials" / filename).read_text(encoding="utf-8")
        destinations = re.findall(r"\]\((<?)\{\{([^}]+)\}\}(>?)\)", template)
        safe_references = set()
        for opening, attribute, closing in destinations:
            if attribute in expected_references:
                if opening != "<" or closing != ">":
                    raise SystemExit(f"editor reference breaks with a spaced source: {filename}: {attribute}")
                safe_references.add(attribute)
        if safe_references != expected_references:
            raise SystemExit(f"editor reference destinations are missing: {filename}")
    if "ability.reference" not in ability_view:
        raise SystemExit("shared creature ability names are not linked")
    if "ability.effect" not in ability_view:
        raise SystemExit("creature abilities do not render the optional Effect field")
    if "ability.trigger" not in ability_view:
        raise SystemExit("creature abilities do not render the optional Trigger field")
    activation_view = (REPO / "views/partials/item-activation.md").read_text(encoding="utf-8")
    for attribute in field_attributes(ability_form) | {"text"}:
        if f"activation.{attribute}" not in activation_view:
            raise SystemExit(f"named item activations do not render their editable/legacy {attribute}")
    structured_condition = "{% if activation.description or activation.trigger or activation.effect %}"
    if structured_condition not in activation_view or "{% else %}{% if activation.text %}" not in activation_view:
        raise SystemExit("named activations must prefer structured rules with a legacy-text fallback")
    for flag in ("triggerBeforeDescription", "triggerParagraphBreak"):
        if f"activation.{flag}" not in activation_view:
            raise SystemExit(f"named activations lose the shared ability's {flag} ordering")
    item_html = (REPO / "views/item.html").read_text(encoding="utf-8")
    native_item_view = json5.loads((REPO / "views/item.json").read_text(encoding="utf-8"))
    for template in (item_html, json.dumps(native_item_view)):
        if "for activation in data.activations" not in template or "item-activation.md" not in template:
            raise SystemExit("both item display modes must use the named-activation renderer in its row context")
        if "{{data.craftRequirements}}" not in template or "Item.CraftRequirements" not in template:
            raise SystemExit("both item display modes must render editable crafting requirements")
        if "for type in data.types" not in template or "item-type.md" not in template:
            raise SystemExit("both item display modes must render editable variants")
    variant_view = (REPO / "views/partials/item-type.md").read_text(encoding="utf-8")
    for attribute in field_attributes(form("partials/item-type.json")):
        if not re.search(r"{{\s*" + re.escape(attribute) + r"(?:\s*\||\s*}})", variant_view):
            raise SystemExit(f"item variants do not render their editable {attribute}")
    if "{% if level != nil %}" not in variant_view:
        raise SystemExit("item variants must display level zero")
    if '/icons/actions/{{activation.actions}}.png' not in activation_view:
        raise SystemExit("named activation action icons use an invalid route")
    if re.search(r"{%\s*elsif\b", ability_view):
        raise SystemExit("creature ability view uses unsupported elsif syntax")
    if (
        "/trait/{{trait}}" not in ability_view
        or (
            "/trait/{{trait}}" not in attack_view
            and "/trait/{% if trait" not in attack_view
        )
    ):
        raise SystemExit("creature ability or attack traits are not linked")
    if (
        "/action/recall-knowledge-player-core" not in creature_view
        or "data.recallKnowledge.dc" not in creature_view
        or "data.recallKnowledge.entries" not in creature_view
        or "data.languages" not in creature_view
        or "/rule/languages-rules-2080" not in creature_view
        or "/rule/skills-rules-2276" not in creature_view
        or "/rule/{{key}}-skill-player-core" not in creature_view
        or "/rule/lore-skill-player-core" not in creature_view
        or "/language/{{language}}" not in creature_view
    ):
        raise SystemExit("creature identity fields are not separated in the stat block")
    if "/trait/{{data.recallKnowledge.subject" in creature_view:
        raise SystemExit("Recall Knowledge subjects duplicate the linked creature tags")
    if (
        "data.skills or data.loreSkills" not in creature_view
        or "[{{skill.name}}](/rule/lore-skill-player-core)" not in creature_view
        or "[**Lore**](/rule/lore-skill-player-core)" in creature_view
    ):
        raise SystemExit("named Lore skills are not integrated into the Skills field")

    secondary_view = (REPO / "views/partials/creature-secondary.md").read_text(encoding="utf-8")
    if "/rule/immunity-rules-2313" not in secondary_view or "/rule/resistance-rules-2318" not in secondary_view:
        raise SystemExit("creature defenses are missing quick-rule links")
    if (
        "[{{immunity|lowercase}}](/rule/immunity-rules-2313)" in secondary_view
        or "[{{ key|map: 'Damage'|lowercase }}](/rule/resistance-rules-2318)" in secondary_view
    ):
        raise SystemExit("individual creature defenses still point to a generic category rule")
    if " contains " in attack_view:
        raise SystemExit("creature attack view uses an unsupported template expression")
    for route_fragment in (
        "range-and-reach-rules-2379",
        "trait == 'reach-10'",
        "trait == 'reach-15'",
    ):
        if route_fragment not in attack_view:
            raise SystemExit(f"creature attack view is missing parameterized routing: {route_fragment}")

    trait_slugs = {record["slug"] for record in records("traits.json")}
    attack_trait_routes: dict[str, str] = {}
    for expression, destination in re.findall(
        r"\{% if ([^%]+) %\}([a-z][a-z0-9-]*)\{% else %\}",
        attack_view,
    ):
        for slug in re.findall(r"trait == '([^']+)'", expression):
            attack_trait_routes[slug] = destination
    for creature in creatures:
        for attack in creature.get("data", {}).get("attacks", []):
            for trait in attack.get("traits", []):
                slug = str(trait).strip().casefold().replace("_", "-").replace(" ", "-")
                family = parameterized_trait_family(slug)
                if family and slug != family and (
                    attack_trait_routes.get(slug) != family
                    or family not in trait_slugs
                ):
                    raise SystemExit(
                        f"parameterized attack trait has no canonical destination: "
                        f"{creature['slug']}: {slug}"
                    )

    skill_rules = {
        rule["slug"]: rule
        for rule in records("rules.json")
        if rule.get("slug", "").endswith("-skill-player-core")
    }
    if len(skill_rules) != 17:
        raise SystemExit("individual Player Core skill quick references are incomplete")
    for slug, rule in skill_rules.items():
        description = str(rule.get("descr") or "")
        if (
            len(description) < 200
            or "Complete " in description
            or re.search(r"\]\(https?://", description)
            or rule.get("attributes", {}).get("contentOrigin") != "Player Core (ORC)"
            or rule.get("data", {}).get("referenceUrl")
        ):
            raise SystemExit(f"skill reference is not imported Player Core content: {slug}")

    items = {record["slug"]: record for record in records("items.json")}
    adamantine_weapon = items.get("adamantine-weapon-gm-core", {})
    if (
        adamantine_weapon.get("name") != "Adamantine Weapon"
        or adamantine_weapon.get("data", {}).get("subcategory") != "preciousMaterialWeapon"
        or adamantine_weapon.get("attributes", {}).get("contentOrigin") != "GM Core (ORC)"
        or re.search(r"\]\(https?://", str(adamantine_weapon.get("descr") or ""))
    ):
        raise SystemExit("Adamantine Weapon is not an imported internal GM Core reference")

    creature_form = form("creature.json")
    creature_tabs = creature_form.get("tabs", [])
    if len(creature_tabs) != 4 or creature_form.get("sections"):
        raise SystemExit("creature editor must use four task-based tabs")
    if any(tab.get("attribute") or tab.get("visibleIf") for tab in creature_tabs):
        raise SystemExit("creature tabs must retain entity context and be accessible when empty")
    creature_sections = [section for tab in creature_tabs for section in tab.get("sections", [])]
    invalid_top_level_types = {
        index: section.get("type")
        for index, section in enumerate(creature_sections)
        if section.get("type") not in {"group", "list"}
    }
    if invalid_top_level_types:
        raise SystemExit(f"creature editor has invalid top-level sections: {invalid_top_level_types}")
    creature_fields = field_attributes({"sections": creature_sections})
    if not {
        "data.hardness",
        "data.languagesDetails",
        "data.saves.details",
    }.issubset(creature_fields):
        raise SystemExit("creature editor does not expose restored metadata")
    editor_fields = {
        str(node["attribute"]): node
        for node in form_nodes(creature_form)
        if node.get("attribute")
    }
    required_creature_attributes = {
        "data.level", "data.rarity", "data.size", "data.traits", "data.perception",
        "data.languages", "data.languagesDetails", "data.senseEntries", "data.itemEntries",
        *(f"data.attributes.{key}" for key in ("str", "dex", "con", "int", "wis", "cha")),
        "data.ac.value", "data.ac.details", "data.hp.value", "data.hp.details", "data.hardness",
        *(f"data.saves.{key}" for key in ("fortitude", "reflex", "will", "details")),
        "data.weaknessEntries", "data.resistanceEntries", "data.attacks", "data.spellcasting",
        "data.ritualcasting", *(f"data.abilities.{key}" for key in ("interaction", "defensive", "offensive")),
    }
    if set(editor_fields) != required_creature_attributes:
        raise SystemExit("creature navigation changed the inline editable storage paths")
    # Ordinary values stay directly editable; the proven object/list editors
    # retain their own navigation rather than acquiring another subform scope.
    direct_nodes = [node for section in creature_sections for node in section.get("fields", [])]
    direct_attributes = set()
    while direct_nodes:
        node = direct_nodes.pop()
        if node.get("attribute"):
            direct_attributes.add(node["attribute"])
        direct_nodes.extend(node.get("fields", []))
    for attribute in ("data.ac.value", "data.hp.value", "data.perception", "data.hardness",
                      "data.languages", "data.saves.fortitude", "data.saves.reflex", "data.saves.will"):
        if attribute not in direct_attributes:
            raise SystemExit(f"creature navigation hides a frequent statistic in another editor: {attribute}")
    for attribute in ("data.ac.details", "data.hp.details", "data.saves.details", "data.languagesDetails"):
        if not editor_fields[attribute].get("title"):
            raise SystemExit(f"creature editor notes need an explicit label: {attribute}")
    required_structured_lists = {
        "data.senseEntries": "sense",
        "data.itemEntries": "creature-item",
        "data.ritualcasting": "rituals",
    }
    for attribute, partial in required_structured_lists.items():
        section = editor_fields.get(attribute, {})
        if section.get("type") != "list" or section.get("form", {}).get("partial") != partial:
            raise SystemExit(f"creature editor lacks its structured list: {attribute}")
    item_section = editor_fields["data.itemEntries"]
    if item_section.get("attributeType") != "Item":
        raise SystemExit("creature item editor does not use the searchable Item picker")
    recall_section = next(
        node for node in form_nodes(creature_form)
        if node.get("form", {}).get("partial") == "recall-knowledge"
    )
    if recall_section.get("type") != "form" or recall_section.get("form", {}).get("partial") != "recall-knowledge":
        raise SystemExit("Recall Knowledge does not expose its complete nested editor")
    skills_section = next(
        field for section in creature_sections
        for field in section.get("fields", [])
        if field.get("form", {}).get("partial") == "creature-skills"
    )
    if skills_section.get("type") != "form" or skills_section.get("form", {}).get("partial") != "creature-skills":
        raise SystemExit("named Lore is not integrated into the Skills editor")
    if skills_section.get("attribute"):
        raise SystemExit("Skills must retain the entity context for its nested list bindings")
    if "data.loreSkills" in editor_fields or "data.skills" in editor_fields:
        raise SystemExit("creature editor still exposes legacy separate skill menus")
    immunity_section = next(
        field
        for section in creature_sections
        for field in section.get("fields", [])
        if field.get("form", {}).get("partial") == "immunities"
    )
    if (
        immunity_section.get("type") != "form"
        or immunity_section.get("attribute")
        or immunity_section.get("form", {}).get("partial") != "immunities"
        or "Common.None" not in immunity_section.get("text", "")
    ):
        raise SystemExit("empty immunities do not use a clear None editor state")
    type_definitions = json5.loads(
        (REPO / "types.json").read_text(encoding="utf-8"),
        allow_duplicate_keys=False,
    )
    if "lore" in type_definitions.get("CreatureSkill", {}):
        raise SystemExit("named Lore still appears in the generic creature skill picker")
    sense_form = form("partials/sense.json")
    if field_attributes(sense_form) != {
        "name", "reference", "acuity", "acuityReference", "details", "customText"
    }:
        raise SystemExit("special-sense editor does not expose references and custom text")
    # Fixed acuities must resolve from the live choice, ahead of any saved legacy link.
    for acuity in type_definitions["SenseAcuity"]:
        route = next(route for pattern, route in SENSE_ROUTES if pattern.fullmatch(acuity))
        branch = re.search(r"\{% (?:if|elif) sense\.acuity == '" + acuity + r"' %\}(.*?)(?=\{% (?:elif|else|endif))", creature_view)
        if not branch or f"]({route})" not in branch.group(1):
            raise SystemExit(f"sense acuity {acuity} does not link its selected rule automatically")
    if creature_view.index("sense.acuity == 'vague'") > creature_view.index("elif sense.acuityReference"):
        raise SystemExit("legacy acuity references override the live choice")
    custom_acuity = next(section for section in sense_form["sections"]
                        if any(field.get("attribute") == "acuityReference" for field in section.get("fields", [])))
    if custom_acuity.get("visibleIf") != "{% if acuity and acuity != 'precise' and acuity != 'imprecise' and acuity != 'vague' %}true{% endif %}":
        raise SystemExit("manual acuity reference must appear only for a nonempty custom acuity")
    for path in (REPO / "forms").rglob("*.json"):
        for node in form_nodes(json5.loads(path.read_text())):
            if any(field.get("type") == "reference" for field in node.get("fields", [])):
                if node.get("title") not in {"Reference", "Custom Acuity Reference"}:
                    raise SystemExit(f"reference picker lacks a visible section label: {path}")
    item_form = form("partials/creature-item.json")
    if field_attributes(item_form) != {"name", "quantity", "reference"}:
        raise SystemExit("creature item editor must expose only name, quantity, and reference")
    immunity_form = form("partials/immunity.json")
    if field_attributes(immunity_form) != {"name", "reference", "customText"}:
        raise SystemExit("immunity editor must omit the unnecessary Details field")
    immunity_choice = immunity_form["sections"][0]["fields"][0]
    if (immunity_choice.get("type"), immunity_choice.get("attribute"), immunity_choice.get("attributeType")) != ("picker", "name", "ImmunityChoice"):
        raise SystemExit("immunity choices must keep the existing editable name path")
    immunity_reference = next(section for section in immunity_form["sections"]
                              if any(field.get("type") == "reference" for field in section.get("fields", [])))
    if immunity_reference.get("visibleIf") != "{% if customText %}true{% endif %}":
        raise SystemExit("manual immunity reference must accompany custom text only")
    choices = type_definitions["ImmunityChoice"]
    routes = type_definitions["ImmunityReference"]
    if {name.lower() for name in choices} != set(routes):
        raise SystemExit("every built-in immunity needs an automatic route")
    published_routes = {f"/{route_kind}/{row['slug']}"
                        for collection, route_kind in (("rules.json", "rule"), ("conditions.json", "condition"), ("traits.json", "trait"))
                        for row in records(collection)}
    if set(routes.values()) - published_routes:
        raise SystemExit(f"immunity choices point to unpublished rules: {set(routes.values()) - published_routes}")
    for label, route in {"Poison": "/trait/poison", "Paralyzed": "/condition/paralyzed-player-core",
                         "Critical Hits": "/rule/immunity-to-critical-hits-rules-2314"}.items():
        if routes.get(label.lower()) != route:
            raise SystemExit(f"wrong automatic immunity route for {label}")
    immunity_view = (REPO / "views/partials/creature-secondary.md").read_text()
    if "immunityName|valueMap: 'ImmunityReference'" not in immunity_view or "[{{immunity.customText|lowercase}}](<{{immunity.reference}}>)" not in immunity_view:
        raise SystemExit("immunity view lacks automatic choices or linked custom text")
    if immunity_view.index("if immunityRoute") > immunity_view.index("elif immunity.reference"):
        raise SystemExit("saved immunity reference overrides a newly selected built-in choice")
    skills_form = form("partials/creature-skills.json")
    invalid_skills_section_types = {
        index: section.get("type")
        for index, section in enumerate(skills_form.get("sections", []))
        if section.get("type") not in {"group", "list"}
    }
    if invalid_skills_section_types:
        raise SystemExit(
            f"Skills editor has invalid top-level sections: {invalid_skills_section_types}"
        )
    skills_fields = {
        str(field.get("attribute")): field
        for section in skills_form.get("sections", [])
        for field in ([section] if section.get("attribute") else []) + section.get("fields", [])
        if field.get("attribute")
    }
    if (
        skills_fields.get("data.skillsEditor.skills", {}).get("attributeType") != "CreatureSkill"
        or skills_fields.get("data.skillsEditor.loreSkills", {}).get("form", {}).get("partial") != "lore-skill"
    ):
        raise SystemExit("Skills editor does not include named Lore")
    immunity_list = form("partials/immunities.json").get("sections", [{}])[0]
    if (
        immunity_list.get("attribute") != "data.immunityEditor.entries"
        or immunity_list.get("form", {}).get("partial") != "immunity"
    ):
        raise SystemExit("Immunities must bind its list through the entity context")
    recall_editor = form("partials/recall-knowledge.json")
    recall_editor_fields = {
        str(section.get("attribute")): section
        for section in recall_editor.get("sections", [])
        if section.get("attribute")
    }
    if recall_editor_fields.get("data.recallKnowledge.entries", {}).get("form", {}).get("partial") != "recall-knowledge-entry":
        raise SystemExit("Recall Knowledge editor does not list knowledge-skill pairs")
    if field_attributes(recall_editor) != {"data.recallKnowledge.dc"}:
        raise SystemExit("Recall Knowledge DC does not bind through the entity context")
    if field_attributes(form("partials/movement.json")) != {
        f"data.movement.{key}" for key in ("walk", "burrow", "climb", "fly", "swim", "other")
    }:
        raise SystemExit("shared movement editor does not preserve its entity storage paths")
    item_editor = form("item.json")
    if re.search(r"{%\s*elsif\b", json.dumps(item_editor)):
        raise SystemExit("item category visibility uses unsupported elsif syntax")
    deity_native = (REPO / "views/deity.json").read_text()
    deity_html = (REPO / "views/deity.html").read_text()
    deity_stats = (REPO / "views/partials/deity-stats.md").read_text()
    if "deity-stats.md" not in deity_native:
        raise SystemExit("native deity preview does not render current editable fields")
    for field in ("areasOfConcern", "edicts", "anathema", "divineAttribute", "clericFont",
                  "sanctification", "sanctificationOptions", "divineSkill", "favoredWeapon",
                  "domains", "alternateDomains", "spells"):
        if f"data.{field}" not in deity_stats or f"data.{field}" not in deity_html:
            raise SystemExit(f"deity previews omit current {field}")
    for preview in (deity_html, deity_native):
        if "descr != data.rulesText" not in preview:
            raise SystemExit("deity previews lose custom descriptions or duplicate the import summary")
    for preview in (deity_html, deity_stats):
        if "reference.value == value" not in preview or "{% else %}{{value" not in preview:
            raise SystemExit("deity reference caches override edited values without a live fallback")
        for field in ("edictsText", "anathemaText"):
            if f"data.{field} != nil" not in preview or f"{{{{data.{field}" not in preview:
                raise SystemExit(f"deity preview loses the editable/cleared multiline {field}")
        if "data.deityDirectiveFormat == 'text'" not in preview:
            raise SystemExit("cleared deity text fields must not fall back to old array values")
    deity_fields = {node.get("attribute"): node for node in form_nodes(form("deity.json")) if node.get("attribute")}
    for field in ("edictsText", "anathemaText"):
        control = deity_fields.get(f"data.{field}", {})
        if control.get("type") != "textArea" or control.get("custom", {}).get("lines") != 2:
            raise SystemExit(f"deity {field} needs the requested two-line multiline editor")
    if deity_fields["data.divineAttribute"].get("attributeType") != "DeityAttribute" or "any" not in type_definitions["DeityAttribute"]:
        raise SystemExit("deity attribute choices must include Any")
    for field in ("divineAttributeNotes", "sanctificationText"):
        if deity_fields.get(f"data.{field}", {}).get("type") != "textArea":
            raise SystemExit(f"deity {field} is not editable")
        if f"data.{field}" not in deity_html or f"data.{field}" not in deity_stats:
            raise SystemExit(f"deity {field} is not displayed in both views")
    for preview in (deity_html, deity_stats):
        if "data.deitySanctificationFormat == 'text'" not in preview:
            raise SystemExit("cleared sanctification prose falls back to stale legacy values")
    skill_routes = type_definitions["SkillReference"]
    if set(skill_routes) != set(type_definitions["Skill"]):
        raise SystemExit("every divine skill needs its own rule route")
    published_rules = {"/rule/" + row["slug"] for row in records("rules.json")}
    for route in skill_routes.values():
        if route not in published_rules:
            raise SystemExit(f"divine skill link is missing from the package: {route}")
    if not any(row["slug"] == "raised-by-belief-player-core" for row in records("backgrounds.json")):
        raise SystemExit("Divine Attribute heading points to an unpublished background")
    for preview in (deity_html, deity_stats):
        if "valueMap: 'SkillReference'" not in preview:
            raise SystemExit("deity preview is missing live skill-value links")
        if "/background/raised-by-belief-player-core" not in preview:
            raise SystemExit("Divine Attribute must link to Raised by Belief")
        if "attributeRoute" in preview or "DeityAttributeReference" in preview or "/rule/skills-rules-2276" in preview:
            raise SystemExit("deity attribute values and Divine Skill heading must stay unlinked")
    for cell in re.findall(r"<td>(.*?)</td>", deity_html, re.S):
        if "for value in data." in cell:
            if cell.count("{% markdown -%}") != 1 or cell.count("{% endmarkdown %}") != 1 or "|md" in cell:
                raise SystemExit("deity table lists must render together, not as separate Markdown paragraphs")
    item_nodes = list(form_nodes(item_editor))
    item_controls = [node for node in item_nodes if node.get("attribute")]
    required_item_attributes = {
        "data.category", "data.level", "data.rarity", "data.traits", "data.subcategory",
        "data.price", "data.usage", "data.bulk", "data.ammunition", "data.onset",
        "data.craftRequirements", "data.ac", "data.dexCap", "data.checkPenalty",
        "data.speedPenalty", "data.str", "data.armorCategory", "data.armorGroup",
        "data.hardness", "data.hp", "data.bt", "data.damage", "data.range",
        "data.reload", "data.hands", "data.weaponType", "data.weaponCategory",
        "data.weaponGroup", "descr", "data.activation.actions", "data.activation.type",
        "data.activation.traits", "data.activation.text", "data.activations", "data.types",
    }
    if {node["attribute"] for node in item_controls} != required_item_attributes:
        raise SystemExit("item editor regrouping changed editable storage paths")
    item_by_attribute = {node["attribute"]: node for node in item_controls}
    for attribute, kind in {
        "data.speedPenalty": "decimal", "data.traits": "tags",
        "data.activation.actions": "picker", "data.activation.traits": "tags",
        "data.activation.text": "textArea", "data.craftRequirements": "textArea",
        "descr": "textArea",
    }.items():
        if item_by_attribute[attribute].get("type") != kind:
            raise SystemExit(f"item editor changed the input type for {attribute}")
    details = next(node for node in item_nodes if node.get("type") == "form"
                   and node.get("title") == "Item.AdditionalDetails")
    if details.get("attribute") or details.get("visibleIf"):
        raise SystemExit("optional item details must be accessible for every category, including empty items")
    if field_attributes(details["form"]) != {
        "data.ammunition", "data.onset", "data.craftRequirements"
    }:
        raise SystemExit("optional item details lost ammunition, onset, or crafting")
    for attribute in field_attributes(details["form"]):
        if "{{" + attribute + "}}" not in details["text"]:
            raise SystemExit(f"item details summary omits {attribute}")
    if "'Common.None'|l" not in details["text"]:
        raise SystemExit("empty item details need a localized summary")
    for attribute, partial in (("data.activations", "ability"), ("data.types", "item-type")):
        control = item_by_attribute[attribute]
        if control.get("type") != "list" or control.get("form", {}).get("partial") != partial:
            raise SystemExit(f"item editor changed the list entry schema for {attribute}")
    activation = next(
        node for node in item_nodes
        if node.get("type") == "form" and node.get("title") == "Item.PrimaryActivation"
    )
    if field_attributes(activation.get("form", {})) != {
        f"data.activation.{key}" for key in ("actions", "type", "traits", "text")
    }:
        raise SystemExit("item activation editor does not preserve its entity storage paths")
    for attribute in field_attributes(activation["form"]):
        if attribute not in activation["text"]:
            raise SystemExit(f"primary activation summary omits {attribute}")
    if "'Common.None'|l" not in activation["text"]:
        raise SystemExit("empty primary activation needs a localized summary")
    defense_form = form("partials/defense-entry.json")
    if field_attributes(defense_form) != {"type", "value"}:
        raise SystemExit("weakness and resistance entries must use Type and Value")
    ability_form = form("partials/ability.json")
    if field_attributes(ability_form) != {
        "name", "actions", "traits", "description", "trigger", "effect", "reference"
    }:
        raise SystemExit("creature ability editor does not expose Description, Trigger, and Effect")
    for attribute in ("data.weaknessEntries", "data.resistanceEntries"):
        field = editor_fields.get(attribute, {})
        if field.get("type") != "list" or field.get("form", {}).get("partial") != "defense-entry":
            raise SystemExit(f"creature editor lacks a typed defense list: {attribute}")
    save_details = editor_fields.get("data.saves.details", {})
    if save_details.get("title") != "Creature.SpecialSaveModifiers":
        raise SystemExit("saving throw details are not labeled Special Save Modifiers")
    recall_form = form("partials/recall-knowledge-entry.json")
    if field_attributes(recall_form) != {"subject", "skills"}:
        raise SystemExit("Recall Knowledge editor does not expose subject-skill pairs")
    migration = (REPO / "migrations" / "1.7.3.js").read_text(encoding="utf-8")
    for field in (
        "recall.entries",
        "data.skillsEditor",
        "data.weaknessEntries",
        "data.resistanceEntries",
        "abilityEditorFields",
    ):
        if field not in migration:
            raise SystemExit(f"existing creatures are not migrated for editor field: {field}")
    if "data.hardness" not in secondary_view:
        raise SystemExit("creature view does not render Hardness")

    attack_form = form("partials/attack.json")
    if "effects" not in {
        str(section.get("attribute")) for section in attack_form.get("sections", [])
    }:
        raise SystemExit("attack editor does not expose linked Strike effects")
    required_lists = {
        "data.abilities.interaction",
        "data.abilities.defensive",
        "data.abilities.offensive",
    }
    sections = {
        section.get("attribute"): section
        for section in creature_sections
        if section.get("attribute")
    }
    for attribute in required_lists:
        if sections.get(attribute, {}).get("type") != "list" or sections[attribute].get("form", {}).get("partial") != "ability":
            raise SystemExit(f"creature editor lost a distinct ability list: {attribute}")
        if sections.get(attribute, {}).get("custom", {}).get("itemDetail"):
            raise SystemExit(f"ability list should remain name-only: {attribute}")

    # List previews expose the mechanics needed to choose an entry without
    # navigating into it. Keep structured editors and legacy display fallbacks.
    for editor in (creature_form, form("character.json")):
        list_controls = {node.get("attribute"): node for node in form_nodes(editor)
                         if node.get("type") == "list"}
        attack_preview = list_controls["data.attacks"].get("custom", {}).get("itemDetail", "")
        for value in ("type", "actions", "attack|signed", "part.name", "part.formula",
                      "part.details", "part.connector", "damage", "effect.name"):
            if value not in attack_preview:
                raise SystemExit(f"attack preview omits {value}")
        if "attack != nil" not in attack_preview:
            raise SystemExit("attack previews must retain zero modifiers")
        casting_preview = list_controls["data.spellcasting"].get("custom", {}).get("itemDetail", "")
        for value in ("spellDC", "spellAttack|signed", "focusPoints", "group.label"):
            if value not in casting_preview:
                raise SystemExit(f"casting preview omits {value}")
        for value in ("spellDC", "spellAttack", "focusPoints"):
            if value + " != nil" not in casting_preview:
                raise SystemExit(f"casting previews must retain zero values: {value}")
            if value + " != ''" not in casting_preview:
                raise SystemExit(f"casting previews must omit cleared values: {value}")
    damage_list = next(section for section in attack_form["sections"]
                       if section.get("attribute") == "damageParts")
    damage_title = damage_list.get("custom", {}).get("itemTitle", "")
    if "{{name}}" not in damage_title or "{{formula}}" not in damage_title:
        raise SystemExit("damage rows must preview both current and legacy formulas")

    spellcasting = form("partials/spellcasting.json")
    spell_groups = next(
        section for section in spellcasting["sections"] if section.get("attribute") == "spellGroups"
    )
    if spell_groups.get("custom", {}).get("itemTitle") != "{{label}}" or "spell.name" not in spell_groups.get("custom", {}).get("itemDetail", ""):
        raise SystemExit("spell groups do not preview their rank and spell names")
    for value in ("spell.atWill", "spell.details"):
        if value not in spell_groups["custom"]["itemDetail"]:
            raise SystemExit(f"spell-group previews omit usage notes: {value}")

    rituals = form("partials/rituals.json")
    ritual_groups = next(
        section for section in rituals["sections"] if section.get("attribute") == "ritualGroups"
    )
    if ritual_groups.get("custom", {}).get("itemTitle") != "{{label}}" or "ritual.name" not in ritual_groups.get("custom", {}).get("itemDetail", ""):
        raise SystemExit("ritual groups do not preview their rank and ritual names")
    if "ritual.details" not in ritual_groups["custom"]["itemDetail"]:
        raise SystemExit("ritual-group previews omit usage notes")
    for filename, attribute in (("spellcasting-group.json", "spells"), ("ritual-group.json", "rituals")):
        rows = next(section for section in form("partials/" + filename)["sections"]
                    if section.get("attribute") == attribute)
        detail = rows.get("custom", {}).get("itemDetail", "")
        if "rank != nil" not in detail or "'Spell.Rank'|l" not in detail or "{{rank}}" not in detail:
            raise SystemExit(f"{filename}: previews must localize ranks, retain rank zero, and omit missing ranks")
        if "details" not in detail:
            raise SystemExit(f"{filename}: previews omit entry usage notes")
    for language in ("en", "fr"):
        labels = json.loads((REPO / "lang" / (language + ".json")).read_text())
        if not labels.get("Spellcasting.AtWill"):
            raise SystemExit(f"{language}: at-will summaries need a localized label")

    print(
        f"Validated {ability_count} editable creature abilities, "
        f"{shared_reference_count} shared-rule links, {len(GLOSSARY)} shared rules, "
        f"{sense_reference_count} linked senses, {item_editor_count} item editors, "
        f"{immunity_editor_count} immunity editors, {ritual_editor_count} ritual editors, "
        "and spell/ritual editor previews"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
