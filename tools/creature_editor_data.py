"""Build lossless structured mirrors for the Encounter+ creature editor.

The published fields remain in place for compatibility.  These mirrors give
the native editor searchable references and repeatable rows without changing
the text rendered by existing creatures.
"""

from __future__ import annotations

import copy
import re
from typing import Any


LEADING_LINK = re.compile(r"^\[([^]]+)\]\(([^)]+)\)(.*)$", re.S)
ACUITY = re.compile(
    r"^\s*\(\[([^]]+)\]\(([^)]+)\)\)(.*)$",
    re.S,
)
PLAIN_ACUITY = re.compile(
    r"^(.*?)\s+\(\[([^]]+)\]\(([^)]+)\)\)(.*)$",
    re.S,
)
QUANTITY = re.compile(r"^(.*?)\s+\((\d+)\)$", re.S)
ABILITY_TRIGGER = re.compile(r"\*\*Trigger\*\*\s*", re.I)
ABILITY_EFFECT = re.compile(r"\*\*Effect\*\*\s*", re.I)
ABILITY_METADATA = re.compile(
    r"\*\*(?:Frequency|Requirements|Trigger|Effect)\*\*\s*",
    re.I,
)
PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def split_entries(value: str) -> list[str]:
    """Split a comma list without splitting Markdown links or notes."""
    result: list[str] = []
    start = 0
    square_depth = 0
    round_depth = 0
    for index, char in enumerate(value):
        if char == "[":
            square_depth += 1
        elif char == "]" and square_depth:
            square_depth -= 1
        elif char == "(":
            round_depth += 1
        elif char == ")" and round_depth:
            round_depth -= 1
        elif char == "," and square_depth == 0 and round_depth == 0:
            entry = value[start:index].strip()
            if entry:
                result.append(entry)
            start = index + 1
    entry = value[start:].strip()
    if entry:
        result.append(entry)
    return result


def parse_item_entries(value: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for text in split_entries(value):
        entry: dict[str, Any] = {}
        linked = LEADING_LINK.match(text)
        if linked:
            entry["name"] = linked.group(1)
            entry["reference"] = linked.group(2)
            suffix = linked.group(3).strip()
            quantity = re.match(r"^\((\d+)\)(.*)$", suffix, re.S)
            if quantity:
                entry["quantity"] = int(quantity.group(1))
                suffix = quantity.group(2).strip()
            if suffix:
                entry["details"] = suffix
        else:
            quantity = QUANTITY.match(text)
            if quantity:
                entry["name"] = quantity.group(1).strip()
                entry["quantity"] = int(quantity.group(2))
            else:
                entry["name"] = text
        entries.append(entry)
    return entries


def render_item_entries(entries: list[dict[str, Any]]) -> str:
    """Reference renderer used to prove the structured mirror is lossless."""
    rendered: list[str] = []
    for entry in entries:
        name = str(entry.get("name") or "")
        reference = str(entry.get("reference") or "")
        text = f"[{name}]({reference})" if reference else name
        quantity = entry.get("quantity")
        if isinstance(quantity, int) and quantity > 1:
            text += f" ({quantity})"
        details = str(entry.get("details") or "").strip()
        if details:
            text += f" {details}"
        rendered.append(text)
    return ", ".join(rendered)


def parse_sense_entries(value: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    parts = split_entries(value)
    # Preserve intentionally unusual punctuation exactly instead of silently
    # normalizing it merely to fit the assisted editor rows.
    if ", ".join(parts) != value.strip():
        return [{"customText": value.strip()}]
    for text in parts:
        entry: dict[str, Any] = {}
        linked = LEADING_LINK.match(text)
        if linked:
            entry["name"] = linked.group(1)
            entry["reference"] = linked.group(2)
            suffix = linked.group(3)
            acuity = ACUITY.match(suffix)
            if acuity:
                entry["acuity"] = acuity.group(1)
                entry["acuityReference"] = acuity.group(2)
                suffix = acuity.group(3)
            suffix = suffix.strip()
            if suffix:
                entry["details"] = suffix
        else:
            acuity = PLAIN_ACUITY.match(text)
            if acuity and "[" not in acuity.group(1):
                entry["name"] = acuity.group(1).strip()
                entry["acuity"] = acuity.group(2)
                entry["acuityReference"] = acuity.group(3)
                suffix = acuity.group(4).strip()
                if suffix:
                    entry["details"] = suffix
            elif "[" in text or "](" in text:
                entry["customText"] = text
            else:
                entry["name"] = text
        entries.append(entry)
    return entries


def render_sense_entries(entries: list[dict[str, Any]]) -> str:
    """Reference renderer used to prove the structured mirror is lossless."""
    rendered: list[str] = []
    for entry in entries:
        custom = str(entry.get("customText") or "")
        if custom:
            rendered.append(custom)
            continue
        name = str(entry.get("name") or "")
        reference = str(entry.get("reference") or "")
        text = f"[{name}]({reference})" if reference else name
        acuity = str(entry.get("acuity") or "")
        acuity_reference = str(entry.get("acuityReference") or "")
        if acuity:
            if acuity_reference:
                text += f" ([{acuity}]({acuity_reference}))"
            else:
                text += f" ({acuity})"
        details = str(entry.get("details") or "").strip()
        if details:
            text += f" {details}"
        rendered.append(text)
    return ", ".join(rendered)


def parse_reference_entry(value: str) -> dict[str, Any]:
    linked = LEADING_LINK.match(value)
    if linked:
        entry: dict[str, Any] = {
            "name": linked.group(1),
            "reference": linked.group(2),
        }
        details = linked.group(3).strip()
        if details:
            entry["details"] = details
        return entry
    if "[" in value or "](" in value:
        return {"customText": value}
    return {"name": value}


def render_reference_entry(entry: dict[str, Any]) -> str:
    custom = str(entry.get("customText") or "")
    if custom:
        return custom
    name = str(entry.get("name") or "")
    reference = str(entry.get("reference") or "")
    text = f"[{name}]({reference})" if reference else name
    details = str(entry.get("details") or "").strip()
    if details:
        text += f" {details}"
    return text


def parse_defense_entries(values: dict[str, Any]) -> list[dict[str, Any]]:
    """Preserve ordered weakness/resistance mappings with clearer editor names."""
    return [
        {"type": key, "value": copy.deepcopy(value)}
        for key, value in values.items()
    ]


def render_defense_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Reference renderer used to prove defense editor mirrors are lossless."""
    return {
        str(entry.get("type") or ""): copy.deepcopy(entry.get("value"))
        for entry in entries
    }


def _trim_metadata_separator(value: str) -> str:
    return value.strip().strip(";").strip()


def _join_ability_description(before: str, after: str) -> str:
    before = _trim_metadata_separator(before)
    after = _trim_metadata_separator(after)
    if before and after:
        return f"{before}; {after}"
    return before or after


def parse_ability_editor_fields(value: str) -> dict[str, Any]:
    """Expose Trigger and Effect without discarding the published ability text."""
    description = value.strip()
    result: dict[str, Any] = {}

    effect_match = ABILITY_EFFECT.search(description)
    if effect_match:
        result["effect"] = _trim_metadata_separator(description[effect_match.end():])
        description = _trim_metadata_separator(description[:effect_match.start()])

    trigger_match = ABILITY_TRIGGER.search(description)
    if trigger_match:
        value_start = trigger_match.end()
        next_label = ABILITY_METADATA.search(description, value_start)
        paragraph = PARAGRAPH_BREAK.search(description, value_start)
        candidates = [
            match.start()
            for match in (next_label, paragraph)
            if match is not None
        ]
        value_end = min(candidates) if candidates else len(description)
        result["trigger"] = _trim_metadata_separator(
            description[value_start:value_end]
        )
        before = description[:trigger_match.start()]
        after = description[value_end:]
        result["triggerBeforeDescription"] = not bool(
            _trim_metadata_separator(before)
        )
        if paragraph is not None and paragraph.start() == value_end:
            result["triggerParagraphBreak"] = True
            after = description[paragraph.end():]
        description = _join_ability_description(before, after)

    result["description"] = description
    return result


def render_ability_editor_fields(fields: dict[str, Any]) -> str:
    """Reference renderer proving the structured editor keeps visible content."""
    description = str(fields.get("description") or "").strip()
    trigger = str(fields.get("trigger") or "").strip()
    effect = str(fields.get("effect") or "").strip()
    rendered = ""
    if trigger and fields.get("triggerBeforeDescription"):
        rendered = f"**Trigger** {trigger}"
        if description:
            rendered += "\n\n" if fields.get("triggerParagraphBreak") else "; "
    if description:
        rendered += description
    if trigger and not fields.get("triggerBeforeDescription"):
        if rendered:
            rendered += "; "
        rendered += f"**Trigger** {trigger}"
    if effect:
        if rendered:
            rendered += "; "
        rendered += f"**Effect** {effect}"
    return rendered


def configure_creature_editor_data(entity: dict[str, Any]) -> bool:
    """Add structured editor data while retaining all published source fields."""
    if entity.get("kind") != "Creature":
        return False
    data = entity.get("data")
    if not isinstance(data, dict):
        return False

    before = copy.deepcopy(data)
    senses = str(data.get("senses") or "").strip()
    if senses:
        data["senseEntries"] = parse_sense_entries(senses)

    items = str(data.get("items") or "").strip()
    if items:
        data["itemEntries"] = parse_item_entries(items)

    immunities = data.get("immunities")
    if isinstance(immunities, list) and immunities:
        data["immunityEditor"] = {
            "entries": [parse_reference_entry(str(value)) for value in immunities]
        }

    skills = data.get("skills")
    lore_skills = data.get("loreSkills")
    if isinstance(skills, dict) or isinstance(lore_skills, list):
        data["skillsEditor"] = {
            "skills": copy.deepcopy(skills) if isinstance(skills, dict) else {},
            "loreSkills": (
                copy.deepcopy(lore_skills) if isinstance(lore_skills, list) else []
            ),
        }

    for source, target in (
        ("weaknesses", "weaknessEntries"),
        ("resistances", "resistanceEntries"),
    ):
        values = data.get(source)
        if isinstance(values, dict) and values:
            data[target] = parse_defense_entries(values)

    rituals = data.get("rituals")
    if isinstance(rituals, dict) and any(rituals.values()):
        data["ritualcasting"] = [copy.deepcopy(rituals)]

    abilities = data.get("abilities")
    if isinstance(abilities, dict):
        for entries in abilities.values():
            if not isinstance(entries, list):
                continue
            for ability in entries:
                if not isinstance(ability, dict):
                    continue
                ability.update(
                    parse_ability_editor_fields(str(ability.get("text") or ""))
                )

    return data != before
