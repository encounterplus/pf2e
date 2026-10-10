"""Imported Player Core skill references used by creature quick links.

The checked-in source is a normalized cache of the ORC-licensed Player Core
skill pages. It excludes Archives of Nethys' generated item and feat indexes,
while preserving the book's skill rules and linking referenced rules to
Encounter+ entities. Build output never depends on network access.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import uuid
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "tools" / "data" / "player-core-skills.json"
STAGING = REPO.parent / "structured-modules"

COLLECTION_ROUTES = {
    "actions.json": "action",
    "conditions.json": "condition",
    "deities.json": "deity",
    "feats.json": "feat",
    "items.json": "item",
    "rules.json": "rule",
    "spells.json": "spell",
    "traits.json": "trait",
}
LINK_COLLECTIONS = {
    "Actions.aspx": "action",
    "Conditions.aspx": "condition",
    "Deities.aspx": "deity",
    "Equipment.aspx": "item",
    "Feats.aspx": "feat",
    "Rules.aspx": "rule",
    "Spells.aspx": "spell",
    "Traits.aspx": "trait",
}
SKILL_IDS = {
    34: "acrobatics",
    35: "arcana",
    36: "athletics",
    37: "crafting",
    38: "deception",
    39: "diplomacy",
    40: "intimidation",
    41: "lore",
    42: "medicine",
    43: "nature",
    44: "occultism",
    45: "performance",
    46: "religion",
    47: "society",
    48: "stealth",
    49: "survival",
    50: "thievery",
}
MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((/[^)]+)\)")


def _records() -> list[dict[str, Any]]:
    records = json.loads(SOURCE.read_text(encoding="utf-8"))
    if not isinstance(records, list) or len(records) != len(SKILL_IDS):
        raise ValueError("Player Core skill source must contain all 17 skills")
    return records


def skill_reference_records() -> list[dict[str, Any]]:
    records = []
    for source in _records():
        name = str(source["name"])
        aon_id = int(source["aonId"])
        slug = f"{name.casefold()}-skill-player-core"
        url = f"https://2e.aonprd.com/Skills.aspx?ID={aon_id}"
        records.append(
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"pf2e-remaster:{slug}")).upper(),
                "kind": "Rule",
                "system": "pf2e-remaster",
                "systemVersion": "1.2.10",
                "name": name,
                "slug": slug,
                "type": "skill",
                "descr": source["descr"],
                "data": {
                    "type": "skill",
                    "attribute": source["attribute"],
                },
                "attributes": {
                    "remaster": True,
                    "sourceId": "player-core",
                    "contentOrigin": "Player Core (ORC)",
                },
                "tags": ["player-core", "remaster", "rule", "skill"],
                "sources": [
                    {
                        "name": "Player Core",
                        "page": source["page"],
                        "url": url,
                    }
                ],
                "modifiers": [],
                "created": "2026-09-07T00:00:00Z",
                "modified": "2026-09-07T00:00:00Z",
            }
        )
    return records


def _plain_label(value: str) -> str:
    return re.sub(r"[*_`]", "", html.unescape(value)).strip()


def _route_index() -> dict[str, dict[str, str]]:
    """Index imported entities by visible name, preferring Player Core."""
    result: dict[str, dict[str, str]] = {
        route: {} for route in set(COLLECTION_ROUTES.values())
    }
    modules = sorted(
        (path for path in STAGING.iterdir() if path.is_dir()),
        key=lambda path: (path.name != "player-core", path.name),
    )
    for module in modules:
        for filename, route in COLLECTION_ROUTES.items():
            path = module / filename
            if not path.is_file():
                continue
            for record in json.loads(path.read_text(encoding="utf-8")):
                name = str(record.get("name") or "").strip()
                slug = str(record.get("slug") or "").strip()
                if name and slug:
                    result[route].setdefault(name.casefold(), f"/{route}/{slug}")
    for skill in SKILL_IDS.values():
        result.setdefault("skill", {})[skill] = f"/rule/{skill}-skill-player-core"
    return result


def _action_document_index(action_search: dict[str, Any]) -> dict[str, str]:
    return {
        str(hit.get("_source", {}).get("id")): str(hit.get("_source", {}).get("name"))
        for hit in action_search.get("hits", {}).get("hits", [])
        if hit.get("_source", {}).get("id") and hit.get("_source", {}).get("name")
    }


def _internal_link(label: str, target: str, routes: dict[str, dict[str, str]]) -> str:
    visible = html.unescape(label)
    name = _plain_label(visible)
    if re.fullmatch(r"/(?:action|condition|deity|feat|item|rule|spell|trait)/[^)]+", target):
        return f"[{visible}]({target})"
    path, _, query = target.lstrip("/").partition("?")
    if path == "Skills.aspx":
        parameters = dict(re.findall(r"(?:^|&)([^=&]+)=([^&]+)", html.unescape(query)))
        if parameters.get("General", "").casefold() == "true":
            route = routes.get("action", {}).get(name.casefold())
        else:
            try:
                skill = SKILL_IDS.get(int(parameters.get("ID", "0")))
            except ValueError:
                skill = None
            route = f"/rule/{skill}-skill-player-core" if skill else routes.get("skill", {}).get(name.casefold())
    else:
        collection = LINK_COLLECTIONS.get(path)
        route = routes.get(collection or "", {}).get(name.casefold())
        if not route and name.casefold().endswith("s"):
            route = routes.get(collection or "", {}).get(name.casefold()[:-1])
    return f"[{visible}]({route})" if route else visible


def _trait_template(match: re.Match[str], routes: dict[str, dict[str, str]]) -> str:
    label = html.unescape(match.group(1)).strip()
    route = routes.get("trait", {}).get(label.casefold())
    return f"[{label}]({route})" if route else label


def _table_markdown(table: str, routes: dict[str, dict[str, str]]) -> str:
    rows: list[list[str]] = []
    for raw_row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table, flags=re.I | re.S):
        cells: list[str] = []
        for raw_cell in re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", raw_row, flags=re.I | re.S):
            cell = re.sub(
                r'\{\{traits\s+\d+\s+"([^"]+)"\}\}',
                lambda match: _trait_template(match, routes),
                raw_cell,
                flags=re.I,
            )
            cell = MARKDOWN_LINK.sub(lambda match: _internal_link(match.group(1), match.group(2), routes), cell)
            cell = re.sub(r"<[^>]+>", "", cell)
            cells.append(html.unescape(cell).strip().replace("|", r"\|"))
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    return "\n".join(
        [
            "| " + " | ".join(rows[0]) + " |",
            "| " + " | ".join(["---"] * width) + " |",
            *["| " + " | ".join(row) + " |" for row in rows[1:]],
        ]
    )


def _tidy_markdown(value: str) -> str:
    blocks: list[str] = []
    for block in re.split(r"\n\s*\n", value):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.startswith(("#", "-", "|")) for line in lines):
            blocks.append("\n".join(lines))
        else:
            blocks.append(" ".join(lines))
    return "\n\n".join(blocks)


def _normalize_markup(
    markdown: str,
    routes: dict[str, dict[str, str]],
    action_documents: dict[str, str],
) -> str:
    # AoN appends live indexes for items and feats. They are not Player Core
    # book content and can include later publications, so they are excluded.
    cutoff = re.search(r'<title\b[^>]*>Item Bonuses for ', markdown, flags=re.I)
    body = markdown[: cutoff.start()] if cutoff else markdown

    # Action blocks are authoritative Player Core structure and can appear
    # after AoN's generated item index. Rebuild only their headings and links.
    action_blocks: list[str] = []
    for match in re.finditer(
        r'<title\b[^>]*>([^<]* Actions)</title>(.*?)(?=<title\b|\Z)',
        markdown,
        flags=re.I | re.S,
    ):
        names = [
            action_documents.get(document_id, "")
            for document_id in re.findall(r'<document\b[^>]*id="([^"]+)"[^>]*/>', match.group(2), flags=re.I)
        ]
        links = []
        for name in filter(None, names):
            route = routes.get("action", {}).get(name.casefold())
            if not route:
                raise ValueError(f"Player Core skill action is not imported: {name}")
            links.append(f"- [{name}]({route})")
        if links:
            action_blocks.append(f"## {html.unescape(match.group(1)).strip()}\n\n" + "\n".join(links))

    body = re.sub(r'<title\b[^>]*>.*?</title>\s*', "", body, count=1, flags=re.I | re.S)
    body = re.sub(r'^\*\*Source\*\*[^\n]*\n?', "", body, count=1, flags=re.I | re.M)
    body = re.sub(
        r"<table\b[^>]*>.*?</table>",
        lambda match: "\n\n" + _table_markdown(match.group(0), routes) + "\n\n",
        body,
        flags=re.I | re.S,
    )
    body = re.sub(
        r'\{\{traits\s+\d+\s+"([^"]+)"\}\}',
        lambda match: _trait_template(match, routes),
        body,
        flags=re.I,
    )
    body = re.sub(
        r'<title\b[^>]*level="([23])"[^>]*>(.*?)</title>',
        lambda match: "\n\n" + ("##" if match.group(1) == "2" else "###") + " " + _plain_label(match.group(2)) + "\n\n",
        body,
        flags=re.I | re.S,
    )
    body = re.sub(r'<li\b[^>]*>', "\n- ", body, flags=re.I)
    body = re.sub(r'</li>', "", body, flags=re.I)
    body = re.sub(r'</?(?:ul|ol)\b[^>]*>', "\n", body, flags=re.I)
    body = re.sub(r'<document\b[^>]*/>', "", body, flags=re.I)
    body = re.sub(r'<[^>]+>', "", body)
    body = MARKDOWN_LINK.sub(lambda match: _internal_link(match.group(1), match.group(2), routes), body)
    body = html.unescape(body)
    body = re.sub(r"(?m)^##\s*$", "", body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    body = _tidy_markdown(body)

    # Do not append a duplicate action block when the book expressed the list
    # directly, as Lore does.
    existing_headings = {
        heading.casefold()
        for heading in re.findall(r"^##\s+(.+)$", body, flags=re.M)
    }
    additions = [
        block
        for block in action_blocks
        if block.split("\n", 1)[0][3:].casefold() not in existing_headings
    ]
    return "\n\n".join([body, *additions]).strip()


def import_source(skill_search: Path, action_search: Path, output: Path = SOURCE) -> None:
    skills = json.loads(skill_search.read_text(encoding="utf-8"))
    actions = json.loads(action_search.read_text(encoding="utf-8"))
    routes = _route_index()
    documents = _action_document_index(actions)
    records: list[dict[str, Any]] = []
    for hit in skills.get("hits", {}).get("hits", []):
        source = hit.get("_source", {})
        match = re.fullmatch(r"skill-(\d+)", str(source.get("id") or ""))
        if not match or int(match.group(1)) not in SKILL_IDS:
            continue
        page_match = re.search(r"\bpg\.\s*(\d+)", str(source.get("primary_source_raw") or ""))
        if not page_match:
            raise ValueError(f"missing Player Core page for {source.get('name')}")
        records.append(
            {
                "name": source["name"],
                "aonId": int(match.group(1)),
                "attribute": [str(value).casefold() for value in source.get("attribute", [])],
                "page": int(page_match.group(1)),
                "descr": _normalize_markup(str(source.get("markdown") or ""), routes, documents),
            }
        )
    records.sort(key=lambda record: record["aonId"])
    if {record["aonId"] for record in records} != set(SKILL_IDS):
        raise ValueError("AoN response did not contain every current Player Core skill")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the checked-in Player Core skill source cache")
    parser.add_argument("--import-skills", type=Path, required=True)
    parser.add_argument("--import-actions", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=SOURCE)
    args = parser.parse_args()
    import_source(args.import_skills, args.import_actions, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
