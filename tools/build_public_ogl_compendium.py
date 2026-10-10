#!/usr/bin/env python3
"""Build the separately licensed OGL Rage of Elements source pack."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
from pathlib import Path
from typing import Any

from build_public_orc_compendium import (
    COLLECTION_KIND,
    CANONICAL_TRAIT_SLUGS,
    COMMUNITY_USE_NOTICE,
    PRIVATE_OR_PROVENANCE_KEYS,
    STRIP_TOP_LEVEL_DESCRIPTION,
    add_trait_links,
    background_mechanics,
    canonical_trait_catalog,
    clean_foundry_markup,
    dedupe_entity_links,
    load_catalog,
    normalize_trait_arrays,
    normalize_trait_routes,
    normalize_external_reference_routes,
    remove_generated_conflict_copies,
)
from build_reference_tables import build_tables
from creature_ability_glossary import configure_creature_abilities
from creature_senses import configure_creature_senses
from creature_editor_data import configure_creature_editor_data
from item_editor_data import configure_item_editor_data
from creature_spellcasting import configure_creature_spellcasting
from creature_metadata import configure_creature_metadata
from spell_area_templates import configure_spell_area_template
from spell_load_data import configure_spell_load_data
from spell_editor_data import configure_spell_editor_data


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO.parent / "structured-modules" / "rage-of-elements"
DEFAULT_OUTPUT = REPO / "compendium" / "ogl-packs" / "rage-of-elements"
SOURCE_CATALOG = REPO / "compendium" / "ogl-sources.json"
LICENSE_TEXT = REPO / "compendium" / "OGL-1.0a.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


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


def sanitize_entity(entity: dict[str, Any], expected_kind: str) -> dict[str, Any]:
    if entity.get("kind") != expected_kind:
        raise ValueError(f"expected {expected_kind}, found {entity.get('kind')!r}")

    result = scrub_tree(copy.deepcopy(entity))
    normalize_trait_arrays(result)
    result["system"] = "pf2e-remaster"
    result.setdefault("attributes", {})["license"] = "OGL-1.0a"

    if expected_kind in STRIP_TOP_LEVEL_DESCRIPTION:
        result["descr"] = ""
    elif expected_kind == "Background":
        result["descr"] = background_mechanics(str(result.get("descr") or ""))

    data = result.get("data")
    if isinstance(data, dict):
        add_trait_links(data)
    if isinstance(data, dict) and expected_kind in {"Ancestry", "Class"}:
        data["summary"] = ""
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
    dedupe_entity_links(result)
    if expected_kind == "Creature":
        # Build mirrors from the final linked text so the editor and view stay
        # byte-for-byte aligned after reference de-duplication.
        configure_creature_editor_data(result)
    if expected_kind == "Spell":
        configure_spell_editor_data(result)
    return result


def community_use_notice() -> str:
    common = COMMUNITY_USE_NOTICE.read_text().split(
        "This notice applies to descriptive references", 1
    )[0]
    return (
        common
        + "This notice applies to descriptive references to Paizo-owned names and marks.\n"
        + "The game mechanics and functional rules text supplied with this source pack\n"
        + "are separately licensed under OGL 1.0a; see the accompanying `OGL-1.0a.txt`.\n"
    )


def main() -> int:
    args = parse_args()
    source_records = json.loads(SOURCE_CATALOG.read_text())
    if len(source_records) != 1 or source_records[0].get("id") != "rage-of-elements":
        raise SystemExit("OGL catalog must contain only the reviewed Rage of Elements source")
    source = source_records[0]
    if source.get("license") != "OGL-1.0a":
        raise SystemExit("Rage of Elements source is not marked OGL-1.0a")
    if not (args.source / "module.json").is_file():
        raise SystemExit(f"private staging module not found: {args.source}")

    # Populate the same global trait-route aliases used by the ORC build so
    # OGL entries link into the single canonical trait catalog.
    canonical_trait_catalog(args.source.parent, load_catalog())

    args.output.mkdir(parents=True, exist_ok=True)
    remove_generated_conflict_copies(args.output)

    counts: dict[str, int] = {}
    module_records: list[dict[str, Any]] = []
    written: set[str] = set()
    for path in sorted(args.source.glob("*.json")):
        expected_kind = COLLECTION_KIND.get(path.name)
        if expected_kind is None:
            continue
        records = json.loads(path.read_text())
        if not isinstance(records, list):
            raise ValueError(f"{path} must contain a JSON array")
        cleaned = [sanitize_entity(record, expected_kind) for record in records]
        if cleaned:
            # Preserve printed table order while exposing editable activation fields.
            module_records.extend(copy.deepcopy(cleaned) if expected_kind == "Item" else cleaned)
            if expected_kind == "Item":
                for entity in cleaned:
                    configure_item_editor_data(entity, CANONICAL_TRAIT_SLUGS)
            (args.output / path.name).write_text(
                json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n"
            )
            written.add(path.name)
            counts[expected_kind] = len(cleaned)

    tables = build_tables(module_records, source["id"])
    if tables:
        (args.output / "tables.json").write_text(
            json.dumps(tables, ensure_ascii=False, indent=2) + "\n"
        )
        written.add("tables.json")
        counts["Table"] = len(tables)

    original_module = json.loads((args.source / "module.json").read_text())
    module = {
        "id": original_module["id"],
        "system": "pf2e-remaster",
        "systemVersion": original_module.get("systemVersion", "1.2.10"),
        "name": "Rage of Elements (OGL)",
        "slug": "pf2e-remaster-rage-of-elements-ogl-source",
        "category": "other",
        "descr": "Source pack for separately licensed OGL records bundled into the PF2E Remaster system installer.",
        "author": "Encounter+ adaptation by Saharory and contributors",
        "version": original_module.get("version", "1.2.10"),
        "license": "OGL-1.0a",
        "licenseFile": "OGL-1.0a.txt",
        "communityUseNotice": "COMMUNITY-USE-NOTICE.md",
    }
    (args.output / "module.json").write_text(
        json.dumps(module, ensure_ascii=False, indent=2) + "\n"
    )
    (args.output / "source.json").write_text(
        json.dumps(
            {
                "id": source["id"],
                "name": source["name"],
                "system": "pf2e-remaster",
                "license": source["license"],
                "verification": source["verification"],
                "counts": counts,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    shutil.copyfile(LICENSE_TEXT, args.output / "OGL-1.0a.txt")
    (args.output / "COMMUNITY-USE-NOTICE.md").write_text(community_use_notice())
    written.update({"module.json", "source.json", "OGL-1.0a.txt", "COMMUNITY-USE-NOTICE.md"})
    managed = set(COLLECTION_KIND) | {
        "module.json",
        "source.json",
        "OGL-1.0a.txt",
        "COMMUNITY-USE-NOTICE.md",
    }
    for filename in managed - written:
        stale = args.output / filename
        if stale.is_file():
            stale.unlink()
    remove_generated_conflict_copies(args.output)

    summary_path = args.output.parents[1] / "ogl-summary.json"
    summary_path.write_text(
        json.dumps({"rage-of-elements": counts}, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"Built one OGL source pack with {sum(counts.values())} records in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
