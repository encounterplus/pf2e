#!/usr/bin/env python3
"""Regression checks for source-backed Encounter+ reference tables."""

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_reference_tables import OGL_PACKS, PACKS, build_tables, markdown_tables
from build_operations_center import REPO, groups, pages, reference_picker, reference_tables, validate


EXPECTED_ORC_TABLES = {
    "battlecry": 3,
    "dark-archive": 2,
    "gm-core": 36,
    "guns-and-gears-remastered": 2,
    "howl-of-the-wild": 1,
    "monster-core": 1,
    "player-core": 4,
    "player-core-2": 2,
    "treasure-vault-remastered": 1,
}


def records_in(pack: Path) -> list[dict]:
    records = []
    for path in sorted(pack.glob("*.json")):
        if path.name in {"manifest.json", "module.json", "source.json", "tables.json"}:
            continue
        value = json.loads(path.read_text())
        if isinstance(value, list):
            records.extend(record for record in value if isinstance(record, dict))
    return records


class ReferenceTableTests(unittest.TestCase):
    def test_source_table_parser_preserves_links_and_dice(self) -> None:
        tables = markdown_tables(
            "| **Name** | **Result** |\n| --- | --- |\n"
            "| [Cover](/rule/cover-rules-2372) | 2d6 |"
        )
        self.assertEqual(tables, [
            (["Name", "Result"], [["[Cover](/rule/cover-rules-2372)", "2d6"]])
        ])

    def test_curated_tables_match_published_rules_and_sources(self) -> None:
        for source_id, expected_count in EXPECTED_ORC_TABLES.items():
            with self.subTest(source_id=source_id):
                path = PACKS / source_id
                saved = json.loads((path / "tables.json").read_text())
                self.assertEqual(saved, build_tables(records_in(path), source_id))
                self.assertEqual(len(saved), expected_count)
                self.assertEqual(len({table["id"] for table in saved}), expected_count)
                self.assertTrue(all(table["sources"][0].get("name") for table in saved))
                self.assertTrue(all(table["attributes"]["license"] == "ORC-1.0a" for table in saved))

        ogl = OGL_PACKS / "rage-of-elements"
        saved = json.loads((ogl / "tables.json").read_text())
        self.assertEqual(saved, build_tables(records_in(ogl), "rage-of-elements"))
        self.assertEqual(len(saved), 2)
        self.assertTrue(all(table["attributes"]["license"] == "OGL-1.0a" for table in saved))

    def test_roll_tables_encode_dice_ranges_for_the_native_roller(self) -> None:
        roll_tables = []
        for source_id in EXPECTED_ORC_TABLES:
            roll_tables.extend(
                table
                for table in json.loads((PACKS / source_id / "tables.json").read_text())
                if "rollable" in table.get("tags", [])
            )
        roll_tables.extend(json.loads((OGL_PACKS / "rage-of-elements/tables.json").read_text()))
        self.assertEqual(len(roll_tables), 30)
        self.assertEqual(len({table["name"] for table in roll_tables}), 30)

        for table in roll_tables:
            with self.subTest(name=table["name"]):
                formula = table["columns"][0]["name"]
                match = re.fullmatch(r"(?:1)?d(\d+)", formula)
                self.assertIsNotNone(match)
                outcomes = set(range(1, int(match.group(1)) + 1))
                covered = set()
                for row in table["rows"]:
                    bounds = [int(value) for value in row[0].split("-", 1)]
                    values = {bounds[0]} if len(bounds) == 1 else set(range(bounds[0], bounds[1] + 1))
                    self.assertFalse(covered & values, f"overlapping ranges in {table['name']}")
                    covered.update(values)
                self.assertEqual(covered, outcomes)
                self.assertEqual(table["rollMode"], "normal")
                self.assertIn("rollable", table["tags"])
                self.assertTrue(table["sources"][0].get("name"))

    def test_key_numbers_and_detection_links(self) -> None:
        gm = {table["name"]: table for table in json.loads((PACKS / "gm-core/tables.json").read_text())}
        player = {table["name"]: table for table in json.loads((PACKS / "player-core/tables.json").read_text())}
        self.assertIn(["20", "40"], gm["DCs by Level"]["rows"])
        self.assertEqual(gm["Simple DCs"]["sources"][0]["page"], 53)
        self.assertIn(["Extreme", "160", "40"], gm["Encounter XP Budget"]["rows"])
        self.assertIn(["6-7", "Hazard"], gm["Random Encounter Type"]["rows"])
        self.assertEqual(gm["Random Encounter Type"]["sources"][0]["page"], 209)
        self.assertEqual(gm["Random Terrain Type"]["sources"][0]["page"], 207)
        self.assertIn(["Thin wood", "3", "12", "6", "Chair, club, sapling, wooden shield"],
                      gm["Material Hardness, HP, and BT"]["rows"])
        self.assertIn(["Standard", "+2 to AC, Reflex, Stealth", "Yes"], player["Cover"]["rows"])
        self.assertEqual(player["Detection and Targeting"]["rows"][1][2], "DC 11")
        self.assertIn("/rule/hidden-rules-2416", player["Detection and Targeting"]["rows"][1][0])

    def test_operations_center_picker_is_compact_and_source_backed(self) -> None:
        markup = reference_picker("DC", ["DCs by Level"], "20")
        payload = json.loads(
            re.search(
                r'<script type="application/json" data-ops-payload>(.*?)</script>',
                markup,
            ).group(1)
        )
        self.assertEqual(payload[0]["rows"], reference_tables()["DCs by Level"]["rows"])
        self.assertIn('<span>40</span>', markup)
        self.assertIn("/table/dcs-by-level-gm-core", markup)
        self.assertNotIn("<table", markup)

    def test_operations_center_creature_picker_covers_all_benchmarks(self) -> None:
        names = [name for name in reference_tables() if name.startswith("Creature Building — ")]
        markup = reference_picker("Benchmarks", names)
        self.assertEqual(markup.count("data-ops-reference>"), 1)
        self.assertIn("data-ops-stat", markup)
        self.assertIn('value="–1"', markup)
        self.assertIn('value="24"', markup)

    def test_generated_operations_pages_keep_valid_table_routes(self) -> None:
        generated = [page.record() for page in pages()]
        validate(generated, groups())
        saved = json.loads((REPO / "pages.json").read_text())
        self.assertEqual(saved, generated)
        creature = next(
            page for page in saved if page["slug"] == "pf2e-ops-creature-benchmarks"
        )
        self.assertIn("data-ops-reference", creature["content"])
        self.assertIn(
            "/table/creature-building-attribute-modifiers-gm-core",
            creature["content"],
        )


if __name__ == "__main__":
    unittest.main()
