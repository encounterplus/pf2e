"""Restore shared monster abilities and clean creature ability presentation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


GLOSSARY_PATH = Path(__file__).with_name("creature-ability-glossary.json")
GLOSSARY: dict[str, str] = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
SEPARATOR = re.compile(r"\n\s*---\s*\n")
PARAGRAPH_SEPARATOR = re.compile(r"\n\s*---\s*\n|\n{2,}")

# Creature stat blocks intentionally summarize these shared rules. The complete
# explanation lives in the linked Action entry, mirroring the way the printed
# bestiaries use page references instead of repeating the glossary in every
# creature. A few legacy glossary names point to their remastered equivalents.
GLOSSARY_ROUTES = {
    "AllAroundVision": "/action/all-around-vision-monster-core",
    "AquaticAmbush": "/action/aquatic-ambush-monster-core",
    "AtWillSpells": "/action/at-will-spells-monster-core",
    "AttackOfOpportunity": "/action/reactive-strike-monster-core",
    "Aura": "/action/aura-monster-core",
    "Buck": "/action/buck-monster-core",
    "ChangeFormation": "/action/change-formation-npc-core",
    "ChangeShape": "/action/change-shape-monster-core",
    "ConstantSpells": "/action/constant-spells-monster-core",
    "Constrict": "/action/constrict-monster-core",
    "Coven": "/action/coven-monster-core",
    "Darkvision": "/action/darkvision-monster-core",
    "Disease": "/action/disease-monster-core",
    "Engulf": "/action/engulf-monster-core",
    "FastHealing": "/action/fast-healing-monster-core",
    "Ferocity": "/action/ferocity-monster-core",
    "FrightfulPresence": "/action/frightful-presence-monster-core",
    "Grab": "/action/grab-monster-core",
    "GreaterConstrict": "/action/greater-constrict-monster-core",
    "GreaterDarkvision": "/action/greater-darkvision-monster-core",
    "ImprovedGrab": "/action/improved-grab-monster-core",
    "ImprovedKnockdown": "/action/improved-knockdown-monster-core",
    "ImprovedPush": "/action/improved-push-monster-core",
    "Knockdown": "/action/knockdown-monster-core",
    "Lifesense": "/action/lifesense-monster-core",
    "LightBlindness": "/action/light-blindness-monster-core",
    "LowLightVision": "/action/low-light-vision-monster-core",
    "NegativeHealing": "/action/void-healing-monster-core",
    "Poison": "/action/poison-monster-core",
    "Pull": "/action/pull-monster-core",
    "Push": "/action/push-monster-core",
    "ReactiveStrike": "/action/reactive-strike-monster-core",
    "Regeneration": "/action/regeneration-monster-core",
    "Rend": "/action/rend-monster-core",
    "RetributiveStrike": "/action/retributive-strike-player-core-2",
    "Scent": "/action/scent-monster-core",
    "ShieldBlock": "/action/shield-block-monster-core",
    "Stench": "/action/stench-monster-core",
    "SwallowWhole": "/action/swallow-whole-monster-core",
    "SwarmMind": "/action/swarm-mind-monster-core",
    "Telepathy": "/action/telepathy-monster-core",
    "ThrowRock": "/action/throw-rock-monster-core",
    "Trample": "/action/trample-monster-core",
    "Tremorsense": "/action/tremorsense-monster-core",
    "TroopDefenses": "/action/troop-defenses-npc-core",
    "TroopMovement": "/action/troop-movement-npc-core",
    "Wavesense": "/action/wavesense-monster-core",
}

INLINE_MECHANIC_ROUTES = (
    ("greater striking", "/item/striking-greater-gm-core"),
    ("basic Reflex save", "/rule/basic-saving-throws-rules-2297"),
    ("basic Fortitude save", "/rule/basic-saving-throws-rules-2297"),
    ("basic Will save", "/rule/basic-saving-throws-rules-2297"),
    ("burrow Speed", "/rule/burrow-speed-rules-2348"),
    ("climb Speed", "/rule/climb-speed-rules-2349"),
    ("fly Speed", "/rule/fly-speed-rules-2350"),
    ("swim Speed", "/rule/swim-speed-rules-2351"),
    ("Burrow", "/action/burrow-player-core"),
    ("Climb", "/action/climb-player-core"),
    ("Crawl", "/action/crawl-player-core"),
    ("Escape", "/action/escape-player-core"),
    ("Fly", "/action/fly-player-core"),
    ("Grapple", "/action/grapple-player-core"),
    ("Interact", "/action/interact-player-core"),
    ("Leap", "/action/leap-player-core"),
    ("Reposition", "/action/reposition-player-core"),
    ("Seek", "/action/seek-player-core"),
    ("Shove", "/action/shove-player-core"),
    ("Step", "/action/step-player-core"),
    ("Stride", "/action/stride-player-core"),
    ("Strike", "/action/strike-player-core"),
    ("Swim", "/action/swim-player-core"),
    ("Trip", "/action/trip-player-core"),
    ("auditory", "/trait/auditory"),
    ("holy", "/trait/holy"),
    ("unholy", "/trait/unholy"),
    ("divine", "/trait/divine"),
    ("earth", "/trait/earth"),
    ("cone", "/rule/cone-rules-2386"),
    ("concealment", "/condition/concealed-player-core"),
)

ACTION_LABEL = re.compile(
    r"^\s*\*\*(?:free action|reaction|single action|one action|two actions|three actions)\*\*\s*",
    re.I,
)
LEADING_TRAITS = re.compile(r"^\s*\(([^()\n]+)\)\s*")
DEGREE_OUTCOME_BREAK = re.compile(
    r"\n+[ \t\u2003]*(?=\*\*(?:Critical Success|Success|Failure|Critical Failure)\*\*)"
)
DEGREE_OUTCOME = re.compile(
    r"(?m)^[ \t\u2003]*(\*\*(?:Critical Success|Success|Failure|Critical Failure)\*\*)"
)
MOVE_ACTION = re.compile(r"(?<![\w\[])move(?=\s+actions?\b)", re.I)


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def trait_code(value: str) -> str:
    label = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", value).strip()
    code = re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-")
    return re.sub(r"^(reach|range-increment)-.*$", r"\1", code)


def extract_leading_metadata(value: str) -> tuple[str, list[str]]:
    """Remove prose that duplicates the native action icon and trait chips."""
    text = ACTION_LABEL.sub("", str(value or ""), count=1)
    match = LEADING_TRAITS.match(text)
    traits: list[str] = []
    if match:
        for raw in match.group(1).split(","):
            code = trait_code(raw)
            if code and code not in traits:
                traits.append(code)
        text = text[match.end():]
    return text.strip(), traits


GLOSSARY_CODES_BY_KEY = {normalize(code): code for code in GLOSSARY}
GLOSSARY_BY_KEY = {normalize(code): text for code, text in GLOSSARY.items()}
GLOSSARY_CODES_BY_TEXT = {normalize(text): code for code, text in GLOSSARY.items()}


def link_inline_mechanics(value: str) -> str:
    """Add conservative AoN-style links for capitalized core actions and Speeds."""
    text = value
    linked_routes = set(re.findall(r"\[[^\]]+\]\((/[^)]+)\)", text))
    for label, route in INLINE_MECHANIC_ROUTES:
        if route in linked_routes:
            continue
        protected = [
            (match.start(), match.end())
            for match in re.finditer(r"\[[^\]]+\]\([^)]+\)", text)
        ]
        pattern = re.compile(rf"(?<![\w]){re.escape(label)}(?![\w])")
        match = next(
            (
                candidate
                for candidate in pattern.finditer(text)
                if not any(
                    candidate.start() < end and candidate.end() > start
                    for start, end in protected
                )
            ),
            None,
        )
        if match:
            text = (
                text[: match.start()]
                + f"[{match.group(0)}]({route})"
                + text[match.end() :]
            )
            linked_routes.add(route)
    move_route = "/trait/move"
    if move_route not in linked_routes:
        protected = [
            (match.start(), match.end())
            for match in re.finditer(r"\[[^\]]+\]\([^)]+\)", text)
        ]
        match = next(
            (
                candidate
                for candidate in MOVE_ACTION.finditer(text)
                if not any(
                    candidate.start() < end and candidate.end() > start
                    for start, end in protected
                )
            ),
            None,
        )
        if match:
            text = (
                text[: match.start()]
                + f"[{match.group(0)}]({move_route})"
                + text[match.end() :]
            )
    return text


def indent_degree_outcomes(value: str) -> str:
    """Visually group saving-throw outcomes beneath their owning ability."""
    # A blank Markdown line starts a new paragraph and causes Encounter+ to
    # discard the leading indentation. Keep every outcome in its owning
    # ability paragraph, matching the compact printed stat-block hierarchy.
    normalized = DEGREE_OUTCOME_BREAK.sub("\n", value)
    return DEGREE_OUTCOME.sub("\u2003\\1", normalized)


def compact_stat_block_sections(value: str) -> str:
    """Keep an ability's setup labels and Effect in one readable paragraph."""
    parts = [part.strip() for part in PARAGRAPH_SEPARATOR.split(value)]
    if len(parts) < 2:
        return value.strip()

    inline_labels = {"cost", "frequency", "trigger", "requirement", "requirements", "effect"}

    def leading_label(part: str) -> str:
        match = re.match(r"\*\*([^*]+)\*\*", part)
        return normalize(match.group(1)) if match else ""

    result = parts[0]
    previous_label = leading_label(parts[0])
    for part in parts[1:]:
        current_label = leading_label(part)
        separator = (
            "; "
            if previous_label in inline_labels and current_label in inline_labels
            else "\n\n"
        )
        result += separator + part
        previous_label = current_label
    return result.strip()


def remove_duplicate_tail(name: str, value: str) -> str:
    paragraphs = [part.strip() for part in value.split("\n\n") if part.strip()]
    if paragraphs and normalize(paragraphs[-1]) in {
        normalize(name),
        normalize("Effect " + name),
    }:
        paragraphs.pop()
    return "\n\n".join(paragraphs)


def expanded_text(name: str, value: str) -> str:
    """Expand a flattened glossary token and remove artificial dividers."""
    text = str(value or "").strip()
    direct = GLOSSARY_BY_KEY.get(normalize(text))
    if direct:
        return direct

    parts = [part.strip() for part in SEPARATOR.split(text)]
    if len(parts) > 1:
        glossary = GLOSSARY_BY_KEY.get(normalize(parts[-1]))
        if glossary:
            parts[-1] = glossary
        elif normalize(parts[-1]) in {normalize(name), normalize("Effect " + name)}:
            parts.pop()
        text = "\n\n".join(part for part in parts if part)

    paragraphs = [part.strip() for part in text.split("\n\n")]
    if len(paragraphs) > 1 and normalize(paragraphs[-1]) in {
        normalize(name),
        normalize("Effect " + name),
    }:
        return "\n\n".join(part for part in paragraphs[:-1] if part)

    if not text:
        return GLOSSARY_BY_KEY.get(normalize(name), "")
    return text


def creature_ability_text(name: str, value: str) -> str:
    """Keep creature-specific text and link out to reusable shared rules."""
    text = str(value or "").strip()
    parts = [part.strip() for part in SEPARATOR.split(text)]
    direct_code = GLOSSARY_CODES_BY_KEY.get(normalize(text)) or GLOSSARY_CODES_BY_TEXT.get(
        normalize(text)
    )
    tail_code = GLOSSARY_CODES_BY_KEY.get(normalize(parts[-1])) if parts else None
    code = direct_code or tail_code

    if code and code in GLOSSARY_ROUTES:
        specific = (
            ""
            if direct_code
            else remove_duplicate_tail(
                name, compact_stat_block_sections("\n\n---\n\n".join(parts[:-1]))
            )
        )
        return link_inline_mechanics(specific)

    # Some legacy glossary entries have no standalone public reference. A
    # creature-specific prefix already contains everything the stat block
    # needs, so discard only its duplicate glossary tail. A bare token still
    # needs the complete rule because there is nowhere useful to link.
    if tail_code and not direct_code:
        return link_inline_mechanics(
            remove_duplicate_tail(
                name, compact_stat_block_sections("\n\n---\n\n".join(parts[:-1]))
            )
        )
    return link_inline_mechanics(
        remove_duplicate_tail(name, compact_stat_block_sections(expanded_text(name, text)))
    )


def creature_ability_reference(value: str, name: str = "") -> str:
    """Return the shared Action linked by a creature ability, when available."""
    text = str(value or "").strip()
    parts = [part.strip() for part in SEPARATOR.split(text)]
    code = GLOSSARY_CODES_BY_KEY.get(normalize(text)) or GLOSSARY_CODES_BY_TEXT.get(
        normalize(text)
    )
    if code is None and parts:
        code = GLOSSARY_CODES_BY_KEY.get(normalize(parts[-1]))
    if code is None and name:
        code = GLOSSARY_CODES_BY_KEY.get(normalize(name))
    return GLOSSARY_ROUTES.get(code or "", "")


def configure_creature_abilities(entity: dict[str, Any]) -> int:
    """Apply editable, complete ability text to an Action or Creature."""
    changed = 0
    if entity.get("kind") == "Action":
        original = str(entity.get("descr") or "")
        updated = expanded_text(str(entity.get("name") or ""), original)
        if updated != original:
            entity["descr"] = updated
            changed += 1

    if entity.get("kind") != "Creature":
        return changed
    abilities = entity.get("data", {}).get("abilities", {})
    if not isinstance(abilities, dict):
        return changed
    for entries in abilities.values():
        if not isinstance(entries, list):
            continue
        for ability in entries:
            if not isinstance(ability, dict):
                continue
            original = str(ability.get("text") or "")
            name = str(ability.get("name") or "")
            cleaned, parsed_traits = extract_leading_metadata(original)
            current_traits = list(ability.get("traits") or [])
            merged_traits = list(dict.fromkeys([*current_traits, *parsed_traits]))
            if merged_traits != current_traits:
                ability["traits"] = merged_traits
                changed += 1
            updated = indent_degree_outcomes(creature_ability_text(name, cleaned))
            if updated != original:
                ability["text"] = updated
                changed += 1
            reference = creature_ability_reference(original, name)
            if reference and ability.get("reference") != reference:
                ability["reference"] = reference
                changed += 1
            if normalize(name) == "attackofopportunity" and reference == GLOSSARY_ROUTES["AttackOfOpportunity"]:
                ability["name"] = "Reactive Strike"
                changed += 1
    return changed
