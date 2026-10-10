"""Small, reviewed mechanics supplements for the published hazard/vehicle packs.

Strikes come from the corresponding ORC-compatible hazard records in the
Pathfinder 2e Foundry source.  Their narrative descriptions are not copied.
The fixture is keyed by the unique published slug, never by a fuzzy name.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any


STRIKES = json.loads(
    (Path(__file__).resolve().parents[1] / "compendium/hazard-strikes.json").read_text()
)
DETAILS = json.loads(
    (Path(__file__).resolve().parents[1] / "compendium/hazard-vehicle-details.json").read_text()
)
HAZARD_SUMMARIES = json.loads(
    (Path(__file__).resolve().parents[1] / "compendium/hazard-summaries.json").read_text()
)
VEHICLE_SUMMARIES = json.loads(
    (Path(__file__).resolve().parents[1] / "compendium/vehicle-summaries.json").read_text()
)
VERIFIED_PAGES = {"ghostly-choir-gm-core": 102, "airship-gm-core": 213}
CONDITION_ROUTES = {
    entry["name"]: f"/condition/{entry['slug']}"
    for entry in json.loads((Path(__file__).resolve().parents[1] / "compendium/packs/player-core/conditions.json").read_text())
    if ":" not in entry["name"]
}
VALUED_CONDITION_ROUTES = {
    entry["name"].lower(): f"/condition/{entry['slug']}"
    for entry in json.loads((Path(__file__).resolve().parents[1] / "compendium/packs/player-core/conditions.json").read_text())
    if entry.get("data", {}).get("valued") and ":" not in entry["name"]
}
CONDITION_MENTIONS = re.compile(
    r"(?<![\w/])(" + "|".join(re.escape(name) for name in sorted(CONDITION_ROUTES, key=len, reverse=True)) + r")(?:\s+\d+)?\b"
)
VALUED_MENTIONS = re.compile(
    r"(?<![\w/])(" + "|".join(re.escape(name) for name in sorted(VALUED_CONDITION_ROUTES, key=len, reverse=True)) + r")\s+\d+\b",
    re.I,
)
MARKDOWN_LINKS = re.compile(r"(\[[^\]]+\]\([^)]+\))")


def link_condition_mentions(text: str) -> str:
    """Link explicit condition names, without nesting links inside existing ones."""
    def linked(match: re.Match[str]) -> str:
        return f"[{match.group()}]({CONDITION_ROUTES[match.group(1)]})"

    linked_names = "".join(
        part if index % 2 else CONDITION_MENTIONS.sub(linked, part)
        for index, part in enumerate(MARKDOWN_LINKS.split(text))
    )
    linked_values = "".join(
        part if index % 2 else VALUED_MENTIONS.sub(
            lambda match: f"[{match.group()}]({VALUED_CONDITION_ROUTES[match.group(1).lower()]})", part
        )
        for index, part in enumerate(MARKDOWN_LINKS.split(linked_names))
    )

    # If the source explicitly linked a valued condition once, keep later
    # lowercase mentions clickable too (for example “Clumsy 1 … clumsy
    # condition”). These repeats are often the exact adjudication reference a
    # GM needs, and hazards deliberately do not deduplicate them.
    repeated: dict[str, str] = {}
    for label, route in re.findall(r"\[([^\]]+)\]((?:\(/condition/[^)]+\)))", linked_values):
        base = re.sub(r"\s+\d+\s*$", "", label).strip()
        repeated[base.casefold()] = route[1:-1]

    def link_repeats(part: str) -> str:
        for label, route in sorted(repeated.items(), key=lambda item: -len(item[0])):
            part = re.sub(
                rf"(?<![\w/]){re.escape(label)}(?![\w])",
                lambda match: f"[{match.group()}]({route})",
                part,
                flags=re.I,
            )
        return part

    return "".join(
        part if index % 2 else link_repeats(part)
        for index, part in enumerate(MARKDOWN_LINKS.split(linked_values))
    )


def supplement(entity: dict[str, Any], kind: str) -> None:
    data = entity.get("data")
    if not isinstance(data, dict):
        return
    slug = entity.get("slug")
    details = DETAILS.get(slug, {})
    sources = entity.get("sources")
    if isinstance(sources, list) and sources and isinstance(sources[0], dict):
        page = details.get("page", VERIFIED_PAGES.get(slug))
        if page:
            sources[0].setdefault("page", page)
    for key in ("stealthDetails", "immunities", "weaknesses", "resistances"):
        if key in details and not data.get(key):
            data[key] = copy.deepcopy(details[key])
    if "bt" in details and isinstance(data.get("hp"), dict):
        data["hp"].setdefault("bt", details["bt"])
    if kind == "Hazard":
        if slug in HAZARD_SUMMARIES and not data.get("description"):
            data["description"] = HAZARD_SUMMARIES[slug]
        if data.get("complexity", "").lower() == "simple" and isinstance(data.get("stealth"), (int, float)) and data["stealth"] != 0:
            data.setdefault("stealthDC", data["stealth"] + 10)
        for ability in data.get("abilities", []):
            if isinstance(ability, dict) and isinstance(ability.get("text"), str):
                ability["text"] = link_condition_mentions(ability["text"].replace("\n\n---\n\n", "\n\n"))
        for field in ("routine", "reset"):
            if isinstance(data.get(field), str):
                data[field] = link_condition_mentions(data[field])
        strikes = STRIKES.get(slug)
        if strikes and not data.get("attacks"):
            data["attacks"] = copy.deepcopy(strikes)
    elif kind == "Vehicle":
        if slug in VEHICLE_SUMMARIES and not data.get("description"):
            data["description"] = VEHICLE_SUMMARIES[slug]
        if details.get("abilities") and not data.get("abilities"):
            data["abilities"] = copy.deepcopy(details["abilities"])
        for ability in data.get("abilities", []):
            if isinstance(ability, dict) and isinstance(ability.get("text"), str):
                ability["text"] = link_condition_mentions(ability["text"])
        price = data.get("price")
        if isinstance(price, (int, float)) and not isinstance(price, bool):
            if price > 0:
                data["price"] = f"{price:,} gp"
            else:
                # Zero in these records denotes an unspecified price, not a
                # free vehicle.  Do not suggest a false market value.
                data["price"] = ""
