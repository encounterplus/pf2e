#!/usr/bin/env python3
"""Build linked creature spell and ritual lists from licensed source data.

Older source packs carry complete embedded spellcasting entries in the PF2E
Foundry data. Newer source packs are imported from the structured AoN feed and
carry the same stat-block lists in their source markdown. This tool converts
both shapes into the small, source-independent structure rendered by
Encounter+ and writes a deterministic catalog consumed by the public builders.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[1]
DEFAULT_STAGING = REPO.parent / "structured-modules"
DEFAULT_FOUNDRY = REPO.parent / "foundry-pf2e" / "packs" / "pf2e"
DEFAULT_AON = REPO / "reference" / "aon-orc-sources"
DEFAULT_OUTPUT = REPO / "tools" / "creature-spellcasting.json"

SOURCE_ID = re.compile(r"\.Item\.([A-Za-z0-9]+)$")
AON_ROUTE = re.compile(r"/(Spells|Rituals)\.aspx\?ID=(\d+)", re.I)
HEADING = re.compile(r"\*\*([^*\n]*(?:Spells|Rituals))\*\*([^\n]*)", re.I)
RANK_LINE = re.compile(r"(?:^|\n)-\s*\*\*([^*]+)\*\*\s*\n", re.M)
LINK = re.compile(r"\[([^\]]+)\]\((/(?:Spells|Rituals)\.aspx\?ID=\d+)\)", re.I)
QUALIFIER = re.compile(r"\(([^()]*)\)")
AT_WILL = re.compile(r"\bat[ -]?will\b", re.I)
CONSTANT = re.compile(r"\bconstant\b", re.I)
DC = re.compile(r"\bDC\s*(\d+)\b", re.I)
ATTACK = re.compile(r"\battack\s*\+?(\d+)\b", re.I)
FOCUS_POINTS = re.compile(r"\b(\d+)\s+Focus Points?\b", re.I)
ORDINAL = re.compile(r"\b(\d+)(?:st|nd|rd|th)\b", re.I)
PAREN_RANK = re.compile(r"\((\d+)(?:st|nd|rd|th)\)", re.I)
EXPECTED_DISPLAY_ONLY = {
    ("crystal-strider-rage-of-elements", "Chromatic Ray (Release Light)"),
    ("jann-shuyookh-rage-of-elements", "Wall of Water"),
    ("stone-lion-cub-monster-core-2", "Detect Alignment (At Will) (Evil Only)"),
    ("tantriog-rage-of-elements", "Wall of Water"),
    ("urdefhan-tormentor-monster-core-2", "Daemonic Pact"),
    ("wood-scamp-rage-of-elements", "Verdant Sprout"),
}
ABILITY_GRANTED_SPELL_QUALIFIERS = {"echo the past"}


def compact_repeated_spells(spells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse identical prepared slots into one editable ``×N`` entry."""
    compacted: list[dict[str, Any]] = []
    positions: dict[tuple[Any, ...], int] = {}
    counts: dict[tuple[Any, ...], int] = {}
    for spell in spells:
        key = (
            spell.get("name"),
            spell.get("rank"),
            spell.get("reference"),
            bool(spell.get("atWill")),
            spell.get("details"),
        )
        if key not in positions:
            positions[key] = len(compacted)
            counts[key] = 1
            compacted.append(dict(spell))
            continue
        counts[key] += 1

    for key, count in counts.items():
        if count < 2:
            continue
        entry = compacted[positions[key]]
        details = str(entry.get("details") or "")
        entry["details"] = "; ".join(filter(None, (details, f"×{count}")))
    return compacted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, default=DEFAULT_STAGING)
    parser.add_argument("--foundry", type=Path, default=DEFAULT_FOUNDRY)
    parser.add_argument("--aon", type=Path, default=DEFAULT_AON)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def normalize_name(value: str) -> str:
    value = value.casefold().replace("’", "'")
    value = re.sub(r"\([^)]*(?:at[ -]?will|constant|dc\s*\d+)[^)]*\)", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def rank_label(rank: int) -> str:
    if 10 <= rank % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")
    return f"{rank}{suffix}"


def route_record(record: dict[str, Any], kind: str) -> dict[str, str]:
    return {
        "kind": kind,
        "name": str(record.get("name") or ""),
        "route": f"/{kind.casefold()}/{record['slug']}",
        "source": str(record.get("attributes", {}).get("sourceId") or ""),
        "remaster": str(bool(record.get("attributes", {}).get("remaster"))).lower(),
    }


def build_reference_indexes(staging: Path) -> dict[str, Any]:
    foundry: dict[str, dict[str, str]] = {}
    aon: dict[str, dict[str, str]] = {}
    names: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for module in sorted(path for path in staging.iterdir() if path.is_dir()):
        for filename, kind in (("spells.json", "Spell"), ("rituals.json", "Ritual")):
            path = module / filename
            if not path.is_file():
                continue
            for record in json.loads(path.read_text(encoding="utf-8")):
                resolved = route_record(record, kind)
                attributes = record.get("attributes", {})
                foundry_id = str(attributes.get("foundryId") or "")
                if foundry_id:
                    foundry.setdefault(foundry_id, resolved)
                aon_id = str(attributes.get("aonId") or "")
                if aon_id:
                    aon.setdefault(aon_id, resolved)
                names[(kind, normalize_name(resolved["name"]))].append(resolved)
    return {"foundry": foundry, "aon": aon, "names": names}


def choose_name_reference(
    indexes: dict[str, Any], kind: str, name: str, publication: str = ""
) -> dict[str, str] | None:
    candidates = indexes["names"].get((kind, normalize_name(name)), [])
    if not candidates:
        return None
    publication_key = normalize_name(publication)
    return max(
        candidates,
        key=lambda item: (
            bool(publication_key and normalize_name(item["source"]) in publication_key),
            item["remaster"] == "true",
            item["source"] in {"player-core", "player-core-2", "gm-core"},
        ),
    )


def resolve_foundry_spell(spell: dict[str, Any], indexes: dict[str, Any]) -> dict[str, str] | None:
    source = str(spell.get("_stats", {}).get("compendiumSource") or "")
    match = SOURCE_ID.search(source)
    if match and match.group(1) in indexes["foundry"]:
        return indexes["foundry"][match.group(1)]
    system = spell.get("system", {})
    kind = "Ritual" if system.get("ritual") else "Spell"
    return choose_name_reference(
        indexes,
        kind,
        str(spell.get("name") or system.get("slug") or ""),
        str(system.get("publication", {}).get("title") or ""),
    )


def resolve_aon_route(route: str, name: str, indexes: dict[str, Any]) -> dict[str, str] | None:
    match = AON_ROUTE.search(route)
    if not match:
        return None
    kind = "Ritual" if match.group(1).casefold() == "rituals" else "Spell"
    aon_id = f"{kind.casefold()}-{match.group(2)}"
    return indexes["aon"].get(aon_id) or choose_name_reference(indexes, kind, name)


def spell_rank(spell: dict[str, Any], creature_level: int, mode: str) -> int:
    system = spell.get("system", {})
    location = system.get("location") or {}
    traits = system.get("traits", {}).get("value") or []
    if "cantrip" in traits or "focus" in traits or mode == "focus":
        return int(location.get("heightenedLevel") or max(1, min(10, (creature_level + 1) // 2)))
    return int(location.get("heightenedLevel") or system.get("level", {}).get("value") or 0)


def spell_flags(spell: dict[str, Any]) -> tuple[bool, bool, list[str]]:
    name = str(spell.get("name") or "")
    qualifiers = [value.strip() for value in QUALIFIER.findall(name)]
    at_will = any(AT_WILL.search(value) for value in qualifiers)
    constant = any(CONSTANT.search(value) for value in qualifiers)
    details = [
        value
        for value in qualifiers
        if not AT_WILL.search(value) and not CONSTANT.search(value) and not DC.search(value)
    ]
    uses = (spell.get("system", {}).get("location") or {}).get("uses") or {}
    maximum = int(uses.get("max") or 0)
    if maximum >= 99:
        at_will = True
    elif maximum > 1:
        details.append(f"×{maximum}")
    return at_will, constant, details


def is_ability_granted_spell(spell: dict[str, Any]) -> bool:
    """Keep spells listed inside a bespoke ability out of the casting summary."""
    _, _, details = spell_flags(spell)
    return any(normalize_name(value) in ABILITY_GRANTED_SPELL_QUALIFIERS for value in details)


def linked_entry(
    spell: dict[str, Any], indexes: dict[str, Any], rank: int
) -> tuple[dict[str, Any], bool]:
    reference = resolve_foundry_spell(spell, indexes)
    at_will, _, details = spell_flags(spell)
    result: dict[str, Any] = {
        "name": reference["name"] if reference else str(spell.get("name") or "Unknown spell"),
        "rank": rank,
    }
    if reference:
        result["reference"] = reference["route"]
    if at_will:
        result["atWill"] = True
    if details:
        result["details"] = "; ".join(dict.fromkeys(details))
    return result, reference is not None


def group_label(mode: str, rank: int, slots: int = 0) -> str:
    label = rank_label(rank)
    if slots and mode in {"prepared", "spontaneous"}:
        label += f" ({slots} slot{'s' if slots != 1 else ''})"
    return label


def actor_spellcasting(
    actor: dict[str, Any], indexes: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, int]]:
    items = [item for item in actor.get("items", []) if isinstance(item, dict)]
    entries = [item for item in items if item.get("type") == "spellcastingEntry"]
    spells = [item for item in items if item.get("type") == "spell"]
    by_id = {str(item.get("_id")): item for item in spells}
    by_location: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rituals: list[dict[str, Any]] = []
    for spell in spells:
        location = str((spell.get("system", {}).get("location") or {}).get("value") or "")
        # Some older actors place ordinary spells in a folder named
        # "rituals". Only the spell's actual ritual data is authoritative;
        # otherwise entries such as Darkness or Cursed Metamorphosis are
        # incorrectly published as rituals.
        if spell.get("system", {}).get("ritual"):
            rituals.append(spell)
        elif location:
            by_location[location].append(spell)

    creature_level = int(actor.get("system", {}).get("details", {}).get("level", {}).get("value") or 0)
    focus_points = int(actor.get("system", {}).get("resources", {}).get("focus", {}).get("max") or 0)
    converted: list[dict[str, Any]] = []
    stats = {"linked": 0, "unresolved": 0, "spells": 0, "rituals": 0}

    for entry in sorted(entries, key=lambda item: int(item.get("sort") or 0)):
        entry_id = str(entry.get("_id") or "")
        system = entry.get("system", {})
        mode = str(system.get("prepared", {}).get("value") or "")
        entry_spells = sorted(
            (
                spell
                for spell in by_location.get(entry_id, [])
                if not is_ability_granted_spell(spell)
            ),
            key=lambda item: int(item.get("sort") or 0),
        )
        slots = system.get("slots") or {}
        grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)

        if mode == "prepared" and any(slot.get("prepared") for slot in slots.values()):
            used_ids: set[str] = set()
            for slot_name, slot in sorted(slots.items(), key=lambda item: int(re.sub(r"\D", "", item[0]) or 0), reverse=True):
                slot_rank = int(re.sub(r"\D", "", slot_name) or 0)
                for prepared in slot.get("prepared") or []:
                    spell = by_id.get(str(prepared.get("id") or ""))
                    if not spell:
                        continue
                    used_ids.add(str(spell.get("_id") or ""))
                    rank = spell_rank(spell, creature_level, mode) if slot_rank == 0 else slot_rank
                    key = ("cantrip", rank) if slot_rank == 0 else ("rank", rank)
                    linked, ok = linked_entry(spell, indexes, rank)
                    grouped[key].append(linked)
                    stats["linked" if ok else "unresolved"] += 1
                    stats["spells"] += 1
            for spell in entry_spells:
                if str(spell.get("_id") or "") in used_ids:
                    continue
                traits = spell.get("system", {}).get("traits", {}).get("value") or []
                if "cantrip" not in traits and "focus" not in traits:
                    continue
                rank = spell_rank(spell, creature_level, mode)
                linked, ok = linked_entry(spell, indexes, rank)
                grouped[("cantrip", rank)].append(linked)
                stats["linked" if ok else "unresolved"] += 1
                stats["spells"] += 1
        else:
            for spell in entry_spells:
                traits = spell.get("system", {}).get("traits", {}).get("value") or []
                rank = spell_rank(spell, creature_level, mode)
                _, constant, _ = spell_flags(spell)
                if constant:
                    key = ("constant", rank)
                elif "cantrip" in traits:
                    key = ("cantrip", rank)
                elif mode == "focus" or "focus" in traits:
                    key = ("focus", rank)
                else:
                    key = ("rank", rank)
                linked, ok = linked_entry(spell, indexes, rank)
                grouped[key].append(linked)
                stats["linked" if ok else "unresolved"] += 1
                stats["spells"] += 1

        spell_groups: list[dict[str, Any]] = []
        ordered_keys = sorted(
            grouped,
            key=lambda key: (
                {"rank": 0, "cantrip": 1, "focus": 1, "constant": 2}.get(key[0], 3),
                -key[1],
            ),
        )
        for kind, rank in ordered_keys:
            if kind == "cantrip":
                label = f"Cantrips ({rank_label(rank)})"
            elif kind == "focus":
                label = f"Focus Spells ({rank_label(rank)})"
            elif kind == "constant":
                label = f"Constant ({rank_label(rank)})"
            else:
                slot = slots.get(f"slot{rank}") or {}
                label = group_label(mode, rank, int(slot.get("max") or 0))
            spell_groups.append(
                {
                    "label": label,
                    "spells": compact_repeated_spells(grouped[(kind, rank)]),
                }
            )

        if not spell_groups:
            continue
        spelldc = system.get("spelldc") or {}
        converted_entry: dict[str, Any] = {
            "name": str(entry.get("name") or "Spellcasting"),
            "spellGroups": spell_groups,
        }
        if spelldc.get("dc") is not None:
            converted_entry["spellDC"] = int(spelldc["dc"])
        if spelldc.get("value") is not None:
            converted_entry["spellAttack"] = int(spelldc["value"])
        if mode == "focus" and focus_points:
            converted_entry["focusPoints"] = focus_points
        converted.append(converted_entry)

    ritual_data: dict[str, Any] | None = None
    if rituals:
        ritual_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
        dcs: set[int] = set()
        for ritual in sorted(rituals, key=lambda item: int(item.get("sort") or 0)):
            name = str(ritual.get("name") or "")
            dcs.update(int(value) for value in DC.findall(name))
            rank = int(ritual.get("system", {}).get("level", {}).get("value") or 0)
            linked, ok = linked_entry(ritual, indexes, rank)
            ritual_groups[rank].append(linked)
            stats["linked" if ok else "unresolved"] += 1
            stats["rituals"] += 1
        ritual_data = {
            "type": "Rituals",
            "ritualGroups": [
                {"label": rank_label(rank), "rituals": ritual_groups[rank]}
                for rank in sorted(ritual_groups, reverse=True)
            ],
        }
        if len(dcs) == 1:
            ritual_data["dc"] = next(iter(dcs))
    return converted, ritual_data, stats


def section_end(markdown: str, start: int) -> int:
    candidates = [len(markdown)]
    for pattern in (r"\n\n\*\*[^*\n]+\*\*", r"\n\s*---\s*\n", r"\n</column>"):
        match = re.search(pattern, markdown[start:])
        if match:
            candidates.append(start + match.start())
    return min(candidates)


def parse_rank(value: str) -> int:
    match = ORDINAL.search(value) or PAREN_RANK.search(value)
    return int(match.group(1)) if match else 0


def aon_spellcasting(
    record: dict[str, Any], indexes: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, int]]:
    markdown = str(record.get("markdown") or "")
    spellcasting: list[dict[str, Any]] = []
    ritual_sets: list[dict[str, Any]] = []
    stats = {"linked": 0, "unresolved": 0, "spells": 0, "rituals": 0}
    for heading in HEADING.finditer(markdown):
        name = heading.group(1).strip()
        meta = heading.group(2).strip()
        body = markdown[heading.end():section_end(markdown, heading.end())]
        rank_matches = list(RANK_LINE.finditer(body))
        groups: list[dict[str, Any]] = []
        for index, rank_match in enumerate(rank_matches):
            label = rank_match.group(1).strip()
            content_end = rank_matches[index + 1].start() if index + 1 < len(rank_matches) else len(body)
            content = body[rank_match.end():content_end]
            rank = parse_rank(label)
            entries: list[dict[str, Any]] = []
            links = list(LINK.finditer(content))
            for link_index, link in enumerate(links):
                tail_end = links[link_index + 1].start() if link_index + 1 < len(links) else len(content)
                tail = content[link.end():tail_end].strip(" ,;\n")
                reference = resolve_aon_route(link.group(2), link.group(1), indexes)
                item: dict[str, Any] = {
                    "name": reference["name"] if reference else link.group(1),
                    "rank": rank,
                }
                if reference:
                    item["reference"] = reference["route"]
                    stats["linked"] += 1
                else:
                    stats["unresolved"] += 1
                qualifiers = [value.strip() for value in QUALIFIER.findall(tail)]
                at_will = any(AT_WILL.search(value) for value in qualifiers)
                qualifiers = [
                    AT_WILL.sub("", value).strip(" ;,")
                    for value in qualifiers
                    if not (AT_WILL.fullmatch(value.strip()) or CONSTANT.fullmatch(value.strip()))
                ]
                qualifiers = [value for value in qualifiers if value]
                if at_will:
                    item["atWill"] = True
                if qualifiers:
                    item["details"] = "; ".join(qualifiers)
                entries.append(item)
            if entries:
                groups.append({"label": label, "entries": entries})
        if not groups:
            continue
        dc_match = DC.search(meta)
        attack_match = ATTACK.search(meta)
        focus_match = FOCUS_POINTS.search(meta)
        if "ritual" in name.casefold():
            ritual_set: dict[str, Any] = {
                "type": name,
                "ritualGroups": [
                    {"label": group["label"], "rituals": group["entries"]}
                    for group in groups
                ],
            }
            if dc_match:
                ritual_set["dc"] = int(dc_match.group(1))
            ritual_sets.append(ritual_set)
            stats["rituals"] += sum(len(group["entries"]) for group in groups)
        else:
            entry: dict[str, Any] = {
                "name": name,
                "spellGroups": [
                    {"label": group["label"], "spells": group["entries"]}
                    for group in groups
                ],
            }
            if dc_match:
                entry["spellDC"] = int(dc_match.group(1))
            if attack_match:
                entry["spellAttack"] = int(attack_match.group(1))
            if focus_match:
                entry["focusPoints"] = int(focus_match.group(1))
            spellcasting.append(entry)
            stats["spells"] += sum(len(group["entries"]) for group in groups)
    ritual_data: dict[str, Any] | None = None
    if ritual_sets:
        ritual_data = ritual_sets[0]
        for extra in ritual_sets[1:]:
            ritual_data["ritualGroups"].extend(extra["ritualGroups"])
    return spellcasting, ritual_data, stats


def actor_index(foundry: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(foundry.rglob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and value.get("type") == "npc" and value.get("_id"):
            result[str(value["_id"])].append(value)
    return result


def aon_index(aon: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(aon.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for record in payload.get("records", []):
            if record.get("category") == "creature" and record.get("id"):
                result[str(record["id"])] = record
    return result


def staging_creatures(staging: Path) -> Iterable[dict[str, Any]]:
    for path in sorted(staging.glob("*/creatures.json")):
        yield from json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    indexes = build_reference_indexes(args.staging)
    actors = actor_index(args.foundry)
    aon_records = aon_index(args.aon)
    catalog: dict[str, dict[str, Any]] = {}

    for creature in staging_creatures(args.staging):
        attributes = creature.get("attributes", {})
        foundry_id = str(attributes.get("foundryId") or "")
        spellcasting: list[dict[str, Any]] = []
        rituals: dict[str, Any] | None = None
        if foundry_id and foundry_id in actors:
            candidates = actors[foundry_id]
            actor = next(
                (value for value in candidates if value.get("name") == creature.get("name")),
                candidates[0],
            )
            spellcasting, rituals, _ = actor_spellcasting(actor, indexes)
        else:
            aon_id = str(attributes.get("aonId") or "")
            if aon_id in aon_records:
                spellcasting, rituals, _ = aon_spellcasting(aon_records[aon_id], indexes)
        if not spellcasting and not rituals:
            continue
        value: dict[str, Any] = {}
        if spellcasting:
            value["spellcasting"] = spellcasting
        if rituals:
            value["rituals"] = rituals
        catalog[str(creature["slug"])] = value

    # Report the compact entries that users actually receive, rather than raw
    # prepared slots consumed while building the catalog.
    totals = defaultdict(int)
    totals["creatures"] = len(catalog)
    for configured in catalog.values():
        entries = [
            spell
            for casting in configured.get("spellcasting", [])
            for group in casting.get("spellGroups", [])
            for spell in group.get("spells", [])
        ]
        ritual_entries = [
            ritual
            for group in configured.get("rituals", {}).get("ritualGroups", [])
            for ritual in group.get("rituals", [])
        ]
        totals["spells"] += len(entries)
        totals["rituals"] += len(ritual_entries)
        for entry in [*entries, *ritual_entries]:
            totals["linked" if entry.get("reference") else "unresolved"] += 1

    output = {
        "stats": dict(sorted(totals.items())),
        "creatures": dict(sorted(catalog.items())),
    }
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["stats"], sort_keys=True))
    display_only: set[tuple[str, str]] = set()
    for slug, configured in catalog.items():
        entries = [
            spell
            for casting in configured.get("spellcasting", [])
            for group in casting.get("spellGroups", [])
            for spell in group.get("spells", [])
        ]
        entries.extend(
            ritual
            for group in configured.get("rituals", {}).get("ritualGroups", [])
            for ritual in group.get("rituals", [])
        )
        display_only.update(
            (slug, str(entry.get("name") or ""))
            for entry in entries
            if not entry.get("reference")
        )
    if display_only != EXPECTED_DISPLAY_ONLY:
        print(
            "Unexpected display-only creature spells: "
            + json.dumps(sorted(display_only), ensure_ascii=False)
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
