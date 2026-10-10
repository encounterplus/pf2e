"""Expose explicitly printed item rules without guessing prose mechanics."""

from __future__ import annotations

import re
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from collections.abc import Collection

from creature_editor_data import parse_ability_editor_fields, split_entries


ACTIVATE = re.compile(r"(?m)^[ \t]*\*\*Activate(?P<name>\s*[—–:-]\s*[^*\n]+)?\*\*")
HEADING = re.compile(r"(?m)^#{1,6}\s+([^\n]+)$")
DIVIDER = re.compile(r"(?m)^---+[ \t]*$")
ITEM_PROPERTY = re.compile(
    r"(?m)^\*\*(?:Usage|Bulk|Price|Access|Onset|Saving Throw|Maximum Duration|"
    r"Craft Requirements|Ammunition|Type|Category|Level)\*\*"
)
COST = re.compile(
    r"^(?P<bold>\*\*|)(?P<cost>Single Action|One Action|Two Actions|Three Actions|"
    r"Free Action|Reaction|[123ADTRFfr])(?P=bold)(?=\s|[;(]|$)"
)
ACTION_CODES = {
    "Single Action": "one", "One Action": "one", "Two Actions": "two",
    "Three Actions": "three", "Free Action": "free", "Reaction": "reaction",
    "1": "one", "2": "two", "3": "three", "A": "one", "D": "two",
    "T": "three", "R": "reaction", "F": "free", "f": "free", "r": "reaction",
}
TRAIT_LINK = re.compile(r"^\[([^]]+)\]\(/trait/([a-z0-9-]+)\)$")
METHOD = re.compile(r"^(Cast [Aa] Spell|Interact|Command|Envision|Strike)(?=\s|;|$)")
CRAFTING = re.compile(r"(?m)^\*\*Craft Requirements\*\*")
PROPERTY_LINE = re.compile(r"(?m)^[ \t]*\*\*[A-Z][^*\n]*\*\*")
SHIELD_TABLE = re.compile(r"(?m)^\|\s*Hardness\s*\|\s*HP\s*\|\s*BT\s*\|")


@lru_cache(maxsize=1)
def known_traits() -> frozenset[str]:
    packs = Path(__file__).resolve().parents[1] / "compendium" / "packs"
    return frozenset(
        str(record["slug"])
        for path in packs.glob("*/traits.json")
        for record in json.loads(path.read_text())
    )


@dataclass(frozen=True)
class ActivationBlock:
    start: int
    end: int
    original: str
    fields: dict[str, Any]


def _label(value: str) -> str:
    return " ".join(value.replace("*", "").replace("_", "").casefold().split())


def _metadata(value: str, trait_slugs: Collection[str]) -> tuple[dict[str, Any], str]:
    fields: dict[str, Any] = {}
    rest = value.strip()
    # Empty bold markup occurs where the source had no fixed action glyph.
    if rest.startswith("****"):
        rest = rest[4:].lstrip()
    cost = COST.match(rest)
    if cost and not re.match(
        r"\s*(?:or\b|to\b|seconds?\b|minutes?\b|hours?\b|days?\b)", rest[cost.end():], re.I
    ):
        fields["actions"] = ACTION_CODES[cost["cost"]]
        rest = rest[cost.end():].lstrip()
    if rest.startswith("(") and ")" in rest:
        end = rest.index(")")
        # Linked traits have their own closing parentheses.
        depth = 0
        for index, char in enumerate(rest):
            depth += char == "("
            depth -= char == ")"
            if depth == 0:
                end = index
                break
        traits: list[str] = []
        for part in split_entries(rest[1:end]):
            linked = TRAIT_LINK.fullmatch(part)
            slug = linked[2] if linked else part
            if slug not in trait_slugs:
                traits = []
                break
            traits.append(slug)
        if traits:
            fields["traits"] = traits
            rest = rest[end + 1:].lstrip(" ;\t\n")
    return fields, rest.strip()


def parse_item_activations(description: str, name: str, trait_slugs: Collection[str] | None = None) -> list[ActivationBlock]:
    """Only root blocks and exact-name variant blocks belong to this item."""
    trait_slugs = known_traits() if trait_slugs is None else trait_slugs
    headings = list(HEADING.finditer(description))
    activations = list(ACTIVATE.finditer(description))
    divider = DIVIDER.search(description)
    result: list[ActivationBlock] = []
    for index, match in enumerate(activations):
        previous_heading = next((h for h in reversed(headings) if h.start() < match.start()), None)
        if previous_heading and _label(previous_heading[1]) != _label(name):
            continue
        end = activations[index + 1].start() if index + 1 < len(activations) else len(description)
        next_heading = next((h for h in headings if h.start() > match.start()), None)
        if next_heading:
            end = min(end, next_heading.start())
        crafting = CRAFTING.search(description, match.end(), end)
        if crafting:
            end = crafting.start()
        shield_table = SHIELD_TABLE.search(description, match.end(), end)
        if shield_table:
            end = shield_table.start()
            separators = list(DIVIDER.finditer(description, match.end(), end))
            if separators and not description[separators[-1].end():end].strip():
                end = separators[-1].start()
        named = re.sub(r"^\s*[—–:-]\s*", "", match["name"] or "").strip()
        # An equipment-header Activate property precedes the first divider.
        # Its following general item prose is not an explicitly labeled Effect.
        if not named and divider and match.start() < divider.start() < end:
            before_divider = description[match.end():divider.start()]
            if "**Effect**" not in before_divider:
                end = divider.start()
                prop = ITEM_PROPERTY.search(description, match.end(), end)
                if prop:
                    end = prop.start()
        fields, body = _metadata(description[match.end():end], trait_slugs)
        if not fields and not body and not named:
            continue
        fields["name"] = named
        fields["text"] = body
        fields.update(parse_ability_editor_fields(body))
        result.append(ActivationBlock(match.start(), end, description[match.start():end], fields))
    return result


def configure_item_crafting_data(entity: dict[str, Any]) -> bool:
    """Move explicit root/exact-variant requirements into their editable field.

    Keep other variants and following labeled properties/dividers in general
    prose. Explicit GM settings, including a cleared field, take precedence.
    """
    data = entity["data"]
    if "craftRequirements" in data:
        return False
    description = str(entity.get("descr") or "")
    headings = list(HEADING.finditer(description))
    spans: list[tuple[int, int]] = []
    requirements: list[str] = []
    for match in CRAFTING.finditer(description):
        previous_heading = next((h for h in reversed(headings) if h.start() < match.start()), None)
        if previous_heading and _label(previous_heading[1]) != _label(str(entity.get("name") or "")):
            continue
        end = len(description)
        for boundary in (HEADING, DIVIDER, PROPERTY_LINE):
            following = boundary.search(description, match.end())
            if following:
                end = min(end, following.start())
        text = description[match.end():end].strip()
        if not text:
            continue
        requirements.append(text)
        spans.append((match.start(), end))
    if not spans:
        return False
    pieces: list[str] = []
    cursor = 0
    for start, end in spans:
        pieces.append(description[cursor:start])
        cursor = end
    pieces.append(description[cursor:])
    data["craftRequirements"] = "\n\n".join(requirements)
    entity["descr"] = re.sub(r"\n{3,}", "\n\n", "".join(pieces)).strip()
    return True


def configure_item_editor_data(entity: dict[str, Any], trait_slugs: Collection[str] | None = None) -> bool:
    """Convert printed fields; preserve explicitly supplied/cleared GM settings."""
    if entity.get("kind") != "Item" or not isinstance(entity.get("data"), dict):
        return False
    data = entity["data"]
    changed = configure_item_crafting_data(entity)
    if "activation" in data or "activations" in data:
        return changed
    description = str(entity.get("descr") or "")
    blocks = parse_item_activations(description, str(entity.get("name") or ""), trait_slugs)
    if not blocks:
        return changed
    additional: list[dict[str, Any]] = []
    for block in blocks:
        fields = dict(block.fields)
        if not fields["name"] and "activation" not in data:
            primary = {key: fields[key] for key in ("actions", "traits") if key in fields}
            body = fields["text"]
            method = METHOD.match(body)
            if method:
                primary["type"] = method[1]
                body = body[method.end():].lstrip(" ;\t\n")
            primary["text"] = body
            data["activation"] = primary
        else:
            if not fields["name"]:
                fields["name"] = f"Activation {len(additional) + 1}"
            additional.append(fields)
    if additional:
        data["activations"] = additional
    pieces: list[str] = []
    cursor = 0
    for block in blocks:
        pieces.append(description[cursor:block.start])
        cursor = block.end
    pieces.append(description[cursor:])
    entity["descr"] = re.sub(r"\n{3,}", "\n\n", "".join(pieces)).strip()
    return True


def main() -> None:
    """Regenerate editor fields after the existing public link-enrichment pass.

    Like other editor/table enrichment tools, this touches only its owned
    collections. Full ORC/OGL builds also call the same conversion function.
    """
    repo = Path(__file__).resolve().parents[1]
    converted = primary = additional = crafting = files = 0
    for root in (repo / "compendium/packs", repo / "compendium/ogl-packs"):
        for path in sorted(root.glob("*/items.json")):
            records = json.loads(path.read_text())
            changed = False
            for item in records:
                if configure_item_editor_data(item):
                    converted += 1
                    primary += bool(item["data"].get("activation"))
                    additional += len(item["data"].get("activations", []))
                    crafting += bool(item["data"].get("craftRequirements"))
                    changed = True
            if changed:
                path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
                files += 1
    print(json.dumps({"convertedItems": converted, "primary": primary, "additional": additional, "crafting": crafting, "files": files}))


if __name__ == "__main__":
    main()
