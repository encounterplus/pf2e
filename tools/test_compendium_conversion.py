#!/usr/bin/env python3
"""Focused regression tests for source-to-compendium text and price conversion."""

from __future__ import annotations

import unittest
from copy import deepcopy
from collections import Counter
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_aon_orc_staging import item_price
from foundry_markup import has_conversion_artifact, replace_foundry_directives
from package_public_release import clear_owned_output
from item_editor_data import configure_item_editor_data, parse_item_activations
from creature_editor_data import render_ability_editor_fields
from spell_editor_data import configure_spell_editor_data
from deity_editor_data import configure_deity_editor_data, linked_value, ranked_spell, LINK as DEITY_LINK


class FoundryMarkupTests(unittest.TestCase):
    def test_nested_damage_type_and_options(self) -> None:
        rendered = replace_foundry_directives(
            "Creatures take @Damage[10d6[bludgeoning]|options:area-damage] damage."
        )
        self.assertEqual(rendered, "Creatures take 10d6 bludgeoning damage.")
        self.assertFalse(has_conversion_artifact(rendered))

    def test_template_includes_shape_and_distance(self) -> None:
        self.assertEqual(
            replace_foundry_directives("a @Template[line|distance:60] of stones"),
            "a 60-foot line of stones",
        )

    def test_roll_with_nested_healing_type(self) -> None:
        self.assertEqual(
            replace_foundry_directives("[[/r 4d8[healing] #Treat Wounds]] Hit Points"),
            "4d8 healing Hit Points",
        )

    def test_dynamic_formula_uses_readable_variable_name(self) -> None:
        rendered = replace_foundry_directives(
            "@Damage[(@item.rank+1)d8[acid]|options:area-damage]"
        )
        self.assertEqual(rendered, "(spell rank+1)d8 acid")
        self.assertNotIn("current value", rendered)

    def test_dynamic_formula_is_evaluated_for_the_record_level(self) -> None:
        rendered = replace_foundry_directives(
            "@Damage[(floor((@actor.level -1)/2) +2)d4[slashing]]",
            {"@actor.level": 5},
        )
        self.assertEqual(rendered, "4d4 slashing")
        self.assertFalse(has_conversion_artifact(rendered))

    def test_conditional_formula_is_evaluated_for_the_record_level(self) -> None:
        rendered = replace_foundry_directives(
            "@Damage[(ternary(gte(@actor.level,20),10,9))d10[bludgeoning]]",
            {"@actor.level": 18},
        )
        self.assertEqual(rendered, "9d10 bludgeoning")

    def test_template_type_property_is_humanized(self) -> None:
        self.assertEqual(
            replace_foundry_directives("@Template[type:burst|distance:20]"),
            "20-foot burst",
        )

    def test_basic_save_uses_book_order(self) -> None:
        self.assertEqual(
            replace_foundry_directives("(@Check[reflex|dc:28|basic] save)"),
            "(DC 28 basic Reflex save)",
        )

    def test_action_roll_preserves_its_dc(self) -> None:
        self.assertEqual(
            replace_foundry_directives("becoming immobilized ([[/act escape dc=34]])"),
            "becoming immobilized (Escape DC 34)",
        )

    def test_labeled_action_roll_preserves_its_dc(self) -> None:
        self.assertEqual(
            replace_foundry_directives("until it [[/act escape dc=34]]{Escapes}"),
            "until it Escapes (DC 34)",
        )


class ItemPriceTests(unittest.TestCase):
    def test_variant_price_fallback_matches_base_level(self) -> None:
        record = {
            "level": 3,
            "markdown": """
                <title level="2" right="Item 3">Base Item</title>
                **Price** 50 gp
                <title level="2" right="Item 7">Greater Item</title>
                **Price** 360 gp
            """,
        }
        self.assertEqual(item_price(record), "50 gp")

    def test_missing_printed_price_stays_blank(self) -> None:
        self.assertEqual(item_price({"level": 5, "markdown": "No price listed."}), "")

    def test_zero_price_is_preserved(self) -> None:
        self.assertEqual(item_price({"price": 0}), "0 gp")


class ItemActivationTests(unittest.TestCase):
    def item(self, text: str, name: str = "Test Item") -> dict:
        return {"kind": "Item", "name": name, "descr": text, "data": {"level": 3}}

    def test_equipment_header_keeps_general_prose(self) -> None:
        item = self.item("**Activate** A (manipulate)\n\n---\n\nGeneral item rules.")
        self.assertTrue(configure_item_editor_data(item))
        self.assertEqual(item["data"]["activation"], {"actions": "one", "traits": ["manipulate"], "text": ""})
        self.assertEqual(item["descr"], "---\n\nGeneral item rules.")

    def test_named_reaction_preserves_rules_links_and_variant_text(self) -> None:
        body = "**Frequency** once per day; **Trigger** An ally falls; **Effect** Cast [heal](/spell/heal-player-core).\n\nA second paragraph."
        item = self.item("Overview.\n\n**Activate—Restore** **Reaction** ([healing](/trait/healing)) " + body + "\n\n## Greater Item\n\nOther variant rules.")
        self.assertTrue(configure_item_editor_data(item))
        activation = item["data"]["activations"][0]
        self.assertEqual(activation["name"], "Restore")
        self.assertEqual(activation["actions"], "reaction")
        self.assertEqual(activation["traits"], ["healing"])
        self.assertEqual(activation["trigger"], "An ally falls")
        self.assertEqual(render_ability_editor_fields(activation), body)
        self.assertEqual(item["descr"], "Overview.\n\n## Greater Item\n\nOther variant rules.")

    def test_primary_and_additional_activations_stay_independent(self) -> None:
        item = self.item("Overview.\n\n**Activate** Cast a Spell; Cast [light](/spell/light-player-core).\n\n**Activate - Flash** **Two Actions** (manipulate) **Effect** Bright light.")
        self.assertTrue(configure_item_editor_data(item))
        self.assertEqual(item["data"]["activation"]["type"], "Cast a Spell")
        self.assertIn("/spell/light-player-core", item["data"]["activation"]["text"])
        self.assertEqual(item["data"]["activations"][0]["effect"], "Bright light.")
        self.assertEqual(item["descr"], "Overview.")

    def test_crafting_and_shield_properties_remain_general(self) -> None:
        text = "Overview.\n\n**Activate—Flash** **Free Action** **Effect** Light.\n\n---\n\n| Hardness | HP | BT |\n| --- | --- | --- |\n| 3 | 6 | 3 |\n\n**Craft Requirements** A crystal."
        item = self.item(text)
        configure_item_editor_data(item)
        self.assertEqual(item["data"]["activations"][0]["effect"], "Light.")
        self.assertIn("| Hardness | HP | BT |", item["descr"])
        self.assertNotIn("**Craft Requirements**", item["descr"])
        self.assertEqual(item["data"]["craftRequirements"], "A crystal.")

    def test_variable_or_timed_cost_is_not_guessed(self) -> None:
        for cost in ("1 minute", "10 minutes", "1 or 2", "1 to 3"):
            with self.subTest(cost=cost):
                item = self.item(f"**Activate—Travel** {cost} (manipulate) **Effect** Travel safely.")
                configure_item_editor_data(item)
                activation = item["data"]["activations"][0]
                self.assertNotIn("actions", activation)
                self.assertIn(cost, activation["description"])

    def test_only_exact_matching_variant_is_extracted(self) -> None:
        text = "Overview.\n\n## Test Item\n\nBase rules.\n\n## Greater Item\n\n**Activate—Flash** **Two Actions** **Effect** Light."
        base = self.item(text)
        self.assertFalse(configure_item_editor_data(base))
        self.assertEqual(base["descr"], text)
        greater = self.item(text, "Greater Item")
        self.assertTrue(configure_item_editor_data(greater))
        self.assertEqual(greater["data"]["activations"][0]["name"], "Flash")
        self.assertIn("Base rules.", greater["descr"])

    def test_existing_or_cleared_gm_settings_are_preserved(self) -> None:
        for key, value in (("activation", {}), ("activations", []), ("activation", {"text": "Custom"})):
            item = self.item("**Activate** 1 (manipulate)")
            item["data"][key] = value
            before = deepcopy(item)
            self.assertFalse(configure_item_editor_data(item))
            self.assertEqual(item, before)

    def test_incidental_mentions_and_empty_headers_are_preserved(self) -> None:
        for text in ("You do not need to Activate this item.", "**Activate**"):
            item = self.item(text)
            self.assertFalse(configure_item_editor_data(item))
            self.assertEqual(item["descr"], text)

    def test_spans_preserve_original_text_and_conversion_is_idempotent(self) -> None:
        text = "Overview.\n\n**Activate—Flash** 1 (manipulate) **Effect** Light.\n\n**Activate—Hide** **Free Action** **Trigger** You hide; **Effect** Darkness.\n\n## Other Item\n\nRemaining rules."
        blocks = parse_item_activations(text, "Test Item")
        rebuilt = "";cursor = 0
        for block in blocks:
            rebuilt += text[cursor:block.start] + block.original
            cursor = block.end
        self.assertEqual(rebuilt + text[cursor:], text)
        item = self.item(text)
        self.assertTrue(configure_item_editor_data(item))
        converted = deepcopy(item)
        self.assertFalse(configure_item_editor_data(item))
        self.assertEqual(item, converted)

    def test_published_named_activation_rules_and_links_are_preserved(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        checked = 0
        for root in (repo / "compendium/packs", repo / "compendium/ogl-packs"):
            for path in root.glob("*/items.json"):
                for item in json.loads(path.read_text()):
                    for activation in item.get("data", {}).get("activations", []):
                        if "text" not in activation:
                            continue
                        # The shared editor may group Requirements with Frequency,
                        # but no rule word, number, sign, or link may disappear.
                        tokens = lambda text: Counter(re.sub(r"[;\s]+", " ", text).strip().split())
                        self.assertEqual(tokens(activation["text"]), tokens(render_ability_editor_fields(activation)), item["name"])
                        checked += 1
        self.assertGreater(checked, 1000, "published activations were not populated")


class ItemCraftingTests(unittest.TestCase):
    def item(self, text: str, name: str = "Test Item") -> dict:
        return {"kind": "Item", "name": name, "descr": text, "data": {}}

    def test_explicit_requirements_preserve_links_and_following_properties(self) -> None:
        item = self.item("Overview.\n\n**Craft Requirements** Supply [caltrops](/item/caltrops-player-core).\n\n**Special** Keep this rule.")
        self.assertTrue(configure_item_editor_data(item))
        self.assertEqual(item["data"]["craftRequirements"], "Supply [caltrops](/item/caltrops-player-core).")
        self.assertEqual(item["descr"], "Overview.\n\n**Special** Keep this rule.")

    def test_divider_separates_following_note(self) -> None:
        item = self.item("**Craft Requirements** Supply a spell.\n\n---\n\nA general note.")
        configure_item_editor_data(item)
        self.assertEqual(item["data"]["craftRequirements"], "Supply a spell.")
        self.assertEqual(item["descr"], "---\n\nA general note.")

    def test_only_current_variant_requirements_are_extracted(self) -> None:
        text = "Overview.\n\n## Test Item\n\n**Craft Requirements** A crystal.\n\n## Greater Item\n\n**Craft Requirements** A diamond."
        item = self.item(text)
        configure_item_editor_data(item)
        self.assertEqual(item["data"]["craftRequirements"], "A crystal.")
        self.assertIn("**Craft Requirements** A diamond.", item["descr"])
        other = self.item(text, "Unmatched Item")
        self.assertFalse(configure_item_editor_data(other))
        self.assertEqual(other["descr"], text)

    def test_existing_activation_does_not_block_crafting_conversion(self) -> None:
        item = self.item("**Craft Requirements** A crystal.")
        item["data"]["activations"] = [{"name": "Flash", "effect": "Light."}]
        before = deepcopy(item["data"]["activations"])
        self.assertTrue(configure_item_editor_data(item))
        self.assertEqual(item["data"]["activations"], before)
        converted = deepcopy(item)
        self.assertFalse(configure_item_editor_data(item))
        self.assertEqual(item, converted)

    def test_explicit_or_cleared_crafting_settings_are_preserved(self) -> None:
        for value in ("", "Custom requirement"):
            item = self.item("**Craft Requirements** A crystal.")
            item["data"]["craftRequirements"] = value
            before = deepcopy(item)
            self.assertFalse(configure_item_editor_data(item))
            self.assertEqual(item, before)

    def test_empty_and_incidental_mentions_are_preserved(self) -> None:
        for text in ("**Craft Requirements**", "Some items have Craft Requirements."):
            item = self.item(text)
            self.assertFalse(configure_item_editor_data(item))
            self.assertEqual(item["descr"], text)


class SpellMetadataTests(unittest.TestCase):
    def spell(self, text: str, **data) -> dict:
        return {"kind": "Spell", "descr": text, "data": data}

    def test_duplicates_move_out_of_description_with_body_and_heightening_intact(self) -> None:
        body = "Two trees grow.\n\n- **Tree of Death** Damage.\n\n---\n**Heightened (+1)** More damage."
        spell = self.spell("**Traditions**\nDivine, Primal\n\n**Range** 120 feet\n\n**Duration** 1 minute\n\n---\n\n" + body,
                           traditionsText="Divine, Primal", range="120 feet", durationText="1 minute", duration=1, durationType="time", durationUnit="minute")
        before = deepcopy(spell["data"])
        self.assertTrue(configure_spell_editor_data(spell))
        self.assertEqual(spell["descr"], body)
        self.assertEqual(spell["data"], before)
        converted = deepcopy(spell)
        self.assertFalse(configure_spell_editor_data(spell))
        self.assertEqual(spell, converted)

    def test_missing_trigger_requirements_and_links_are_preserved_in_fields(self) -> None:
        spell = self.spell("**Trigger** You [fall](/rule/falling).\n\n**Requirements** You can bleed.\n\n---\n\nSpell effect.", trigger="", requirements="")
        configure_spell_editor_data(spell)
        self.assertEqual(spell["data"]["trigger"], "You [fall](/rule/falling).")
        self.assertEqual(spell["data"]["requirements"], "You can bleed.")
        self.assertEqual(spell["descr"], "Spell effect.")

    def test_unknown_patron_theme_and_unsupported_defense_remain_printed(self) -> None:
        spell = self.spell("**Patron Theme**\nParadox of Opposites\n\n**Range** 30 feet\n\n**Defense** AC\n\n---\n\nEffect.", range="30 feet", defense="")
        configure_spell_editor_data(spell)
        self.assertIn("Paradox of Opposites", spell["descr"])
        self.assertIn("**Defense** AC", spell["descr"])
        self.assertNotIn("**Range**", spell["descr"])
        self.assertEqual(spell["data"]["defense"], "")

    def test_defense_option_is_normalized_only_for_known_native_choices(self) -> None:
        spell = self.spell("**Defense**\nBasic Fortitude\n\n---\n\nEffect.", defense="")
        configure_spell_editor_data(spell)
        self.assertEqual(spell["data"]["defense"], "basicfortitude")
        self.assertEqual(spell["descr"], "Effect.")

    def test_linked_defense_header_keeps_its_rule_link(self) -> None:
        spell = self.spell("**Range** 30 feet\n\n**Defense** [basic](/rule/basic-saving-throws) Fortitude\n\n---\n\nEffect.", range="30 feet", defense="basicfortitude")
        self.assertTrue(configure_spell_editor_data(spell))
        self.assertNotIn("**Range**", spell["descr"])
        self.assertIn("/rule/basic-saving-throws", spell["descr"])

    def test_linked_duration_keeps_route_without_changing_native_timer(self) -> None:
        spell = self.spell("**Range** 30 feet\n\n**Duration** [sustained](/action/sustain) up to 1 minute\n\n---\n\nEffect.", range="30 feet", durationText="sustained up to 1 minute", duration=1, durationType="time", durationUnit="minute")
        before = deepcopy(spell["data"])
        configure_spell_editor_data(spell)
        self.assertIn("/action/sustain", spell["descr"])
        self.assertEqual(spell["data"], before)

    def test_conflicts_qualified_area_and_area_links_do_not_change_templates(self) -> None:
        for text in ("30-foot burst centered on you", "30-foot [burst](/rule/burst)"):
            spell = self.spell(f"**Range** 60 feet\n\n**Area** {text}\n\n---\n\nEffect.", range="30 feet", area="30-foot burst", areaEffectShape="sphere", areaEffectSize=30)
            before = deepcopy(spell)
            self.assertFalse(configure_spell_editor_data(spell))
            self.assertEqual(spell, before)

    def test_body_labels_and_inline_headers_are_not_guessed(self) -> None:
        for text in ("Effect.\n\n**Range** 30 feet", "**Range** 30 feet; **Targets** one creature"):
            spell = self.spell(text)
            before = deepcopy(spell)
            self.assertFalse(configure_spell_editor_data(spell))
            self.assertEqual(spell, before)

    def test_repeated_header_fields_are_preserved(self) -> None:
        spell = self.spell("**Range** 30 feet\n\n**Range** 60 feet\n\n---\n\nEffect.", range="30 feet")
        before = deepcopy(spell)
        self.assertFalse(configure_spell_editor_data(spell))
        self.assertEqual(spell, before)

    def test_reported_spells_have_clean_headers_and_preserve_special_metadata(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        spells = {
            item["name"]: item
            for book in ("impossible-magic", "divine-mysteries")
            for item in json.loads((repo / "compendium/packs" / book / "spells.json").read_text())
        }
        tree = spells["Tree of Life and Death"]
        trade = spells["Trade Death for Life"]
        self.assertTrue(tree["descr"].startswith("The cycle of life"))
        self.assertIn("**Patron Theme**", trade["descr"])
        for spell in (tree, trade):
            for label in ("Range", "Target", "Traditions", "Duration", "Defense"):
                self.assertNotIn(f"**{label}**", spell["descr"])
            self.assertIn("**Heightened (+1)**", spell["descr"])
            self.assertFalse(configure_spell_editor_data(deepcopy(spell)))


class DeityDisplayTests(unittest.TestCase):
    def test_confirmed_missing_mechanics_are_restored(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        deities = {row["name"]: row for book in ("divine-mysteries", "shining-kingdoms")
                   for row in json.loads((repo / "compendium/packs" / book / "deities.json").read_text())}
        tides = deities["The Tides of Chaos"]["data"]
        self.assertEqual(tides["divineAttribute"], ["dexterity", "intelligence"])
        self.assertEqual(tides["favoredWeapon"], ["dagger"])
        self.assertTrue(all(tides[field] for field in ("areasOfConcern", "edictsText", "anathemaText")))
        self.assertEqual(tides["sanctificationText"], "Can choose unholy")
        self.assertIn("/item/dagger-player-core", tides["deityReferences"]["favoredWeapon"][0]["text"])
        self.assertEqual(deities["Angazhan (The Ravenous King)"]["data"]["sanctificationText"], "Must choose unholy")
        self.assertEqual(deities["Ydersius (Lord of Coiling Poison)"]["data"]["areasOfConcern"], "serpentfolk, immortality, poison")
        asmodeus = deities["Asmodeus (The Prince of Darkness)"]["data"]
        self.assertEqual(asmodeus["divineAttribute"], ["any"])
        self.assertIn("soul", asmodeus["divineAttributeNotes"])
        # Publisher conflict and unverified source differences remain unchanged.
        self.assertEqual(deities["Rokoga Gin (The World Walker)"]["data"]["sanctificationOptions"], [])

    def test_divine_skill_array_is_editable_without_losing_values(self) -> None:
        deity = {"kind": "Deity", "data": {"divineSkill": ["stealth"]}}
        configure_deity_editor_data(deity)
        self.assertEqual(deity["data"]["divineSkill"], "stealth")
        self.assertFalse(configure_deity_editor_data(deity))
        deity["data"]["divineSkill"] = ["stealth", "deception"]
        configure_deity_editor_data(deity)
        self.assertEqual(deity["data"]["divineSkill"], "stealth, deception")

    def test_sanctification_sentence_and_clearing_are_authoritative(self) -> None:
        deity = {"kind": "Deity", "data": {"sanctification": "unholy", "sanctificationOptions": ["unholy"], "sanctificationText": "Must choose unholy"}}
        configure_deity_editor_data(deity)
        self.assertEqual(deity["data"]["sanctificationText"], "Must choose unholy")
        deity["data"]["sanctificationText"] = ""
        configure_deity_editor_data(deity)
        self.assertEqual(deity["data"]["sanctificationText"], "")
        del deity["data"]["sanctificationText"]
        configure_deity_editor_data(deity)
        self.assertNotIn("sanctificationText", deity["data"])
        self.assertEqual(deity["data"]["sanctification"], "unholy")
        deity["data"]["sanctificationText"] = "None"
        configure_deity_editor_data(deity)
        self.assertEqual(deity["data"]["sanctificationText"], "None")

    def test_import_summary_is_removed_from_editable_description_only_when_exact(self) -> None:
        summary = "**Edicts** Help others.\n\n**Divine Font** [Heal](/spell/heal-player-core)"
        deity = {"kind": "Deity", "descr": summary, "data": {"edicts": ["Help others."], "clericFont": ["heal"], "rulesText": summary}}
        self.assertTrue(configure_deity_editor_data(deity))
        self.assertEqual(deity["descr"], "")
        self.assertEqual(deity["data"]["rulesText"], summary)
        self.assertIn("/spell/heal-player-core", json.dumps(deity["data"]["deityReferences"]))
        self.assertFalse(configure_deity_editor_data(deity))
        deity["descr"] = summary + "\n\nA custom note."
        configure_deity_editor_data(deity)
        self.assertTrue(deity["descr"].endswith("A custom note."))

    def test_source_reference_cache_preserves_live_values_and_description(self) -> None:
        deity = {"kind": "Deity", "descr": "Custom text.", "data": {
            "edicts": ["Cast heal for an ally."], "clericFont": ["heal"],
            "rulesText": "**Edicts** Cast [heal](/spell/heal-player-core) for an ally.\n\n**Divine Font** [Heal](/spell/heal-player-core)"}}
        before = deepcopy(deity)
        self.assertTrue(configure_deity_editor_data(deity))
        self.assertEqual(deity["descr"], before["descr"])
        self.assertEqual(deity["data"]["edicts"], before["data"]["edicts"])
        self.assertEqual(deity["data"]["deityReferenceKeys"]["clericFont"], ["heal"])
        self.assertEqual(deity["data"]["deityReferences"]["edicts"][0]["text"], "Cast [heal](</spell/heal-player-core>) for an ally.")
        converted = deepcopy(deity)
        self.assertFalse(configure_deity_editor_data(deity))
        self.assertEqual(deity, converted)

    def test_reference_cache_cannot_match_changed_or_removed_values(self) -> None:
        deity = {"kind": "Deity", "data": {"clericFont": ["heal"], "rulesText": "**Divine Font** [Heal](/spell/heal-player-core)"}}
        configure_deity_editor_data(deity)
        deity["data"]["clericFont"] = ["New custom value"]
        self.assertNotIn(deity["data"]["clericFont"][0], deity["data"]["deityReferenceKeys"]["clericFont"])
        deity["data"]["clericFont"] = []
        self.assertFalse(deity["data"]["clericFont"])

    def test_existing_markdown_and_overlapping_labels_are_not_corrupted(self) -> None:
        text = "[heal](/spell/heal-player-core) or harm"
        self.assertEqual(linked_value(text, [("heal", "/other")]), text)
        self.assertEqual(linked_value("Air Walk and air", [("Air", "/domain/air"), ("Air Walk", "/spell/air-walk")]), "[Air Walk](</spell/air-walk>) and [air](</domain/air>)")

    def test_legacy_spell_rank_dictionary_is_losslessly_editable(self) -> None:
        deity = {"kind": "Deity", "data": {"spells": {"1": "Ill Omen", "5": "Subconscious Suggestion"}}}
        configure_deity_editor_data(deity)
        self.assertEqual(deity["data"]["spells"], ["1st: Ill Omen", "5th: Subconscious Suggestion"])
        self.assertFalse(configure_deity_editor_data(deity))

    def test_rank_ordinals_and_catalog_links_apply_to_every_deity(self) -> None:
        for rank, ordinal in ((1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"), (12, "12th"), (13, "13th"), (21, "21st")):
            self.assertEqual(ranked_spell(f"{rank}: Test"), f"{ordinal}: Test")
        for name in ("First test deity", "Another test deity"):
            deity = {"kind": "Deity", "name": name, "data": {"spells": {"3": "Fireball"}}}
            configure_deity_editor_data(deity)
            self.assertEqual(deity["data"]["spells"], ["3rd: Fireball"])
            self.assertIn("/spell/fireball-player-core", deity["data"]["deityReferences"]["spells"][0]["text"])
        self.assertEqual(ranked_spell("Fireball"), "Fireball")

    def test_multiline_directives_preserve_links_and_explicit_clearing(self) -> None:
        deity = {"kind": "Deity", "data": {"edicts": ["Cast heal.", "Help others."], "anathema": ["Lie."], "rulesText": "**Edicts** Cast [heal](/spell/heal-player-core); Help others."}}
        configure_deity_editor_data(deity)
        self.assertEqual(deity["data"]["edictsText"], "Cast [heal](</spell/heal-player-core>).\n\nHelp others.")
        self.assertEqual(deity["data"]["anathemaText"], "Lie.")
        deity["data"]["edictsText"] = ""
        configure_deity_editor_data(deity)
        self.assertEqual(deity["data"]["edictsText"], "")
        self.assertEqual(deity["data"]["edicts"], ["Cast heal.", "Help others."])

    def test_all_published_original_deity_reference_routes_are_preserved(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        count = 0
        for path in (repo / "compendium/packs").glob("*/deities.json"):
            for deity in json.loads(path.read_text()):
                data = deity["data"]
                visible = {k: v for k, v in data.items() if k not in {"rulesText"}}
                for _, route in DEITY_LINK.findall(data["rulesText"]):
                    self.assertIn(route.strip("<>"), json.dumps(visible), deity["name"])
                    count += 1
                self.assertIsInstance(data["spells"], list, deity["name"])
        self.assertGreater(count, 4000)


class ReleaseOutputTests(unittest.TestCase):
    def test_cleanup_removes_generated_conflict_copies_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            generated = {
                "manifest.json",
                "manifest 2.json",
                "release-summary 3.json",
                "SHA256SUMS 12.txt",
                "pf2e-remaster 2.system",
            }
            for name in [*generated, "notes 2.txt"]:
                (output / name).write_text(name, encoding="utf-8")

            clear_owned_output(output)

            self.assertFalse(any((output / name).exists() for name in generated))
            self.assertTrue((output / "notes 2.txt").is_file())


if __name__ == "__main__":
    unittest.main()
