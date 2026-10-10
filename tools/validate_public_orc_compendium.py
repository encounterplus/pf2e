#!/usr/bin/env python3
"""Fail closed when public compendium data contains known private residue."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from build_public_orc_compendium import (
    PARAMETERIZED_TRAIT_NAMES,
    canonical_trait_slug,
    parameterized_trait_family,
)
from foundry_markup import has_conversion_artifact


REPO = Path(__file__).resolve().parents[1]
COMPENDIUM = REPO / "compendium"
PACKS = COMPENDIUM / "packs"
CATALOG = COMPENDIUM / "sources.json"

BANNED_KEYS = {
    "rawText",
    "foundryId",
    "aonId",
    "aonUrl",
    "pdfPath",
    "sourcePath",
    "watermark",
}
BANNED_TEXT = (
    "@UUID[",
    "@Embed[",
    "@Check[",
    "@Damage[",
    "@Template[",
    "@Localize[",
    "Compendium.pf2e.",
    "[[/",
    "{{collection",
    "{{creatureAbilities",
    "/Users/",
    "user's local source library",
    "PF2E for Foundry VTT contributors",
)
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
UUID = re.compile(r"^[0-9A-F]{8}-[0-9A-F]{4}-[1-5][0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$")
STRIPPED_DESCRIPTION_KINDS = {
    "Ancestry",
    "Class",
    "Creature",
    "Deity",
    "Hazard",
    "Vehicle",
}
ROUTE_BY_KIND = {
    "Action": "action",
    "Affliction": "affliction",
    "Ancestry": "ancestry",
    "Archetype": "archetype",
    "Background": "background",
    "Class": "class",
    "Creature": "creature",
    "Deity": "deity",
    "Domain": "domain",
    "Feat": "feat",
    "Hazard": "hazard",
    "Heritage": "heritage",
    "Item": "item",
    "Language": "language",
    "Ritual": "ritual",
    "Rule": "rule",
    "Spell": "spell",
    "StatusEffect": "condition",
    "Table": "table",
    "Trait": "trait",
    "Vehicle": "vehicle",
}
INTERNAL_LINK = re.compile(r"\[[^\]]+\]\(/([a-z-]+)/([^)\s]+)\)")
EXTERNAL_MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(https?://[^)]+\)", re.I)
RICH_TEXT_KEYS = {
    "classDescription",
    "classFeaturesText",
    "description",
    "rulesText",
    "summary",
    "text",
}


def inspect(value: Any, location: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in BANNED_KEYS:
                errors.append(f"{location}: banned key {key}")
            inspect(child, f"{location}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            inspect(child, f"{location}[{index}]", errors)
    elif isinstance(value, str):
        for marker in BANNED_TEXT:
            if marker in value:
                errors.append(f"{location}: banned text marker {marker!r}")
        if EMAIL.search(value):
            errors.append(f"{location}: possible email/private watermark")
        if has_conversion_artifact(value):
            errors.append(f"{location}: malformed converted rules text")
        if EXTERNAL_MARKDOWN_LINK.search(value):
            errors.append(f"{location}: gameplay reference must use an in-app entity")


def inspect_sources(record: dict[str, Any], location: str, errors: list[str]) -> None:
    sources = record.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append(f"{location}: {record.get('name')} lacks source attribution")
        return
    for index, source in enumerate(sources):
        source_location = f"{location}.sources[{index}]"
        if not isinstance(source, dict) or not str(source.get("name") or "").strip():
            errors.append(f"{source_location}: source book name is missing")
            continue
        page = source.get("page")
        if page is not None and (not isinstance(page, int) or isinstance(page, bool) or page <= 0):
            errors.append(f"{source_location}: source page must be a positive integer")


def rich_text_values(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in RICH_TEXT_KEYS and isinstance(child, str):
                result.append(child)
            elif isinstance(child, (dict, list)):
                result.extend(rich_text_values(child))
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, (dict, list)):
                result.extend(rich_text_values(child))
    return result


def main() -> int:
    sources = json.loads(CATALOG.read_text())
    source_ids = {record["id"] for record in sources}
    pack_ids = {path.name for path in PACKS.iterdir() if path.is_dir()}
    errors: list[str] = []

    if source_ids != pack_ids:
        errors.append(f"pack/catalog mismatch: expected {sorted(source_ids)}, found {sorted(pack_ids)}")
    if "rage-of-elements" in pack_ids:
        errors.append("OGL-only Rage of Elements must not appear in the ORC packs")

    total = 0
    ids: set[str] = set()
    by_kind: dict[str, list[dict[str, Any]]] = {}
    collection_counts: dict[str, dict[str, int]] = {}
    linked_records: list[tuple[Path, dict[str, Any]]] = []
    valid_routes: set[tuple[str, str]] = set()
    for path in sorted(PACKS.rglob("*.json")):
        value = json.loads(path.read_text())
        inspect(value, str(path.relative_to(REPO)), errors)
        if path.name not in {"module.json", "source.json"}:
            if not isinstance(value, list):
                errors.append(f"{path}: entity collection is not an array")
            else:
                total += len(value)
                source_id = path.parent.name
                collection_counts.setdefault(source_id, {})
                for record in value:
                    if not isinstance(record, dict):
                        continue
                    kind = str(record.get("kind") or "")
                    collection_counts[source_id][kind] = collection_counts[source_id].get(kind, 0) + 1
                    by_kind.setdefault(kind, []).append(record)
                    linked_records.append((path, record))
                    route_kind = ROUTE_BY_KIND.get(kind)
                    if route_kind and record.get("slug"):
                        valid_routes.add((route_kind, str(record["slug"])))
                    record_id = str(record.get("id") or "")
                    if not UUID.match(record_id):
                        errors.append(f"{path}: invalid entity UUID {record_id!r}")
                    if record_id in ids:
                        errors.append(f"{path}: duplicate entity UUID {record_id}")
                    ids.add(record_id)
                    if not record.get("name") or not record.get("slug"):
                        errors.append(f"{path}: record lacks a name or slug")
                    if record.get("system") != "pf2e-remaster":
                        errors.append(f"{path}: wrong entity system")
                    inspect_sources(record, str(path), errors)
                    if record.get("attributes", {}).get("license") != "ORC-1.0a":
                        errors.append(f"{path}: {record.get('name')} lacks its ORC marker")
                    allowed_deity_rules = (
                        kind == "Deity"
                        and record.get("descr")
                        == record.get("data", {}).get("rulesText")
                    )
                    if (
                        kind in STRIPPED_DESCRIPTION_KINDS
                        and record.get("descr")
                        and not allowed_deity_rules
                    ):
                        errors.append(f"{path}: {kind} lore description was not stripped")
                    if kind in {"Ancestry", "Class"} and record.get("data", {}).get("summary"):
                        errors.append(f"{path}: {kind} summary lore was not stripped")
                    if kind == "Rule":
                        for line in str(record.get("descr") or "").splitlines():
                            if line.startswith("## ") and len(line) > 80:
                                errors.append(
                                    f"{path}: probable flattened rule heading in {record.get('name')}: {line[:80]!r}"
                                )
                    if kind == "Table":
                        columns = record.get("columns")
                        rows = record.get("rows")
                        if not isinstance(columns, list) or not columns or not isinstance(rows, list) or not rows:
                            errors.append(f"{path}: malformed native table {record.get('name')}")
                        elif any(not isinstance(row, list) or len(row) != len(columns) for row in rows):
                            errors.append(f"{path}: ragged native table {record.get('name')}")

    for source_id in sorted(pack_ids):
        notice = PACKS / source_id / "ORC-NOTICE.md"
        if not notice.is_file() or "TX 9-307-067" not in notice.read_text():
            errors.append(f"{source_id}: missing complete ORC notice")
        community_notice = PACKS / source_id / "COMMUNITY-USE-NOTICE.md"
        if not community_notice.is_file():
            errors.append(f"{source_id}: missing Community Use notice")
        else:
            community_text = community_notice.read_text()
            if "expressly prohibited from charging" not in community_text or "Saharory" not in community_text:
                errors.append(f"{source_id}: incomplete Community Use notice")
        source_meta = json.loads((PACKS / source_id / "source.json").read_text())
        if source_meta.get("counts") != collection_counts.get(source_id, {}):
            errors.append(f"{source_id}: source.json counts do not match entity files")
        module = json.loads((PACKS / source_id / "module.json").read_text())
        if module.get("system") != "pf2e-remaster" or not UUID.match(str(module.get("id") or "")):
            errors.append(f"{source_id}: invalid module metadata")
        if module.get("communityUseNotice") != "COMMUNITY-USE-NOTICE.md":
            errors.append(f"{source_id}: module does not identify its Community Use notice")

    backgrounds = by_kind.get("Background", [])
    for background in backgrounds:
        descr = str(background.get("descr") or "").casefold()
        if "attribute boost" not in descr and "ability boost" not in descr:
            errors.append(f"background mechanics were lost: {background.get('name')}")

    classes = by_kind.get("Class", [])
    if len(classes) != 28:
        errors.append(f"expected 28 ORC Remaster class records, found {len(classes)}")
    for class_record in classes:
        data = class_record.get("data", {})
        advancement = str(data.get("classAdvancement") or "")
        rows = [line for line in advancement.splitlines() if line.startswith("| ")][2:]
        if len(rows) != 20:
            errors.append(f"incomplete class advancement table: {class_record.get('name')}")
        features = data.get("classFeatures")
        if not isinstance(features, list) or not features or not all(feature.get("text") for feature in features):
            errors.append(f"incomplete class features: {class_record.get('name')}")

    traits = by_kind.get("Trait", [])
    required_core_traits = {
        "Attached", "City", "Coagulant", "Deadly", "Erratic", "Fatal",
        "Finite", "Flowing", "High Gravity", "Immeasurable", "Jousting",
        "Low Gravity", "Metamorphic", "Metropolis", "Microgravity",
        "Minion", "Munsahir", "Sentient", "Soulrider", "Static",
        "Strange Gravity", "Subjective Gravity", "Timeless", "Town",
        "Two-Hand", "Unbounded", "Venomous", "Versatile", "Village", "Volley",
    }
    required_parameterized_families = set(PARAMETERIZED_TRAIT_NAMES.values())
    trait_names = {str(trait.get("name") or "") for trait in traits}
    trait_slugs = {str(trait.get("slug") or "") for trait in traits}
    if (
        len(traits) < 438
        or not all(trait.get("descr") for trait in traits)
        or not required_core_traits.issubset(trait_names)
        or not required_parameterized_families.issubset(trait_names)
    ):
        errors.append("trait catalog is incomplete")
    if len(trait_names) != len(traits) or len(trait_slugs) != len(traits):
        errors.append("trait catalog contains duplicate names or routes")
    for trait in traits:
        slug = str(trait.get("slug") or "")
        family = parameterized_trait_family(slug)
        if family and slug != family:
            errors.append(f"parameterized trait was not consolidated: {trait.get('name')}")

    for record in [entry for records in by_kind.values() for entry in records]:
        data = record.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("traits"), list):
            continue
        raw_traits = data["traits"]
        links = data.get("traitLinks")
        if not isinstance(links, list) or len(links) != len(raw_traits):
            errors.append(f"{record.get('name')}: trait navigation metadata is incomplete")
            continue
        for raw_trait, link in zip(raw_traits, links):
            if not isinstance(raw_trait, str) or not isinstance(link, dict):
                errors.append(f"{record.get('name')}: malformed trait navigation metadata")
                break
            canonical_slug = canonical_trait_slug(raw_trait)
            expected_slug = canonical_slug if canonical_slug in trait_slugs else ""
            if link.get("label") != raw_trait or link.get("slug") != expected_slug:
                errors.append(f"{record.get('name')}: trait label or destination was altered")
                break
            if record.get("kind") == "Item" and not link.get("slug"):
                errors.append(f"{record.get('name')}: item trait links to a missing entry")
                break

    domains = by_kind.get("Domain", [])
    if len(domains) < 61 or not all(domain.get("descr") for domain in domains):
        errors.append("domain catalog or descriptions are incomplete")

    languages = by_kind.get("Language", [])
    if len(languages) < 73 or not all(language.get("descr") for language in languages):
        errors.append("language catalog or access descriptions are incomplete")

    deities = by_kind.get("Deity", [])
    if len(deities) != 420:
        errors.append(f"expected 420 mechanical deity records, found {len(deities)}")
    for deity in deities:
        data = deity.get("data", {})
        if not data.get("rulesText"):
            errors.append(f"incomplete mechanical deity record: {deity.get('name')}")
        if deity.get("descr"):
            errors.append(f"deity import description duplicates structured mechanics: {deity.get('name')}")
        if not isinstance(data.get("deityReferences"), dict) or not isinstance(data.get("deityReferenceKeys"), dict):
            errors.append(f"deity live display lacks preserved references: {deity.get('name')}")

    create_undead = next(
        (ritual for ritual in by_kind.get("Ritual", []) if ritual.get("name") == "Create Undead"),
        None,
    )
    if not create_undead or "| Creature Level | Spell Rank Required | Cost |" not in str(create_undead.get("descr")):
        errors.append("Create Undead ritual table is missing or flattened")

    # OGL records are installed in the same system bundle and are therefore
    # valid cross-link destinations from ORC records (and vice versa).
    for path in sorted((COMPENDIUM / "ogl-packs").rglob("*.json")):
        if path.name in {"module.json", "source.json"}:
            continue
        value = json.loads(path.read_text())
        if not isinstance(value, list):
            continue
        for record in value:
            if not isinstance(record, dict):
                continue
            linked_records.append((path, record))
            route_kind = ROUTE_BY_KIND.get(str(record.get("kind") or ""))
            if route_kind and record.get("slug"):
                valid_routes.add((route_kind, str(record["slug"])))

    for path, record in linked_records:
        displayed_text = [str(record.get("descr") or "")]
        displayed_text.extend(rich_text_values(record.get("data")))
        if record.get("kind") == "Table":
            displayed_text.extend(
                cell
                for row in record.get("rows", [])
                if isinstance(row, list)
                for cell in row
                if isinstance(cell, str)
            )
        displayed_text = list(dict.fromkeys(displayed_text))
        destinations = [
            match.groups()
            for value in displayed_text
            for match in INTERNAL_LINK.finditer(value)
        ]
        missing = [destination for destination in destinations if destination not in valid_routes]
        if missing:
            errors.append(
                f"{path}: {record.get('name')} links to missing entries {missing[:5]}"
            )
        # A route can legitimately appear in more than one structured field. For
        # example, separate creature abilities can each instruct the GM to Fly.
        # Only flag repeated destinations inside the same rich-text field, where
        # they usually indicate that the source-link cleanup failed to dedupe it.
        # Hazard outcomes often repeat conditions at different values inside one
        # field, and every occurrence remains useful during play.
        is_skill_reference = (
            record.get("kind") == "Rule"
            and isinstance(record.get("data"), dict)
            and record["data"].get("type") == "skill"
        )
        if record.get("kind") not in {"Hazard", "Vehicle"} and not is_skill_reference:
            duplicate_count = sum(
                len(field_destinations) - len(set(field_destinations))
                for value in displayed_text
                if (
                    field_destinations := [
                        match.groups() for match in INTERNAL_LINK.finditer(value)
                    ]
                )
            )
            if duplicate_count:
                errors.append(
                    f"{path}: {record.get('name')} repeats {duplicate_count} "
                    "internal destination links inside individual text fields"
                )

    dying_rule = next(
        (rule for rule in by_kind.get("Rule", []) if rule.get("slug") == "dying-rules-2325"),
        None,
    )
    dying_text = str(dying_rule.get("descr") if dying_rule else "")
    if (
        "/condition/dying-player-core" not in dying_text
        or
        "/condition/unconscious-player-core" not in dying_text
        or "/condition/wounded-player-core" not in dying_text
        or "## Conditions Related to Dying" in dying_text
        or "## Unconscious" in dying_text
    ):
        errors.append("Dying rule does not use continuous first-mention condition links")

    if total < 17289:
        errors.append(f"public ORC record count is unexpectedly low: {total}")

    if errors:
        print("Public compendium validation failed:", file=sys.stderr)
        for error in errors[:100]:
            print(f"- {error}", file=sys.stderr)
        if len(errors) > 100:
            print(f"- ...and {len(errors) - 100} more", file=sys.stderr)
        return 1

    print(f"Validated {len(pack_ids)} ORC modules and {total} entity records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
