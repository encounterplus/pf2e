"""Expose leading printed spell metadata without stripping spell rules."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


FIELDS = {
    "Cast": "cast", "Casting": "cast", "Range": "range", "Area": "area",
    "Target": "targets", "Targets": "targets", "Duration": "durationText",
    "Requirements": "requirements", "Requirement": "requirements",
    "Cost": "cost", "Trigger": "trigger", "Defense": "defense",
    "Saving Throw": "defense", "Traditions": "traditionsText",
    "Tradition": "traditionsText",
}
LABEL = re.compile(r"\*\*([^*\n]+)\*\*[ \t]*\n?")
BOUNDARY = re.compile(r"\n[ \t]*\n|\n(?=\*\*|---)")
LINK = re.compile(r"\[([^]]+)\]\([^\n]+?\)")
DEFENSES = {"fortitude", "reflex", "will", "basicfortitude", "basicreflex", "basicwill"}
UNMAPPED_METADATA = {
    "Deity", "Deities", "Mystery", "Domain", "Patron Theme",
    "There is a more recent version of this, click here to view.",
}


def leading_spell_fields(description: str) -> list[tuple[int, int, str, str]]:
    """Only consecutive leading labeled paragraphs are metadata candidates."""
    result = []
    cursor = 0
    while True:
        while cursor < len(description) and description[cursor].isspace():
            cursor += 1
        match = LABEL.match(description, cursor)
        if not match or match[1] not in FIELDS.keys() | UNMAPPED_METADATA:
            break
        boundary = BOUNDARY.search(description, match.end())
        end = boundary.start() if boundary else len(description)
        value = description[match.end():end].strip()
        # A combined inline header is ambiguous; keep it intact.
        if "**" in value:
            break
        result.append((match.start(), end, match[1], value))
        cursor = end
    return result


def normalized(value: Any) -> str:
    return " ".join(LINK.sub(r"\1", str(value)).split()).casefold().rstrip(".")


def configure_spell_editor_data(entity: dict[str, Any]) -> bool:
    """Remove represented metadata, filling missing text fields on stock imports.

    Never overwrite a conflicting populated field, infer a defense option, or
    change a native timer/map template. Keep unknown metadata and qualifiers.
    This conversion runs on compendium/build inputs, not saved personal spells.
    """
    if entity.get("kind") != "Spell" or not isinstance(entity.get("data"), dict):
        return False
    description = str(entity.get("descr") or "")
    candidates = leading_spell_fields(description)
    counts = Counter(FIELDS.get(label) for _, _, label, _ in candidates)
    data = entity["data"]
    removed = []
    for start, end, label, value in candidates:
        key = FIELDS.get(label)
        if not key or not value or counts[key] != 1:
            continue
        current = data.get(key)
        if key == "defense":
            # The native picker stores an enum, so it cannot carry a printed
            # rule link. Keep that linked header rather than silently lose it.
            if LINK.search(value):
                continue
            code = re.sub(r"\s+", "", normalized(value))
            if code not in DEFENSES or (current and current != code):
                continue
            data[key] = code
        else:
            if current and normalized(current) != normalized(value):
                continue
            if key in {"area", "durationText"}:
                # Preserve qualifiers/links instead of changing established
                # native template or timer parsing in a text repair.
                if not current or (LINK.search(value) and not LINK.search(str(current))):
                    continue
            if key == "traditionsText" and not current:
                continue
            if not current or LINK.search(value):
                data[key] = value
        removed.append((start, end))
    if not removed:
        return False
    pieces = []
    cursor = 0
    for start, end in removed:
        pieces.append(description[cursor:start])
        cursor = end
    pieces.append(description[cursor:])
    text = re.sub(r"\n{3,}", "\n\n", "".join(pieces)).strip()
    # When every header is gone, its leading separator is no longer needed.
    text = re.sub(r"^---+[ \t]*(?:\n|$)", "", text).lstrip()
    entity["descr"] = text
    return True


def main() -> None:
    """Deterministic post-link enrichment; preserve unrelated published data."""
    repo = Path(__file__).resolve().parents[1]
    changed = files = 0
    for root in (repo / "compendium/packs", repo / "compendium/ogl-packs"):
        for path in sorted(root.glob("*/spells.json")):
            records = json.loads(path.read_text())
            count = sum(configure_spell_editor_data(record) for record in records)
            if count:
                path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
                changed += count
                files += 1
    print(json.dumps({"convertedSpells": changed, "collections": files}))


if __name__ == "__main__":
    main()
