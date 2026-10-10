#!/usr/bin/env python3
"""Regression checks for native spell loading: map areas and token effects."""

from __future__ import annotations

import json
import os
import subprocess
from copy import deepcopy
from pathlib import Path

import json5

from spell_area_templates import parse_spell_area
from spell_load_data import (
    MANUAL_REMINDER_DURATION, configure_spell_load_data, parse_spell_duration,
)
from eplus_dev import validate_form_definition


REPO = Path(__file__).resolve().parents[1]
EXPECTED_AREA_SPELLS = 333
EXPECTED_CONFIGURED = 308
EXPECTED_SKIPPED = 25

PILOT_SPELLS = {
    "breathe-fire-player-core": ("15-foot cone", "cone", 15),
    "detect-magic-player-core": ("30-foot emanation", "sphere", 30),
    "fireball-player-core": ("20-foot burst", "sphere", 20),
    "lightning-bolt-player-core": ("120-foot line", "line", 120),
    "hellfire-plume-player-core-2": ("10-foot cylinder", "cylinder", 10),
    "spout-player-core-2": ("5-foot cube", "cube", 5),
}


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def form_nodes(definition: dict, location: str = ""):
    """Find controls by meaning while allowing editor sections to move."""
    yield location, definition
    for key in ("tabs", "sections", "fields"):
        for index, child in enumerate(definition.get(key, [])):
            path = f"{location}.{key}[{index}]" if location else f"{key}[{index}]"
            yield from form_nodes(child, path)
    if isinstance(definition.get("form"), dict):
        yield from form_nodes(definition["form"], f"{location}.form")


def main() -> None:
    records: dict[str, dict] = {}
    area_spells = 0
    configured = 0
    skipped = 0
    durations: list[dict] = []
    manual_reminders = 0

    roots = (REPO / "compendium" / "packs", REPO / "compendium" / "ogl-packs")
    for root in roots:
        for path in sorted(root.glob("*/spells.json")):
            for record in load_json(path):
                slug = str(record.get("slug") or "")
                records[slug] = record
                data = record.get("data") or {}
                assert isinstance(data.get("durationText"), str), f"{slug}: missing duration prose"
                expected_duration = parse_spell_duration(data["durationText"])
                actual_duration = {
                    key: data[key] for key in ("duration", "durationType", "durationUnit")
                    if key in data
                }
                assert actual_duration == expected_duration, f"{slug}: incorrect native duration"
                assert not isinstance(data.get("duration"), str), f"{slug}: legacy duration passed to native loading"
                if not data.get("durationType"):
                    manual_reminders += 1
                    assert actual_duration == {"durationUnit": "round"}, f"{slug}: reminder acquired a countdown"
                durations.append({"kind": "Spell", "data": {"duration": data["durationText"]}})
                area = str(data.get("area") or "").strip()
                parsed = parse_spell_area(area)
                has_shape = "areaEffectShape" in data
                has_size = "areaEffectSize" in data
                assert has_shape == has_size, f"{slug}: incomplete area template"

                if not area:
                    assert not has_shape, f"{slug}: area-less spell has a template"
                    continue

                area_spells += 1
                if parsed is None:
                    skipped += 1
                    assert not has_shape, f"{slug}: exceptional area must remain manual"
                    continue

                configured += 1
                expected_shape, expected_size = parsed
                assert data["areaEffectShape"] == expected_shape, f"{slug}: wrong template shape"
                assert data["areaEffectSize"] == expected_size, f"{slug}: wrong template size"

    assert area_spells == EXPECTED_AREA_SPELLS, (
        f"area spell count changed: expected {EXPECTED_AREA_SPELLS}, got {area_spells}"
    )
    assert configured == EXPECTED_CONFIGURED, (
        f"configured spell count changed: expected {EXPECTED_CONFIGURED}, got {configured}"
    )
    assert skipped == EXPECTED_SKIPPED, (
        f"manual spell count changed: expected {EXPECTED_SKIPPED}, got {skipped}"
    )

    for slug, (area, shape, size) in PILOT_SPELLS.items():
        data = records[slug]["data"]
        assert data["area"] == area, f"{slug}: source-book area text changed"
        assert data["areaEffectShape"] == shape, f"{slug}: wrong template shape"
        assert data["areaEffectSize"] == size, f"{slug}: wrong template size"

    entities = json5.loads((REPO / "entities.json").read_text(encoding="utf-8"))
    spell = next(entity for entity in entities if entity.get("name") == "Spell")
    assert spell.get("loadable") is True, "Spell must be loadable for map placement"

    expected_durations = {
        "haste-player-core": {"durationType": "time", "duration": 1, "durationUnit": "minute"},
        "shield-player-core": {"durationType": "sourceStartNextTurn", "duration": 1, "durationUnit": "round"},
        "command-player-core": {"durationType": "targetEndNextTurn", "duration": 1, "durationUnit": "round"},
        "heal-player-core": MANUAL_REMINDER_DURATION,
        "mystic-armor-player-core": MANUAL_REMINDER_DURATION,
    }
    for slug, expected in expected_durations.items():
        data = records[slug]["data"]
        assert parse_spell_duration(data["durationText"]) == expected, slug
    for slug, text in {
        "haste-player-core": "1 minute",
        "shield-player-core": "until the start of your next turn",
        "command-player-core": "until the end of the target's next turn",
        "mystic-armor-player-core": "until your next daily preparations",
    }.items():
        assert records[slug]["data"]["durationText"] == text, f"{slug}: source duration changed"

    for text, expected in {
        "sustained for up to 10 minutes": {"durationType": "time", "duration": 10, "durationUnit": "minute"},
        "1 week": {"durationType": "time", "duration": 7, "durationUnit": "day"},
        "1 minute or until expended": {"durationType": "time", "duration": 1, "durationUnit": "minute"},
        "10 minutes or 8 hours": MANUAL_REMINDER_DURATION,
        "until the end of your turn": MANUAL_REMINDER_DURATION,
        "1 or more rounds": MANUAL_REMINDER_DURATION,
        "varies": MANUAL_REMINDER_DURATION,
        "1 year": MANUAL_REMINDER_DURATION,
        "0 rounds": MANUAL_REMINDER_DURATION,
    }.items():
        assert parse_spell_duration(text) == expected, text
        durations.append({"kind": "Spell", "data": {"duration": text}})

    # Existing/custom records need the same lossless conversion as the builders.
    already_converted = {
        "kind": "Spell", "data": {"durationText": "until your next daily preparations"}
    }
    fixtures = durations + [
        {"kind": "Spell", "data": {"duration": 3, "durationUnit": "round", "durationType": "time"}},
        {"kind": "Spell", "data": {"durationType": "untilDispelled", "durationUnit": "round"}},
        {"kind": "Spell", "data": {"durationType": "savingThrow", "durationUnit": "round"}},
        {"kind": "Spell", "data": {"duration": "custom", "durationType": "targetEndNextTurn"}},
        {"kind": "Spell", "data": {}},
        {"kind": "Creature", "data": {"duration": "1 minute"}},
        {"kind": "Spell", "data": {"duration": "1 minute", "durationText": "GM notes"}},
        already_converted,
        {"kind": "Spell", "data": {"duration": "1 minute", "durationType": ""}},
        {"kind": "Spell", "data": {"durationUnit": "round"}},
        {"kind": "Spell", "data": {"duration": 2, "durationType": "", "durationUnit": "minute"}},
    ]
    converted = deepcopy(fixtures)
    for entity in converted:
        configure_spell_load_data(entity)
        again = deepcopy(entity)
        assert not configure_spell_load_data(entity), "duration conversion must be idempotent"
        assert entity == again, "duration conversion changed native GM settings"
    runner = """
const fs = require('node:fs'), vm = require('node:vm');
const context = {};
vm.runInNewContext(fs.readFileSync('migrations/0.9.02.js', 'utf8'), context);
const fixtures = JSON.parse(fs.readFileSync(0, 'utf8'));
for (const entity of fixtures) {
  context.migrate(entity, {});
  if (context.migrate(entity, {}) !== null) throw Error('migration is not idempotent');
}
process.stdout.write(JSON.stringify(fixtures));
"""
    migrated = subprocess.run(
        [os.environ.get("NODE", "node"), "-e", runner], input=json.dumps(fixtures),
        cwd=REPO, text=True, capture_output=True, check=True,
    )
    assert json.loads(migrated.stdout) == converted, "native migration and builder disagree"
    assert manual_reminders == 595, f"unexpected manual reminder count: {manual_reminders}"
    # A missing or empty expiry type cannot turn a manual marker into a timer,
    # even when switching a GM-authored timed spell to manual leaves an amount.
    for original, result in zip(fixtures, converted):
        if original.get("kind") == "Spell" and original["data"].get("durationType") == "":
            assert not result["data"].get("durationType"), "manual selection became a timer"
        if original.get("kind") == "Spell" and original["data"].get("durationType") in ("untilDispelled", "savingThrow"):
            assert result == original, "conversion changed a native engine expiry choice"
    migrated_reminder = converted[fixtures.index(already_converted)]
    assert migrated_reminder["data"] == {
        "durationText": "until your next daily preparations", "durationUnit": "round"
    }, "already-converted spells did not gain manual loading"

    types = json5.loads((REPO / "types.json").read_text(encoding="utf-8"))
    shapes = set(types["AreaEffectShape"])
    configured_shapes = {
        record["data"]["areaEffectShape"]
        for record in records.values()
        if "areaEffectShape" in (record.get("data") or {})
    }
    assert configured_shapes <= shapes, "AreaEffectShape is missing a configured shape"

    form = json5.loads((REPO / "forms" / "spell.json").read_text(encoding="utf-8"))
    assert not validate_form_definition(form), "spell editor has invalid native form types"
    area_path, area_field = next(
        (path, node) for path, node in form_nodes(form)
        if node.get("type") == "form" and node.get("title") == "Spell.AreaTemplate"
    )
    area_form = area_field["form"]
    size_section = area_form["sections"][1]
    assert size_section["type"] == "group", "area size must use a group section"
    size_field = size_section["fields"][0]
    assert size_field["type"] == "decimal", "area size must allow fractional values"
    assert size_field["units"] == "ft", "area size must support native unit conversion"

    # The screenshot failure must be caught at the same nested decoder path.
    broken = deepcopy(form)
    broken_area = next(
        node for _, node in form_nodes(broken)
        if node.get("type") == "form" and node.get("title") == "Spell.AreaTemplate"
    )
    broken_area["form"]["sections"][1] = {
        "type": "decimal", "attribute": "data.areaEffectSize"
    }
    assert validate_form_definition(broken) == [
        f"{area_path}.form.sections[1].type: invalid section type 'decimal'"
    ], "validation missed the spell editor decoding failure"

    # Check the same rules inside tabs, list row editors, and field containers.
    nested = {
        "tabs": [{"sections": [{
            "type": "list",
            "form": {"sections": [{"type": "group", "fields": [{
                "type": "hStack", "fields": [{"type": "decimal"}]
            }]}]},
        }]}]
    }
    assert not validate_form_definition(nested), "valid nested editors were rejected"
    nested["tabs"][0]["sections"][0]["form"]["sections"][0]["fields"][0]["fields"][0]["type"] = "group"
    assert validate_form_definition(nested) == [
        "tabs[0].sections[0].form.sections[0].fields[0].fields[0].type: invalid field type 'group'"
    ], "validation missed an invalid nested field type"

    effect_field = next(
        node for _, node in form_nodes(form)
        if node.get("type") == "form" and node.get("title") == "Spell.EffectDuration"
    )
    assert effect_field["form"] == {
        "title": "Spell.Duration", "partial": "spell-effect-duration",
    }, "duration controls must stay in a dedicated partial form, not on the main spell page"
    effect_form = json5.loads((REPO / "forms" / "partials" / "spell-effect-duration.json").read_text())
    assert not validate_form_definition(effect_form), "duration partial has invalid native form types"
    # Regrouping must retain every editable mechanic, including variable casting
    # actions and both the legacy prose and native numeric duration controls.
    editable_fields = [
        node for definition in (form, effect_form)
        for _, node in form_nodes(definition) if node.get("attribute")
    ]
    required_attributes = {
        "data.type", "data.rank", "data.rarity", "data.traits",
        "data.castActions", "data.traditions", "data.requirements", "data.cast",
        "data.cost", "data.trigger", "data.range", "data.area", "data.targets",
        "data.defense", "data.durationText", "data.duration", "data.durationType",
        "data.durationUnit", "data.areaEffectShape", "data.areaEffectSize",
    }
    assert {
        field["attribute"] for field in editable_fields
    } == required_attributes, "spell editor changed its entity storage paths"
    for attribute in ("data.castActions", "data.traditions"):
        field = next(field for field in editable_fields if field["attribute"] == attribute)
        assert field["type"] == "multiPicker", (
            f"{attribute}: multiple selections must remain editable"
        )
    assert {
        field.get("type", "text") for field in editable_fields
        if field["attribute"] == "data.duration"
    } == {"text", "number"}, "legacy duration prose and numeric token timers need separate controls"

    casting_field = next(
        node for _, node in form_nodes(form)
        if node.get("type") == "form" and node.get("title") == "Spell.CastingDetails"
    )
    assert not casting_field.get("attribute"), "casting details must retain the entity context"
    assert not casting_field.get("visibleIf"), "empty spells must allow adding optional casting details"
    for attribute in ("data.cast", "data.requirements", "data.cost", "data.trigger"):
        assert any(
            node.get("attribute") == attribute for _, node in form_nodes(casting_field["form"])
        ), f"casting details lost the editor for {attribute}"
        assert "{{" + attribute + "}}" in casting_field["text"], (
            f"casting summary omits {attribute}"
        )
    assert "'Common.None'|l" in casting_field["text"], "empty casting details need a localized summary"
    assert "'Common.None'|l" in area_field["text"], "unconfigured map templates need a localized summary"
    assert effect_field["detail"] == "Spell.EffectDurationHelp"
    assert all(
        field.get("attribute")
        for section in effect_form["sections"] for field in section.get("fields", [])
    ), "unbound help text becomes a misleading None input in the native editor"
    assert not effect_field.get("attribute"), "duration subform must retain the entity context"
    assert effect_form["title"] == "Spell.Duration"
    assert len(effect_form["sections"]) == 3
    type_section, duration_section, unit_section = effect_form["sections"]
    assert type_section["type"] == "picker", "show expiry choices inline, without another picker screen"
    assert type_section["attribute"] == "data.durationType"
    assert type_section["attributeType"] == "DurationType", "spell expiry choices must match the native effect editor"
    assert type_section["placeholder"] == "Common.None"
    assert duration_section["type"] == "group"
    assert len(duration_section["fields"]) == 1
    duration_field = duration_section["fields"][0]
    assert duration_field["type"] == "number", "native duration must be numeric"
    assert duration_field["attribute"] == "data.duration"
    assert unit_section["type"] == "picker", "show units directly below the value"
    assert unit_section["attribute"] == "data.durationUnit"
    assert unit_section["attributeType"] == "DurationUnit"
    assert unit_section["defaultValue"] == "round"
    for section in (duration_section, unit_section):
        assert section["visibleIf"] == "{% if data.durationType == 'time' %}true{% endif %}", "timer controls must use the 5e template pattern to expand below Time"
    collections = json5.loads((REPO / "collections.json").read_text())
    assert collections["DurationType"] == [
        "savingThrow", "sourceEndNextTurn", "sourceStartNextTurn",
        "targetEndNextTurn", "targetStartNextTurn", "time", "untilDispelled",
    ], "duration choices must follow the native editor order"
    assert collections["DurationUnit"] == ["round", "minute", "hour", "day"]
    assert "SpellEffectDurationType" not in types, "spell expiry types must not diverge from native types"
    # Like 5e, declare picker value/label maps in the package, rather than relying
    # on injected app enums. Collection ordering alone cannot supply these labels.
    expected_types = {
        "DurationType": {
            "savingThrow": "DurationType.SavingThrow",
            "sourceEndNextTurn": "DurationType.SourceEndNextTurn",
            "sourceStartNextTurn": "DurationType.SourceStartNextTurn",
            "targetEndNextTurn": "DurationType.TargetEndNextTurn",
            "targetStartNextTurn": "DurationType.TargetStartNextTurn",
            "time": "DurationType.Time",
            "untilDispelled": "DurationType.UntilDispelled",
        },
        "DurationUnit": {unit: f"DurationUnit.{unit.title()}" for unit in ("round", "minute", "hour", "day")},
    }
    for name, values in expected_types.items():
        assert types.get(name) == values, f"{name}: incomplete or unmapped native duration choices"
        assert set(collections[name]) == set(values), f"{name}: ordering drops duration choices"
    required_labels = {"Common.Unit"}
    required_labels.update({
        "Spell.CastActions", "Spell.Casting", "Spell.CastingDetails",
        "Spell.CastingNotes", "Spell.RangeAndEffect", "Spell.MapAndTokenEffects",
    })
    required_labels.update(f"DurationType.{value}" for value in (
        "SavingThrow", "SourceEndNextTurn", "SourceStartNextTurn",
        "TargetEndNextTurn", "TargetStartNextTurn", "Time", "UntilDispelled",
    ))
    required_labels.update(f"DurationUnit.{unit.title()}" for unit in ("round", "minute", "hour", "day"))
    required_labels.update(f"durationunit.{unit}.{count}" for unit in ("round", "minute", "hour", "day") for count in ("one", "other"))
    for path in sorted((REPO / "lang").glob("*.json")):
        language = json5.loads(path.read_text(encoding="utf-8"))
        for key in required_labels:
            assert language.get(key) and language[key] != key, f"{path.name}: untranslated duration label {key}"
    summary = (REPO / "views" / "partials" / "spell-effect-duration.md").read_text()
    assert "map: 'DurationType'" in summary, "spell summary does not use native expiry labels"
    assert "'Common.None'|l" in summary, "unconfigured expiry must match the native None label"
    assert "data.duration == 1" in summary and "suffix: '.one'" in summary and "suffix: '.other'" in summary, "spell summary loses singular/plural units"

    primary = (REPO / "views" / "partials" / "spell-primary.md").read_text()
    assert "data.durationText|lowercase" in primary, "spell card lost source duration text"
    assert "data.duration|lowercase" in primary, "spell card lost legacy/custom fallback"

    print(
        f"spell area templates: {configured} configured, {skipped} manual, "
        f"{area_spells} total area spells OK"
    )
    print(f"spell effect durations: {len(records) - manual_reminders} timed/turn, {manual_reminders} manual; lossless migration OK")


if __name__ == "__main__":
    main()
