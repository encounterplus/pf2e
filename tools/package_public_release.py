#!/usr/bin/env python3
"""Build the public Encounter+ release deterministically.

The normal release is one installable ``pf2e-remaster.system`` archive. It
contains the system definitions, every reviewed ORC pack, and the separately
licensed Rage of Elements OGL records. The records retain their individual
license markers and both complete notice sets are embedded in the archive.

The per-book ORC module sources remain in the repository for review,
attribution, and maintenance. They can still be built explicitly with
``--individual-modules`` but are not part of the normal user install.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable


REPO = Path(__file__).resolve().parents[1]
FIXED_TIME = (2020, 1, 1, 0, 0, 0)
SYSTEM_VERSION = json.loads((REPO / "system.json").read_text(encoding="utf-8"))["version"]
SYSTEM_FILES = {
    "system.json",
    "manifest.json",
    "config.json",
    "entities.json",
    "types.json",
    "collections.json",
    "filters.json",
    "gm-tools.json",
    "groups.json",
    "pages.json",
    "pf2e-banner.png",
    "COMMUNITY-USE-NOTICE.md",
    "CONTENT-LICENSES.md",
}
SYSTEM_DIRS = {
    "assets",
    "fonts",
    "forms",
    "icons",
    "images",
    "lang",
    "migrations",
    "scripts",
    "styles",
    "themes",
    "views",
}
GENERATED_FILES = {
    "manifest.json",
    "rage-of-elements-ogl-manifest.json",
    "release-summary.json",
    "SHA256SUMS.txt",
}
CONFLICT_COPY = re.compile(
    r"^(?P<stem>.+) (?P<copy>(?:[2-9]|[1-9]\d+))(?P<suffix>\.[^.]+)$"
)

DAMAGE_COMPONENT = re.compile(
    r"(^|(?P<connector>\s*(?:;|,|\bplus\b|\band\b)\s*))"
    r"(?P<amount>(?:\d+)?d\d+(?:\s*[+-]\s*\d+)?|\d+)(?=\s|$)",
    re.IGNORECASE,
)
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=REPO / "dist")
    parser.add_argument(
        "--individual-modules",
        action="store_true",
        help="also build the 22 source-by-source ORC modules under dist/individual",
    )
    parser.add_argument(
        "--test-shell",
        action="store_true",
        help="also build a content-free temporary system under dist/test for clean-install testing",
    )
    return parser.parse_args()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def add_bytes(bundle: zipfile.ZipFile, name: str, content: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    bundle.writestr(info, content)


def add_file(bundle: zipfile.ZipFile, source: Path, name: str) -> None:
    add_bytes(bundle, name, source.read_bytes())


def parse_damage_parts(value: object) -> list[dict[str, str]]:
    """Split legacy natural-language damage into editable, explicitly rollable parts."""
    if not isinstance(value, str) or not value.strip():
        return []

    text = value.strip()
    matches = list(DAMAGE_COMPONENT.finditer(text))
    if not matches:
        amount, separator, details = text.partition(" ")
        return [{"name": amount, "details": details if separator else ""}]

    parts: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        details = text[match.end("amount") : end].strip()
        part = {
            "name": re.sub(r"\s+", "", match.group("amount")),
            "details": details,
        }
        connector = match.group("connector")
        if parts and connector:
            token = connector.strip().casefold()
            part["connector"] = {
                ";": "; ",
                ",": ", ",
                "plus": " plus ",
                "and": " and ",
            }[token]
        parts.append(part)

    return parts


def add_creature_damage_parts(record: dict) -> None:
    if record.get("kind") != "Creature":
        return
    attacks = record.get("data", {}).get("attacks", [])
    if not isinstance(attacks, list):
        return
    for attack in attacks:
        if not isinstance(attack, dict) or isinstance(attack.get("damageParts"), list):
            continue
        parts = parse_damage_parts(attack.get("damage"))
        if parts:
            attack["damageParts"] = parts


def visible_files(directory: Path) -> Iterable[Path]:
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if not path.is_file() or any(part.startswith(".") for part in relative.parts):
            continue
        if "__MACOSX" in relative.parts or "__pycache__" in relative.parts:
            continue
        yield path


def system_source_files() -> Iterable[tuple[Path, str]]:
    for name in sorted(SYSTEM_FILES):
        path = REPO / name
        if path.is_file():
            yield path, name

    for directory_name in sorted(SYSTEM_DIRS):
        directory = REPO / directory_name
        if not directory.is_dir():
            continue
        for path in visible_files(directory):
            yield path, path.relative_to(REPO).as_posix()


def load_orc_collections() -> tuple[dict[str, list[dict]], dict[str, int]]:
    collections: dict[str, list[dict]] = defaultdict(list)
    seen_ids: dict[str, str] = {}

    for pack in sorted((REPO / "compendium" / "packs").iterdir()):
        if not pack.is_dir() or not (pack / "module.json").is_file():
            continue
        for path in sorted(pack.glob("*.json")):
            if path.name in {"module.json", "source.json", "manifest.json"}:
                continue
            records = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(records, list):
                raise ValueError(f"{path}: expected a JSON array")
            for record in records:
                record_id = str(record.get("id") or "")
                if not record_id:
                    raise ValueError(f"{path}: record without an id")
                if record_id in seen_ids:
                    raise ValueError(
                        f"duplicate entity id {record_id} in {seen_ids[record_id]} and {path}"
                    )
                seen_ids[record_id] = str(path)
                source_names = []
                for source in record.get("sources", []):
                    if not isinstance(source, dict):
                        continue
                    name = str(source.get("name") or "").strip()
                    if not name:
                        continue
                    page = source.get("page")
                    source_names.append(f"{name} pg. {page}" if page else name)
                if source_names:
                    record.setdefault("data", {})["sourceName"] = ", ".join(source_names)
                add_creature_damage_parts(record)
                record["systemVersion"] = SYSTEM_VERSION
            collections[path.name].extend(records)

    for records in collections.values():
        records.sort(
            key=lambda record: (
                str(record.get("kind") or "").casefold(),
                str(record.get("name") or "").casefold(),
                str(record.get("id") or ""),
            )
        )

    counts = {name: len(records) for name, records in sorted(collections.items())}
    return dict(collections), counts


def load_ogl_collections(existing_ids: set[str]) -> tuple[dict[str, list[dict]], dict[str, int]]:
    root = REPO / "compendium" / "ogl-packs" / "rage-of-elements"
    collections: dict[str, list[dict]] = defaultdict(list)
    seen_ids = set(existing_ids)

    for path in sorted(root.glob("*.json")):
        if path.name in {"module.json", "source.json", "manifest.json"}:
            continue
        records = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError(f"{path}: expected a JSON array")
        for record in records:
            record_id = str(record.get("id") or "")
            if not record_id:
                raise ValueError(f"{path}: record without an id")
            if record_id in seen_ids:
                raise ValueError(f"duplicate ORC/OGL entity id {record_id} in {path}")
            seen_ids.add(record_id)
            source_names = []
            for source in record.get("sources", []):
                if not isinstance(source, dict):
                    continue
                name = str(source.get("name") or "").strip()
                if not name:
                    continue
                page = source.get("page")
                source_names.append(f"{name} pg. {page}" if page else name)
            if source_names:
                record.setdefault("data", {})["sourceName"] = ", ".join(source_names)
            add_creature_damage_parts(record)
            record["systemVersion"] = SYSTEM_VERSION
        collections[path.name].extend(records)

    counts = {name: len(records) for name, records in sorted(collections.items())}
    return dict(collections), counts


def load_project_collections() -> tuple[dict[str, list[dict]], dict[str, int]]:
    records = json.loads((REPO / "gm-tools.json").read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("gm-tools.json: expected a JSON array")
    for record in records:
        if (record.get("attributes") or {}).get("license") != "Project-Code":
            raise ValueError("gm-tools.json: every tool must carry the Project-Code marker")
        record["systemVersion"] = SYSTEM_VERSION
    return {"gm-tools.json": records}, {"gm-tools.json": len(records)}


def build_system(target: Path) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    orc_collections, orc_counts = load_orc_collections()
    orc_ids = {
        str(record.get("id") or "")
        for records in orc_collections.values()
        for record in records
    }
    ogl_collections, ogl_counts = load_ogl_collections(orc_ids)
    project_collections, project_counts = load_project_collections()
    collections: dict[str, list[dict]] = defaultdict(list)
    for source in (orc_collections, ogl_collections, project_collections):
        for name, records in source.items():
            collections[name].extend(records)
    for records in collections.values():
        records.sort(
            key=lambda record: (
                str(record.get("kind") or "").casefold(),
                str(record.get("name") or "").casefold(),
                str(record.get("id") or ""),
            )
        )

    with zipfile.ZipFile(
        target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as bundle:
        written: set[str] = set()
        for source, name in system_source_files():
            if name in project_collections:
                continue
            if name in written:
                raise ValueError(f"duplicate system archive path: {name}")
            add_file(bundle, source, name)
            written.add(name)

        for name, records in sorted(collections.items()):
            if name in written:
                raise ValueError(f"ORC collection conflicts with system file: {name}")
            add_bytes(bundle, name, json_bytes(records))
            written.add(name)

        notices = REPO / "compendium"
        add_file(bundle, notices / "ORC-NOTICE.md", "ORC-NOTICE.md")
        add_file(bundle, notices / "sources.json", "notices/ORC-SOURCES.json")
        add_file(bundle, notices / "summary.json", "notices/ORC-SUMMARY.json")
        ogl_root = notices / "ogl-packs" / "rage-of-elements"
        add_file(bundle, ogl_root / "OGL-1.0a.txt", "OGL-1.0a.txt")
        add_file(bundle, ogl_root / "source.json", "notices/OGL-RAGE-OF-ELEMENTS.json")

    return orc_counts, ogl_counts, project_counts


def build_test_shell(target: Path) -> None:
    metadata = json.loads((REPO / "system.json").read_text(encoding="utf-8"))
    metadata.update(
        {
            "id": "codex-test-shell",
            "name": "Temporary Test System",
            "shortName": "Test Shell",
            "shortDescr": "Content-free unload target for clean-install verification.",
            "descr": "Temporary local system used only while testing package replacement.",
            "version": "0.0.1",
        }
    )
    for key in ("package", "repository", "website"):
        metadata.pop(key, None)

    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as bundle:
        for source, name in system_source_files():
            if name in {"gm-tools.json", "groups.json", "pages.json"}:
                continue
            if name == "manifest.json":
                continue
            if name == "system.json":
                add_bytes(bundle, name, json_bytes(metadata))
            else:
                add_file(bundle, source, name)


def build_directory_archive(directory: Path, target: Path) -> None:
    with zipfile.ZipFile(
        target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as bundle:
        for path in visible_files(directory):
            add_file(bundle, path, path.relative_to(directory).as_posix())


def clear_owned_output(output: Path) -> None:
    for path in output.iterdir() if output.exists() else []:
        conflict = CONFLICT_COPY.match(path.name)
        canonical = (
            f"{conflict.group('stem')}{conflict.group('suffix')}"
            if conflict
            else ""
        )
        if path.is_file() and (
            path.suffix in {".system", ".module"}
            or path.name in GENERATED_FILES
            or canonical in GENERATED_FILES
        ):
            path.unlink()


def copy_json(source: Path, target: Path) -> None:
    value = json.loads(source.read_text(encoding="utf-8"))
    target.write_bytes(json_bytes(value))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    clear_owned_output(args.output)

    system_target = args.output / "pf2e-remaster.system"
    orc_counts, ogl_counts, project_counts = build_system(system_target)

    copy_json(REPO / "manifest.json", args.output / "manifest.json")

    individual_count = 0
    if args.individual_modules:
        individual_root = args.output / "individual"
        individual_root.mkdir(parents=True, exist_ok=True)
        for pack in sorted((REPO / "compendium" / "packs").iterdir()):
            if not pack.is_dir() or not (pack / "module.json").is_file():
                continue
            build_directory_archive(pack, individual_root / f"{pack.name}.module")
            individual_count += 1

    test_shell = None
    if args.test_shell:
        test_shell = args.output / "test" / "temporary-test-system.system"
        build_test_shell(test_shell)

    summary = {
        "system": system_target.name,
        "orcCollections": orc_counts,
        "orcRecords": sum(orc_counts.values()),
        "oglCollections": ogl_counts,
        "oglRecords": sum(ogl_counts.values()),
        "projectCollections": project_counts,
        "toolRecords": sum(project_counts.values()),
        "contentRecords": sum(orc_counts.values()) + sum(ogl_counts.values()),
        "totalRecords": sum(orc_counts.values()) + sum(ogl_counts.values()) + sum(project_counts.values()),
        "installablePackages": 1,
        "individualModulesBuilt": individual_count,
        "testShellBuilt": test_shell is not None,
    }
    (args.output / "release-summary.json").write_bytes(json_bytes(summary))

    checksummed = [
        system_target,
        args.output / "manifest.json",
        args.output / "release-summary.json",
    ]
    checksum_text = "".join(f"{sha256(path)}  {path.name}\n" for path in checksummed)
    (args.output / "SHA256SUMS.txt").write_text(checksum_text, encoding="utf-8")

    print(json.dumps(summary, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
