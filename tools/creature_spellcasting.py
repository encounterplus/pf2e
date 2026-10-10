"""Apply the generated linked spell and ritual catalog to creatures."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any


CATALOG_PATH = Path(__file__).with_name("creature-spellcasting.json")
CATALOG_PAYLOAD = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
CREATURE_SPELLCASTING: dict[str, dict[str, Any]] = CATALOG_PAYLOAD["creatures"]
CATALOG_STATS: dict[str, int] = CATALOG_PAYLOAD["stats"]
AT_WILL = re.compile(r"^at will(?:\s*;\s*)?", flags=re.I)


def configure_creature_spellcasting(entity: dict[str, Any]) -> bool:
    """Add complete source-derived spellcasting to a matching creature."""
    configured = CREATURE_SPELLCASTING.get(str(entity.get("slug") or ""))
    if configured is None:
        return False
    data = entity.setdefault("data", {})
    for key, value in configured.items():
        data[key] = copy.deepcopy(value)

    has_at_will_spells = False
    for spellcasting in data.get("spellcasting", []):
        for group in spellcasting.get("spellGroups", []):
            for spell in group.get("spells", []):
                if spell.get("atWill"):
                    has_at_will_spells = True
                details = str(spell.get("details") or "")
                match = AT_WILL.match(details)
                if not match:
                    continue
                spell["atWill"] = True
                spell["details"] = details[match.end() :].strip()
                has_at_will_spells = True

    # The structured AoN importer previously kept a lossy comma-separated
    # placeholder ability. Once the real list exists it would be duplicate and
    # misleading, so remove only that generated placeholder.
    offensive = data.get("abilities", {}).get("offensive")
    if isinstance(offensive, list):
        data["abilities"]["offensive"] = [
            ability
            for ability in offensive
            if not (
                ability.get("name") == "Spellcasting"
                and not ability.get("actions")
                and not ability.get("traits")
            )
        ]

    if has_at_will_spells:
        abilities = data.get("abilities", {})
        for category, entries in list(abilities.items()):
            if isinstance(entries, list):
                abilities[category] = [
                    ability
                    for ability in entries
                    if ability.get("name") != "At-Will Spells"
                ]
    return True
