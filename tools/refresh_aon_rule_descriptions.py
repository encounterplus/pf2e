#!/usr/bin/env python3
"""Refresh AoN-backed rule Markdown without rebuilding private book staging.

The first bulk importer flattened some inline ``<title>`` and list markup. This
focused repair re-runs the current conservative AoN cleaner for Rule records
that retain an AoN identifier in private staging, leaving every other entity
and structured field unchanged.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from build_aon_orc_staging import description


REPO = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = REPO.parent / "reference" / "aon-remaster.json"
DEFAULT_STAGING = REPO.parent / "structured-modules"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--staging", type=Path, default=DEFAULT_STAGING)
    return parser.parse_args()


def indexed_records(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for collection in payload.values():
        if not isinstance(collection, list):
            continue
        for record in collection:
            if isinstance(record, dict) and record.get("id"):
                records[str(record["id"])] = record
    return records


def remove_dying_condition_reprints(text: str) -> str:
    """Keep the Dying rule continuous instead of reprinting three conditions.

    The cross-link pass links the first in-context mentions of Dying,
    Unconscious, and Wounded. The complete condition text remains in each
    condition's own entry, so AoN's large related-condition sidebar would be
    duplicate content and visual noise in Encounter+.
    """
    result, count = re.subn(
        r"## Conditions Related to Dying\n\n.*?(?=\n\n## Heroic Recovery)",
        "",
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise ValueError("Dying rule no longer contains the expected related-condition sidebar")
    return result


def main() -> int:
    args = parse_args()
    raw_records = indexed_records(json.loads(args.reference.read_text()))
    matched = 0
    changed_records = 0
    changed_files = 0
    missing = 0

    for path in sorted(args.staging.glob("*/rules.json")):
        rows = json.loads(path.read_text())
        file_changed = False
        for row in rows:
            aon_id = str(row.get("attributes", {}).get("aonId") or "")
            raw = raw_records.get(aon_id)
            if raw is None:
                if aon_id:
                    missing += 1
                continue
            matched += 1
            refreshed = description(raw)
            if aon_id == "rules-2325":
                refreshed = remove_dying_condition_reprints(refreshed)
            if refreshed != row.get("descr", ""):
                row["descr"] = refreshed
                changed_records += 1
                file_changed = True
        if file_changed:
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
            changed_files += 1

    print(
        json.dumps(
            {
                "matched": matched,
                "changedRecords": changed_records,
                "changedFiles": changed_files,
                "unmatchedStagingRecords": missing,
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
