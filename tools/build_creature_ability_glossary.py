#!/usr/bin/env python3
"""Build the shared PF2E monster-ability glossary used by creature sheets.

Foundry creature records refer to these rules with ``@Localize`` tokens. The
original importer flattened those tokens into labels such as ``Atwillspells``
or ``Rend``. This generator preserves the actual shared rules text and converts
source references into Encounter+ links before the public compendium is built.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from foundry_markup import replace_foundry_directives


REPO = Path(__file__).resolve().parents[1]
DEFAULT_STAGING = REPO.parent / "structured-modules"
DEFAULT_LANGUAGE = REPO.parent / "foundry-pf2e" / "static" / "lang" / "en.json"
DEFAULT_OUTPUT = REPO / "tools" / "creature-ability-glossary.json"

ROUTE_BY_KIND = {
    "Action": "action",
    "Affliction": "affliction",
    "Ancestry": "ancestry",
    "Archetype": "archetype",
    "Background": "background",
    "Class": "class",
    "Creature": "creature",
    "Deity": "deity",
    "Domain": "domain",
    "Feat": "feat",
    "Hazard": "hazard",
    "Heritage": "heritage",
    "Item": "item",
    "Language": "language",
    "Ritual": "ritual",
    "Rule": "rule",
    "Spell": "spell",
    "StatusEffect": "condition",
    "Trait": "trait",
    "Vehicle": "vehicle",
}
UUID = re.compile(r"@UUID\[([^\]]+)\](?:\{([^}]+)\})?")
SEPARATOR = re.compile(r"\n\s*---\s*\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, default=DEFAULT_STAGING)
    parser.add_argument("--language", type=Path, default=DEFAULT_LANGUAGE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def title_from_code(value: str) -> str:
    value = value.rsplit(".", 1)[-1].replace("-", " ").replace("_", " ")
    return " ".join(word.capitalize() for word in value.split())


def reference_index(staging: Path) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for module in sorted(path for path in staging.iterdir() if path.is_dir()):
        source_id = module.name
        for path in sorted(module.glob("*.json")):
            try:
                records = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if not isinstance(records, list):
                continue
            for record in records:
                kind = str(record.get("kind") or "")
                route_kind = ROUTE_BY_KIND.get(kind)
                foundry_id = str(record.get("attributes", {}).get("foundryId") or "")
                if not route_kind or not foundry_id or not record.get("slug"):
                    continue
                result[foundry_id].append(
                    {
                        "name": str(record.get("name") or ""),
                        "route": f"/{route_kind}/{record['slug']}",
                        "source": source_id,
                    }
                )
    return result


def choose_reference(candidates: list[dict[str, str]]) -> dict[str, str] | None:
    if not candidates:
        return None
    preferred = ("player-core", "gm-core", "monster-core", "player-core-2", "monster-core-2")
    return min(
        candidates,
        key=lambda item: (
            preferred.index(item["source"]) if item["source"] in preferred else len(preferred),
            item["route"],
        ),
    )


def html_to_markdown(value: str) -> str:
    text = re.sub(r"<\s*br\s*/?>", "\n", value, flags=re.I)
    text = re.sub(r"<\s*/?p(?:\s[^>]*)?>", "\n\n", text, flags=re.I)
    text = re.sub(r"<\s*hr\s*/?>", "\n\n", text, flags=re.I)
    text = re.sub(r"<\s*strong(?:\s[^>]*)?>", "**", text, flags=re.I)
    text = re.sub(r"<\s*/strong\s*>", "**", text, flags=re.I)
    text = re.sub(r"<\s*em(?:\s[^>]*)?>", "*", text, flags=re.I)
    text = re.sub(r"<\s*/em\s*>", "*", text, flags=re.I)
    text = re.sub(r"<\s*li(?:\s[^>]*)?>", "\n- ", text, flags=re.I)
    text = re.sub(r"<\s*/li\s*>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def render(value: str, references: dict[str, list[dict[str, str]]]) -> str:
    markers: dict[str, str] = {}

    def replace_uuid(match: re.Match[str]) -> str:
        target_id = match.group(1).rsplit(".", 1)[-1]
        target = choose_reference(references.get(target_id, []))
        explicit = html_to_markdown(match.group(2) or "")
        label = explicit or (target["name"] if target else title_from_code(target_id))
        replacement = f"[{label}]({target['route']})" if target else label
        marker = f"\ue000{len(markers)}\ue001"
        markers[marker] = replacement
        return marker

    annotated = UUID.sub(replace_uuid, value)
    cleaned = html_to_markdown(replace_foundry_directives(annotated))
    cleaned = SEPARATOR.sub("\n\n", cleaned)
    for marker, replacement in markers.items():
        cleaned = cleaned.replace(marker, replacement)
    return cleaned.strip()


def main() -> int:
    args = parse_args()
    language = json.loads(args.language.read_text(encoding="utf-8"))
    glossary: dict[str, str] = language["PF2E"]["NPC"]["Abilities"]["Glossary"]
    references = reference_index(args.staging)
    rendered = {code: render(value, references) for code, value in sorted(glossary.items())}
    unresolved = [code for code, value in rendered.items() if "@" in value or "Compendium." in value]
    if unresolved:
        raise SystemExit("unresolved monster ability glossary markup: " + ", ".join(unresolved))
    args.output.write_text(
        json.dumps(rendered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"abilities": len(rendered)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
