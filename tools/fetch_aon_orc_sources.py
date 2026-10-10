#!/usr/bin/env python3
"""Cache AoN records for reviewed Remaster books in small, verified batches.

The cache is private build input and is written beneath ``reference/``, which
is intentionally ignored by git.  Fetching per source and category avoids the
large single-response truncation that can occur at the public search endpoint.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
ENDPOINT = "https://elasticsearch.aonprd.com/aon/_search"
DEFAULT_OUTPUT = REPO / "reference" / "aon-orc-sources"

# Only released Remaster sources whose game mechanics are intended for the
# public ORC compendium.  The Divine Mysteries web supplement belongs in the
# same module as the book.  Secrets of the Unlit Star is an adventure and is
# deliberately outside this management-tool scope.
SOURCES: dict[str, tuple[str, ...]] = {
    "tian-xia-world-guide": ("Tian Xia World Guide",),
    "tian-xia-character-guide": ("Tian Xia Character Guide",),
    "divine-mysteries": ("Divine Mysteries", "Divine Mysteries Web Supplement"),
    "draconic-codex": ("Draconic Codex",),
    "hellfire-dispatches": ("Hellfire Dispatches",),
    "high-seas": ("High Seas",),
    "impossible-magic": ("Impossible Magic",),
}

INDEX_FIELDS = (
    "category",
    "id",
    "name",
    "primary_source",
    "primary_source_raw",
    "release_date",
    "url",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def request(query: str, size: int, source_fields: tuple[str, ...] | None = None) -> dict[str, Any]:
    parameters: dict[str, Any] = {"size": size, "q": query}
    if source_fields:
        parameters["_source"] = ",".join(source_fields)
    url = f"{ENDPOINT}?{urllib.parse.urlencode(parameters)}"
    response = subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--max-time", "90", url],
        check=True,
        capture_output=True,
    )
    payload = json.loads(response.stdout)
    if not isinstance(payload, dict) or not isinstance(payload.get("hits"), dict):
        raise ValueError("AoN returned an unexpected response")
    return payload


def records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for hit in payload["hits"].get("hits", []):
        source = hit.get("_source") if isinstance(hit, dict) else None
        if isinstance(source, dict):
            result.append(source)
    return result


def exact_source_query(source_name: str) -> str:
    escaped = source_name.replace('"', r'\"')
    return f'primary_source:"{escaped}"'


def fetch_source(source_name: str) -> tuple[list[dict[str, Any]], Counter[str]]:
    index_payload = request(exact_source_query(source_name), 10000, INDEX_FIELDS)
    # ``primary_source`` is analyzed text rather than a keyword field.  A
    # phrase query for "Divine Mysteries" therefore also matches "Divine
    # Mysteries Web Supplement"; enforce exact equality locally.
    index = [record for record in records(index_payload) if record.get("primary_source") == source_name]
    if not index:
        raise ValueError(f"{source_name}: exact source returned no records")

    expected = Counter(str(record.get("category") or "") for record in index)
    fetched: list[dict[str, Any]] = []
    for category, count in sorted(expected.items()):
        if not category:
            raise ValueError(f"{source_name}: record without a category")
        query = f'category:{category} AND {exact_source_query(source_name)}'
        payload = request(query, 10000)
        batch = [
            record
            for record in records(payload)
            if record.get("primary_source") == source_name and record.get("category") == category
        ]
        if len(batch) != count:
            raise ValueError(
                f"{source_name}/{category}: expected {count} exact records, received {len(batch)}"
            )
        fetched.extend(batch)

    ids = [str(record.get("id") or "") for record in fetched]
    if not all(ids) or len(ids) != len(set(ids)) or set(ids) != {str(record.get("id")) for record in index}:
        raise ValueError(f"{source_name}: fetched IDs do not match the verified index")
    return fetched, expected


def main() -> int:
    args = parse_args()
    staged: dict[str, dict[str, Any]] = {}
    grand_total = 0

    # Finish and validate every network request before replacing any cache.
    for module_id, source_names in SOURCES.items():
        module_records: list[dict[str, Any]] = []
        source_counts: dict[str, dict[str, int]] = {}
        for source_name in source_names:
            fetched, counts = fetch_source(source_name)
            module_records.extend(fetched)
            source_counts[source_name] = dict(sorted(counts.items()))
        module_records.sort(key=lambda record: (str(record.get("category")), str(record.get("name")), str(record.get("id"))))
        staged[module_id] = {
            "moduleId": module_id,
            "provider": "Archives of Nethys",
            "providerUrl": "https://2e.aonprd.com/",
            "sourceCounts": source_counts,
            "records": module_records,
        }
        grand_total += len(module_records)

    args.output.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {"modules": {}, "total": grand_total}
    for module_id, payload in staged.items():
        target = args.output / f"{module_id}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        summary["modules"][module_id] = {
            "records": len(payload["records"]),
            "sourceCounts": payload["sourceCounts"],
        }
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(f"Cached {grand_total} verified AoN records for {len(staged)} ORC modules in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
