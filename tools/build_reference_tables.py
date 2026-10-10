#!/usr/bin/env python3
"""Build native Encounter+ reference tables from the published ORC rules.

The source rule, not a copied spreadsheet, remains authoritative. A changed or
missing source table fails the build instead of silently publishing stale data.
"""

from __future__ import annotations

import copy
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PACKS = REPO / "compendium" / "packs"
OGL_PACKS = REPO / "compendium" / "ogl-packs"
NAMESPACE = uuid.UUID("cc23cc69-3bc8-4df1-8605-a82bf1114c86")

# (source rule slug, native table title, zero-based table index in that rule)
TABLES: dict[str, list[tuple[str, str, int]]] = {
    "gm-core": [
        ("level-based-dcs-rules-2629", "DCs by Level", 0),
        ("level-based-dcs-rules-2629", "Spell Rank DCs", 1),
        ("simple-dcs-rules-2628", "Simple DCs", 0),
        ("adjusting-difficulty-rules-2630", "DC Adjustments", 0),
        ("attribute-modifiers-rules-2881", "Creature Building — Attribute Modifiers", 0),
        ("perception-rules-2882", "Creature Building — Perception", 0),
        ("skills-rules-2885", "Creature Building — Skills", 0),
        ("armor-class-rules-2889", "Creature Building — Armor Class", 0),
        ("saving-throws-rules-2890", "Creature Building — Saving Throws", 0),
        ("hit-points-rules-2891", "Creature Building — Hit Points", 0),
        ("immunities-weaknesses-and-resistances-rules-2893", "Creature Building — Resistances and Weaknesses", 0),
        ("strike-attack-bonus-rules-2896", "Creature Building — Strike Attack Bonus", 0),
        ("strike-damage-rules-2897", "Creature Building — Strike Damage", 0),
        ("spell-dc-and-spell-attack-modifier-rules-2899", "Creature Building — Spell DC and Attack", 0),
        ("damage-dealing-abilities-rules-2910", "Creature Building — Area Damage", 0),
        ("xp-budget-rules-2717", "Encounter XP Budget", 0),
        ("choosing-creatures-rules-2718", "Creature XP and Role", 0),
        ("treasure-by-level-rules-2656", "Party Treasure by Level", 0),
        ("environmental-damage-rules-2769", "Environmental Damage", 0),
        ("environmental-damage-rules-2769", "Environmental Features", 1),
        ("material-statistics-rules-3189", "Material Hardness, HP, and BT", 0),
    ],
    "player-core": [
        ("cover-rules-2372", "Cover", 0),
        ("counteracting-rules-3280", "Counteract Results by Rank", 0),
    ],
}

@dataclass(frozen=True)
class RollTableSpec:
    kind: str
    slug: str
    name: str
    table_index: int = 0
    section_index: int = 0


# Encounter+ identifies a genuine roll table by a dice expression in the first
# column header and result ranges in that column's cells. These are the actual
# random-result tables embedded in the licensed records we distribute. Lookup
# tables and generated item lists are intentionally absent.
ROLL_TABLES: dict[str, list[RollTableSpec]] = {
    "battlecry": [
        RollTableSpec("Rule", "what-do-the-heroes-do-rules-3436", "War Situation — Strategic", 0),
        RollTableSpec("Rule", "what-do-the-heroes-do-rules-3436", "War Situation — Operational", 1),
        RollTableSpec("Rule", "what-do-the-heroes-do-rules-3436", "War Situation — Tactical", 2),
    ],
    "dark-archive": [
        RollTableSpec("Feat", "eerie-proclamation-dark-archive", "Eerie Proclamation Failure"),
        RollTableSpec("Rule", "quirks-rules-3509", "Deviant Ability Quirk"),
    ],
    "gm-core": [
        RollTableSpec("Rule", "random-encounters-rules-3114", "Random Encounter Type", 1),
        RollTableSpec("Rule", "running-hexploration-rules-3110", "Random Terrain Type", 0),
        RollTableSpec("Rule", "running-hexploration-rules-3110", "Random Terrain Feature", 1),
        RollTableSpec("Rule", "gems-rules-3228", "Lesser Semiprecious Stones", 0, 0),
        RollTableSpec("Rule", "gems-rules-3228", "Moderate Semiprecious Stones", 0, 1),
        RollTableSpec("Rule", "gems-rules-3228", "Greater Semiprecious Stones", 0, 2),
        RollTableSpec("Rule", "gems-rules-3228", "Lesser Precious Stones", 0, 3),
        RollTableSpec("Rule", "gems-rules-3228", "Moderate Precious Stones", 0, 4),
        RollTableSpec("Rule", "gems-rules-3228", "Greater Precious Stones", 0, 5),
        RollTableSpec("Rule", "art-objects-rules-3229", "Minor Art Object", 0, 0),
        RollTableSpec("Rule", "art-objects-rules-3229", "Lesser Art Object", 0, 1),
        RollTableSpec("Rule", "art-objects-rules-3229", "Moderate Art Object", 0, 2),
        RollTableSpec("Rule", "art-objects-rules-3229", "Greater Art Object", 0, 3),
        RollTableSpec("Rule", "art-objects-rules-3229", "Major Art Object", 0, 4),
        RollTableSpec("Item", "madcap-top-gm-core", "Madcap Top Effect"),
    ],
    "guns-and-gears-remastered": [
        RollTableSpec("Item", "lucky-draw-bandolier-guns-and-gears-remastered", "Lucky Draw Bandolier Ammunition"),
        RollTableSpec("Item", "pistol-of-wonder-guns-and-gears-remastered", "Pistol of Wonder Effect"),
    ],
    "howl-of-the-wild": [
        RollTableSpec("Feat", "portents-of-the-haruspex-howl-of-the-wild", "Portents of the Haruspex Damage"),
    ],
    "monster-core": [
        RollTableSpec("Action", "protean-warpwave-monster-core", "Protean Warpwave Effect"),
    ],
    "player-core": [
        RollTableSpec("Spell", "creative-splash-player-core", "Creative Splash Color"),
    ],
    "player-core-2": [
        RollTableSpec("Feat", "signature-crafting-player-core-2", "Signature Crafting Quirk"),
        RollTableSpec("Spell", "chthonian-wrath-player-core-2", "Chthonian Wrath Realm"),
    ],
    "treasure-vault-remastered": [
        RollTableSpec("Rule", "crafting-downtime-events-rules-1920", "Crafting Downtime Event"),
    ],
    "rage-of-elements": [
        RollTableSpec("Item", "octopus-potion-lesser-rage-of-elements", "Octopus Potion Added Effect"),
        RollTableSpec("Spell", "rainbow-fumarole-rage-of-elements", "Rainbow Fumarole Color"),
    ],
}

# These rule sections begin on page 52, but the printed tables are on page 53.
PRINTED_TABLE_PAGES = {
    "DCs by Level": 53,
    "Spell Rank DCs": 53,
    "Simple DCs": 53,
    "DC Adjustments": 53,
}

TABLE_LINE = re.compile(r"^\|.*\|$")
SEPARATOR = re.compile(r"^:?-{3,}:?$")
BOLD = re.compile(r"^\*\*(.*?)\*\*$")
DICE = re.compile(r"^(?P<count>\d*)d(?P<sides>\d+|%)$", re.I)

ENTRY_ROUTE = {
    "Action": "action",
    "Feat": "feat",
    "Item": "item",
    "Rule": "rule",
    "Spell": "spell",
}


def markdown_tables(description: str) -> list[tuple[list[str], list[list[str]]]]:
    """Extract only well-formed pipe tables; retain cell dice and rule links."""
    blocks: list[list[str]] = []
    block: list[str] = []
    for line in description.splitlines() + [""]:
        if TABLE_LINE.fullmatch(line.strip()):
            block.append(line.strip())
        elif block:
            blocks.append(block)
            block = []

    parsed = []
    for block in blocks:
        cells = [[cell.strip() for cell in line[1:-1].split("|")] for line in block]
        if len(cells) < 3 or not all(SEPARATOR.fullmatch(cell) for cell in cells[1]):
            raise ValueError(f"invalid source table header: {block[:2]}")
        width = len(cells[0])
        if any(len(row) != width for row in cells):
            raise ValueError(f"ragged source table: {block[:2]}")
        headers = [BOLD.sub(r"\1", cell) for cell in cells[0]]
        parsed.append((headers, cells[2:]))
    return parsed


def make_table(rule: dict, name: str, headers: list[str], rows: list[list[str]]) -> dict:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    source_id = rule["attributes"]["sourceId"]
    if not rows or not headers or any(len(row) != len(headers) for row in rows):
        raise ValueError(f"empty/ragged table {name}")
    result = {
        "id": str(uuid.uuid5(NAMESPACE, f"{source_id}:{slug}")).upper(),
        "kind": "Table",
        "system": "pf2e-remaster",
        "systemVersion": rule["systemVersion"],
        "name": name,
        "slug": f"{slug}-{source_id}",
        "descr": f"[Open the full rule](/rule/{rule['slug']}) for context. Reference table; entries are not random outcomes.",
        "sources": copy.deepcopy(rule["sources"]),
        "attributes": {
            "remaster": rule["attributes"].get("remaster", True),
            "sourceId": source_id,
            "license": rule["attributes"]["license"],
        },
        "tags": ["table", "reference", source_id],
        "columns": [
            {"name": header, "size": 1 / len(headers), "align": None}
            for header in headers
        ],
        "rows": rows,
    }
    if name in PRINTED_TABLE_PAGES:
        result["sources"][0]["page"] = PRINTED_TABLE_PAGES[name]
    return result


def normalize_formula(value: str) -> str:
    match = DICE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"invalid roll-table dice formula: {value!r}")
    count = match.group("count") or "1"
    sides = "100" if match.group("sides") == "%" else match.group("sides")
    return f"{count}d{sides}"


def roll_table_sections(
    headers: list[str], rows: list[list[str]]
) -> list[tuple[list[str], list[list[str]]]]:
    """Split book tables that repeat a dice header for several value tiers."""
    sections: list[tuple[list[str], list[list[str]]]] = []
    current_headers = headers
    current_rows: list[list[str]] = []
    for row in rows:
        next_headers = [BOLD.sub(r"\1", cell) for cell in row]
        if len(row) == len(headers) and DICE.fullmatch(next_headers[0].strip()):
            if not current_rows:
                raise ValueError(f"empty roll-table section before {next_headers!r}")
            sections.append((current_headers, current_rows))
            current_headers = next_headers
            current_rows = []
        else:
            current_rows.append(row)
    if not current_rows:
        raise ValueError("roll table ends with an empty section")
    sections.append((current_headers, current_rows))
    return sections


def make_roll_table(rule: dict, name: str, headers: list[str], rows: list[list[str]]) -> dict:
    """Build a native Encounter+ roll table from a published dice-range table."""
    formula = normalize_formula(headers[0])
    headers = [formula, *headers[1:]]
    normalized_rows = copy.deepcopy(rows)
    for row in normalized_rows:
        # Module Packer documents ASCII ranges. Normalizing the typographic
        # source dash makes the app's range parser independent of punctuation.
        row[0] = row[0].replace("–", "-").replace("—", "-")
    result = make_table(rule, name, headers, normalized_rows)
    route = ENTRY_ROUTE[rule["kind"]]
    result["descr"] = (
        f"Roll {formula} and use the matching result range. "
        f"[Open the source entry](/{route}/{rule['slug']}) for context."
    )
    result["rollMode"] = "normal"
    result["tags"] = ["table", "rollable", rule["attributes"]["sourceId"]]
    return result


def detection_table(rules: dict[str, dict]) -> dict:
    """A short index of the published detection rules, not a new rule set."""
    overview = rules["perception-and-detection-rules-2277"]
    detail = rules["observed-rules-2415"]
    rows = [
        ["[Observed](/rule/observed-rules-2415)", "Space known; target normally", "—"],
        ["[Hidden](/rule/hidden-rules-2416)", "Space known; targeting requires a flat check", "DC 11"],
        ["[Undetected](/rule/undetected-rules-2417)", "Space unknown; choose a square; GM rolls in secret", "DC 11"],
        ["[Unnoticed](/rule/unnoticed-rules-2418)", "You are unaware of the creature", "—"],
        ["[Concealed](/rule/concealed-rules-2419)", "Obscured; can coexist with observed", "DC 5"],
        ["[Invisible](/rule/invisible-rules-2420)", "Usually undetected by sight; Seek can make it hidden", "See rule"],
    ]
    result = make_table(detail, "Detection and Targeting", ["State", "Reminder", "Targeting flat check"], rows)
    result["sources"].insert(0, copy.deepcopy(overview["sources"][0]))
    result["descr"] = f"[Open the detection rules](/rule/{overview['slug']}). Targeting depends on the observer and the target."
    return result


def build_tables(records: list[dict], source_id: str) -> list[dict]:
    if source_id not in TABLES and source_id not in ROLL_TABLES and source_id != "player-core":
        return []
    rules = {record["slug"]: record for record in records if record.get("kind") == "Rule"}
    entities = {
        (record.get("kind"), record.get("slug")): record
        for record in records
        if record.get("kind") and record.get("slug")
    }
    result = []
    for slug, name, index in TABLES.get(source_id, []):
        rule = rules[slug]
        tables = markdown_tables(rule.get("descr") or "")
        if index >= len(tables):
            raise ValueError(f"missing table {index} from {source_id}/{slug}")
        headers, rows = tables[index]
        if name == "Spell Rank DCs" and rows[-1][0].startswith("*If the spell"):
            headers = [headers[0].rstrip("*"), *headers[1:]]
            rows = rows[:-1]
            table = make_table(rule, name, headers, rows)
            table["descr"] += " Uncommon and rare spells may need a DC adjustment."
        else:
            table = make_table(rule, name, headers, rows)
        result.append(table)
    for spec in ROLL_TABLES.get(source_id, []):
        entity = entities[(spec.kind, spec.slug)]
        tables = markdown_tables(entity.get("descr") or "")
        if entity.get("kind") == "Item":
            # Activation-owned tables move with their source text into the
            # editable fields. Keep them available to reference-table rebuilds.
            data = entity.get("data") or {}
            primary = data.get("activation") or {}
            tables.extend(markdown_tables(primary.get("text") or ""))
            for activation in data.get("activations") or []:
                tables.extend(markdown_tables(activation.get("text") or ""))
        if spec.table_index >= len(tables):
            raise ValueError(
                f"missing roll table {spec.table_index} from {source_id}/{spec.slug}"
            )
        headers, rows = tables[spec.table_index]
        sections = roll_table_sections(headers, rows)
        if spec.section_index >= len(sections):
            raise ValueError(
                f"missing roll-table section {spec.section_index} from {source_id}/{spec.slug}"
            )
        section_headers, section_rows = sections[spec.section_index]
        result.append(make_roll_table(entity, spec.name, section_headers, section_rows))
    if source_id == "player-core":
        # All six linked rules must exist in the published compendium.
        for slug in (
            "observed-rules-2415", "hidden-rules-2416", "undetected-rules-2417",
            "unnoticed-rules-2418", "concealed-rules-2419", "invisible-rules-2420",
        ):
            if slug not in rules:
                raise ValueError(f"missing detection rule {slug}")
        result.append(detection_table(rules))
    return result


def main() -> None:
    summary_path = REPO / "compendium" / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    ogl_summary_path = REPO / "compendium" / "ogl-summary.json"
    ogl_summary = json.loads(ogl_summary_path.read_text(encoding="utf-8"))
    for source_id in sorted(set(TABLES) | set(ROLL_TABLES)):
        pack = PACKS / source_id
        if not pack.is_dir():
            pack = OGL_PACKS / source_id
        records: list[dict] = []
        for path in sorted(pack.glob("*.json")):
            if path.name in {"manifest.json", "module.json", "source.json", "tables.json"}:
                continue
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, list):
                records.extend(record for record in value if isinstance(record, dict))
        tables = build_tables(records, source_id)
        (pack / "tables.json").write_text(json.dumps(tables, ensure_ascii=False, indent=2) + "\n")
        source_path = pack / "source.json"
        source = json.loads(source_path.read_text(encoding="utf-8"))
        source["counts"]["Table"] = len(tables)
        source_path.write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n")
        if pack.parent == PACKS:
            summary[source_id]["Table"] = len(tables)
        else:
            ogl_summary[source_id]["Table"] = len(tables)
        print(f"{source_id}: {len(tables)} native tables")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    ogl_summary_path.write_text(json.dumps(ogl_summary, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
