#!/usr/bin/env python3
"""Fast, safe development commands for the Encounter+ PF2E system.

This tool intentionally never edits Encounter+'s database and never deletes
installed content. Definition files can be checksum-synced to the installed
system folder, after which the app's supported Reload System action picks them
up. Content modules still go through Encounter+'s importer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = (
    Path.home()
    / "Library/Containers/sk.qbit.tracker/Data/Documents/systems/pf2e-remaster"
)
SYSTEM_ID = "pf2e-remaster"
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
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
    "COMMUNITY-USE-NOTICE.md",
}
SYSTEM_DIRS = {
    "assets",
    "fonts",
    "forms",
    "icons",
    "images",
    "lang",
    "scripts",
    "styles",
    "themes",
    "views",
}
COLLECTION_TITLES = {
    "actions": "Actions",
    "afflictions": "Afflictions",
    "ancestries": "Ancestries",
    "archetypes": "Archetypes",
    "backgrounds": "Backgrounds",
    "characters": "Characters",
    "classes": "Classes",
    "conditions": "Conditions & Effects",
    "creatures": "Creatures",
    "deities": "Deities",
    "domains": "Domains",
    "feats": "Feats",
    "gm-tools": "GM Tools",
    "hazards": "Hazards",
    "heritages": "Heritages",
    "items": "Items",
    "languages": "Languages",
    "rituals": "Rituals",
    "rules": "Rules",
    "spells": "Spells",
    "tables": "Tables",
    "traits": "Traits",
    "vehicles": "Vehicles",
}
LABEL_TO_COLLECTION = {
    "action": "actions",
    "affliction": "afflictions",
    "ancestry": "ancestries",
    "archetype": "archetypes",
    "background": "backgrounds",
    "character": "characters",
    "hero": "characters",
    "class": "classes",
    "condition": "conditions",
    "status-effect": "conditions",
    "creature": "creatures",
    "deity": "deities",
    "domain": "domains",
    "feat": "feats",
    "gm-tool": "gm-tools",
    "hazard": "hazards",
    "heritage": "heritages",
    "item": "items",
    "language": "languages",
    "ritual": "rituals",
    "rule": "rules",
    "spell": "spells",
    "table": "tables",
    "trait": "traits",
    "vehicle": "vehicles",
}

# Encounter+ uses separate enums for section containers and input fields.
# https://docs.encounter.plus/reference/schema/form-definition/
FORM_SECTION_TYPES = {"group", "list", "picker", "multiPicker", "dnd5eClassFeatures"}
FORM_FIELD_TYPES = {
    "number", "decimal", "toggle", "reference", "text", "textArea", "picker",
    "multiPicker", "colorPicker", "menu", "tags", "attributes", "modifiers",
    "list", "form", "hStack", "checkbox",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json5(path: Path) -> Any:
    try:
        import json5  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing development dependency 'json5'. Run: "
            "python3 -m pip install -r requirements-dev.txt"
        ) from exc
    return json5.loads(path.read_text(encoding="utf-8"), allow_duplicate_keys=False)


def validate_form_definition(definition: Any) -> list[str]:
    """Check native container/input types, including tabs and nested editors.

    JSON5 parsing alone cannot catch a valid field type used as a section.
    Standalone partials are checked by the same pass as top-level forms.
    """
    errors: list[str] = []

    def walk(node: Any, role: str, location: str) -> None:
        if not isinstance(node, dict):
            errors.append(f"{location or 'form'}: expected an object")
            return
        if role != "form":
            default = "group" if role == "section" else "text"
            kind = node.get("type") if node.get("type") is not None else default
            allowed = FORM_SECTION_TYPES if role == "section" else FORM_FIELD_TYPES
            if not isinstance(kind, str) or kind not in allowed:
                errors.append(f"{location}.type: invalid {role} type {kind!r}")

        children = (
            {"tabs": "form", "sections": "section"}
            if role == "form" else {"fields": "field"}
        )
        for key, child_role in children.items():
            value = node.get(key)
            if value is None:
                continue
            child_path = f"{location}.{key}" if location else key
            if not isinstance(value, list):
                errors.append(f"{child_path}: expected an array")
                continue
            for index, child in enumerate(value):
                walk(child, child_role, f"{child_path}[{index}]")
        if role != "form" and node.get("form") is not None:
            walk(node["form"], "form", f"{location}.form")

    walk(definition, "form", "")
    return errors


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def definition_files() -> list[Path]:
    files = [REPO / name for name in sorted(SYSTEM_FILES) if name.endswith(".json")]
    for directory in sorted(SYSTEM_DIRS):
        root = REPO / directory
        if root.is_dir():
            files.extend(sorted(root.rglob("*.json")))
    return files


def sync_files() -> list[Path]:
    files = [REPO / name for name in sorted(SYSTEM_FILES) if (REPO / name).is_file()]
    for directory in sorted(SYSTEM_DIRS):
        root = REPO / directory
        if not root.is_dir():
            continue
        files.extend(
            path
            for path in sorted(root.rglob("*"))
            if path.is_file()
            and not any(part.startswith(".") for part in path.relative_to(REPO).parts)
            and "__pycache__" not in path.parts
        )
    return files


def run_validator(script: str) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, str(REPO / "tools" / script)],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return result.returncode == 0, lines[-1] if lines else script


def run_node_tests() -> tuple[bool, str]:
    node = os.environ.get("NODE") or shutil.which("node")
    tests = sorted((REPO / "tests").glob("*.test.cjs"))
    if not node:
        return False, "Node.js is required for the system UI regression suite"
    result = subprocess.run(
        [node, "--test", *(str(path) for path in tests)],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode == 0:
        return True, f"Validated {len(tests)} system UI regression files"
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    failure = next(
        (
            line
            for line in reversed(lines)
            if (line.startswith("✖") or line.startswith("not ok"))
            and "failing tests:" not in line.casefold()
        ),
        None,
    )
    return False, failure or (lines[-1] if lines else "system UI regressions failed")


def validate_project() -> dict[str, Any]:
    errors: list[str] = []
    parsed = 0
    for path in definition_files():
        try:
            definition = load_json5(path)
            parsed += 1
            if path.is_relative_to(REPO / "forms"):
                errors.extend(
                    f"{path.relative_to(REPO)}: {error}"
                    for error in validate_form_definition(definition)
                )
        except Exception as exc:  # decoder messages are the useful result here
            errors.append(f"{path.relative_to(REPO)}: {exc}")

    try:
        system = load_json5(REPO / "system.json")
        manifest = load_json(REPO / "manifest.json")
        for field in ("id", "name", "version"):
            if not system.get(field):
                errors.append(f"system.json: missing {field}")
        for field in ("id", "name", "type", "version", "download"):
            if not manifest.get(field):
                errors.append(f"manifest.json: missing {field}")
        if system.get("id") != SYSTEM_ID or manifest.get("id") != SYSTEM_ID:
            errors.append("system and package ids must both be pf2e-remaster")
        if manifest.get("type") != "system":
            errors.append("manifest.json: type must be system")
        if system.get("version") != manifest.get("version"):
            errors.append("system.json and manifest.json versions differ")
        if not SEMVER.match(str(system.get("version") or "")):
            errors.append("system.json: version is not semantic versioning")
        if not str(system.get("package") or "").endswith("/manifest.json"):
            errors.append("system.json: package must point at the latest manifest")
        if not str(manifest.get("download") or "").endswith("/pf2e-remaster.system"):
            errors.append("manifest.json: download must point at pf2e-remaster.system")

        entities = load_json5(REPO / "entities.json")
        names: set[str] = set()
        labels: set[str] = set()
        collections: set[str] = set()
        for index, entity in enumerate(entities):
            name = str(entity.get("name") or "")
            label = str(entity.get("label") or "")
            collection = str((entity.get("collection") or {}).get("label") or "")
            if not name or not label or not collection:
                errors.append(f"entities.json[{index}]: missing name, label, or collection")
            if name in names or label in labels or collection in collections:
                errors.append(f"entities.json[{index}]: duplicate entity identifier")
            names.add(name)
            labels.add(label)
            collections.add(collection)

        pages = load_json(REPO / "pages.json")
        groups = load_json(REPO / "groups.json")
        page_slugs = {str(page.get("slug") or "") for page in pages}
        group_ids = {str(group.get("id") or "") for group in groups}
        record_ids = [str(record.get("id") or "") for record in pages + groups]
        if not pages or not groups:
            errors.append("Operations Center pages and groups must not be empty")
        if "" in page_slugs or len(page_slugs) != len(pages):
            errors.append("pages.json: missing or duplicate page slug")
        if "" in record_ids or len(record_ids) != len(set(record_ids)):
            errors.append("pages/groups: missing or duplicate record id")
        for page in pages:
            slug = str(page.get("slug") or "")
            content = str(page.get("content") or "")
            if str(page.get("parentId") or "") not in group_ids:
                errors.append(f"pages.json: {slug} has an unknown parent group")
            if "<style data-pf2e-operations-center>" not in content or ".pf2e-ops {" not in content:
                errors.append(f"pages.json: {slug} is missing its standalone page styles")
            for target_slug in re.findall(r'href="/page/([^\"]+)"', content):
                if target_slug not in page_slugs:
                    errors.append(f"pages.json: {slug} links to unknown page {target_slug}")
            if slug != "pf2e-operations-center" and 'href="/page/pf2e-operations-center"' not in content:
                errors.append(f"pages.json: {slug} has no Home breadcrumb")

        rule_slugs: set[str] = set()
        for rules_file in (REPO / "compendium").glob("**/rules.json"):
            for rule in load_json(rules_file):
                rule_slugs.add(str(rule.get("slug") or ""))
        tool_slugs = {
            str(tool.get("slug") or "")
            for tool in load_json(REPO / "gm-tools.json")
        }
        action_slugs: set[str] = set()
        for actions_file in (REPO / "compendium").glob("**/actions.json"):
            for action in load_json(actions_file):
                action_slugs.add(str(action.get("slug") or ""))
        table_slugs: set[str] = set()
        for tables_file in (REPO / "compendium").glob("**/tables.json"):
            for table in load_json(tables_file):
                table_slugs.add(str(table.get("slug") or ""))
        for page in pages:
            slug = str(page.get("slug") or "")
            content = str(page.get("content") or "")
            for target_slug in re.findall(r'href="/rule/([^\"]+)"', content):
                if target_slug not in rule_slugs:
                    errors.append(f"pages.json: {slug} links to unknown rule {target_slug}")
            for target_slug in re.findall(r'href="/gm-tool/([^\"]+)"', content):
                if target_slug not in tool_slugs:
                    errors.append(f"pages.json: {slug} links to unknown GM tool {target_slug}")
            for target_slug in re.findall(r'href="/action/([^\"]+)"', content):
                if target_slug not in action_slugs:
                    errors.append(f"pages.json: {slug} links to unknown action {target_slug}")
            for target_slug in re.findall(r'href="/table/([^\"]+)"', content):
                if target_slug not in table_slugs:
                    errors.append(f"pages.json: {slug} links to unknown table {target_slug}")
    except Exception as exc:
        errors.append(f"metadata validation: {exc}")

    ogl_root = REPO / "compendium" / "ogl-packs" / "rage-of-elements"
    try:
        module = load_json(ogl_root / "module.json")
        if module.get("license") != "OGL-1.0a":
            errors.append("Rage of Elements source pack lacks its OGL marker")
        if module.get("licenseFile") != "OGL-1.0a.txt":
            errors.append("Rage of Elements source pack lacks its OGL license file")
    except Exception as exc:
        errors.append(f"Rage of Elements metadata validation: {exc}")

    validators: dict[str, str] = {}
    for script in (
        "validate_public_orc_compendium.py",
        "validate_public_ogl_compendium.py",
        "test_compendium_conversion.py",
        "test_creature_editability.py",
        "test_creature_spellcasting.py",
        "test_hazard_vehicle_mechanics.py",
        "test_reference_tables.py",
        "test_spell_area_templates.py",
    ):
        ok, message = run_validator(script)
        validators[script] = message
        if not ok:
            errors.append(f"{script}: {message}")

    ok, message = run_node_tests()
    validators["system-ui-regressions"] = message
    if not ok:
        errors.append(f"system-ui-regressions: {message}")

    return {
        "ok": not errors,
        "definitionFiles": parsed,
        "validators": validators,
        "errors": errors,
    }


def git_changes() -> list[str]:
    commands = (
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    paths: set[str] = set()
    for command in commands:
        result = subprocess.run(
            command,
            cwd=REPO,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        paths.update(line for line in result.stdout.splitlines() if line)
    return sorted(paths)


def impacted_collections(paths: Iterable[str]) -> list[str]:
    impacted: set[str] = set()
    all_collections = False
    for value in paths:
        path = Path(value)
        if path.name in {"manifest.json", "system.json"} and "compendium" not in path.parts:
            impacted.add("System package details")
            continue
        if path.parts and path.parts[0] in {"styles", "themes", "scripts"}:
            all_collections = True
            continue
        if path.name in {
            "config.json",
            "entities.json",
            "types.json",
            "collections.json",
            "filters.json",
            "groups.json",
            "pages.json",
        }:
            all_collections = True
            continue
        if path.parts and path.parts[0] in {"forms", "views"}:
            if "partials" in path.parts:
                all_collections = True
                continue
            label = path.stem.removesuffix("-compact")
            collection = LABEL_TO_COLLECTION.get(label)
            if collection:
                impacted.add(collection)
            continue
        if "compendium" in path.parts and path.suffix == ".json":
            if path.stem in COLLECTION_TITLES:
                impacted.add(path.stem)
    if all_collections:
        return ["All compendium views"]
    return [COLLECTION_TITLES.get(name, name) for name in sorted(impacted)]


def sync_status(target: Path) -> dict[str, Any]:
    changed: list[str] = []
    missing: list[str] = []
    same = 0
    for source in sync_files():
        relative = source.relative_to(REPO)
        destination = target / relative
        if not destination.is_file():
            missing.append(relative.as_posix())
        elif sha256(source) != sha256(destination):
            changed.append(relative.as_posix())
        else:
            same += 1
    candidates = sorted(changed + missing)
    return {
        "target": str(target),
        "changed": sorted(changed),
        "missing": sorted(missing),
        "unchanged": same,
        "uiTargets": impacted_collections(candidates),
    }


def verify_target(target: Path) -> None:
    if not target.is_dir():
        raise RuntimeError(f"installed system folder not found: {target}")
    installed = load_json5(target / "system.json")
    if installed.get("id") != SYSTEM_ID:
        raise RuntimeError(f"refusing to sync into a different system: {target}")


def sync_system(target: Path, apply: bool) -> dict[str, Any]:
    check = validate_project()
    if not check["ok"]:
        return {"ok": False, "applied": False, "errors": check["errors"]}
    verify_target(target)
    status = sync_status(target)
    copied: list[str] = []
    if apply:
        for relative in status["changed"] + status["missing"]:
            source = REPO / relative
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(relative)
    return {
        "ok": True,
        "applied": apply,
        "copied": sorted(copied),
        "pending": [] if apply else sorted(status["changed"] + status["missing"]),
        "unchanged": status["unchanged"],
        "uiTargets": status["uiTargets"],
        "note": "No files are ever deleted by sync-system.",
    }


def clean_zip_names(names: Iterable[str]) -> list[str]:
    return sorted(
        name
        for name in names
        if "__MACOSX" in Path(name).parts
        or any(part.startswith("._") for part in Path(name).parts)
        or Path(name).name == ".DS_Store"
    )


def inspect_release(dist: Path) -> dict[str, Any]:
    errors: list[str] = []
    system_path = dist / "pf2e-remaster.system"
    required = {
        system_path,
        dist / "manifest.json",
        dist / "release-summary.json",
        dist / "SHA256SUMS.txt",
    }
    for path in sorted(required):
        if not path.is_file():
            errors.append(f"missing release file: {path.name}")

    orc_records = 0
    ogl_records = 0
    tool_records = 0
    orc_ids: set[str] = set()
    collection_counts: dict[str, int] = {}
    if system_path.is_file():
        with zipfile.ZipFile(system_path) as bundle:
            names = set(bundle.namelist())
            junk = clean_zip_names(names)
            if junk:
                errors.append(f"system archive contains macOS junk: {junk[:3]}")
            for required_name in (
                "system.json",
                "manifest.json",
                "ORC-NOTICE.md",
                "OGL-1.0a.txt",
                "CONTENT-LICENSES.md",
                "COMMUNITY-USE-NOTICE.md",
                "notices/ORC-SOURCES.json",
                "notices/OGL-RAGE-OF-ELEMENTS.json",
            ):
                if required_name not in names:
                    errors.append(f"system archive missing {required_name}")
            if "module.json" in names:
                errors.append("system archive contains module installer metadata")

            for name in sorted(names):
                if name not in {f"{label}.json" for label in COLLECTION_TITLES}:
                    continue
                records = json.loads(bundle.read(name))
                collection_counts[name] = len(records)
                for record in records:
                    record_id = str(record.get("id") or "")
                    if not record_id or record_id in orc_ids:
                        errors.append(f"missing or duplicate entity id in {name}")
                        break
                    orc_ids.add(record_id)
                    if record.get("system") != SYSTEM_ID:
                        errors.append(f"wrong entity system in {name}")
                        break
                    license_name = (record.get("attributes") or {}).get("license")
                    if license_name == "ORC-1.0a":
                        orc_records += 1
                    elif license_name == "OGL-1.0a":
                        ogl_records += 1
                    elif license_name == "Project-Code" and name == "gm-tools.json":
                        tool_records += 1
                    else:
                        errors.append(f"unknown entity license in {name}: {license_name!r}")
                        break
                    source_name = str((record.get("data") or {}).get("sourceName") or "")
                    if license_name in {"ORC-1.0a", "OGL-1.0a"} and not source_name.strip():
                        errors.append(f"entity is missing its packaged source name in {name}")
                        break

    for obsolete in (
        dist / "rage-of-elements-ogl.module",
        dist / "rage-of-elements-ogl-manifest.json",
    ):
        if obsolete.exists():
            errors.append(f"obsolete second installer remains in release: {obsolete.name}")

    expected_orc = sum(
        sum(kinds.values()) for kinds in load_json(REPO / "compendium" / "summary.json").values()
    )
    expected_ogl = sum(
        sum(kinds.values())
        for kinds in load_json(REPO / "compendium" / "ogl-summary.json").values()
    )
    if orc_records != expected_orc:
        errors.append(f"ORC record count {orc_records} != expected {expected_orc}")
    if ogl_records != expected_ogl:
        errors.append(f"OGL record count {ogl_records} != expected {expected_ogl}")
    expected_tools = len(load_json(REPO / "gm-tools.json"))
    if tool_records != expected_tools:
        errors.append(f"GM tool record count {tool_records} != expected {expected_tools}")

    return {
        "ok": not errors,
        "installablePackages": 1,
        "orcRecords": orc_records,
        "oglRecords": ogl_records,
        "toolRecords": tool_records,
        "contentRecords": orc_records + ogl_records,
        "totalRecords": orc_records + ogl_records + tool_records,
        "collectionCounts": collection_counts,
        "systemBytes": system_path.stat().st_size if system_path.is_file() else 0,
        "errors": errors,
    }


def emit(result: dict[str, Any], compact: bool) -> None:
    if compact:
        print(json.dumps(result, separators=(",", ":"), ensure_ascii=False))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="run local syntax, metadata, and license checks")
    check.add_argument("--json", action="store_true", help="emit one compact JSON line")

    status = commands.add_parser("status", help="show changed files and targeted UI checks")
    status.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    status.add_argument("--json", action="store_true", help="emit one compact JSON line")

    sync = commands.add_parser("sync-system", help="checksum-sync system definition files")
    sync.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    sync.add_argument("--apply", action="store_true", help="copy files; default is dry-run")
    sync.add_argument("--json", action="store_true", help="emit one compact JSON line")

    inspect = commands.add_parser("inspect-release", help="inspect generated release archives")
    inspect.add_argument("--dist", type=Path, default=REPO / "dist")
    inspect.add_argument("--json", action="store_true", help="emit one compact JSON line")
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "check":
        result = validate_project()
    elif args.command == "status":
        verify_target(args.target)
        changes = git_changes()
        result = {
            "ok": True,
            "gitChanges": changes,
            "gitUiTargets": impacted_collections(changes),
            "sync": sync_status(args.target),
        }
    elif args.command == "sync-system":
        result = sync_system(args.target, args.apply)
    else:
        result = inspect_release(args.dist)
    emit(result, args.json)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
