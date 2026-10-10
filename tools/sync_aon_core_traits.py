#!/usr/bin/env python3
"""Add missing Remaster Core trait entries from the reviewed AoN cache."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_aon_orc_staging import base_entity, map_simple


REPO = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = REPO.parent / "reference" / "aon-remaster.json"
DEFAULT_STAGING = REPO.parent / "structured-modules"

MODULE_BY_SOURCE = {
    "Player Core": "player-core",
    "GM Core": "gm-core",
    "Monster Core": "monster-core",
    "Player Core 2": "player-core-2",
    "Monster Core 2": "monster-core-2",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--staging", type=Path, default=DEFAULT_STAGING)
    return parser.parse_args()


def load_existing(staging: Path) -> set[str]:
    names: set[str] = set()
    for path in staging.glob("*/traits.json"):
        for row in json.loads(path.read_text()):
            if not isinstance(row, dict):
                continue
            names.add(str(row.get("name") or "").casefold())
    return names


def main() -> int:
    args = parse_args()
    payload = json.loads(args.reference.read_text())
    records = [record for record in payload.get("traits", []) if isinstance(record, dict)]
    existing_names = load_existing(args.staging)
    additions: dict[str, list[dict[str, Any]]] = {
        module_id: [] for module_id in MODULE_BY_SOURCE.values()
    }

    for record in records:
        module_id = MODULE_BY_SOURCE.get(str(record.get("primary_source") or ""))
        name = str(record.get("name") or "").strip()
        aon_id = str(record.get("id") or "")
        if not module_id or not name or not aon_id:
            continue
        # Parameterized variants such as Deadly d8 legitimately share the
        # generic Deadly trait's AoN ID. Name—not source ID—is the uniqueness
        # boundary for this synchronization step.
        if name.casefold() in existing_names:
            continue
        prepared = dict(record)
        prepared["category"] = "trait"
        data, descr = map_simple(prepared)
        entity = base_entity(prepared, module_id, "Trait", data, descr)
        entity["tags"] = sorted(set(entity["tags"] + ["trait"]))
        additions[module_id].append(entity)
        existing_names.add(name.casefold())

    added = 0
    changed_files = 0
    names: list[str] = []
    for module_id, new_rows in additions.items():
        if not new_rows:
            continue
        path = args.staging / module_id / "traits.json"
        rows = json.loads(path.read_text()) if path.is_file() else []
        rows.extend(new_rows)
        rows.sort(key=lambda row: (str(row.get("name") or "").casefold(), str(row.get("slug") or "")))
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
        added += len(new_rows)
        changed_files += 1
        names.extend(str(row["name"]) for row in new_rows)

    print(
        json.dumps(
            {
                "added": added,
                "changedFiles": changed_files,
                "names": sorted(names, key=str.casefold),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
