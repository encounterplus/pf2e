"""Preserve linked deity metadata while rendering the live editable fields."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


FIELDS = {
    "Areas of Concern": "areasOfConcern", "Edicts": "edicts",
    "Anathema": "anathema", "Divine Attribute": "divineAttribute",
    "Divine Font": "clericFont", "Sanctification": "sanctificationOptions",
    "Divine Skill": "divineSkill", "Favored Weapon": "favoredWeapon",
    "Domains": "domains", "Alternate Domains": "alternateDomains",
    "Cleric Spells": "spells",
}
LINK = re.compile(r"\[([^]]+)\]\(([^)]+)\)")


def spell_name(value: str) -> str:
    return " ".join(value.replace("’", "'").casefold().split())


@lru_cache(maxsize=1)
def known_spell_references() -> dict[str, str]:
    """Resolve reviewed published spell names, preferring the core catalog."""
    repo = Path(__file__).resolve().parents[1]
    choices = {}
    for root in (repo / "compendium/packs", repo / "compendium/ogl-packs"):
        for path in sorted(root.glob("*/spells.json")):
            for spell in json.loads(path.read_text()):
                name = spell_name(spell["name"])
                slug = spell["slug"]
                priority = (0 if slug.endswith("-player-core") else 1, slug)
                if name not in choices or priority < choices[name][0]:
                    choices[name] = (priority, f"/spell/{slug}")
    return {name: choice[1] for name, choice in choices.items()}


@lru_cache(maxsize=1)
def known_item_references() -> dict[str, str]:
    """Resolve favored weapons against published items, preferring Player Core."""
    repo = Path(__file__).resolve().parents[1]
    choices = {}
    for root in (repo / "compendium/packs", repo / "compendium/ogl-packs"):
        for path in sorted(root.glob("*/items.json")):
            for item in json.loads(path.read_text()):
                name, slug = spell_name(item["name"]), item["slug"]
                priority = (0 if slug.endswith("-player-core") else 1, slug)
                if name not in choices or priority < choices[name][0]:
                    choices[name] = (priority, f"/item/{slug}")
    return {name: choice[1] for name, choice in choices.items()}


def ranked_spell(value: str) -> str:
    """Format only an explicit supplied rank; never infer a grant's rank."""
    rank = re.match(r"^(\d+)(?:st|nd|rd|th)?:\s*", value)
    if not rank:
        return value
    number = int(rank[1])
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}: " + value[rank.end():]


def linked_value(value: str, links: list[tuple[str, str]]) -> str:
    """Link matching words without changing their text or nesting Markdown."""
    if LINK.search(value):
        return value
    spans: list[tuple[int, int, str]] = []
    for label, route in sorted(links, key=lambda item: -len(item[0])):
        for match in re.finditer(r"(?<!\w)" + re.escape(label) + r"(?!\w)", value, re.I):
            if any(match.start() < end and match.end() > start for start, end, _ in spans):
                continue
            spans.append((match.start(), match.end(), route.strip("<>")))
    for start, end, route in sorted(spans, reverse=True):
        value = value[:start] + f"[{value[start:end]}](<{route}>)" + value[end:]
    return value


def configure_deity_editor_data(entity: dict[str, Any]) -> bool:
    """Derive reference caches from the linked import summary, never GM prose.

    Views use a cache entry only while its value still equals the current field;
    new/edited values render directly, so old rules cannot override an edit.
    """
    if entity.get("kind") != "Deity" or not isinstance(entity.get("data"), dict):
        return False
    data = entity["data"]
    before = json.dumps(entity, sort_keys=True)
    # Native skill text fields need a scalar; older imports may use a list.
    if isinstance(data.get("divineSkill"), list):
        data["divineSkill"] = ", ".join(str(value) for value in data["divineSkill"])
    # One legacy source uses rank -> spell rather than the editor's string list.
    if isinstance(data.get("spells"), dict):
        data["spells"] = [f"{rank}: {spell}" for rank, spell in data["spells"].items()]
    if isinstance(data.get("spells"), list):
        data["spells"] = [ranked_spell(value) for value in data["spells"]]
    links_by_field = {}
    for paragraph in str(data.get("rulesText") or "").split("\n\n"):
        heading = re.match(r"^\*\*([^*]+)\*\*\s*(.*)", paragraph, re.S)
        if heading and heading[1] in FIELDS:
            links_by_field[FIELDS[heading[1]]] = LINK.findall(heading[2])
    # Ranked grants still need catalog links when an import has no summary.
    links_by_field.setdefault("spells", [])
    links_by_field.setdefault("favoredWeapon", [])
    catalog = {}
    keys = {}
    for field, links in links_by_field.items():
        values = data.get(field) or []
        if not isinstance(values, list):
            values = [values]
        entries = []
        for value in dict.fromkeys(str(value) for value in values):
            text = linked_value(value, links)
            if field == "spells":
                name = re.sub(r"^\d+(?:st|nd|rd|th)?:\s*", "", value)
                route = known_spell_references().get(spell_name(name))
                if text == value and route and not LINK.search(value):
                    text = linked_value(value, [(name, route)])
            if field == "favoredWeapon" and text == value and not LINK.search(value):
                route = known_item_references().get(spell_name(value))
                if route:
                    text = linked_value(value, [(value, route)])
            if text != value:
                entries.append({"value": value, "text": text})
        if entries:
            catalog[field] = entries
            keys[field] = [entry["value"] for entry in entries]
    data["deityReferences"] = catalog
    data["deityReferenceKeys"] = keys
    for field in ("edicts", "anathema"):
        text_field = field + "Text"
        if text_field not in data:
            by_value = {entry["value"]: entry["text"] for entry in catalog.get(field, [])}
            data[text_field] = "\n\n".join(by_value.get(value, value) for value in data.get(field, []))
    # A single editable sentence retains can/must and unusual conditional rules.
    if "sanctificationText" not in data and data.get("deitySanctificationFormat") != "text":
        options = data.get("sanctificationOptions") or ([data["sanctification"]] if data.get("sanctification") else [])
        by_value = {entry["value"]: entry["text"] for entry in catalog.get("sanctificationOptions", [])}
        data["sanctificationText"] = " or ".join(by_value.get(value, value) for value in options)
    data["deitySanctificationFormat"] = "text"
    # A cleared text attribute must not resurrect its legacy array values.
    data["deityDirectiveFormat"] = "text"
    # The linked import summary is reference metadata, not editable narrative.
    # Clear only its exact duplicate; preserve any GM-authored description.
    summary = str(data.get("rulesText") or "").strip()
    if summary and str(entity.get("descr") or "").strip() == summary:
        entity["descr"] = ""
    return before != json.dumps(entity, sort_keys=True)


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    count = files = 0
    for path in sorted((repo / "compendium/packs").glob("*/deities.json")):
        records = json.loads(path.read_text())
        changed = sum(configure_deity_editor_data(record) for record in records)
        if changed:
            path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
            files += 1
            count += changed
    print(json.dumps({"deities": count, "collections": files}))


if __name__ == "__main__":
    main()
