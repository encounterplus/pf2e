"""Regression checks for published hazard and vehicle mechanics."""

from __future__ import annotations

import copy
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hazard_vehicle_mechanics import HAZARD_SUMMARIES, STRIKES, VEHICLE_SUMMARIES, link_condition_mentions, supplement


class HazardVehicleMechanicsTests(unittest.TestCase):
    def test_strike_fixture_is_present_in_published_hazards(self) -> None:
        hazards = {
            record["slug"]: record
            for path in (ROOT / "compendium/packs").glob("*/hazards.json")
            for record in json.loads(path.read_text())
        }
        self.assertEqual(set(STRIKES), set(STRIKES) & hazards.keys())
        for slug, expected in STRIKES.items():
            record = hazards[slug]
            self.assertEqual(record["data"]["attacks"], expected)
            self.assertTrue(record["sources"])

    def test_supplement_does_not_replace_custom_strikes(self) -> None:
        record = {"slug": "spear-launcher-gm-core", "data": {"attacks": [{"name": "Custom"}]}}
        supplement(record, "Hazard")
        self.assertEqual(record["data"]["attacks"], [{"name": "Custom"}])

    def test_every_record_has_a_short_original_description(self) -> None:
        for kind, fixture, filename in (("Hazard", HAZARD_SUMMARIES, "hazards.json"), ("Vehicle", VEHICLE_SUMMARIES, "vehicles.json")):
            records = [record for path in (ROOT / "compendium/packs").glob(f"*/{filename}") for record in json.loads(path.read_text())]
            self.assertEqual({record["slug"] for record in records}, set(fixture))
            for record in records:
                self.assertEqual(record["data"]["description"], fixture[record["slug"]])

    def test_book_style_detection_defenses_and_vehicle_abilities(self) -> None:
        def record(slug: str, kind: str) -> dict:
            filename = "hazards.json" if kind == "Hazard" else "vehicles.json"
            return next(value for path in (ROOT / "compendium/packs").glob(f"*/{filename}") for value in json.loads(path.read_text()) if value["slug"] == slug)

        choir = record("ghostly-choir-gm-core", "Hazard")
        self.assertEqual((choir["data"]["stealthDC"], choir["data"]["stealthDetails"]), (20, "(expert)"))
        self.assertEqual(choir["sources"][0]["page"], 102)
        self.assertIn("living creatures", choir["data"]["abilities"][0]["text"])
        self.assertIn("[Frightened 2](/condition/frightened-player-core)", choir["data"]["abilities"][0]["text"])
        self.assertIn("[Frightened 3](/condition/frightened-player-core)", choir["data"]["abilities"][0]["text"])
        self.assertNotIn("\n\n---\n\n", choir["data"]["abilities"][0]["text"])
        complex_hazard = record("poisoned-dart-gallery-gm-core", "Hazard")
        self.assertNotIn("stealthDC", complex_hazard["data"])
        airship = record("airship-gm-core", "Vehicle")
        self.assertEqual(airship["data"]["hp"]["bt"], 105)
        self.assertEqual(airship["data"]["weaknesses"], "fire 15 until broken")
        self.assertEqual(airship["sources"][0]["page"], 213)
        paddleboat = record("adaptable-paddleboat-guns-and-gears-remastered", "Vehicle")
        self.assertEqual(paddleboat["data"]["immunities"], ["object immunities"])
        self.assertEqual(paddleboat["data"]["hp"]["bt"], 15)
        ship = record("augustana-s-pride-hellfire-dispatches-vehicle-vehicle-145", "Vehicle")
        self.assertEqual([item["name"] for item in ship["data"]["abilities"]], ["Inspiring Presence", "Weapon Mounts"])
        self.assertEqual(ship["sources"][0]["page"], 94)
        schooneer = record("yellow-sailed-schooner-hellfire-dispatches-vehicle-vehicle-150", "Vehicle")
        self.assertIn("[frightened](/condition/frightened-player-core)", schooneer["data"]["abilities"][0]["text"].lower())

    def test_new_data_does_not_override_user_edits(self) -> None:
        custom = {"slug": "ghostly-choir-gm-core", "data": {"complexity": "simple", "stealth": 10, "stealthDC": 29, "description": "Custom text", "stealthDetails": "(legendary)", "attacks": [{"name": "Own"}]}}
        supplement(custom, "Hazard")
        self.assertEqual(custom["data"]["stealthDC"], 29)
        self.assertEqual(custom["data"]["description"], "Custom text")
        self.assertEqual(custom["data"]["stealthDetails"], "(legendary)")
        self.assertEqual(custom["data"]["attacks"], [{"name": "Own"}])

    def test_condition_links_are_clickable_without_nested_markdown(self) -> None:
        sample = "[Frightened 1](/condition/frightened-player-core), Frightened 2, or frightened 3."
        linked = link_condition_mentions(sample)
        self.assertIn("[Frightened 2](/condition/frightened-player-core)", linked)
        self.assertIn("[frightened 3](/condition/frightened-player-core)", linked)
        self.assertEqual(link_condition_mentions(linked), linked)

    def test_vehicle_prices_show_gp_without_inventing_zero_price(self) -> None:
        for price, expected in ((6000, "6,000 gp"), ("480 gp", "480 gp"), (0, "")):
            record = {"data": {"price": price}}
            supplement(record, "Vehicle")
            self.assertEqual(record["data"].get("price"), expected)

    def test_all_published_vehicle_prices_match_display(self) -> None:
        for path in (ROOT / "compendium/packs").glob("*/vehicles.json"):
            for record in json.loads(path.read_text()):
                rebuilt = copy.deepcopy(record)
                supplement(rebuilt, "Vehicle")
                self.assertEqual(rebuilt["data"], record["data"])

    def test_views_expose_mechanics_and_editors(self) -> None:
        for kind, fields in (
            ("hazard", ("data.stealthDC", "data.stealth", "data.description", "data.hp.bt", "data.immunities", "data.disable", "data.attacks", "data.abilities", "data.routine", "data.reset")),
            ("vehicle", ("data.price", "data.description", "data.hp.bt", "data.immunities", "data.space.long", "data.pilotingCheck", "data.collisionDamage", "data.abilities")),
        ):
            view = json.loads((ROOT / f"views/{kind}.json").read_text())
            html_view = (ROOT / f"views/{kind}.html").read_text()
            form = json.loads((ROOT / f"forms/{kind}.json").read_text())
            self.assertIn(f'{kind}-stats.md', json.dumps(view))
            # Default entities use the HTML renderer. The JSON view alone
            # must never count as a rendered-sheet regression test.
            self.assertIn(f'include "{kind}-stats.md"', html_view)
            self.assertIn('extends "base.html"', html_view)
            self.assertIn('include "footer.html"', html_view)
            combined = (ROOT / f"views/partials/{kind}-stats.md").read_text() + json.dumps(form)
            for field in fields:
                self.assertIn(field, combined)

    def test_scalar_immunities_use_native_text_list_controls(self) -> None:
        for kind in ("hazard", "vehicle"):
            form = json.loads((ROOT / f"forms/{kind}.json").read_text())
            controls = [field for section in form["sections"] for field in section.get("fields", [])
                        if field.get("attribute") == "data.immunities"]
            self.assertEqual(len(controls), 1, kind)
            self.assertEqual(controls[0]["type"], "list", kind)
            self.assertNotIn("form", controls[0], kind)
            for path in (ROOT / "compendium/packs").glob(f"*/{kind}s.json"):
                for entity in json.loads(path.read_text()):
                    for entry in entity.get("data", {}).get("immunities") or []:
                        self.assertIsInstance(entry, str, entity["name"])

    def test_new_partials_use_balanced_supported_control_tags(self) -> None:
        for kind in ("hazard", "vehicle"):
            content = (ROOT / f"views/partials/{kind}-stats.md").read_text()
            stack = []
            for tag in re.findall(r"{%\s*(\w+)[^%]*%}", content):
                if tag in {"if", "for"}:
                    stack.append(tag)
                elif tag in {"endif", "endfor"}:
                    self.assertTrue(stack, f"{kind}: stray {tag}")
                    self.assertEqual(stack.pop(), tag.removeprefix("end"))
                else:
                    self.assertIn(tag, {"else", "include"}, f"{kind}: unsupported {tag}")
            self.assertFalse(stack, f"{kind}: unclosed tags {stack}")


if __name__ == "__main__":
    unittest.main()
