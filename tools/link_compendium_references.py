#!/usr/bin/env python3
"""Restore safe Encounter+ cross-links in private compendium staging.

The source importers intentionally flattened Foundry ``@UUID`` references and
AoN Markdown links into readable text.  This pass recovers those source-authored
references, resolves them against the records that are actually shipped, and
links only the first meaningful mention of each destination in an entry.

The default mode is a read-only audit. Pass ``--write`` to update staging after
the report has no broken destinations. Operations Center pages are deliberately
out of scope: they use their own compact navigation design.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

REPO = Path(__file__).resolve().parents[1]

from build_aon_orc_staging import clean_markup as clean_aon_markup
from build_aon_orc_staging import description as clean_aon_description
from build_public_orc_compendium import COLLECTION_KIND, STRIP_TOP_LEVEL_DESCRIPTION
from foundry_markup import has_conversion_artifact, replace_foundry_directives
from refresh_aon_rule_descriptions import remove_dying_condition_reprints


DEFAULT_STAGING = REPO.parent / "structured-modules"
DEFAULT_FOUNDRY = REPO.parent / "foundry-pf2e" / "packs" / "pf2e"
DEFAULT_AON_REFERENCE = REPO.parent / "reference" / "aon-remaster.json"
DEFAULT_AON_SOURCES = REPO / "reference" / "aon-orc-sources"

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

AON_KIND_BY_PAGE = {
    "actions": "Action",
    "afflictions": "Affliction",
    "ancestries": "Ancestry",
    "archetypes": "Archetype",
    "armor": "Item",
    "backgrounds": "Background",
    "classes": "Class",
    "conditions": "StatusEffect",
    "creatures": "Creature",
    "curses": "Affliction",
    "deities": "Deity",
    "diseases": "Affliction",
    "domains": "Domain",
    "equipment": "Item",
    "feats": "Feat",
    "hazards": "Hazard",
    "heritages": "Heritage",
    "languages": "Language",
    "rituals": "Ritual",
    "rules": "Rule",
    "spells": "Spell",
    "traits": "Trait",
    "vehicles": "Vehicle",
    "weapons": "Item",
}

FOUNDRY_KIND_HINTS = {
    "actionspf2e": "Action",
    "actions": "Action",
    "conditionitems": "StatusEffect",
    "conditions": "StatusEffect",
    "equipment-srd": "Item",
    "equipment": "Item",
    "feats-srd": "Feat",
    "feats": "Feat",
    "spells-srd": "Spell",
    "spells": "Spell",
    "ancestries": "Ancestry",
    "backgrounds": "Background",
    "classes": "Class",
    "deities": "Deity",
    "hazards": "Hazard",
    "heritages": "Heritage",
    "journals": "Rule",
    "vehicles": "Vehicle",
}

# A few Foundry GM-screen pages are compact presentations of entities that
# Encounter+ ships as standalone records. Their pack name only says "journal",
# so retain the page's more precise semantic kind here.
FOUNDRY_JOURNAL_PAGE_KIND = {
    "8gcp880pEWZ9VPnF": "Trait",  # Summon Trait
}

PREFERRED_AON_ID_BY_KIND_NAME = {
    ("Rule", "basic saving throws"): "rules-2297",
    ("Rule", "checks"): "rules-2278",
    ("Rule", "critical specialization"): "rules-2203",
}

FOUNDRY_REF = re.compile(r"@UUID\[([^\]]+)\](?:\{([^}]+)\})?")
AON_REF = re.compile(r"\[([^\]\n]+)\]\((/[^)]+)\)")
MARKDOWN_LINK = re.compile(r"\[([^\[\]]+)\]\((/[^)]+)\)")
WORD = re.compile(r"[^\W_]+(?:[’'][^\W_]+)*", flags=re.UNICODE)

CONTEXT_KINDS = {
    "action": ("Action",),
    "actions": ("Action",),
    "affliction": ("Affliction",),
    "afflictions": ("Affliction",),
    "ancestry": ("Ancestry",),
    "ancestries": ("Ancestry",),
    "archetype": ("Archetype",),
    "archetypes": ("Archetype",),
    "armor": ("Item",),
    "background": ("Background",),
    "backgrounds": ("Background",),
    "class": ("Class",),
    "classes": ("Class",),
    "condition": ("StatusEffect",),
    "conditions": ("StatusEffect",),
    # In rules prose, the word immediately before "creature" is commonly a
    # condition adjective ("off-guard creature"), not the creature entry's
    # proper name. Creature-to-creature links come from exact source markup.
    "creature": ("StatusEffect",),
    "creatures": ("StatusEffect",),
    "curse": ("Affliction",),
    "curses": ("Affliction",),
    "deity": ("Deity",),
    "deities": ("Deity",),
    "disease": ("Affliction",),
    "diseases": ("Affliction",),
    "domain": ("Domain",),
    "domains": ("Domain",),
    "feat": ("Feat",),
    "feats": ("Feat",),
    "hazard": ("Hazard",),
    "hazards": ("Hazard",),
    "heritage": ("Heritage",),
    "heritages": ("Heritage",),
    "item": ("Item",),
    "items": ("Item",),
    "language": ("Language",),
    "languages": ("Language",),
    "ritual": ("Ritual",),
    "rituals": ("Ritual",),
    "rule": ("Rule",),
    "rules": ("Rule",),
    "rune": ("Item",),
    "runes": ("Item",),
    "spell": ("Spell",),
    "spells": ("Spell",),
    "trait": ("Trait",),
    "traits": ("Trait",),
    "vehicle": ("Vehicle",),
    "vehicles": ("Vehicle",),
    "weapon": ("Item",),
    "weapons": ("Item",),
}

LABELED_LIST_KINDS = {
    "alternate domains": ("Domain",),
    "cleric spells": ("Spell",),
    "divine font": ("Spell",),
    "domains": ("Domain",),
    "favored weapon": ("Item",),
    "favored weapons": ("Item",),
}


@dataclass(frozen=True)
class Target:
    kind: str
    name: str
    slug: str
    source_id: str
    foundry_id: str
    aon_id: str
    level: int
    rank: int

    @property
    def route(self) -> str:
        return f"/{ROUTE_BY_KIND[self.kind]}/{self.slug}"


@dataclass(frozen=True)
class SourceReference:
    label: str
    target: Target
    provider: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, default=DEFAULT_STAGING)
    parser.add_argument("--foundry", type=Path, default=DEFAULT_FOUNDRY)
    parser.add_argument("--aon-reference", type=Path, default=DEFAULT_AON_REFERENCE)
    parser.add_argument("--aon-sources", type=Path, default=DEFAULT_AON_SOURCES)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--details", type=int, default=30)
    return parser.parse_args()


def title_from_code(value: str) -> str:
    return re.sub(r"[-_]", " ", value).strip().title()


def replace_foundry_uuid(match: re.Match[str]) -> str:
    return match.group(2) or title_from_code(match.group(1).rsplit(".", 1)[-1])


def replace_foundry_check(match: re.Match[str]) -> str:
    parts = match.group(1).split("|")
    statistic = title_from_code(parts[0])
    dc = next((part.split(":", 1)[1] for part in parts if part.startswith("dc:")), None)
    basic = "basic " if "basic" in parts else ""
    return f"{basic}{statistic}{' DC ' + dc if dc else ''}".strip()


def foundry_markdown_table(value: str) -> str:
    rows: list[list[str]] = []
    for raw_row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", value, flags=re.I | re.S):
        cells = [
            clean_foundry_description(cell).replace("\n", " ").replace("|", r"\|").strip()
            for cell in re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", raw_row, flags=re.I | re.S)
        ]
        if cells:
            rows.append(cells)
    if not rows:
        return clean_foundry_description(value)
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    return "\n".join(
        [
            "| " + " | ".join(rows[0]) + " |",
            "| " + " | ".join(["---"] * width) + " |",
            *["| " + " | ".join(row) + " |" for row in rows[1:]],
        ]
    )


def clean_foundry_description(
    value: Any, variables: dict[str, int | float] | None = None
) -> str:
    """Compatibility cleaner for descriptions produced by the private importer."""
    if not value:
        return ""
    text = replace_foundry_directives(str(value), variables)
    text = re.sub(
        r"<table\b[^>]*>.*?</table>",
        lambda match: "\n\n" + foundry_markdown_table(match.group(0)) + "\n\n",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(
        r"<h([1-6])\b[^>]*>(.*?)</h\1>",
        lambda match: f"\n\n{'#' * int(match.group(1))} {clean_foundry_description(match.group(2))}\n\n",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<\s*/?p(?:\s[^>]*)?>", "\n\n", text, flags=re.I)
    text = re.sub(r"<\s*hr\s*/?>", "\n\n---\n\n", text, flags=re.I)
    text = re.sub(r"<\s*strong(?:\s[^>]*)?>", "**", text, flags=re.I)
    text = re.sub(r"<\s*/strong\s*>", "**", text, flags=re.I)
    text = re.sub(r"<\s*em(?:\s[^>]*)?>", "*", text, flags=re.I)
    text = re.sub(r"<\s*/em\s*>", "*", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_name(value: str) -> str:
    value = html.unescape(value)
    value = unicodedata.normalize("NFKD", value)
    value = value.replace("’", "'").replace("–", "-").replace("—", "-")
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"[*_`]+", "", value)
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value.casefold())
    return " ".join(value.split())


def clean_label(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"[*_`]+", "", value)
    value = re.sub(r'\{\{[A-Za-z-]+\s+\d+\s+"(.*?)"\}\}', r"\1", value)
    return " ".join(value.split()).strip()


def approved_source_ids() -> set[str]:
    sources = json.loads((REPO / "compendium" / "sources.json").read_text())
    result = {str(record["id"]) for record in sources}
    ogl = json.loads((REPO / "compendium" / "ogl-sources.json").read_text())
    result.update(str(record["id"]) for record in ogl)
    return result


def iter_staging_collections(staging: Path) -> Iterable[tuple[str, Path, list[dict[str, Any]]]]:
    for source_id in sorted(approved_source_ids()):
        source_dir = staging / source_id
        for path in sorted(source_dir.glob("*.json")):
            if path.name not in COLLECTION_KIND:
                continue
            rows = json.loads(path.read_text())
            if not isinstance(rows, list):
                raise ValueError(f"{path} must contain a JSON array")
            yield source_id, path, rows


def target_catalog(staging: Path) -> tuple[
    list[Target],
    dict[str, list[Target]],
    dict[str, list[Target]],
    dict[tuple[str, str], list[Target]],
]:
    targets: list[Target] = []
    by_foundry: dict[str, list[Target]] = defaultdict(list)
    by_aon: dict[str, list[Target]] = defaultdict(list)
    by_kind_name: dict[tuple[str, str], list[Target]] = defaultdict(list)
    for source_id, path, rows in iter_staging_collections(staging):
        expected_kind = COLLECTION_KIND[path.name]
        for row in rows:
            kind = str(row.get("kind") or "")
            slug = str(row.get("slug") or "")
            name = str(row.get("name") or "")
            if kind != expected_kind or kind not in ROUTE_BY_KIND or not slug or not name:
                continue
            attrs = row.get("attributes") or {}
            data = row.get("data") or {}
            target = Target(
                kind=kind,
                name=name,
                slug=slug,
                source_id=source_id,
                foundry_id=str(attrs.get("foundryId") or ""),
                aon_id=str(attrs.get("aonId") or ""),
                level=int(data.get("level") or 0),
                rank=int(data.get("rank") or 0),
            )
            targets.append(target)
            if target.foundry_id:
                by_foundry[target.foundry_id].append(target)
            if target.aon_id:
                by_aon[target.aon_id].append(target)
            by_kind_name[(kind, normalize_name(name))].append(target)
    return targets, by_foundry, by_aon, by_kind_name


def choose_target(candidates: Iterable[Target], source_id: str = "") -> Target | None:
    unique = {candidate.route: candidate for candidate in candidates}
    if not unique:
        return None
    if len(unique) == 1:
        return next(iter(unique.values()))
    identities = {(target.kind, normalize_name(target.name)) for target in unique.values()}
    if len(identities) == 1:
        preferred_id = PREFERRED_AON_ID_BY_KIND_NAME.get(next(iter(identities)))
        preferred = [target for target in unique.values() if target.aon_id == preferred_id]
        if len(preferred) == 1:
            return preferred[0]
    same_source = [candidate for candidate in unique.values() if candidate.source_id == source_id]
    if len(same_source) == 1:
        return same_source[0]
    # Core records are the least surprising destination when identical names
    # appear in later supplements as aliases or reprints.
    core_order = ("player-core", "gm-core", "monster-core", "player-core-2", "monster-core-2")
    for core_source in core_order:
        core = [candidate for candidate in unique.values() if candidate.source_id == core_source]
        if len(core) == 1:
            return core[0]
    return None


def source_target(
    row: dict[str, Any],
    by_foundry: dict[str, list[Target]],
    by_aon: dict[str, list[Target]],
) -> Target | None:
    attrs = row.get("attributes") or {}
    source_id = str(attrs.get("sourceId") or "")
    foundry_id = str(attrs.get("foundryId") or "")
    if foundry_id:
        target = choose_target(by_foundry.get(foundry_id, []), source_id)
        if target:
            return target
    aon_id = str(attrs.get("aonId") or "")
    if aon_id:
        return choose_target(by_aon.get(aon_id, []), source_id)
    return None


def description_from_foundry(record: dict[str, Any]) -> str:
    system = record.get("system") or {}
    description = system.get("description") or {}
    if isinstance(description, dict):
        return str(description.get("value") or "")
    return str(description or "")


def load_foundry_records(foundry: Path) -> tuple[dict[str, list[dict[str, Any]]], int]:
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    count = 0
    for path in sorted(foundry.rglob("*.json")):
        try:
            record = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        record_id = str(record.get("_id") or "")
        if not record_id:
            continue
        copy = dict(record)
        copy["__pack"] = path.relative_to(foundry).parts[0]
        by_id[record_id].append(copy)
        count += 1
    return by_id, count


def load_aon_records(reference: Path, sources: Path) -> tuple[dict[str, list[dict[str, Any]]], int]:
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    count = 0

    def collect(payload: Any) -> None:
        nonlocal count
        if isinstance(payload, dict):
            if payload.get("id") and (payload.get("markdown") or payload.get("text")):
                by_id[str(payload["id"])].append(payload)
                count += 1
            else:
                for child in payload.values():
                    collect(child)
        elif isinstance(payload, list):
            for child in payload:
                collect(child)

    if reference.is_file():
        collect(json.loads(reference.read_text()))
    if sources.is_dir():
        for path in sorted(sources.glob("*.json")):
            if path.name == "summary.json":
                continue
            collect(json.loads(path.read_text()))
    return by_id, count


def foundry_kind_hint(uuid_value: str) -> str | None:
    parts = uuid_value.split(".")
    page_kind = FOUNDRY_JOURNAL_PAGE_KIND.get(parts[-1])
    if page_kind:
        return page_kind
    if len(parts) >= 3:
        pack = parts[2].casefold()
        if pack in FOUNDRY_KIND_HINTS:
            return FOUNDRY_KIND_HINTS[pack]
        if "condition" in pack:
            return "StatusEffect"
        if "action" in pack:
            return "Action"
        if "spell" in pack:
            return "Spell"
        if "feat" in pack:
            return "Feat"
        if "equipment" in pack:
            return "Item"
        if "hazard" in pack:
            return "Hazard"
        if "bestiary" in pack:
            return "Creature"
    return None


def aon_kind_and_id(url: str) -> tuple[str | None, str]:
    parsed = urlparse(url)
    page = Path(parsed.path).stem.casefold()
    kind = AON_KIND_BY_PAGE.get(page)
    raw_id = parse_qs(parsed.query).get("ID", parse_qs(parsed.query).get("id", [""]))[0]
    return kind, str(raw_id)


def reference_name_candidates(kind: str | None, label: str) -> list[str]:
    """Return conservative canonical-name aliases for source-authored links."""
    normalized = normalize_name(label)
    candidates = [label]
    if not kind or not normalized:
        return candidates

    if kind == "Action":
        if normalized.startswith("cast") and "spell" in normalized:
            candidates.append("Cast a Spell")
        if normalized == "cast":
            candidates.append("Cast a Spell")
        words = normalized.split()
        final = words[-1]
        stems: list[str] = []
        if final.endswith("ies") and len(final) > 3:
            stems.append(final[:-3] + "y")
        if final.endswith("es") and len(final) > 2:
            stems.extend([final[:-1], final[:-2]])
        elif final.endswith("s") and len(final) > 1:
            stems.append(final[:-1])
        if final.endswith("ed") and len(final) > 2:
            stems.extend([final[:-1], final[:-2]])
        if final.endswith("ing") and len(final) > 3:
            root = final[:-3]
            stems.extend([root, root + "e"])
            if len(root) > 1 and root[-1] == root[-2]:
                stems.append(root[:-1])
        candidates.extend(" ".join([*words[:-1], stem]) for stem in stems if stem)

    if kind == "StatusEffect":
        if normalized == "bleed" or (
            normalized.startswith("persistent ") and normalized.endswith(" damage")
        ):
            candidates.append("Persistent Damage")
        without_value = re.sub(r"\s+\d+$", "", normalized)
        if without_value != normalized:
            candidates.append(without_value)

    if kind == "Item":
        if "striking" in normalized:
            candidates.append("Striking")
        if "resilient" in normalized:
            candidates.append("Resilient")

    if kind == "Rule":
        if "critical specialization" in normalized:
            candidates.append("Critical Specialization")
        if "additional feats" in normalized:
            candidates.append("Additional Feats")
        if normalized in {"flat check", "flat checks"}:
            candidates.append("Checks")
        if normalized == "basic":
            candidates.append("Basic Saving Throws")
        if normalized in {"darkvision", "greater darkvision", "darkvision and greater darkvision"}:
            candidates.append("Darkvision and Greater Darkvision")
        if normalized in {
            "basic spellcasting feat",
            "expert spellcasting feat",
            "master spellcasting feat",
        }:
            candidates.append("Spellcasting Archetypes")
        full_rules = re.search(r"full rules (?:for|on) (.+)$", normalized)
        if full_rules:
            candidates.append(full_rules.group(1))

    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = normalize_name(candidate)
        if key and key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def resolve_reference_target(
    *,
    label: str,
    raw_target: str,
    provider: str,
    source_id: str,
    by_foundry: dict[str, list[Target]],
    by_aon: dict[str, list[Target]],
    by_kind_name: dict[tuple[str, str], list[Target]],
) -> Target | None:
    cleaned = clean_label(label)
    if provider == "foundry":
        final = raw_target.rsplit(".", 1)[-1]
        direct = choose_target(by_foundry.get(final, []), source_id)
        if direct:
            return direct
        kind = foundry_kind_hint(raw_target)
        names = reference_name_candidates(kind, cleaned)
        names.append(final.replace("-", " ").replace("_", " "))
    else:
        kind, numeric_id = aon_kind_and_id(raw_target)
        if numeric_id:
            prefixes = {
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
                "Rule": "rules",
                "Spell": "spell",
                "StatusEffect": "condition",
                "Trait": "trait",
                "Vehicle": "vehicle",
            }
            keys = [f"{prefixes.get(kind, '')}-{numeric_id}", numeric_id]
            for key in keys:
                direct = choose_target(by_aon.get(key, []), source_id)
                if direct:
                    return direct
        names = reference_name_candidates(kind, cleaned)

    for name in names:
        normalized = normalize_name(name)
        if not normalized:
            continue
        if kind:
            target = choose_target(by_kind_name.get((kind, normalized), []), source_id)
            if target:
                return target
        else:
            all_candidates: list[Target] = []
            for (candidate_kind, candidate_name), candidates in by_kind_name.items():
                if candidate_name == normalized:
                    all_candidates.extend(candidates)
            target = choose_target(all_candidates, source_id)
            if target:
                return target

    # A few legacy Foundry spell references became rituals in the Remaster.
    # Resolve them to the current entity kind without reviving the legacy spell.
    normalized_label = normalize_name(cleaned)
    if provider == "foundry" and kind == "Spell" and normalized_label in {"atone", "wish"}:
        target = choose_target(
            by_kind_name.get(("Ritual", normalized_label), []), source_id
        )
        if target:
            return target
    return None


def foundry_references(
    raw: dict[str, Any],
    source_id: str,
    by_foundry: dict[str, list[Target]],
    by_aon: dict[str, list[Target]],
    by_kind_name: dict[tuple[str, str], list[Target]],
) -> tuple[list[SourceReference], list[str]]:
    refs: list[SourceReference] = []
    unresolved: list[str] = []
    for match in FOUNDRY_REF.finditer(description_from_foundry(raw)):
        raw_target = match.group(1)
        explicit_label = match.group(2) or ""
        fallback_label = raw_target.rsplit(".", 1)[-1].replace("-", " ").replace("_", " ")
        label = clean_label(explicit_label or fallback_label)
        target = resolve_reference_target(
            label=label,
            raw_target=raw_target,
            provider="foundry",
            source_id=source_id,
            by_foundry=by_foundry,
            by_aon=by_aon,
            by_kind_name=by_kind_name,
        )
        if target:
            refs.append(SourceReference(label=label or target.name, target=target, provider="foundry"))
        else:
            unresolved.append(f"Foundry:{label or raw_target}")
    return refs, unresolved


def aon_references(
    raw: dict[str, Any],
    source_id: str,
    by_foundry: dict[str, list[Target]],
    by_aon: dict[str, list[Target]],
    by_kind_name: dict[tuple[str, str], list[Target]],
) -> tuple[list[SourceReference], list[str]]:
    refs: list[SourceReference] = []
    unresolved: list[str] = []
    source_text = str(raw.get("markdown") or raw.get("text") or "")
    for match in AON_REF.finditer(source_text):
        label = clean_label(match.group(1))
        raw_target = match.group(2)
        kind, _ = aon_kind_and_id(raw_target)
        if kind is None:
            continue
        target = resolve_reference_target(
            label=label,
            raw_target=raw_target,
            provider="aon",
            source_id=source_id,
            by_foundry=by_foundry,
            by_aon=by_aon,
            by_kind_name=by_kind_name,
        )
        if target:
            refs.append(SourceReference(label=label or target.name, target=target, provider="aon"))
        else:
            unresolved.append(f"AoN:{kind}:{label or raw_target}")
    return refs, unresolved


def choose_source_record(
    records: list[dict[str, Any]], row_name: str, source_id: str = ""
) -> dict[str, Any] | None:
    if not records:
        return None
    exact = [record for record in records if normalize_name(str(record.get("name") or "")) == normalize_name(row_name)]
    if source_id and len(exact) > 1:
        source_label = normalize_name(source_id.replace("-remastered", "").replace("-", " "))

        def source_matches(record: dict[str, Any]) -> bool:
            system = record.get("system") or {}
            publication = system.get("publication") or (system.get("details") or {}).get("publication") or {}
            title = normalize_name(str(publication.get("title") or ""))
            pack = normalize_name(str(record.get("__pack") or ""))
            return bool(source_label and (source_label in title or source_label in pack))

        preferred = [record for record in exact if source_matches(record)]
        if len(preferred) == 1:
            return preferred[0]
    if len(exact) == 1:
        return exact[0]
    with_description = [record for record in records if description_from_foundry(record)]
    if len(with_description) == 1:
        return with_description[0]
    return records[0] if len(records) == 1 else None


def choose_aon_source_record(
    records: list[dict[str, Any]], row_name: str
) -> dict[str, Any] | None:
    if not records:
        return None
    exact = [
        record
        for record in records
        if normalize_name(str(record.get("name") or "")) == normalize_name(row_name)
    ]
    if exact:
        return exact[-1]
    return records[-1] if len(records) == 1 else None


def strip_internal_links(text: str) -> str:
    """Return display text while preserving external Markdown unchanged."""
    return MARKDOWN_LINK.sub(lambda match: match.group(1), text)


def marker(index: int) -> str:
    return f"\ue000PF2EREF{index:05d}\ue001"


def restore_markers(text: str, replacements: dict[str, str]) -> str:
    for token, replacement in replacements.items():
        text = text.replace(token, replacement)
    return text


def render_foundry_links(
    raw: dict[str, Any],
    current: Target,
    source_id: str,
    by_foundry: dict[str, list[Target]],
    by_aon: dict[str, list[Target]],
    by_kind_name: dict[tuple[str, str], list[Target]],
) -> tuple[str, int, list[str]]:
    """Clean a Foundry description while protecting resolved internal links."""
    return render_foundry_text(
        description_from_foundry(raw),
        current,
        source_id,
        by_foundry,
        by_aon,
        by_kind_name,
    )


def render_foundry_text(
    source_text: str,
    current: Target,
    source_id: str,
    by_foundry: dict[str, list[Target]],
    by_aon: dict[str, list[Target]],
    by_kind_name: dict[tuple[str, str], list[Target]],
    preserve_repeated: bool = False,
) -> tuple[str, int, list[str]]:
    """Clean any Foundry rich-text field and preserve resolvable links."""
    replacements: dict[str, str] = {}
    unresolved: list[str] = []
    seen: set[str] = set()
    resolved = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal resolved
        raw_target = match.group(1)
        explicit = match.group(2) or ""
        final = raw_target.rsplit(".", 1)[-1]
        visible = clean_foundry_description(explicit) if explicit else title_from_code(final)
        target = resolve_reference_target(
            label=visible,
            raw_target=raw_target,
            provider="foundry",
            source_id=source_id,
            by_foundry=by_foundry,
            by_aon=by_aon,
            by_kind_name=by_kind_name,
        )
        if target is None:
            unresolved.append(f"Foundry:{visible or raw_target}")
            return visible
        if target.route == current.route or (not preserve_repeated and target.route in seen):
            return visible
        seen.add(target.route)
        token = marker(len(replacements))
        replacements[token] = f"[{visible}]({target.route})"
        resolved += 1
        return token

    annotated = FOUNDRY_REF.sub(replace, source_text)
    variables = {
        "@actor.level": current.level,
        "@actor.system.details.level.value": current.level,
        "@item.level": current.rank or current.level,
        "@item.rank": current.rank,
    }
    rendered = restore_markers(
        clean_foundry_description(annotated, variables), replacements
    )
    return rendered, resolved, unresolved


def foundry_embedded_descriptions(raw: dict[str, Any]) -> dict[str, str]:
    """Index actor-embedded action descriptions by their displayed name."""
    result: dict[str, str] = {}
    for item in raw.get("items") or []:
        if not isinstance(item, dict):
            continue
        name = normalize_name(str(item.get("name") or ""))
        text = description_from_foundry(item)
        if name and text:
            result.setdefault(name, text)
    return result


def refresh_foundry_rich_text(
    data: Any,
    raw: dict[str, Any],
    current: Target,
    source_id: str,
    by_foundry: dict[str, list[Target]],
    by_aon: dict[str, list[Target]],
    by_kind_name: dict[tuple[str, str], list[Target]],
    foundry_by_name: dict[str, list[dict[str, Any]]],
) -> tuple[Any, int, list[str]]:
    """Repair malformed imported actor abilities, routines, and class features."""
    updated = copy.deepcopy(data)
    repaired = 0
    unresolved: list[str] = []
    if not isinstance(updated, dict):
        return updated, repaired, unresolved

    embedded = foundry_embedded_descriptions(raw)

    def repair_named_entries(value: Any, candidates: dict[str, str]) -> None:
        nonlocal repaired
        if isinstance(value, dict):
            name = normalize_name(str(value.get("name") or ""))
            text = value.get("text")
            source_text = candidates.get(name)
            if isinstance(text, str) and source_text:
                rendered, _, missing = render_foundry_text(
                    source_text,
                    current,
                    source_id,
                    by_foundry,
                    by_aon,
                    by_kind_name,
                    preserve_repeated=True,
                )
                # The old importer flattened valid UUID links as well as
                # malformed macros. Restore the source-authored links whenever
                # the visible text is otherwise identical, while refusing to
                # overwrite a GM's edited wording.
                if (
                    has_conversion_artifact(text)
                    or strip_internal_links(rendered) == strip_internal_links(text)
                ) and rendered != text:
                    value["text"] = rendered
                    unresolved.extend(missing)
                    repaired += 1
            for child in value.values():
                if isinstance(child, (dict, list)):
                    repair_named_entries(child, candidates)
        elif isinstance(value, list):
            for child in value:
                if isinstance(child, (dict, list)):
                    repair_named_entries(child, candidates)

    repair_named_entries(updated.get("abilities"), embedded)

    routine = updated.get("routine")
    raw_routine = str(((raw.get("system") or {}).get("details") or {}).get("routine") or "")
    if isinstance(routine, str) and raw_routine and has_conversion_artifact(routine):
        rendered, _, missing = render_foundry_text(
            raw_routine,
            current,
            source_id,
            by_foundry,
            by_aon,
            by_kind_name,
            preserve_repeated=True,
        )
        updated["routine"] = rendered
        unresolved.extend(missing)
        repaired += 1

    details = (raw.get("system") or {}).get("details") or {}
    for key in ("disable", "reset"):
        current_text = updated.get(key)
        source_text = str(details.get(key) or "")
        if (
            isinstance(current_text, str)
            and source_text
            and has_conversion_artifact(current_text)
        ):
            rendered, _, missing = render_foundry_text(
                source_text,
                current,
                source_id,
                by_foundry,
                by_aon,
                by_kind_name,
                preserve_repeated=True,
            )
            updated[key] = rendered
            unresolved.extend(missing)
            repaired += 1

    class_features = updated.get("classFeatures")
    if isinstance(class_features, list):
        sources: dict[str, str] = {}
        for feature in class_features:
            if not isinstance(feature, dict) or not has_conversion_artifact(str(feature.get("text") or "")):
                continue
            name = normalize_name(str(feature.get("name") or ""))
            records = [
                record
                for record in foundry_by_name.get(name, [])
                if description_from_foundry(record)
                and str(record.get("__pack") or "") == "class-features"
            ]
            source = choose_source_record(
                records, str(feature.get("name") or ""), source_id
            )
            if source:
                sources[name] = description_from_foundry(source)
        repair_named_entries(class_features, sources)

    return updated, repaired, unresolved


def render_aon_links(
    raw: dict[str, Any],
    current: Target,
    source_id: str,
    by_foundry: dict[str, list[Target]],
    by_aon: dict[str, list[Target]],
    by_kind_name: dict[tuple[str, str], list[Target]],
) -> tuple[str, int, list[str]]:
    """Clean an AoN description while protecting resolved internal links."""
    source_text = str(raw.get("markdown") or raw.get("text") or raw.get("summary") or "")
    replacements: dict[str, str] = {}
    unresolved: list[str] = []
    seen: set[str] = set()
    resolved = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal resolved
        raw_label = match.group(1)
        raw_target = match.group(2)
        visible = clean_aon_markup(raw_label)
        kind, _ = aon_kind_and_id(raw_target)
        if kind is None:
            return visible
        target = resolve_reference_target(
            label=clean_label(visible),
            raw_target=raw_target,
            provider="aon",
            source_id=source_id,
            by_foundry=by_foundry,
            by_aon=by_aon,
            by_kind_name=by_kind_name,
        )
        if target is None:
            unresolved.append(f"AoN:{kind}:{clean_label(visible) or raw_target}")
            return visible
        if target.route == current.route or target.route in seen:
            return visible
        seen.add(target.route)
        token = marker(len(replacements))
        replacements[token] = f"[{visible}]({target.route})"
        resolved += 1
        return token

    annotated = AON_REF.sub(replace, source_text)
    copy = dict(raw)
    if raw.get("markdown"):
        copy["markdown"] = annotated
    elif raw.get("text"):
        copy["text"] = annotated
    else:
        copy["summary"] = annotated
    rendered = restore_markers(clean_aon_description(copy), replacements)
    if current.aon_id == "rules-2325":
        rendered = remove_dying_condition_reprints(rendered)
    return rendered, resolved, unresolved


def markdown_link_spans(text: str) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in MARKDOWN_LINK.finditer(text)]


def heading_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("#"):
            spans.append((offset, offset + len(line)))
        offset += len(line)
    return spans


def source_markup_spans(text: str) -> list[tuple[int, int]]:
    """Protect unresolved VTT macros from contextual fallback insertion."""
    spans = [
        (match.start(), match.end())
        for match in re.finditer(r"\[\[/.*?\]\](?:\{[^}]+\})?", text, flags=re.S)
    ]
    spans.extend(
        (match.start(), match.end())
        for match in re.finditer(r"@[A-Za-z]+\[[^\]]+\](?:\{[^}]+\})?", text)
    )
    return spans


def overlaps(start: int, end: int, spans: Iterable[tuple[int, int]]) -> bool:
    return any(start < span_end and end > span_start for span_start, span_end in spans)


def label_pattern(label: str) -> re.Pattern[str] | None:
    words = re.findall(r"[\w’']+", label, flags=re.UNICODE)
    if not words:
        return None
    separator = r"(?:[\s\-–—]+)"
    body = separator.join(re.escape(word) for word in words)
    return re.compile(rf"(?<![\w]){body}(?![\w])", flags=re.I)


def existing_routes(text: str) -> set[str]:
    return {match.group(2) for match in MARKDOWN_LINK.finditer(text)}


def insert_reference(text: str, reference: SourceReference) -> tuple[str, bool, str]:
    if reference.target.route in existing_routes(text):
        return text, False, "existing"
    protected = markdown_link_spans(text) + heading_spans(text) + source_markup_spans(text)
    candidates: list[str] = []
    for label in (reference.label, reference.target.name):
        if normalize_name(label) and normalize_name(label) not in {normalize_name(item) for item in candidates}:
            candidates.append(label)
    matches: list[tuple[int, int]] = []
    for label in candidates:
        pattern = label_pattern(label)
        if pattern is None:
            continue
        for match in pattern.finditer(text):
            if not overlaps(match.start(), match.end(), protected):
                matches.append((match.start(), match.end()))
                break
    if not matches:
        return text, False, "label-not-found"
    start, end = min(matches)
    return text[:start] + f"[{text[start:end]}]({reference.target.route})" + text[end:], True, "inserted"


def dedupe_source_references(refs: Iterable[SourceReference], self_route: str) -> list[SourceReference]:
    result: list[SourceReference] = []
    seen: set[str] = set()
    for ref in refs:
        if ref.target.route == self_route or ref.target.route in seen:
            continue
        seen.add(ref.target.route)
        result.append(ref)
    return result


def contextual_cross_links(
    text: str,
    current: Target,
    by_kind_name: dict[tuple[str, str], list[Target]],
    blocked_routes: set[str] | None = None,
) -> tuple[str, list[tuple[str, str]]]:
    """Link explicit ``<entry name> <entry kind>`` references conservatively.

    This is intentionally narrower than arbitrary name matching. A phrase such
    as ``wounded condition`` or ``Interact action`` has enough context to choose
    an entity kind, while an ordinary word such as ``fire`` does not.
    """
    tokens = list(WORD.finditer(text))
    if not tokens:
        return text, []
    protected = markdown_link_spans(text) + heading_spans(text) + source_markup_spans(text)
    already = existing_routes(text) | set(blocked_routes or set())
    candidates: list[tuple[int, int, Target]] = []

    def target_for(kind: str, start: int, end: int) -> Target | None:
        if overlaps(start, end, protected):
            return None
        normalized = normalize_name(text[start:end])
        if not normalized:
            return None
        target = choose_target(by_kind_name.get((kind, normalized), []), current.source_id)
        if target is None or target.route == current.route or target.route in already:
            return None
        return target

    for index, cue_match in enumerate(tokens):
        kinds = CONTEXT_KINDS.get(cue_match.group(0).casefold())
        if not kinds:
            continue
        found: tuple[int, int, Target] | None = None
        # Prefer the longest name immediately before the type word. This covers
        # the natural PF2E wording: "the wounded condition" and "Interact action".
        for width in range(min(12, index), 0, -1):
            start = tokens[index - width].start()
            end = tokens[index - 1].end()
            for kind in kinds:
                target = target_for(kind, start, end)
                if target:
                    found = (start, end, target)
                    break
            if found:
                break
        # Also support definitions such as "the condition Frightened".
        if found is None:
            remaining = len(tokens) - index - 1
            for width in range(min(12, remaining), 0, -1):
                start = tokens[index + 1].start()
                end = tokens[index + width].end()
                for kind in kinds:
                    target = target_for(kind, start, end)
                    if target:
                        found = (start, end, target)
                        break
                if found:
                    break
        if found:
            candidates.append(found)

    selected: list[tuple[int, int, Target]] = []
    selected_routes = set(already)
    for start, end, target in sorted(candidates, key=lambda item: (item[0], -(item[1] - item[0]))):
        if target.route in selected_routes:
            continue
        if any(start < other_end and end > other_start for other_start, other_end, _ in selected):
            continue
        selected.append((start, end, target))
        selected_routes.add(target.route)

    additions = [(text[start:end], target.route) for start, end, target in selected]
    for start, end, target in sorted(selected, key=lambda item: item[0], reverse=True):
        text = text[:start] + f"[{text[start:end]}]({target.route})" + text[end:]
    return text, additions


def labeled_list_cross_links(
    text: str,
    current: Target,
    by_kind_name: dict[tuple[str, str], list[Target]],
    blocked_routes: set[str] | None = None,
) -> tuple[str, list[tuple[str, str]]]:
    """Link every resolvable member of compact mechanical name lists."""
    protected = markdown_link_spans(text) + heading_spans(text) + source_markup_spans(text)
    already = existing_routes(text) | set(blocked_routes or set())
    selected: list[tuple[int, int, Target]] = []

    line_pattern = re.compile(r"(?m)^\*\*([^*\n]+)\*\*\s*([^\n]+)$")
    for line in line_pattern.finditer(text):
        kinds = LABELED_LIST_KINDS.get(normalize_name(line.group(1)))
        if not kinds:
            continue
        value_start = line.start(2)
        value = line.group(2)
        for part in re.finditer(r"[^,;]+", value):
            raw_start = value_start + part.start()
            raw_end = value_start + part.end()
            while raw_start < raw_end and text[raw_start].isspace():
                raw_start += 1
            while raw_end > raw_start and text[raw_end - 1].isspace():
                raw_end -= 1
            if raw_start >= raw_end or overlaps(raw_start, raw_end, protected):
                continue
            label = re.sub(r"\s*\([^)]*\)\s*$", "", text[raw_start:raw_end]).strip()
            label_end = raw_start + len(label)
            normalized = normalize_name(label)
            if not normalized:
                continue
            target = None
            for kind in kinds:
                target = choose_target(
                    by_kind_name.get((kind, normalized), []), current.source_id
                )
                if target:
                    break
            if (
                target is None
                or target.route == current.route
                or target.route in already
                or overlaps(raw_start, label_end, protected)
            ):
                continue
            selected.append((raw_start, label_end, target))
            already.add(target.route)

    additions = [(text[start:end], target.route) for start, end, target in selected]
    for start, end, target in sorted(selected, key=lambda item: item[0], reverse=True):
        text = text[:start] + f"[{text[start:end]}]({target.route})" + text[end:]
    return text, additions


RICH_TEXT_KEYS = {
    "classDescription",
    "classFeaturesText",
    "description",
    "rulesText",
    "summary",
    "text",
}


def link_rich_data(
    value: Any,
    current: Target,
    by_kind_name: dict[tuple[str, str], list[Target]],
    blocked_routes: set[str],
) -> tuple[Any, list[tuple[str, str]]]:
    """Cross-link Markdown-capable structured text without touching data codes."""
    additions: list[tuple[str, str]] = []
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if key in RICH_TEXT_KEYS and isinstance(child, str) and child:
                if key == "summary" and current.kind in {"Ancestry", "Class"}:
                    result[key] = child
                    continue
                blocked_routes.update(existing_routes(child))
                linked, child_additions = contextual_cross_links(
                    child, current, by_kind_name, blocked_routes
                )
                blocked_routes.update(route for _, route in child_additions)
                linked, list_additions = labeled_list_cross_links(
                    linked, current, by_kind_name, blocked_routes
                )
                blocked_routes.update(route for _, route in list_additions)
                additions.extend(child_additions)
                additions.extend(list_additions)
                result[key] = linked
            elif isinstance(child, (dict, list)):
                linked, child_additions = link_rich_data(
                    child, current, by_kind_name, blocked_routes
                )
                additions.extend(child_additions)
                result[key] = linked
            else:
                result[key] = child
        return result, additions
    if isinstance(value, list):
        result_list: list[Any] = []
        for child in value:
            if isinstance(child, (dict, list)):
                linked, child_additions = link_rich_data(
                    child, current, by_kind_name, blocked_routes
                )
                additions.extend(child_additions)
                result_list.append(linked)
            else:
                result_list.append(child)
        return result_list, additions
    return value, additions


def main() -> int:
    args = parse_args()
    targets, by_foundry, by_aon, by_kind_name = target_catalog(args.staging)
    foundry_records, foundry_count = load_foundry_records(args.foundry)
    aon_records, aon_count = load_aon_records(args.aon_reference, args.aon_sources)
    foundry_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for records in foundry_records.values():
        for record in records:
            name = normalize_name(str(record.get("name") or ""))
            if name:
                foundry_by_name[name].append(record)

    stats: Counter[str] = Counter()
    unresolved: Counter[str] = Counter()
    render_mismatches: Counter[str] = Counter()
    fallback_examples: Counter[str] = Counter()
    changed_files = 0

    for source_id, path, rows in iter_staging_collections(args.staging):
        file_changed = False
        for row in rows:
            stats["entities"] += 1
            text = str(row.get("descr") or "")
            kind = str(row.get("kind") or "")
            slug = str(row.get("slug") or "")
            if kind not in ROUTE_BY_KIND or not slug:
                stats["entitiesWithoutRoute"] += 1
                continue
            if text:
                stats["descriptions"] += 1

            attrs = row.get("attributes") or {}
            foundry_id = str(attrs.get("foundryId") or "")
            aon_id = str(attrs.get("aonId") or "")
            current_target = Target(
                kind=kind,
                name=str(row.get("name") or ""),
                slug=slug,
                source_id=source_id,
                foundry_id=foundry_id,
                aon_id=aon_id,
                level=int((row.get("data") or {}).get("level") or 0),
                rank=int((row.get("data") or {}).get("rank") or 0),
            )
            updated = text
            fallback_additions: list[tuple[str, str]] = []
            list_additions: list[tuple[str, str]] = []

            # These descriptions are intentionally stripped by the public
            # license builder. Their displayed mechanics live in structured
            # rich-text fields, processed below.
            if text and kind not in STRIP_TOP_LEVEL_DESCRIPTION:
                plain = strip_internal_links(text)
                updated = plain
                rendered: str | None = None
                resolved_count = 0
                provider = ""

                if aon_id:
                    raw = choose_aon_source_record(
                        aon_records.get(aon_id, []), str(row.get("name") or "")
                    )
                    if raw:
                        stats["matchedAoNSources"] += 1
                        provider = "AoN"
                        rendered, resolved_count, source_unresolved = render_aon_links(
                            raw, current_target, source_id, by_foundry, by_aon, by_kind_name
                        )
                        unresolved.update(source_unresolved)
                    else:
                        stats["missingAoNSources"] += 1
                elif foundry_id:
                    raw = choose_source_record(
                        foundry_records.get(foundry_id, []),
                        str(row.get("name") or ""),
                        source_id,
                    )
                    if raw:
                        stats["matchedFoundrySources"] += 1
                        provider = "Foundry"
                        rendered, resolved_count, source_unresolved = render_foundry_links(
                            raw, current_target, source_id, by_foundry, by_aon, by_kind_name
                        )
                        unresolved.update(source_unresolved)
                    else:
                        stats["missingFoundrySources"] += 1

                if rendered is not None:
                    stats["resolvedSourceReferences"] += resolved_count
                    if strip_internal_links(rendered) == plain:
                        updated = rendered
                        stats["exactRenderMatches"] += 1
                        stats["insertedLinks"] += len(existing_routes(rendered))
                    else:
                        stats["renderMismatches"] += 1
                        render_mismatches[f"{provider}:{source_id}:{row.get('name')}"] += 1
                        if (
                            "[/act " in plain
                            or "traits=[[" in plain
                            or has_conversion_artifact(plain)
                        ):
                            updated = rendered
                            stats["repairedMalformedSourceMacros"] += 1
                elif foundry_id or aon_id:
                    stats["missingSourceRecords"] += 1

                updated, fallback_additions = contextual_cross_links(
                    updated, current_target, by_kind_name
                )
                updated, list_additions = labeled_list_cross_links(
                    updated,
                    current_target,
                    by_kind_name,
                    {route for _, route in fallback_additions},
                )

            blocked_routes = existing_routes(updated) if kind not in STRIP_TOP_LEVEL_DESCRIPTION else set()
            original_data = row.get("data")
            updated_data = copy.deepcopy(original_data)
            data_additions: list[tuple[str, str]] = []
            if foundry_id and isinstance(updated_data, (dict, list)):
                raw = choose_source_record(
                    foundry_records.get(foundry_id, []),
                    str(row.get("name") or ""),
                    source_id,
                )
                if raw:
                    updated_data, repair_count, repair_unresolved = refresh_foundry_rich_text(
                        updated_data,
                        raw,
                        current_target,
                        source_id,
                        by_foundry,
                        by_aon,
                        by_kind_name,
                        foundry_by_name,
                    )
                    stats["repairedStructuredSourceMacros"] += repair_count
                    unresolved.update(repair_unresolved)

            if (
                kind in {"Archetype", "Feat"}
                and isinstance(updated_data, dict)
                and has_conversion_artifact(str(updated_data.get("benefits") or ""))
                and updated
            ):
                updated_data["benefits"] = updated
                stats["repairedStructuredSourceMacros"] += 1

            if isinstance(updated_data, (dict, list)):
                updated_data, data_additions = link_rich_data(
                    updated_data, current_target, by_kind_name, blocked_routes
                )

            all_fallbacks = fallback_additions + list_additions + data_additions
            stats["contextualFallbackLinks"] += len(all_fallbacks)
            stats["labeledListLinks"] += len(list_additions)
            stats["structuredTextLinks"] += len(data_additions)
            fallback_examples.update(
                f"{label} -> {route}" for label, route in all_fallbacks
            )

            if updated != text or updated_data != original_data:
                stats["changedEntities"] += 1
                file_changed = True
                if args.write:
                    row["descr"] = updated
                    row["data"] = updated_data
        if file_changed:
            changed_files += 1
            if args.write:
                path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")

    stats["catalogTargets"] = len(targets)
    stats["foundrySourceRecords"] = foundry_count
    stats["aonSourceRecords"] = aon_count
    stats["changedFiles"] = changed_files
    report = {
        "mode": "write" if args.write else "audit",
        "stats": dict(sorted(stats.items())),
        "topUnresolvedTargets": unresolved.most_common(args.details),
        "topRenderMismatches": render_mismatches.most_common(args.details),
        "topContextualFallbacks": fallback_examples.most_common(args.details),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
