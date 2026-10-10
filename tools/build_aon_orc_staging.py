#!/usr/bin/env python3
"""Convert reviewed AoN Remaster records into private Encounter+ staging packs.

AoN supplies current rules text and structured fields.  This converter creates
Encounter+ entities while discarding site navigation, images, indexes, lore
summaries, and provider implementation metadata from the entity content.  The
subsequent public builder performs the final Reserved Material scrub.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable


REPO = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO / "reference" / "aon-orc-sources"
DEFAULT_OUTPUT = REPO.parent / "structured-modules"
SYSTEM = "pf2e-remaster"
SYSTEM_VERSION = "1.2.10"
BUILD_DATE = "2026-09-09T00:00:00Z"
NAMESPACE = uuid.UUID("bbb7d31f-bca6-4827-a517-6f8cad56a986")

MODULE_NAMES = {
    "tian-xia-world-guide": "Tian Xia World Guide",
    "tian-xia-character-guide": "Tian Xia Character Guide",
    "divine-mysteries": "Divine Mysteries",
    "draconic-codex": "Draconic Codex",
    "hellfire-dispatches": "Hellfire Dispatches",
    "high-seas": "High Seas",
    "impossible-magic": "Impossible Magic",
}

COLLECTIONS = {
    "Action": "actions",
    "Ancestry": "ancestries",
    "Archetype": "archetypes",
    "Background": "backgrounds",
    "Class": "classes",
    "Creature": "creatures",
    "Deity": "deities",
    "Domain": "domains",
    "Feat": "feats",
    "Heritage": "heritages",
    "Item": "items",
    "Language": "languages",
    "Ritual": "rituals",
    "Rule": "rules",
    "Spell": "spells",
    "Trait": "traits",
    "Vehicle": "vehicles",
}

DIRECT_CATEGORIES = {
    "action": "Action",
    "ancestry": "Ancestry",
    "archetype": "Archetype",
    "background": "Background",
    "class": "Class",
    "creature": "Creature",
    "deity": "Deity",
    "domain": "Domain",
    "equipment": "Item",
    "feat": "Feat",
    "heritage": "Heritage",
    "language": "Language",
    "ritual": "Ritual",
    "rules": "Rule",
    "spell": "Spell",
    "trait": "Trait",
    "vehicle": "Vehicle",
    "weapon": "Item",
}

CLASS_OPTION_CATEGORIES = {
    "arcane-school": "Wizard Arcane School",
    "doctrine": "Cleric Doctrine",
    "draconic-exemplar": "Draconic Exemplar",
    "eidolon": "Summoner Eidolon",
    "fatal-method": "Necromancer Fatal Method",
    "grim-fascination": "Necromancer Grim Fascination",
    "hellknight-order": "Hellknight Order",
    "hybrid-study": "Magus Hybrid Study",
    "methodology": "Investigator Methodology",
    "mystery": "Oracle Mystery",
    "patron": "Witch Patron Theme",
    "runesmith-rune": "Runesmith Rune",
}

OTHER_RULE_CATEGORIES = {
    "animal-companion": "Animal Companion",
    "familiar-ability": "Familiar Ability",
    "familiar-specific": "Specific Familiar",
}

SKIPPED_CATEGORIES = {
    "category-page",
    "class-sample",
    "creature-family",
    "deity-category",
    "item-bonus",
    "sidebar",
    "source",
}

RARITIES = {"common", "uncommon", "rare", "unique"}
SIZES = {"tiny", "small", "medium", "large", "huge", "gargantuan"}
ATTRIBUTE_MAP = {
    "strength": "strength",
    "dexterity": "dexterity",
    "constitution": "constitution",
    "intelligence": "intelligence",
    "wisdom": "wisdom",
    "charisma": "charisma",
}
STANDARD_DC_BY_LEVEL = {
    -1: 13, 0: 14, 1: 15, 2: 16, 3: 18, 4: 19, 5: 20, 6: 22,
    7: 23, 8: 24, 9: 26, 10: 27, 11: 28, 12: 30, 13: 31, 14: 32,
    15: 34, 16: 35, 17: 36, 18: 38, 19: 39, 20: 40, 21: 42,
    22: 44, 23: 46, 24: 48, 25: 50,
}
RARITY_DC_ADJUSTMENT = {"common": 0, "uncommon": 2, "rare": 5, "unique": 10}
RECALL_SKILLS = {
    "arcana": {"arcane", "construct", "dragon", "elemental"},
    "nature": {"animal", "beast", "fey", "fungus", "plant"},
    "occultism": {"aberration", "astral", "dream", "ethereal", "spirit"},
    "religion": {"celestial", "fiend", "monitor", "undead"},
    "society": {"humanoid"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def slugify(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def creature_trait_code(value: str) -> str:
    """Preserve numeric creature-trait parameters used by the stat block."""
    code = slugify(value)
    code = re.sub(r"^(deadly|fatal|two-hand)-1d", r"\1-d", code)
    code = re.sub(r"^(scatter|volley)-(\d+)-feet$", r"\1-\2", code)
    code = re.sub(r"^two-handed-", "two-hand-", code)
    if code == "reach-5" or code == "reach-5-feet":
        return "reach"
    match = re.fullmatch(r"(reach|range-increment|thrown)-(\d+)(?:-feet)?", code)
    return f"{match.group(1)}-{match.group(2)}" if match else code


def provider_text(value: Any) -> str:
    """Resolve AoN's compact ``{{collection id "label"}}`` references."""
    text = str(value or "")
    for _ in range(3):
        text = re.sub(r'\{\{[A-Za-z-]+\s+\d+\s+"(.*?)"\}\}', r"\1", text, flags=re.S)
    text = re.sub(r"</?i>", "", text, flags=re.I)
    return html.unescape(text).strip()


def list_of(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [provider_text(item) for item in value if provider_text(item)]
    text = provider_text(value)
    return [text] if text else []


def lower_list(value: Any) -> list[str]:
    return [slugify(item) for item in list_of(value) if slugify(item)]


def rarity(record: dict[str, Any]) -> str:
    value = str(record.get("rarity") or "common").lower()
    return value if value in RARITIES else "common"


def traits(record: dict[str, Any]) -> list[str]:
    excluded = RARITIES | SIZES
    return sorted({code for code in lower_list(record.get("trait")) if code not in excluded})


def page_number(record: dict[str, Any]) -> int | None:
    match = re.search(r"\bpg\.\s*(\d+)", str(record.get("primary_source_raw") or ""))
    return int(match.group(1)) if match else None


def source_url(record: dict[str, Any]) -> str:
    relative = str(record.get("url") or "")
    return f"https://2e.aonprd.com{relative}" if relative.startswith("/") else relative


def markdown_table(value: str) -> str:
    rows: list[list[str]] = []
    for raw_row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", value, flags=re.I | re.S):
        cells = [
            clean_markup(cell).replace("\n", " ").replace("|", r"\|").strip()
            for cell in re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", raw_row, flags=re.I | re.S)
        ]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    return "\n".join([
        "| " + " | ".join(rows[0]) + " |",
        "| " + " | ".join(["---"] * width) + " |",
        *["| " + " | ".join(row) + " |" for row in rows[1:]],
    ])


def clean_markup(value: Any) -> str:
    text = provider_text(value)
    text = re.sub(
        r"<table\b[^>]*>.*?</table>",
        lambda match: "\n\n" + markdown_table(match.group(0)) + "\n\n",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(
        r"<title\b[^>]*>(.*?)</title>",
        lambda match: "\n\n## " + clean_markup(match.group(1)).strip() + "\n\n",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(r"<actions\b[^>]*string=\"([^\"]*)\"[^>]*/>", r"**\1**", text, flags=re.I)
    text = re.sub(r"<trait\b[^>]*label=\"([^\"]*)\"[^>]*/>", r"\1", text, flags=re.I)
    text = re.sub(r"<document\b[^>]*/>", "", text, flags=re.I)
    text = re.sub(r"<image\b[^>]*/>", "", text, flags=re.I)
    text = re.sub(r"<li\b[^>]*>", "\n- ", text, flags=re.I)
    text = re.sub(r"</li>", "", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</?(?:ul|ol|traits|row|column|aside)\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    # Some AoN monster abilities nest bold markup inside links, while others
    # nest links inside bold markup. Resolve both forms over a few passes.
    for _ in range(3):
        text = re.sub(r"\[([^\[\]]+)\]\(/[^)]+\)", r"\1", text)
    text = re.sub(r"\]\(/[^)]+\)", "", text)
    text = html.unescape(text)
    text = re.sub(r"(?m)^\*\*Source\*\*[^\n]*\n?", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def description(record: dict[str, Any]) -> str:
    raw = str(record.get("markdown") or record.get("text") or record.get("summary") or "")
    raw = re.sub(r"<title\b[^>]*>.*?</title>\s*", "", raw, count=1, flags=re.I | re.S)
    raw = re.sub(r"<traits>.*?</traits>\s*", "", raw, count=1, flags=re.I | re.S)
    return clean_markup(raw)


def action_codes(value: Any) -> list[str]:
    text = str(value or "").casefold()
    if not text:
        return []
    if "reaction" in text:
        return ["reaction"]
    if "free action" in text:
        return ["free"]
    values: list[str] = []
    words = (("single action", "one"), ("one action", "one"), ("two actions", "two"), ("three actions", "three"))
    for label, code in words:
        if label in text and code not in values:
            values.append(code)
    return values


def extract_field(record: dict[str, Any], key: str) -> str:
    raw_key = f"{key}_raw"
    if record.get(raw_key) not in (None, ""):
        return provider_text(record[raw_key])
    value = record.get(key)
    if isinstance(value, list):
        return ", ".join(provider_text(item) for item in value)
    return provider_text(value)


def item_price(record: dict[str, Any]) -> str:
    """Return the explicit price, falling back to the matching item variant.

    AoN's structured feed omits ``price`` for many multi-level items even
    though each variant's price is present in the record's Markdown. Match the
    variant whose displayed item level equals the record's base level. Items
    with no printed price remain blank.
    """
    explicit = record.get("price")
    if explicit == 0:
        return "0 gp"
    value = extract_field(record, "price")
    if value:
        return value

    markdown = str(record.get("markdown") or "")
    level = int(record.get("level") or 0)
    headings = list(
        re.finditer(
            r'<title\b[^>]*level="2"[^>]*right="Item\s+(\d+)(?:\+)?"[^>]*>.*?</title>',
            markdown,
            flags=re.I | re.S,
        )
    )
    for index, heading in enumerate(headings):
        if int(heading.group(1)) != level:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(markdown)
        price = re.search(r"\*\*Price\*\*\s*([^\n<]+)", markdown[heading.end():end], flags=re.I)
        if price:
            return provider_text(price.group(1))
    return ""


def split_clauses(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s*;\s*", text) if part.strip()]


def base_entity(record: dict[str, Any], module_id: str, kind: str, data: dict[str, Any], descr: str) -> dict[str, Any]:
    name = provider_text(record.get("name"))
    aon_id = str(record.get("id") or f"{kind}-{slugify(name)}")
    source_name = provider_text(record.get("primary_source") or MODULE_NAMES[module_id])
    source: dict[str, Any] = {"name": source_name, "url": source_url(record)}
    page = page_number(record)
    if page is not None:
        source["page"] = page
    tag_values = set(traits(record)) | {module_id, "remaster"}
    return {
        "id": str(uuid.uuid5(NAMESPACE, f"aon:{aon_id}")).upper(),
        "kind": kind,
        "system": SYSTEM,
        "systemVersion": SYSTEM_VERSION,
        "name": name,
        "slug": f"{slugify(name)}-{module_id}-{slugify(str(record.get('category') or kind))}-{slugify(aon_id)}",
        "descr": descr,
        "data": data,
        "attributes": {
            "remaster": True,
            "sourceId": module_id,
            "aonId": aon_id,
            "aonUrl": source_url(record),
        },
        "tags": sorted(tag_values),
        "sources": [source],
        "modifiers": [],
        "created": BUILD_DATE,
        "modified": BUILD_DATE,
    }


def map_action(record: dict[str, Any]) -> tuple[dict[str, Any], str]:
    data: dict[str, Any] = {
        "rarity": rarity(record),
        "traits": traits(record),
        "category": str(record.get("type") or "action").lower(),
        "frequency": extract_field(record, "frequency"),
        "requirements": extract_field(record, "requirement"),
        "trigger": extract_field(record, "trigger"),
    }
    actions = action_codes(record.get("actions"))
    if len(actions) == 1:
        data["actions"] = actions[0]
    return data, description(record)


def map_feat(record: dict[str, Any]) -> tuple[dict[str, Any], str]:
    descr = description(record)
    data: dict[str, Any] = {
        "level": int(record.get("level") or 0),
        "rarity": rarity(record),
        "traits": traits(record),
        "prerequisites": extract_field(record, "prerequisite"),
        "frequency": extract_field(record, "frequency"),
        "requirements": extract_field(record, "requirement"),
        "trigger": extract_field(record, "trigger"),
        "benefits": descr,
    }
    actions = action_codes(record.get("actions"))
    if len(actions) == 1:
        data["actions"] = actions[0]
    return data, descr


def normalize_defense(value: Any) -> str:
    text = re.sub(r"\s+", "", str(value or "").lower())
    return text if text in {"basicfortitude", "basicreflex", "basicwill", "fortitude", "reflex", "will"} else ""


def map_spell(record: dict[str, Any]) -> tuple[dict[str, Any], str]:
    actions = action_codes(record.get("actions"))
    data: dict[str, Any] = {
        "rank": int(record.get("level") or 0),
        "rarity": rarity(record),
        "traits": traits(record),
        "cost": extract_field(record, "cost"),
        "cast": str(record.get("actions") or ""),
        "range": extract_field(record, "range"),
        "targets": extract_field(record, "target"),
        "duration": extract_field(record, "duration"),
        "requirements": extract_field(record, "requirement"),
        "trigger": extract_field(record, "trigger"),
        "defense": normalize_defense(record.get("saving_throw")),
        "traditions": lower_list(record.get("tradition")),
        "traditionsText": ", ".join(list_of(record.get("tradition"))),
        "type": "cantrip" if "cantrip" in traits(record) else ("focus" if str(record.get("spell_type") or "").casefold() == "focus" else "spell"),
    }
    area = extract_field(record, "area")
    if area:
        data["area"] = area
    if actions:
        data["castActions"] = actions
    if len(actions) == 1:
        data["actions"] = actions[0]
    return data, description(record)


def map_ritual(record: dict[str, Any]) -> tuple[dict[str, Any], str]:
    data: dict[str, Any] = {
        "rank": int(record.get("level") or 0),
        "rarity": rarity(record),
        "traits": traits(record),
        "cost": extract_field(record, "cost"),
        "cast": str(record.get("actions") or ""),
        "secondaryCasters": extract_field(record, "secondary_casters"),
        "primaryChecks": extract_field(record, "primary_check"),
        "secondaryChecks": extract_field(record, "secondary_check"),
        "range": extract_field(record, "range"),
        "targets": extract_field(record, "target"),
        "duration": extract_field(record, "duration"),
    }
    area = extract_field(record, "area")
    if area:
        data["area"] = area
    return data, description(record)


def item_category(record: dict[str, Any]) -> str:
    category = str(record.get("item_category") or record.get("item_subcategory") or "").casefold()
    if "weapon" in category or record.get("category") == "weapon":
        return "weapon"
    if "armor" in category:
        return "armor"
    if "shield" in category:
        return "shield"
    if "rune" in category:
        return "rune"
    if "consumable" in category:
        return "consumable"
    if "wand" in category:
        return "wand"
    if "staff" in category:
        return "staff"
    if "held" in extract_field(record, "usage").casefold():
        return "held"
    if "worn" in extract_field(record, "usage").casefold():
        return "worn"
    return "other"


def map_item(record: dict[str, Any]) -> tuple[dict[str, Any], str]:
    data: dict[str, Any] = {
        "level": int(record.get("level") or 0),
        "rarity": rarity(record),
        "traits": traits(record),
        "category": item_category(record),
        "price": item_price(record),
        "usage": extract_field(record, "usage"),
        "bulk": extract_field(record, "bulk"),
        "ammunition": extract_field(record, "ammunition"),
    }
    if record.get("category") == "weapon":
        data.update({
            "damage": " ".join(part for part in [str(record.get("damage") or record.get("damage_die") or ""), str(record.get("damage_type") or "")] if part).strip(),
            "range": record.get("range"),
            "hands": record.get("hands"),
            "weaponType": str(record.get("weapon_type") or "").lower(),
            "weaponCategory": str(record.get("weapon_category") or "").lower(),
            "weaponGroup": slugify(str(record.get("weapon_group") or "")),
        })
    return {key: value for key, value in data.items() if value not in (None, "")}, description(record)


def ancestry_abilities(record: dict[str, Any]) -> list[dict[str, str]]:
    raw = str(record.get("markdown") or "")
    marker = re.search(r"<title\b[^>]*level=\"2\"[^>]*>[^<]*Mechanics</title>", raw, flags=re.I)
    if not marker:
        return []
    section = raw[marker.end():]
    headings = list(re.finditer(r"<title\b[^>]*level=\"3\"[^>]*>(.*?)</title>", section, flags=re.I | re.S))
    ignored = {"hit points", "size", "speed", "attribute boosts", "attribute flaws", "languages"}
    result = []
    for index, heading in enumerate(headings):
        name = clean_markup(heading.group(1))
        if name.casefold() in ignored:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(section)
        text = clean_markup(section[heading.end():end])
        if text:
            result.append({"name": name, "text": text})
    return result


def map_ancestry(record: dict[str, Any]) -> tuple[dict[str, Any], str]:
    boosts = [ATTRIBUTE_MAP[value.casefold()] for value in list_of(record.get("attribute")) if value.casefold() in ATTRIBUTE_MAP]
    flaws = [ATTRIBUTE_MAP[value.casefold()] for value in list_of(record.get("attribute_flaw")) if value.casefold() in ATTRIBUTE_MAP]
    size = next((value for value in lower_list(record.get("size")) if value in SIZES), "medium")
    speed = record.get("speed") if isinstance(record.get("speed"), dict) else {}
    movement = {"walk" if key == "land" else key: value for key, value in speed.items() if key != "max"}
    data = {
        "rarity": rarity(record),
        "traits": traits(record),
        "hp": int(record.get("hp") or 0),
        "size": size,
        "movement": movement,
        "attributeBoosts": boosts,
        "attributeFlaws": flaws,
        "languages": lower_list(record.get("language")),
        "abilities": ancestry_abilities(record),
        "summary": "",
    }
    return data, ""


def class_table(raw: str) -> tuple[str, str]:
    heading = re.search(r"<title\b[^>]*level=\"2\"[^>]*>Class Features</title>", raw, flags=re.I)
    if not heading:
        return "", ""
    after = raw[heading.end():]
    table = re.search(r"<table\b[^>]*>.*?</table>", after, flags=re.I | re.S)
    if not table:
        return "", ""
    return markdown_table(table.group(0)), clean_markup(after[:table.start()])


def class_key_terms(raw: str) -> str:
    for aside in re.findall(r"<aside\b[^>]*>(.*?)</aside>", raw, flags=re.I | re.S):
        if re.search(r">\s*Key Terms\s*</title>", aside, flags=re.I):
            return clean_markup(aside)
    return ""


def map_class(record: dict[str, Any], features: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    raw = str(record.get("markdown") or "")
    advancement, feature_intro = class_table(raw)
    spells = []
    if record.get("tradition"):
        spells.append(", ".join(list_of(record.get("tradition"))) + " tradition")
    data = {
        "rarity": rarity(record),
        "traits": traits(record),
        "summary": "",
        "attributes": lower_list(record.get("attribute")),
        "hp": int(record.get("hp") or 0),
        "perception": str(record.get("perception_proficiency") or "trained").lower(),
        "fortitude": str(record.get("fortitude_proficiency") or "trained").lower(),
        "reflex": str(record.get("reflex_proficiency") or "trained").lower(),
        "will": str(record.get("will_proficiency") or "trained").lower(),
        "skills": "; ".join(list_of(record.get("skill_proficiency"))),
        "attacks": "; ".join(list_of(record.get("attack_proficiency"))),
        "defenses": "; ".join(list_of(record.get("defense_proficiency"))),
        "spells": "; ".join(spells),
        "classAdvancement": advancement,
        "classFeaturesText": feature_intro,
        "classFeatures": [
            {
                "name": str(feature.get("name") or "Feature"),
                "level": int(feature.get("level") or 0),
                "text": description(feature),
            }
            for feature in sorted(features, key=lambda item: (int(item.get("level") or 0), str(item.get("name") or "")))
        ],
        "keyTerms": class_key_terms(raw),
    }
    return data, ""


def map_simple(record: dict[str, Any]) -> tuple[dict[str, Any], str]:
    data: dict[str, Any] = {"rarity": rarity(record), "traits": traits(record)}
    if record.get("level") is not None:
        data["level"] = int(record.get("level") or 0)
    if record.get("prerequisite"):
        data["prerequisites"] = extract_field(record, "prerequisite")
    return data, description(record)


def recall_knowledge(level: int, record_rarity: str, creature_traits: list[str]) -> dict[str, Any]:
    dc = STANDARD_DC_BY_LEVEL.get(level, 50 + max(0, level - 25) * 2)
    skill_values = [skill for skill, matching in RECALL_SKILLS.items() if matching.intersection(creature_traits)]
    return {"dc": dc + RARITY_DC_ADJUSTMENT.get(record_rarity, 0), "skills": skill_values}


def parse_attacks(raw: str) -> list[dict[str, Any]]:
    attacks: list[dict[str, Any]] = []
    pattern = re.compile(
        r"\*\*(Melee|Ranged)\*\*\s*<actions\b[^>]*string=\"([^\"]*)\"[^>]*/>\s*"
        r"(.*?)\s+([+-]\d+)\s*(?:\((.*?)\))?,?\s*\*\*Damage\*\*\s*(.*?)(?=\n\s*\n|\*\*(?:Melee|Ranged)\*\*|\Z)",
        flags=re.I | re.S,
    )
    for match in pattern.finditer(raw):
        trait_names = re.findall(r"\[([^\]]+)\]\(/Traits\.aspx[^)]*\)", match.group(5) or "", flags=re.I)
        normalized_traits = []
        for value in trait_names:
            code = creature_trait_code(value)
            if code and code not in normalized_traits:
                normalized_traits.append(code)
        actions = action_codes(match.group(2))
        attacks.append({
            "name": clean_markup(match.group(3)).strip(),
            "type": match.group(1).lower(),
            "actions": actions[0] if len(actions) == 1 else "one",
            "attack": int(match.group(4)),
            "traits": normalized_traits,
            "damage": clean_markup(match.group(6)).strip(" ,"),
        })
    return attacks


def find_ability(raw: str, name: str, next_names: list[str]) -> tuple[str, str, list[str]]:
    escaped = re.escape(name)
    marker = "|".join(
        (
            rf"(?:\*\*)?\[\*\*{escaped}\*\*\]\([^)]+\)(?:\*\*)?",
            rf"\*\*(?:\[)?{escaped}(?:\]\([^)]+\))?\*\*",
            rf"(?<![\w]){escaped}\s+(?=<actions\b|\()",
        )
    )
    start = re.search(marker, raw, flags=re.I)
    if not start:
        return "", "", []
    end = len(raw)
    section_end = re.search(r"\n\s*---\s*\n", raw[start.end():])
    if section_end:
        end = start.end() + section_end.start()
    for next_name in next_names:
        next_escaped = re.escape(next_name)
        next_marker = "|".join(
            (
                rf"(?:\*\*)?\[\*\*{next_escaped}\*\*\]\([^)]+\)(?:\*\*)?",
                rf"\*\*(?:\[)?{next_escaped}(?:\]\([^)]+\))?\*\*",
                rf"(?<![\w]){next_escaped}\s+(?=<actions\b|\()",
            )
        )
        candidate = re.search(next_marker, raw[start.end():], flags=re.I)
        if candidate:
            end = min(end, start.end() + candidate.start())
    fragment = raw[start.end():end]
    action_match = re.match(
        r"\s*<actions\b[^>]*string=\"([^\"]*)\"[^>]*/>\s*",
        fragment,
        flags=re.I,
    )
    codes = action_codes(action_match.group(1) if action_match else "")
    if action_match:
        fragment = fragment[action_match.end():]
    trait_block = re.match(
        r"\s*\(((?:\[[^\]]+\]\(/Traits\.aspx[^)]*\)(?:,\s*)?)+)\)\s*",
        fragment,
        flags=re.I,
    )
    traits = []
    if trait_block:
        for label in re.findall(r"\[([^\]]+)\]\(/Traits\.aspx[^)]*\)", trait_block.group(1), flags=re.I):
            code = creature_trait_code(label)
            if code and code not in traits:
                traits.append(code)
        fragment = fragment[trait_block.end():]
    return clean_markup(fragment).strip(), (codes[0] if len(codes) == 1 else ""), traits


def map_creature(record: dict[str, Any]) -> tuple[dict[str, Any], str]:
    raw = str(record.get("markdown") or "")
    second_title = list(re.finditer(r"<title\b[^>]*right=\"Creature\s+[-\d]+\"[^>]*>.*?</title>", raw, flags=re.I | re.S))
    statblock = raw[second_title[0].end():] if second_title else raw
    sections = re.split(r"\n\s*---\s*\n", statblock)
    creature_traits = traits(record)
    record_rarity = rarity(record)
    level = int(record.get("level") or 0)
    speed = record.get("speed") if isinstance(record.get("speed"), dict) else {}
    movement = {"walk" if key == "land" else key: value for key, value in speed.items() if key != "max"}
    rk = recall_knowledge(level, record_rarity, creature_traits)
    abilities = {"interaction": [], "defensive": [], "offensive": []}
    ability_names = [
        re.sub(r'^\{\{creatureAbilities\s+\d+\s+"?\s*', "", value).strip('"} ')
        for value in list_of(record.get("creature_ability"))
    ]
    for index, name in enumerate(ability_names):
        text, actions, ability_traits = find_ability(
            statblock, name, [other for other in ability_names if other != name]
        )
        if not text:
            continue
        position = statblock.casefold().find(name.casefold())
        first_break = statblock.find("---")
        second_break = statblock.find("---", first_break + 3) if first_break >= 0 else -1
        bucket = "interaction" if first_break < 0 or position < first_break else ("defensive" if second_break < 0 or position < second_break else "offensive")
        entry: dict[str, Any] = {"name": name, "text": text, "traits": ability_traits}
        if actions:
            entry["actions"] = actions
        abilities[bucket].append(entry)
    if record.get("spell_markdown"):
        abilities["offensive"].append({"name": "Spellcasting", "text": clean_markup(record["spell_markdown"]), "traits": []})
    resistances: dict[str, Any] = dict(record.get("resistance") or {})
    resistance_raw = str(record.get("resistance_raw") or "").strip()
    if resistance_raw and len(resistances) == 1:
        only = next(iter(resistances))
        match = re.match(rf"{re.escape(only)}\s+(.*)", resistance_raw, flags=re.I)
        if match:
            resistances[only] = match.group(1)
    save_details = ""
    saves_row = next(
        (
            block
            for block in re.findall(r"<row\b[^>]*>(.*?)</row>", statblock, flags=re.I | re.S)
            if re.search(r"\*\*Fort\*\*", block, flags=re.I)
            and re.search(r"\*\*Ref\*\*", block, flags=re.I)
            and re.search(r"\*\*Will\*\*", block, flags=re.I)
        ),
        "",
    )
    if saves_row:
        save_details = clean_markup(saves_row).replace("**", "")
        save_details = re.sub(
            r"\b(?:AC|Fort|Ref|Will)\b\s*[+-]?\d+\b",
            "",
            save_details,
            flags=re.I,
        )
        save_details = " ".join(save_details.split()).strip(" ;,")

    weaknesses: dict[str, Any] = dict(record.get("weakness") or {})
    weakness_raw = clean_markup(str(record.get("weakness_raw") or ""))
    if weakness_raw:
        entries = [part.strip() for part in re.split(r"[,;]", weakness_raw) if part.strip()]
        inferred_values = {
            int(value)
            for ability in (entry for values in abilities.values() for entry in values)
            for value in re.findall(r"\bweakness\s+(\d+)\b", str(ability.get("text") or ""), flags=re.I)
        }
        inferred_value = next(iter(inferred_values)) if len(inferred_values) == 1 else None
        for entry in entries:
            match = re.match(r"(.+?)\s+(\d+)$", entry)
            key = slugify(match.group(1) if match else entry)
            if key and key not in weaknesses:
                if match:
                    weaknesses[key] = int(match.group(2))
                elif inferred_value is not None:
                    weaknesses[key] = inferred_value
    skill_values = {slugify(key): int(value) for key, value in dict(record.get("skill_mod") or {}).items()}
    lore_skills = []
    for skill_name, value in re.findall(r"\[([^\]]+\s+Lore)\]\(/Skills\.aspx[^)]*\)\s*([+-]\d+)", str(record.get("skill_markdown") or ""), flags=re.I):
        lore_skills.append({"name": skill_name, "value": int(value)})
    data = {
        "level": level,
        "rarity": record_rarity,
        "size": next((value for value in lower_list(record.get("size")) if value in SIZES), "medium"),
        "traits": creature_traits,
        "attributes": {
            "str": int(record.get("strength") or 0), "dex": int(record.get("dexterity") or 0),
            "con": int(record.get("constitution") or 0), "int": int(record.get("intelligence") or 0),
            "wis": int(record.get("wisdom") or 0), "cha": int(record.get("charisma") or 0),
        },
        "perception": int(record.get("perception") or 0),
        "ac": {"value": int(record.get("ac") or 0), "details": ""},
        "hp": {"value": int(record.get("hp") or 0), "details": ""},
        "saves": {
            "fortitude": int(record.get("fortitude_save") or 0),
            "reflex": int(record.get("reflex_save") or 0),
            "will": int(record.get("will_save") or 0),
            "details": save_details,
        },
        "skills": skill_values,
        "loreSkills": lore_skills,
        "languages": lower_list(record.get("language")),
        "senses": provider_text(record.get("sense") or record.get("vision") or ""),
        "immunities": [value.casefold() for value in list_of(record.get("immunity"))],
        "weaknesses": weaknesses,
        "resistances": resistances,
        "movement": movement,
        "attacks": parse_attacks(statblock),
        "abilities": abilities,
        "recallKnowledge": rk,
        "recallKnowledgeText": f"DC {rk['dc']}" + (f" ({', '.join(skill.title() for skill in rk['skills'])})" if rk["skills"] else ""),
        "languagesText": ", ".join(list_of(record.get("language"))),
    }
    return data, ""


def map_vehicle(record: dict[str, Any]) -> tuple[dict[str, Any], str]:
    raw = str(record.get("markdown") or "")
    space: dict[str, int] = {}
    for value, axis in re.findall(r"(\d+)\s+feet\s+(long|wide|high)", str(record.get("space") or ""), flags=re.I):
        space[axis.lower()] = int(value)
    collision = re.search(r"\*\*Collision\*\*\s*([^\n(]+)\s*\(DC\s*(\d+)\)", raw, flags=re.I)
    data = {
        "level": int(record.get("level") or 0),
        "rarity": rarity(record),
        "traits": traits(record),
        "size": next((value for value in lower_list(record.get("size")) if value in SIZES), "gargantuan"),
        "price": extract_field(record, "price"),
        "space": space,
        "crew": str(record.get("crew") or ""),
        "passengers": extract_field(record, "passengers"),
        "pilotingCheck": extract_field(record, "piloting_check"),
        "speed": extract_field(record, "speed"),
        "ac": {"value": int(record.get("ac") or 0), "details": ""},
        "hp": {"value": int(record.get("hp") or 0), "details": ""},
        "hardness": int(record.get("hardness") or 0),
        "fortitude": int(record.get("fortitude_save") or 0),
        "collisionDC": int(collision.group(2)) if collision else None,
        "collisionDamage": collision.group(1).strip() if collision else "",
        "abilities": [],
    }
    return {key: value for key, value in data.items() if value is not None}, ""


def map_deity(record: dict[str, Any]) -> tuple[dict[str, Any], str]:
    sanctification = lower_list(record.get("sanctification"))
    areas = extract_field(record, "area_of_concern")
    edicts = split_clauses(record.get("edict"))
    anathema = split_clauses(record.get("anathema"))
    fonts = lower_list(record.get("divine_font"))
    attributes = lower_list(record.get("attribute"))
    skill = slugify(next(iter(list_of(record.get("skill"))), ""))
    weapons = list_of(record.get("favored_weapon"))
    domains = lower_list(record.get("domain_primary") or record.get("domain"))
    alternate_domains = lower_list(record.get("domain_alternate"))
    spells = list_of(record.get("spell"))
    rules_lines = []
    for label, value in (
        ("Areas of Concern", areas),
        ("Edicts", "; ".join(edicts)),
        ("Anathema", "; ".join(anathema)),
        ("Divine Attribute", ", ".join(value.title() for value in attributes)),
        ("Divine Font", ", ".join(value.title() for value in fonts)),
        ("Sanctification", ", ".join(value.title() for value in sanctification)),
        ("Divine Skill", skill.replace("-", " ").title()),
        ("Favored Weapon", ", ".join(weapons)),
        ("Domains", ", ".join(value.title() for value in domains)),
        ("Alternate Domains", ", ".join(value.title() for value in alternate_domains)),
        ("Cleric Spells", ", ".join(spells)),
    ):
        if value:
            rules_lines.append(f"**{label}** {value}")
    data = {
        "rarity": rarity(record),
        "traits": traits(record),
        "category": str(record.get("deity_category") or ""),
        "areasOfConcern": areas,
        "edicts": edicts,
        "anathema": anathema,
        "clericFont": fonts,
        "divineAttribute": attributes,
        "divineSkill": skill,
        "favoredWeapon": weapons,
        "domains": domains,
        "alternateDomains": alternate_domains,
        "spells": spells,
        "sanctification": sanctification[0] if len(sanctification) == 1 else "",
        "sanctificationOptions": sanctification,
        "rulesText": "\n\n".join(rules_lines),
    }
    return data, ""


def map_domain(record: dict[str, Any]) -> tuple[dict[str, Any], str]:
    domain_spell = str(record.get("domain_spell") or "")
    advanced_spell = str(record.get("advanced_domain_spell") or "")
    data = {
        "rarity": rarity(record),
        "traits": [],
        "domainSpell": domain_spell,
        "advancedDomainSpell": advanced_spell,
        "code": slugify(str(record.get("name") or "")),
        "referenceUrl": source_url(record),
    }
    descr_parts = [provider_text(record.get("summary"))]
    if domain_spell:
        descr_parts.append(f"**Domain Spell** {domain_spell}")
    if advanced_spell:
        descr_parts.append(f"**Advanced Domain Spell** {advanced_spell}")
    return data, "\n\n".join(part for part in descr_parts if part)


def map_language(record: dict[str, Any]) -> tuple[dict[str, Any], str]:
    code = slugify(str(record.get("name") or ""))
    record_rarity = rarity(record)
    descriptions = {
        "common": "This is a common language. A character can typically select it when a rule grants additional languages, subject to that rule's restrictions.",
        "uncommon": "This is an uncommon language. Selecting it normally requires access from an ancestry, region, feat, background, or another rule.",
        "rare": "This is a rare language. Selecting it normally requires specific access or the GM's permission.",
        "unique": "This is a unique language and is available only when a specific rule grants access to it.",
    }
    return {
        "traits": [],
        "category": record_rarity,
        "code": code,
        "rarity": record_rarity,
        "referenceUrl": source_url(record),
    }, descriptions.get(record_rarity, "This language requires access as determined by its source rule and the GM.")


def map_rule(record: dict[str, Any], label: str | None = None) -> tuple[dict[str, Any], str]:
    category = str(record.get("category") or "rules")
    breadcrumbs = list_of(record.get("breadcrumbs"))
    data: dict[str, Any] = {
        "type": "other",
        "category": label or str(record.get("type") or category).replace("-", " ").title(),
        "breadcrumbs": breadcrumbs,
        "referenceUrl": source_url(record),
    }
    return data, description(record)


Mapper = Callable[[dict[str, Any]], tuple[dict[str, Any], str]]


def mapper_for(category: str) -> Mapper:
    return {
        "action": map_action,
        "ancestry": map_ancestry,
        "archetype": map_simple,
        "background": map_simple,
        "creature": map_creature,
        "deity": map_deity,
        "domain": map_domain,
        "equipment": map_item,
        "feat": map_feat,
        "heritage": map_simple,
        "language": map_language,
        "ritual": map_ritual,
        "rules": map_rule,
        "spell": map_spell,
        "trait": map_simple,
        "vehicle": map_vehicle,
        "weapon": map_item,
    }[category]


def convert_module(module_id: str, records: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    feature_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    owner_text = "\n".join(
        str(record.get("markdown") or "")
        for record in records
        if record.get("category") != "action"
    )
    for record in records:
        if record.get("category") == "class-feature":
            feature_records[str(record.get("class") or "")].append(record)

    report = {"input": len(records), "output": 0, "consumed": Counter(), "skipped": Counter(), "byKind": Counter()}
    seen_ids: set[str] = set()
    for record in records:
        category = str(record.get("category") or "")
        name = provider_text(record.get("name"))
        if category == "class-feature":
            report["consumed"][category] += 1
            continue
        if category in SKIPPED_CATEGORIES:
            report["skipped"][category] += 1
            continue
        if category == "action" and str(record.get("markdown") or "").lstrip().startswith("**Activate"):
            activation = re.search(r"\*\*Activate(?:—([^*]+))?\*\*", str(record.get("markdown") or ""))
            activation_name = activation.group(1).strip() if activation and activation.group(1) else ""
            raw_activation = str(record.get("markdown") or "").strip()
            if (activation_name and activation_name in owner_text) or raw_activation in owner_text:
                report["consumed"]["embedded-activation"] += 1
                continue
            record = dict(record)
            record["name"] = activation_name or "Activate"
            name = str(record["name"])
        if not name:
            report["skipped"]["blank-name"] += 1
            continue

        if category == "deity" and record.get("epithet"):
            record = dict(record)
            name = f"{name} ({provider_text(record['epithet'])})"
            record["name"] = name

        if category == "class":
            kind = "Class"
            data, descr = map_class(record, feature_records.get(name, []))
        elif category in CLASS_OPTION_CATEGORIES:
            kind = "Rule"
            data, descr = map_rule(record, CLASS_OPTION_CATEGORIES[category])
        elif category in OTHER_RULE_CATEGORIES:
            kind = "Rule"
            data, descr = map_rule(record, OTHER_RULE_CATEGORIES[category])
        elif category in DIRECT_CATEGORIES:
            kind = DIRECT_CATEGORIES[category]
            data, descr = mapper_for(category)(record)
        else:
            raise ValueError(f"{module_id}: unmapped AoN category {category!r}")

        entity = base_entity(record, module_id, kind, data, descr)
        entity["tags"] = sorted({value for value in entity["tags"] + [slugify(category), slugify(str(data.get("category") or ""))] if value})
        if entity["id"] in seen_ids:
            raise ValueError(f"{module_id}: duplicate entity id {entity['id']}")
        seen_ids.add(entity["id"])
        grouped[kind].append(entity)
        report["output"] += 1
        report["byKind"][kind] += 1

    for values in grouped.values():
        values.sort(key=lambda entity: (entity["name"].casefold(), entity["slug"]))
    report["consumed"] = dict(sorted(report["consumed"].items()))
    report["skipped"] = dict(sorted(report["skipped"].items()))
    report["byKind"] = dict(sorted(report["byKind"].items()))
    return grouped, report


def main() -> int:
    args = parse_args()
    summary: dict[str, Any] = {"modules": {}, "input": 0, "output": 0, "skipped": 0}
    for module_id, module_name in MODULE_NAMES.items():
        source_path = args.input / f"{module_id}.json"
        if not source_path.is_file():
            raise SystemExit(f"AoN cache is missing: {source_path}\nRun tools/fetch_aon_orc_sources.py first.")
        payload = json.loads(source_path.read_text())
        records = [record for record in payload.get("records", []) if isinstance(record, dict)]
        grouped, report = convert_module(module_id, records)

        target = args.output / module_id
        target.mkdir(parents=True, exist_ok=True)
        for collection in COLLECTIONS.values():
            stale = target / f"{collection}.json"
            if stale.exists():
                stale.unlink()
        for kind, entities in grouped.items():
            (target / f"{COLLECTIONS[kind]}.json").write_text(json.dumps(entities, ensure_ascii=False, indent=2) + "\n")
        module_uuid = str(uuid.uuid5(NAMESPACE, f"module:{module_id}")).upper()
        (target / "module.json").write_text(json.dumps({
            "id": module_uuid,
            "system": SYSTEM,
            "systemVersion": SYSTEM_VERSION,
            "name": module_name,
            "slug": f"pf2e-remaster-{module_id}",
            "category": "other",
            "descr": "Remaster rules and game mechanics for Encounter+.",
            "author": "Paizo Inc.; Encounter+ adaptation by Saharory and contributors",
            "version": SYSTEM_VERSION,
        }, ensure_ascii=False, indent=2) + "\n")
        (target / "source.json").write_text(json.dumps({
            "id": module_id,
            "name": module_name,
            "system": SYSTEM,
            "counts": report["byKind"],
            "provider": "Archives of Nethys",
        }, ensure_ascii=False, indent=2) + "\n")
        summary["modules"][module_id] = report
        summary["input"] += report["input"]
        summary["output"] += report["output"]
        summary["skipped"] += sum(report["skipped"].values())

    (args.output / "aon-orc-import-report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(f"Converted {summary['output']} Encounter+ entities from {summary['input']} AoN records; skipped {summary['skipped']} presentation/derived records")
    print(f"Report: {args.output / 'aon-orc-import-report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
