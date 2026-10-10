#!/usr/bin/env python3
"""Build publishable Encounter+ packs from a private structured staging area.

The private staging data may contain text extracted from owned PDFs, source-site
identifiers, and non-mechanical book prose.  None of those fields are copied
directly.  This builder keeps ORC-licensed rules and functional descriptions,
removes known Reserved Material fields, and writes deterministic JSON packs.

This is a publication aid, not legal advice.  New entity kinds and source books
must be reviewed before they are added to the allowlists below.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import uuid
from pathlib import Path
from typing import Any

from foundry_markup import replace_foundry_directives
from hazard_vehicle_mechanics import supplement as supplement_hazard_vehicle
from build_reference_tables import build_tables
from creature_spellcasting import configure_creature_spellcasting
from creature_metadata import configure_creature_metadata
from creature_ability_glossary import configure_creature_abilities
from creature_senses import configure_creature_senses
from creature_editor_data import configure_creature_editor_data
from item_editor_data import configure_item_editor_data
from spell_area_templates import configure_spell_area_template
from spell_load_data import configure_spell_load_data
from spell_editor_data import configure_spell_editor_data
from deity_editor_data import configure_deity_editor_data
from skill_references import skill_reference_records


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO.parent / "structured-modules"
DEFAULT_OUTPUT = REPO / "compendium" / "packs"
SOURCE_CATALOG = REPO / "compendium" / "sources.json"
ROOT_NOTICE = REPO / "compendium" / "ORC-NOTICE.md"
COMMUNITY_USE_NOTICE = REPO / "COMMUNITY-USE-NOTICE.md"
CORE_REFERENCE_ITEMS = json.loads(
    (REPO / "tools" / "data" / "gm-core-reference-items.json").read_text(encoding="utf-8")
)
CONFLICT_COPY = re.compile(r"^(?P<stem>.+) (?P<copy>[2-9]\d*)(?P<suffix>\.[^.]+)$")

COLLECTION_KIND = {
    "actions.json": "Action",
    "afflictions.json": "Affliction",
    "ancestries.json": "Ancestry",
    "archetypes.json": "Archetype",
    "backgrounds.json": "Background",
    "classes.json": "Class",
    "conditions.json": "StatusEffect",
    "creatures.json": "Creature",
    "deities.json": "Deity",
    "domains.json": "Domain",
    "feats.json": "Feat",
    "hazards.json": "Hazard",
    "heritages.json": "Heritage",
    "items.json": "Item",
    "languages.json": "Language",
    "rituals.json": "Ritual",
    "rules.json": "Rule",
    "spells.json": "Spell",
    "traits.json": "Trait",
    "vehicles.json": "Vehicle",
}

# These kinds have a clean mechanical representation in ``data``.  Their
# top-level descriptions are primarily lore, appearance, history, or setting
# prose and are therefore removed wholesale.
STRIP_TOP_LEVEL_DESCRIPTION = {
    "Ancestry",
    "Class",
    "Creature",
    "Deity",
    "Hazard",
    "Vehicle",
}

# Deity narrative is removed wholesale. The structured rules block contains
# only the fields a GM needs to adjudicate cleric and sanctification mechanics;
# proper-name references remain Paizo Reserved Material under the accompanying
# community-use notice and are not offered under the ORC License.
EXCLUDED_KINDS: set[str] = set()

PRIVATE_OR_PROVENANCE_KEYS = {
    "rawText",
    "foundryId",
    "aonId",
    "aonUrl",
    "pdfPath",
    "sourcePath",
    "watermark",
}

FOUNDRY_MARKERS = (
    "@UUID[",
    "@Embed[",
    "@Check[",
    "@Damage[",
    "@Template[",
    "@Localize[",
    "Compendium.pf2e.",
    "[[/",
)

# Parameterized traits carry a value on the item (for example Deadly d8 or
# Versatile P), but the value does not create a different rules concept. Keep
# the complete label on the item and route every variant to one canonical trait
# entry. This also prevents the Traits collection from filling with identical
# descriptions for each die, range, or damage type.
PARAMETERIZED_TRAIT_NAMES = {
    "additive": "Additive",
    "attached": "Attached",
    "capacity": "Capacity",
    "deadly": "Deadly",
    "deflecting": "Deflecting",
    "entrench": "Entrench",
    "fatal": "Fatal",
    "fatal-aim": "Fatal Aim",
    "hefty": "Hefty",
    "integrated": "Integrated",
    "jousting": "Jousting",
    "reach": "Reach",
    "scatter": "Scatter",
    "shield-throw": "Shield Throw",
    "thrown": "Thrown",
    "two-hand": "Two-Hand",
    "versatile": "Versatile",
    "volley": "Volley",
}

PARAMETERIZED_TRAIT_PATTERNS = (
    (re.compile(r"additive-?\d+$"), "additive"),
    (re.compile(r"attached-to-.+$"), "attached"),
    (re.compile(r"capacity-\d+$"), "capacity"),
    (re.compile(r"deadly-(?:\d+)?d\d+$"), "deadly"),
    (re.compile(r"deflecting-.+$"), "deflecting"),
    (re.compile(r"entrench-(?:melee|ranged)$"), "entrench"),
    (re.compile(r"fatal-aim-d\d+$"), "fatal-aim"),
    (re.compile(r"fatal-d\d+$"), "fatal"),
    (re.compile(r"hefty-\d+$"), "hefty"),
    (re.compile(r"integrated-.+$"), "integrated"),
    (re.compile(r"jousting-d\d+$"), "jousting"),
    (re.compile(r"reach-\d+(?:-feet)?$"), "reach"),
    (re.compile(r"scatter-\d+$"), "scatter"),
    (re.compile(r"shield-throw-\d+$"), "shield-throw"),
    (re.compile(r"thrown-\d+(?:-feet)?$"), "thrown"),
    (re.compile(r"two-hand-d\d+$"), "two-hand"),
    (re.compile(r"versatile-[a-z]+$"), "versatile"),
    (re.compile(r"volley-\d+$"), "volley"),
)

# Generic Core traits added from AoN originally received source-qualified
# slugs because their parameterized forms already occupied the short names.
GENERIC_TRAIT_SLUG_ALIASES = {
    "attached-player-core-trait-trait-539": "attached",
    "deadly-player-core-trait-trait-570": "deadly",
    "fatal-player-core-trait-trait-597": "fatal",
    "jousting-player-core-trait-trait-638": "jousting",
    "two-hand-player-core-trait-trait-718": "two-hand",
    "versatile-player-core-trait-trait-724": "versatile",
    "volley-player-core-trait-trait-730": "volley",
}

LEGACY_TRAIT_REPLACEMENTS: dict[str, str | None] = {
    "locathah": "athamaru",
    "metamagic": "spellshape",
    "negative": "void",
    "no-alignment": None,
    "positive": "vitality",
}

# Filled from the complete approved staging catalog before packs are built.
# This lets every source-qualified trait route resolve to the one canonical
# short slug even when the referenced trait lives in another source pack.
TRAIT_SLUG_ALIASES: dict[str, str] = dict(GENERIC_TRAIT_SLUG_ALIASES)
CANONICAL_TRAIT_SLUGS: set[str] = set()

TRAIT_ROUTE = re.compile(r"(/trait/)([a-z0-9-]+)")
EXTERNAL_REFERENCE_ROUTES = (
    (
        re.compile(r"\[([^]]+)\]\(https://2e\.aonprd\.com/Equipment\.aspx\?ID=2855\)", re.I),
        r"[\1](/item/adamantine-weapon-gm-core)",
    ),
    (
        re.compile(r"\[([^]]+)\]\(https://2e\.aonprd\.com/Skills\.aspx\?ID=37\)", re.I),
        r"[\1](/rule/crafting-skill-player-core)",
    ),
    (
        re.compile(r"\[([^]]+)\]\(https://2e\.aonprd\.com/SiegeWeapons\.aspx\)", re.I),
        r"[\1](/rule/siege-weapons-rules-1622)",
    ),
    # The legacy Radiation trait page explicitly has no supplied description.
    # Keep the value, but do not create a fake rule or send users to the web.
    (
        re.compile(r"\[([^]]+)\]\(https://2e\.aonprd\.com/Traits\.aspx\?ID=421\)", re.I),
        r"\1",
    ),
)
INTERNAL_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((/[a-z-]+/[^)\s]+)\)")
RICH_TEXT_KEYS = {
    "classDescription",
    "classFeaturesText",
    "description",
    "rulesText",
    "summary",
    "text",
}

# The combat tracker must offer the canonical Remaster conditions, not every
# spell, stance, aura, and item effect stored in ``conditions.json``.  These
# names are the complete Player Core condition appendix plus the explicit
# Cursebound condition introduced in Player Core 2.
CORE_CONDITIONS = {
    "player-core": {
        "Blinded", "Broken", "Clumsy", "Concealed", "Confused", "Controlled",
        "Dazzled", "Deafened", "Doomed", "Drained", "Dying", "Encumbered",
        "Enfeebled", "Fascinated", "Fatigued", "Fleeing", "Friendly",
        "Frightened", "Grabbed", "Helpful", "Hidden", "Hostile", "Immobilized",
        "Indifferent", "Invisible", "Observed", "Off-Guard", "Paralyzed",
        "Persistent Damage", "Petrified", "Prone", "Quickened", "Restrained",
        "Sickened", "Slowed", "Stunned", "Stupefied", "Unconscious",
        "Undetected", "Unfriendly", "Unnoticed", "Wounded",
    },
    "player-core-2": {"Cursebound"},
}

VALUED_CONDITIONS = {
    "Clumsy", "Cursebound", "Doomed", "Drained", "Dying", "Enfeebled",
    "Frightened", "Sickened", "Slowed", "Stunned", "Stupefied", "Wounded",
}

CONDITION_GROUPS = {
    "Health & Recovery": {
        "Doomed", "Drained", "Dying", "Persistent Damage", "Sickened",
        "Unconscious", "Wounded",
    },
    "Actions & Movement": {
        "Encumbered", "Grabbed", "Immobilized", "Paralyzed", "Petrified",
        "Prone", "Quickened", "Restrained", "Slowed", "Stunned",
    },
    "Senses & Visibility": {
        "Blinded", "Concealed", "Dazzled", "Deafened", "Hidden",
        "Invisible", "Observed", "Undetected", "Unnoticed",
    },
    "Mental & Social": {
        "Confused", "Controlled", "Fascinated", "Fleeing", "Friendly",
        "Frightened", "Helpful", "Hostile", "Indifferent", "Unfriendly",
    },
    "Penalties & Other": {
        "Broken", "Clumsy", "Cursebound", "Enfeebled", "Fatigued",
        "Off-Guard", "Stupefied",
    },
}
CONDITION_GROUP_BY_NAME = {
    name: group
    for group, names in CONDITION_GROUPS.items()
    for name in names
}

# StatusEffect.icon is an image path, not an SF Symbol name. Use the packaged
# condition image so the tracker and token view can always resolve it. Color
# still separates broad families at a glance without changing the rule text.
CONDITION_ICON = "icons/conditions.png"
CONDITION_COLORS = {
    "Blinded": "#5B5F97",
    "Broken": "#8C5A3C",
    "Clumsy": "#9A5B13",
    "Concealed": "#4D6D7A",
    "Confused": "#6A3D9A",
    "Controlled": "#6A3D9A",
    "Cursebound": "#6B2146",
    "Dazzled": "#B47612",
    "Deafened": "#5B5F97",
    "Doomed": "#65131A",
    "Drained": "#65131A",
    "Dying": "#65131A",
    "Encumbered": "#8C5A3C",
    "Enfeebled": "#9A5B13",
    "Fascinated": "#6A3D9A",
    "Fatigued": "#6A5568",
    "Fleeing": "#9A5B13",
    "Friendly": "#2F6B4F",
    "Frightened": "#6A3D9A",
    "Grabbed": "#8C2F39",
    "Helpful": "#2F6B4F",
    "Hidden": "#276A58",
    "Hostile": "#8C2F39",
    "Immobilized": "#8C2F39",
    "Indifferent": "#667070",
    "Invisible": "#276A58",
    "Observed": "#276A58",
    "Off-Guard": "#8C2F39",
    "Paralyzed": "#8C2F39",
    "Persistent Damage": "#A64224",
    "Petrified": "#667070",
    "Prone": "#8C5A3C",
    "Quickened": "#2F6B4F",
    "Restrained": "#8C2F39",
    "Sickened": "#557A3E",
    "Slowed": "#6A3D9A",
    "Stunned": "#B47612",
    "Stupefied": "#6A3D9A",
    "Unconscious": "#65131A",
    "Undetected": "#276A58",
    "Unfriendly": "#9A5B13",
    "Unnoticed": "#276A58",
    "Wounded": "#8C2F39",
}

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def load_catalog() -> dict[str, dict[str, Any]]:
    records = json.loads(SOURCE_CATALOG.read_text())
    if not isinstance(records, list):
        raise ValueError("compendium/sources.json must be a JSON array")
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or not record.get("id"):
            raise ValueError("each source must be an object with an id")
        source_id = str(record["id"])
        if source_id in result:
            raise ValueError(f"duplicate source id: {source_id}")
        if record.get("license") != "ORC-1.0a":
            raise ValueError(f"source is not ORC-approved: {source_id}")
        result[source_id] = record
    return result


def title_from_slug(value: str) -> str:
    return " ".join(part.capitalize() for part in value.replace("_", "-").split("-") if part)


def normalized_trait_token(value: str) -> str:
    value = value.strip().casefold().replace("_", "-").replace(" ", "-")
    return re.sub(r"-+", "-", value)


def parameterized_trait_family(value: str) -> str | None:
    token = normalized_trait_token(value)
    if token in PARAMETERIZED_TRAIT_NAMES:
        return token
    alias = GENERIC_TRAIT_SLUG_ALIASES.get(token)
    if alias:
        return alias
    for pattern, family in PARAMETERIZED_TRAIT_PATTERNS:
        if pattern.fullmatch(token):
            return family
    return None


def canonical_trait_slug(value: str) -> str:
    token = normalized_trait_token(value)
    replacement = LEGACY_TRAIT_REPLACEMENTS.get(token, token)
    if replacement is None:
        return token
    return (
        TRAIT_SLUG_ALIASES.get(token)
        or parameterized_trait_family(token)
        or replacement
    )


def normalize_trait_routes(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return match.group(1) + canonical_trait_slug(match.group(2))

    return TRAIT_ROUTE.sub(replace, value)


def normalize_external_reference_routes(value: str) -> str:
    for pattern, replacement in EXTERNAL_REFERENCE_ROUTES:
        value = pattern.sub(replacement, value)
    return value


def normalize_trait_values(traits: list[str]) -> list[str]:
    normalized_traits: list[str] = []
    seen: set[str] = set()
    for trait in traits:
        token = normalized_trait_token(trait)
        replacement = LEGACY_TRAIT_REPLACEMENTS.get(token, token)
        if replacement is None or replacement in seen:
            continue
        seen.add(replacement)
        # Parameter values remain on the item; only explicitly legacy names
        # are replaced in the displayed tag list.
        normalized_traits.append(replacement if token in LEGACY_TRAIT_REPLACEMENTS else trait)
    return normalized_traits


def normalize_trait_arrays(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"traits", "tags"} and isinstance(child, list) and all(
                isinstance(item, str) for item in child
            ):
                value[key] = normalize_trait_values(child)
            else:
                normalize_trait_arrays(child)
    elif isinstance(value, list):
        for child in value:
            normalize_trait_arrays(child)


def add_trait_links(data: dict[str, Any]) -> None:
    traits = data.get("traits")
    if not isinstance(traits, list) or not all(isinstance(trait, str) for trait in traits):
        return
    normalized_traits = normalize_trait_values(traits)
    data["traits"] = normalized_traits
    data["traitLinks"] = []
    for trait in normalized_traits:
        slug = canonical_trait_slug(trait)
        data["traitLinks"].append(
            {
                "label": trait,
                "slug": slug if not CANONICAL_TRAIT_SLUGS or slug in CANONICAL_TRAIT_SLUGS else "",
            }
        )


def simple_trait_slug(value: str) -> str:
    value = value.casefold().replace("’", "'")
    value = re.sub(r"['\u2019]", "", value)
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def trait_source_score(
    source_id: str,
    record: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
) -> tuple[int, int, int]:
    """Prefer the record housed with the source named in its attribution."""
    pack_name = simple_trait_slug(str(catalog[source_id].get("name") or ""))
    credited = [
        simple_trait_slug(str(source.get("name") or ""))
        for source in record.get("sources", [])
        if isinstance(source, dict)
    ]
    source_match = any(name and (name in pack_name or pack_name in name) for name in credited)
    attrs = record.get("attributes") or {}
    foundry_id = str(attrs.get("foundryId") or "")
    return (
        int(source_match),
        int(not foundry_id.startswith("derived-Trait-")),
        int(bool(attrs.get("aonId"))),
    )


def canonical_trait_catalog(
    source_root: Path,
    catalog: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Build one globally canonical trait catalog, grouped by source pack."""
    candidates: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    parameter_templates: dict[str, tuple[str, dict[str, Any]]] = {}

    for source_id in catalog:
        path = source_root / source_id / "traits.json"
        if not path.is_file():
            continue
        records = json.loads(path.read_text())
        if not isinstance(records, list):
            raise ValueError(f"{path} must contain a JSON array")
        for record in records:
            if not isinstance(record, dict):
                raise ValueError(f"{path} contains a non-object entry")
            prepared = copy.deepcopy(record)
            old_slug = normalized_trait_token(str(prepared.get("slug") or ""))
            family = parameterized_trait_family(old_slug or str(prepared.get("name") or ""))
            if family:
                TRAIT_SLUG_ALIASES[old_slug] = family
                is_generic = normalized_trait_token(str(prepared.get("name") or "")) == family
                if not is_generic:
                    parameter_templates.setdefault(family, (source_id, prepared))
                    continue
                prepared["name"] = PARAMETERIZED_TRAIT_NAMES[family]
                canonical_slug = family
            else:
                canonical_slug = simple_trait_slug(str(prepared.get("name") or ""))
                if not canonical_slug:
                    continue
                legacy = LEGACY_TRAIT_REPLACEMENTS.get(canonical_slug, canonical_slug)
                if legacy is None or legacy != canonical_slug:
                    TRAIT_SLUG_ALIASES[old_slug] = legacy or canonical_slug
                    continue

            TRAIT_SLUG_ALIASES[old_slug] = canonical_slug
            prepared["slug"] = canonical_slug
            candidates.setdefault(canonical_slug, []).append((source_id, prepared))

    for family, (source_id, template) in parameter_templates.items():
        if family in candidates:
            continue
        prepared = copy.deepcopy(template)
        prepared["id"] = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"pf2e-remaster:canonical-trait:{family}")
        ).upper()
        prepared["name"] = PARAMETERIZED_TRAIT_NAMES[family]
        prepared["slug"] = family
        candidates[family] = [(source_id, prepared)]

    grouped: dict[str, list[dict[str, Any]]] = {source_id: [] for source_id in catalog}
    CANONICAL_TRAIT_SLUGS.clear()
    CANONICAL_TRAIT_SLUGS.update(candidates)
    for records in candidates.values():
        source_id, selected = max(
            records,
            key=lambda item: trait_source_score(item[0], item[1], catalog),
        )
        grouped[source_id].append(selected)
    for records in grouped.values():
        records.sort(
            key=lambda record: (
                str(record.get("name") or "").casefold(),
                str(record.get("slug") or ""),
            )
        )
    return grouped


def dedupe_entity_links(result: dict[str, Any]) -> None:
    """Keep only the first link to each destination in each rich-text field.

    Identical mirrored text (notably deity ``descr`` and ``rulesText``) is
    still rewritten identically. Separate creature abilities must each retain
    the references needed to understand them without scanning another block.
    """
    rewritten: dict[str, str] = {}

    def dedupe_text(value: str) -> str:
        if value in rewritten:
            return rewritten[value]
        seen: set[str] = set()

        def replace(match: re.Match[str]) -> str:
            label, route = match.groups()
            if route in seen:
                return label
            seen.add(route)
            return match.group(0)

        updated = INTERNAL_MARKDOWN_LINK.sub(replace, value)
        rewritten[value] = updated
        return updated

    result["descr"] = dedupe_text(str(result.get("descr") or ""))

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in RICH_TEXT_KEYS and isinstance(child, str):
                    value[key] = dedupe_text(child)
                elif isinstance(child, (dict, list)):
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                if isinstance(child, (dict, list)):
                    visit(child)

    visit(result.get("data"))


def configure_core_condition(result: dict[str, Any]) -> None:
    """Mark only canonical Remaster conditions for the combat picker."""
    attributes = result.get("attributes") or {}
    source_id = str(attributes.get("sourceId") or "")
    name = str(result.get("name") or "")
    if name not in CORE_CONDITIONS.get(source_id, set()):
        return

    color = CONDITION_COLORS[name]
    result["type"] = CONDITION_GROUP_BY_NAME[name]
    result["reference"] = f"/condition/{result['slug']}"
    result["icon"] = CONDITION_ICON
    result["color"] = color
    result["descr"] = INTERNAL_MARKDOWN_LINK.sub(r"\1", str(result.get("descr") or ""))

    data = result.setdefault("data", {})
    data.pop("duration", None)
    valued = name in VALUED_CONDITIONS
    data["valued"] = valued
    data["stage"] = max(1, int(data.get("stage") or 0)) if valued else 0
    data["maxStage"] = 4 if name in {"Cursebound", "Doomed", "Dying"} else 6

def clean_foundry_markup(value: str) -> str:
    """Convert leftover VTT-only references into readable plain text."""
    text = replace_foundry_directives(value)

    def action(match: re.Match[str]) -> str:
        label = match.group(2)
        if label:
            return label
        return title_from_slug(match.group(1))

    def roll(match: re.Match[str]) -> str:
        label = match.group(2)
        formula = re.split(r"\s+#", match.group(1), maxsplit=1)[0].strip()
        return label or formula

    text = re.sub(
        r"\[\[/act\s+([a-z0-9-]+)(?:\s+[^\]]*)?\]\](?:\{([^}]+)\})?",
        action,
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\[\[/(?:r|gmr)\s+(.+?)(?:\s+#[^\]]*)?\]\](?:\{([^}]+)\})?",
        roll,
        text,
        flags=re.I,
    )
    text = re.sub(r"\bCompendium\.pf2e\.[A-Za-z0-9_-]+\.Item\.", "", text)
    text = re.sub(r"\[\[/[^\]]+\]\](?:\{([^}]+)\})?", lambda m: m.group(1) or "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def scrub_tree(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: scrub_tree(child)
            for key, child in value.items()
            if key not in PRIVATE_OR_PROVENANCE_KEYS
        }
    if isinstance(value, list):
        return [scrub_tree(child) for child in value]
    if isinstance(value, str):
        return normalize_external_reference_routes(
            normalize_trait_routes(clean_foundry_markup(value))
        )
    return value


def background_mechanics(value: str) -> str:
    """Drop biographical prompts while preserving the selectable rules."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", value) if part.strip()]
    for index, paragraph in enumerate(paragraphs):
        folded = paragraph.casefold().replace("’", "'")
        if (
            "attribute boost" in folded
            or "ability boost" in folded
            or folded.startswith("you gain three free attribute")
            or folded.startswith("you and the gm can work out")
        ):
            return "\n\n".join(paragraphs[index:])
    return ""


def deity_rules_text(data: dict[str, Any]) -> str:
    """Create one display-only mechanics block without deity narrative prose."""
    # The staging cross-link pass may already have produced this mechanical
    # summary with safe Encounter+ links. Preserve it instead of flattening the
    # same structured values a second time.
    existing = str(data.get("rulesText") or "").strip()
    if existing:
        return existing

    def values(value: Any) -> str:
        if isinstance(value, dict):
            return ", ".join(str(item) for item in value.values() if item)
        if isinstance(value, list):
            return "; ".join(str(item) for item in value if item)
        return str(value or "")

    lines = []
    for label, key in (
        ("Areas of Concern", "areasOfConcern"),
        ("Edicts", "edicts"),
        ("Anathema", "anathema"),
        ("Divine Attribute", "divineAttribute"),
        ("Divine Font", "clericFont"),
        ("Sanctification", "sanctificationText" if "sanctificationText" in data else "sanctificationOptions"),
        ("Divine Skill", "divineSkill"),
        ("Favored Weapon", "favoredWeapon"),
        ("Domains", "domains"),
        ("Alternate Domains", "alternateDomains"),
        ("Cleric Spells", "spells"),
    ):
        rendered = values(data.get(key))
        if rendered:
            lines.append(f"**{label}** {rendered}")
    return "\n\n".join(lines)


def sanitize_entity(entity: dict[str, Any], expected_kind: str) -> dict[str, Any] | None:
    if entity.get("kind") != expected_kind:
        raise ValueError(f"expected {expected_kind}, found {entity.get('kind')!r}")
    if expected_kind in EXCLUDED_KINDS:
        return None

    result = scrub_tree(copy.deepcopy(entity))
    normalize_trait_arrays(result)
    result["system"] = "pf2e-remaster"
    result.setdefault("attributes", {})["license"] = "ORC-1.0a"

    if expected_kind in STRIP_TOP_LEVEL_DESCRIPTION:
        result["descr"] = ""
    elif expected_kind == "Background":
        result["descr"] = background_mechanics(str(result.get("descr") or ""))

    data = result.get("data")
    if isinstance(data, dict):
        add_trait_links(data)
    if isinstance(data, dict) and expected_kind in {"Ancestry", "Class"}:
        data["summary"] = ""
    if isinstance(data, dict) and expected_kind == "Deity":
        data["rulesText"] = deity_rules_text(data)
        # Preserve the linked import summary. The editor enrichment below
        # moves its exact duplicate out of the editable description.
        result["descr"] = data["rulesText"]

    if expected_kind in {"Hazard", "Vehicle"}:
        supplement_hazard_vehicle(result, expected_kind)

    if expected_kind == "StatusEffect":
        configure_core_condition(result)

    if expected_kind == "Spell":
        configure_spell_area_template(result)
        configure_spell_load_data(result)

    if expected_kind == "Action":
        configure_creature_abilities(result)

    if expected_kind == "Creature":
        configure_creature_metadata(result)
        configure_creature_abilities(result)
        configure_creature_senses(result)
        configure_creature_spellcasting(result)

    # Hazard and vehicle ability text is an in-play reference. Every explicit
    # condition or rule reference should stay clickable, including repeated
    # references at different outcomes of one saving throw.
    is_skill_reference = (
        expected_kind == "Rule"
        and isinstance(data, dict)
        and data.get("type") == "skill"
    )
    if expected_kind not in {"Hazard", "Vehicle"} and not is_skill_reference:
        dedupe_entity_links(result)
    if expected_kind == "Creature":
        # Editor mirrors must reflect the final linked text, not an earlier
        # version that the reference de-duplicator can still adjust.
        configure_creature_editor_data(result)
    if expected_kind == "Spell":
        configure_spell_editor_data(result)
    if expected_kind == "Deity":
        configure_deity_editor_data(result)

    return result


def module_notice(source: dict[str, Any]) -> str:
    extra = "\n".join(f"- {line}" for line in source.get("additionalAttributions", []))
    if extra:
        extra = "\n" + extra
    return f"""# ORC Notice

This module is licensed under the ORC License located at the Library of
Congress at TX 9-307-067 and available online at various locations including
https://paizo.com/orclicense and https://azoralaw.com/orclicense. All
warranties are disclaimed as set forth therein.

## Attribution

This module is based on the following Licensed Material:

- {source['attribution']}{extra}

If you use the Adapted Licensed Material in this module in your own published
work, please credit it as follows:

Pathfinder Second Edition Remaster system for Encounter+ community compendium
© 2026 Saharory and contributors.

## Reserved Material

Reserved Material elements include all trademarks, registered trademarks,
proper nouns and terms derived from proper nouns, artwork, characters,
dialogue, settings, locations, organizations, plots, storylines, trade dress,
and all other elements designated as Reserved Material under the ORC License.
Paizo-owned names and marks appearing as descriptive references are not offered
under the ORC License and remain Paizo property; their use is governed by the
included Community Use notice.

## Expressly Designated Licensed Material

This module contains no Expressly Designated Licensed Material. The game
mechanics and functional rules text in this module are Adapted Licensed
Material under the ORC License.
"""


def module_community_use_notice() -> str:
    """Make the repository notice self-contained inside a module archive."""
    common = COMMUNITY_USE_NOTICE.read_text().split(
        "This notice applies to descriptive references", 1
    )[0]
    return (
        common
        + "This notice applies to descriptive references to Paizo-owned names and marks.\n"
        + "The game mechanics and functional rules text supplied with this module are\n"
        + "separately licensed under the ORC License; see the accompanying\n"
        + "`ORC-NOTICE.md`.\n"
    )


def remove_generated_conflict_copies(root: Path) -> int:
    """Remove macOS sync conflict copies from the generated-pack directory."""
    removed = 0
    if not root.exists():
        return removed
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        match = CONFLICT_COPY.match(path.name)
        if not match:
            continue
        canonical = path.with_name(match.group("stem") + match.group("suffix"))
        if canonical.is_file():
            path.unlink()
            removed += 1
    return removed


def aggregate_notice(catalog: dict[str, dict[str, Any]]) -> str:
    attributions: list[str] = []
    for source in catalog.values():
        attributions.append(f"- {source['attribution']}")
        attributions.extend(f"- {line}" for line in source.get("additionalAttributions", []))
    joined = "\n".join(attributions)
    return f"""# ORC Notice

The game-mechanics compendium in this directory is licensed under the ORC
License located at the Library of Congress at TX 9-307-067 and available
online at various locations including https://paizo.com/orclicense and
https://azoralaw.com/orclicense. All warranties are disclaimed as set forth
therein.

## Attribution

This compendium is based on the following Licensed Material:

{joined}

If you use the Adapted Licensed Material in this compendium in your own
published work, please credit it as follows:

Pathfinder Second Edition Remaster system for Encounter+ community compendium
© 2026 Saharory and contributors.

## Reserved Material

Reserved Material elements include all trademarks, registered trademarks,
proper nouns and terms derived from proper nouns, artwork, characters,
dialogue, settings, locations, organizations, plots, storylines, trade dress,
and all other elements designated as Reserved Material under the ORC License.
Paizo-owned names and marks appearing as descriptive references are not offered
under the ORC License and remain Paizo property; their use is governed by the
included Community Use notice.

## Expressly Designated Licensed Material

This compendium contains no Expressly Designated Licensed Material. The game
mechanics and functional rules text in the generated packs are Adapted Licensed
Material under the ORC License.
"""


def build_module(
    source_dir: Path,
    output_dir: Path,
    source: dict[str, Any],
    trait_records: list[dict[str, Any]],
) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    excluded = 0
    module_records: list[dict[str, Any]] = []
    written: set[str] = set()

    for path in sorted(source_dir.glob("*.json")):
        expected_kind = COLLECTION_KIND.get(path.name)
        if expected_kind is None:
            continue
        records = trait_records if expected_kind == "Trait" else json.loads(path.read_text())
        if expected_kind == "Rule" and source["id"] == "player-core":
            records = [*records, *skill_reference_records()]
        if expected_kind == "Item" and source["id"] == "gm-core":
            records = [*records, *CORE_REFERENCE_ITEMS]
        if not isinstance(records, list):
            raise ValueError(f"{path} must contain a JSON array")
        cleaned: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                raise ValueError(f"{path} contains a non-object entry")
            entity = sanitize_entity(record, expected_kind)
            if entity is None:
                excluded += 1
            else:
                cleaned.append(entity)
        if cleaned:
            # Roll-table extraction needs the original description/table order.
            module_records.extend(copy.deepcopy(cleaned) if expected_kind == "Item" else cleaned)
            if expected_kind == "Item":
                for entity in cleaned:
                    configure_item_editor_data(entity, CANONICAL_TRAIT_SLUGS)
            (output_dir / path.name).write_text(
                json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n"
            )
            written.add(path.name)
            counts[expected_kind] = len(cleaned)

    # Roll tables can originate in rules, feats, spells, actions, or items.
    # Generate them only after every collection has been sanitized so a full
    # rebuild produces the same tables as the checked-in public packs.
    tables = build_tables(module_records, source["id"])
    if tables:
        (output_dir / "tables.json").write_text(
            json.dumps(tables, ensure_ascii=False, indent=2) + "\n"
        )
        written.add("tables.json")
        counts["Table"] = len(tables)

    original_module = json.loads((source_dir / "module.json").read_text())
    module = {
        "id": original_module["id"],
        "system": "pf2e-remaster",
        "systemVersion": original_module.get("systemVersion", "1.2.10"),
        "name": source["name"],
        "slug": f"pf2e-remaster-{source['id']}",
        "category": "other",
        "descr": "ORC-licensed game mechanics and functional rules text for Encounter+.",
        "author": "Paizo Inc.; Encounter+ adaptation by Saharory and contributors",
        "version": original_module.get("version", "1.2.10"),
        "license": "ORC-1.0a",
        "licenseFile": "ORC-NOTICE.md",
        "communityUseNotice": "COMMUNITY-USE-NOTICE.md",
    }
    (output_dir / "module.json").write_text(json.dumps(module, ensure_ascii=False, indent=2) + "\n")
    (output_dir / "source.json").write_text(
        json.dumps(
            {
                "id": source["id"],
                "name": source["name"],
                "system": "pf2e-remaster",
                "license": "ORC-1.0a",
                "verification": source["verification"],
                "counts": counts,
                "excludedReservedMaterialRecords": excluded,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    (output_dir / "ORC-NOTICE.md").write_text(module_notice(source))
    (output_dir / "COMMUNITY-USE-NOTICE.md").write_text(module_community_use_notice())
    written.update({"module.json", "source.json", "ORC-NOTICE.md", "COMMUNITY-USE-NOTICE.md"})
    managed = set(COLLECTION_KIND) | {
        "module.json",
        "source.json",
        "ORC-NOTICE.md",
        "COMMUNITY-USE-NOTICE.md",
    }
    for filename in managed - written:
        stale = output_dir / filename
        if stale.is_file():
            stale.unlink()
    return counts


def main() -> int:
    args = parse_args()
    catalog = load_catalog()
    if not args.source.is_dir():
        raise SystemExit(f"private staging directory not found: {args.source}")

    trait_catalog = canonical_trait_catalog(args.source, catalog)

    args.output.mkdir(parents=True, exist_ok=True)
    remove_generated_conflict_copies(args.output)

    summary: dict[str, dict[str, int]] = {}
    for source_id, source in catalog.items():
        source_dir = args.source / source_id
        if not (source_dir / "module.json").is_file():
            raise SystemExit(f"approved source pack is missing: {source_dir}")
        summary[source_id] = build_module(
            source_dir,
            args.output / source_id,
            source,
            trait_catalog[source_id],
        )

    summary_path = args.output.parent / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    ROOT_NOTICE.write_text(aggregate_notice(catalog))
    remove_generated_conflict_copies(args.output)

    total = sum(sum(counts.values()) for counts in summary.values())
    print(f"Built {len(summary)} ORC modules with {total} records in {args.output}")
    print(f"Excluded sources not in the ORC allowlist, including Rage of Elements (OGL-only)")
    print(f"Aggregate notice: {ROOT_NOTICE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
