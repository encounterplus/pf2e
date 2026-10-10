#!/usr/bin/env python3
"""Validate the separately licensed Rage of Elements OGL source pack."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from foundry_markup import has_conversion_artifact


REPO = Path(__file__).resolve().parents[1]
PACK = REPO / "compendium" / "ogl-packs" / "rage-of-elements"
ORC_PACKS = REPO / "compendium" / "packs"
UUID = re.compile(r"^[0-9A-F]{8}-[0-9A-F]{4}-[1-5][0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$")
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
EXTERNAL_MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(https?://[^)]+\)", re.I)
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
    "/Users/",
    "user's local source library",
    "PF2E for Foundry VTT contributors",
)
STRIPPED_DESCRIPTION_KINDS = {
    "Ancestry",
    "Class",
    "Creature",
    "Domain",
    "Hazard",
    "Language",
    "Vehicle",
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


def main() -> int:
    errors: list[str] = []
    if not PACK.is_dir():
        print("OGL validation failed: generated Rage of Elements pack is missing", file=sys.stderr)
        return 1

    module = json.loads((PACK / "module.json").read_text())
    if module.get("license") != "OGL-1.0a" or module.get("licenseFile") != "OGL-1.0a.txt":
        errors.append("module does not identify the OGL 1.0a license")
    if not UUID.match(str(module.get("id") or "")):
        errors.append("module id is not a valid UUID")

    license_path = PACK / "OGL-1.0a.txt"
    license_text = license_path.read_text() if license_path.is_file() else ""
    required_notices = (
        "OPEN GAME LICENSE Version 1.0a",
        "Pathfinder Core Rulebook (Second Edition) Copyright 2019, Paizo Inc.",
        "Pathfinder Rage of Elements Copyright 2023, Paizo Inc.",
        "OPEN GAME CONTENT DESIGNATION",
        "PRODUCT IDENTITY DESIGNATION",
    )
    for marker in required_notices:
        if marker not in license_text:
            errors.append(f"OGL license is missing required notice: {marker}")
    if not (PACK / "COMMUNITY-USE-NOTICE.md").is_file():
        errors.append("Community Use notice is missing")

    ogl_ids: set[str] = set()
    kinds: dict[str, int] = {}
    total = 0
    for path in sorted(PACK.glob("*.json")):
        if path.name in {"module.json", "source.json", "manifest.json"}:
            continue
        records = json.loads(path.read_text())
        if not isinstance(records, list):
            errors.append(f"{path.name}: collection is not an array")
            continue
        total += len(records)
        for record in records:
            inspect(record, path.name, errors)
            inspect_sources(record, path.name, errors)
            record_id = str(record.get("id") or "")
            kind = str(record.get("kind") or "")
            kinds[kind] = kinds.get(kind, 0) + 1
            if not UUID.match(record_id):
                errors.append(f"{path.name}: invalid UUID {record_id!r}")
            if record_id in ogl_ids:
                errors.append(f"{path.name}: duplicate OGL UUID {record_id}")
            ogl_ids.add(record_id)
            if record.get("attributes", {}).get("license") != "OGL-1.0a":
                errors.append(f"{path.name}: {record.get('name')} lacks its OGL marker")
            if kind in STRIPPED_DESCRIPTION_KINDS and record.get("descr"):
                errors.append(f"{path.name}: {kind} lore description was not stripped")
            if kind in {"Ancestry", "Class"} and record.get("data", {}).get("summary"):
                errors.append(f"{path.name}: {kind} summary lore was not stripped")

    orc_ids: set[str] = set()
    for path in ORC_PACKS.rglob("*.json"):
        if path.name in {"module.json", "source.json"}:
            continue
        records = json.loads(path.read_text())
        if isinstance(records, list):
            orc_ids.update(str(record.get("id") or "") for record in records if isinstance(record, dict))
    collisions = sorted(ogl_ids & orc_ids)
    if collisions:
        errors.append(f"OGL records collide with {len(collisions)} ORC entity UUIDs")

    expected = {
        "Action": 18,
        "Archetype": 2,
        "Background": 10,
        "Class": 1,
        "StatusEffect": 91,
        "Creature": 81,
        "Feat": 200,
        "Heritage": 2,
        "Item": 150,
        "Ritual": 3,
        "Rule": 1,
        "Spell": 120,
        "Table": 2,
    }
    if kinds != expected:
        errors.append(f"unexpected OGL entity counts: {kinds}")

    source = json.loads((PACK / "source.json").read_text())
    if source.get("license") != "OGL-1.0a" or source.get("counts") != kinds:
        errors.append("source metadata does not match the generated collections")

    if errors:
        print("OGL source-pack validation failed:", file=sys.stderr)
        for error in errors[:100]:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Validated the Rage of Elements OGL source pack with {total} entity records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
