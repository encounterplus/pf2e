#!/usr/bin/env python3
"""Collect omitted, functional hazard/vehicle statistics into a public fixture.

Reads the existing private structured staging and its reviewed Foundry/AoN
cross-checks. The output contains only game mechanics, no source identifiers,
art, provider markup, private PDFs, or book descriptions.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

from build_aon_orc_staging import clean_markup
from foundry_markup import replace_foundry_directives


REPO = Path(__file__).resolve().parents[1]
WORK = REPO.parent


def plain(value: Any) -> str:
    without_tags = re.sub(r"<[^>]*>", " ", str(value or ""))
    without_tags = html.unescape(without_tags)
    return re.sub(r"\s+", " ", replace_foundry_directives(without_tags)).strip()


def immunity_name(code: str) -> str:
    return {"precision": "precision damage", "critical-hits": "critical hits"}.get(
        code, code.replace("-", " ")
    )


def find_foundry_records() -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for path in (WORK / "foundry-pf2e/packs/pf2e").rglob("*.json"):
        value = json.loads(path.read_text())
        if isinstance(value, dict) and value.get("type") in {"hazard", "vehicle"}:
            indexed.setdefault(str(value.get("_id")), []).append(value)
    return indexed


def find_aon_vehicles() -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for path in (REPO / "reference/aon-orc-sources").glob("*.json"):
        for value in json.loads(path.read_text()).get("records", []):
            if value.get("category") == "vehicle":
                indexed[str(value.get("id"))] = value
    return indexed


def ability_entries(markdown: str) -> list[dict[str, Any]]:
    """Only the functional ability block after Collision, never the lore above it."""
    tail = re.split(r"\*\*Collision\*\*[^\n]*", markdown, maxsplit=1, flags=re.I)
    if len(tail) < 2:
        return []
    block = tail[1].split("</column>", 1)[0]
    headings = list(re.finditer(r"(?m)^\s*\*\*([^*\n]+)\*\*\s*", block))
    abilities: list[dict[str, Any]] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(block)
        name = plain(heading.group(1))
        ability_source = block[heading.end():end]
        # The generic AoN cleanup intentionally drops all links. These are
        # actual rules references, so retain safe links in the playable view.
        ability_source = re.sub(
            r"\]\((/(?:[A-Za-z]+\.aspx(?:\?[^)]*)?))\)",
            r"](https://2e.aonprd.com\1)",
            ability_source,
        )
        text = clean_markup(ability_source).strip()
        for label, slug in (("concealed", "concealed-player-core"), ("frightened", "frightened-player-core")):
            text = re.sub(
                rf"\[({label})\]\(https://2e\.aonprd\.com/Conditions\.aspx\?ID=\d+\)",
                rf"[\1](/condition/{slug})",
                text,
                flags=re.I,
            )
        text = re.sub(
            r"\[([^]]+)\]\(https://2e\.aonprd\.com/Skills\.aspx\?ID=37\)",
            r"[\1](/rule/crafting-skill-player-core)",
            text,
            flags=re.I,
        )
        text = re.sub(
            r"\[([^]]+)\]\(https://2e\.aonprd\.com/SiegeWeapons\.aspx\)",
            r"[\1](/rule/siege-weapons-rules-1622)",
            text,
            flags=re.I,
        )
        if re.search(r"\]\(https?://", text, flags=re.I):
            raise ValueError(f"vehicle ability has no imported Encounter+ reference: {name}")
        if name and text:
            entry: dict[str, Any] = {"name": name, "text": text, "traits": []}
            action = re.match(r"^\*\*(Single Action|Two Actions|Three Actions|Reaction|Free Action)\*\*\s*", text, flags=re.I)
            if action:
                entry["actions"] = {
                    "single action": "one", "two actions": "two", "three actions": "three",
                    "reaction": "reaction", "free action": "free",
                }[action.group(1).lower()]
                text = text[action.end():].strip()
            traits = re.match(r"^\(((?:\[[^\]]+\]\([^)]+\)|[^()])*)\)\s*", text)
            trait_labels = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", traits.group(1)) if traits else ""
            if traits and all(re.fullmatch(r"[A-Za-z-]+", part.strip()) for part in trait_labels.split(",")):
                entry["traits"] = [part.strip().lower() for part in trait_labels.split(",")]
                text = text[traits.end():].strip()
            entry["text"] = text
            abilities.append(entry)
    return abilities


def foundry_details(record: dict[str, Any], kind: str) -> dict[str, Any]:
    system = record.get("system") or {}
    attrs = system.get("attributes") or {}
    result: dict[str, Any] = {}
    if kind == "Hazard":
        stealth = plain((attrs.get("stealth") or {}).get("details"))
        if stealth:
            result["stealthDetails"] = stealth
    raw_immunities = [
        immunity_name(str(value["type"]))
        for value in attrs.get("immunities") or []
        if isinstance(value, dict) and value.get("type")
    ]
    if raw_immunities:
        # Hazards and vehicles with object defenses use the standard object
        # immunities even when the source's internal actor omits that label.
        if kind == "Hazard" and {"critical hits", "precision damage"}.issubset(raw_immunities) and "object immunities" not in raw_immunities:
            raw_immunities.insert(0, "object immunities")
        result["immunities"] = raw_immunities

    for key in ("weaknesses", "resistances"):
        values = []
        for value in attrs.get(key) or []:
            if isinstance(value, dict) and value.get("type") and value.get("value"):
                values.append(f"{immunity_name(str(value['type']))} {value['value']}")
        if key == "weaknesses":
            for item in record.get("items") or []:
                for rule in (item.get("system") or {}).get("rules") or []:
                    if isinstance(rule, dict) and rule.get("key") == "Weakness" and rule.get("type") and rule.get("value"):
                        note = " until broken" if "self:condition:broken" in str(rule.get("predicate")) else ""
                        values.append(f"{immunity_name(str(rule['type']))} {rule['value']}{note}")
        if values:
            result[key] = ", ".join(dict.fromkeys(values))
    return result


def aon_details(record: dict[str, Any]) -> dict[str, Any]:
    markdown = str(record.get("markdown") or "")
    result: dict[str, Any] = {}
    source_page = re.search(r"\*\*Source\*\*[^\n]+\bpg\.\s*(\d+)\b", markdown)
    if source_page:
        result["page"] = int(source_page.group(1))
    immunity = record.get("immunity") or []
    if immunity:
        result["immunities"] = [plain(value) for value in immunity if plain(value)]
    for key in ("weaknesses", "resistances"):
        label = "Weaknesses" if key == "weaknesses" else "Resistances"
        match = re.search(rf"\*\*{label}\*\*\s*([^\n<]+)", markdown, flags=re.I)
        if match:
            value = clean_markup(match.group(1)).strip()
            result[key] = re.sub(r"^(\d+)\s+([a-z]+)\b", r"\2 \1", value)
    abilities = ability_entries(markdown)
    if abilities:
        result["abilities"] = abilities
    hp = re.search(r"\*\*HP\*\*\s*\d+\s*\(BT\s*(\d+)\)", markdown, flags=re.I)
    if hp:
        result["bt"] = int(hp.group(1))
    return result


def build() -> dict[str, dict[str, Any]]:
    foundry = find_foundry_records()
    aon = find_aon_vehicles()
    result: dict[str, dict[str, Any]] = {}
    for kind, filename in (("Hazard", "hazards.json"), ("Vehicle", "vehicles.json")):
        for path in (WORK / "structured-modules").glob(f"*/{filename}"):
            for record in json.loads(path.read_text()):
                attrs = record.get("attributes") or {}
                candidates = foundry.get(str(attrs.get("foundryId")), [])
                source = next((candidate for candidate in candidates if candidate.get("name") == record.get("name")), None)
                if source:
                    fields = foundry_details(source, kind)
                elif kind == "Vehicle":
                    other = aon.get(str(attrs.get("aonId")))
                    if not other:
                        raise ValueError(f"no reviewed vehicle source for {record['slug']}")
                    fields = aon_details(other)
                else:
                    raise ValueError(f"no reviewed hazard source for {record['slug']}")
                hp = (record.get("data") or {}).get("hp") or {}
                value = hp.get("value")
                if "bt" not in fields and isinstance(value, int) and value >= 2:
                    fields["bt"] = value // 2
                if fields:
                    # The printed vehicle entries are authoritative where
                    # Foundry encodes a different shorthand for immunities.
                    if record["slug"] == "airship-gm-core":
                        fields["immunities"] = ["critical hits", "object immunities", "precision damage"]
                    if record["slug"] == "adaptable-paddleboat-guns-and-gears-remastered":
                        fields["immunities"] = ["object immunities"]
                    result[record["slug"]] = fields
    return dict(sorted(result.items()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=REPO / "compendium/hazard-vehicle-details.json")
    args = parser.parse_args()
    details = build()
    args.output.write_text(json.dumps(details, ensure_ascii=False, indent=2) + "\n")
    print(f"Collected reviewed mechanics for {len(details)} hazard and vehicle records")


if __name__ == "__main__":
    main()
