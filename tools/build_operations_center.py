#!/usr/bin/env python3
"""Generate the bookmarkable PF2E Operations Center pages.

The pages are deliberately generated from a small, reviewable information
architecture. Every shortcut stays inside the Operations Center until the GM
chooses an explicitly labelled full-rule or interactive-tool link.
"""

from __future__ import annotations

import html
import json
import re
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
NAMESPACE = uuid.UUID("69c971eb-925c-44e1-8a5a-791d364ba773")
HOME = "pf2e-operations-center"
ENCOUNTERS = "pf2e-ops-encounters-combat"
CHECKS = "pf2e-ops-checks-dcs-actions"
CONDITIONS = "pf2e-ops-conditions-damage"
EXPLORATION = "pf2e-ops-exploration-travel"
DOWNTIME = "pf2e-ops-downtime-crafting"
CREATURES = "pf2e-ops-creatures-hazards"
MAGIC = "pf2e-ops-magic-rituals"
EQUIPMENT = "pf2e-ops-equipment-treasure"
PARTY = "pf2e-ops-party-advancement"
SUBSYSTEMS = "pf2e-ops-gm-subsystems"
INDEX = "pf2e-ops-index"
STYLE_MARKER = "/* PF2E Operations Center"
XP_STYLE_MARKER = "/* Encounter XP planner"


def stable_id(kind: str, slug: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{kind}:{slug}")).upper()


@lru_cache(maxsize=1)
def embedded_styles() -> str:
    """Return the scoped Operations Center CSS for standalone Page HTML.

    Encounter+ updates imported Page records while an active system can retain
    older on-disk styles. Embedding the scoped rules makes bookmark panels
    independent of that cache without maintaining a second CSS source.
    """
    stylesheet = (REPO / "styles" / "default.css").read_text(encoding="utf-8")
    marker = stylesheet.find(STYLE_MARKER)
    if marker < 0:
        raise ValueError("Operations Center style marker is missing from styles/default.css")
    css = stylesheet[marker:]
    return css.replace("url('../images/", "url('images/")


@lru_cache(maxsize=1)
def embedded_xp_styles() -> str:
    stylesheet = (REPO / "styles" / "default.css").read_text(encoding="utf-8")
    start = stylesheet.find(XP_STYLE_MARKER)
    end = stylesheet.find(STYLE_MARKER)
    if start < 0 or end <= start:
        raise ValueError("XP Planner style markers are missing or out of order")
    return stylesheet[start:end].replace("url('../images/", "url('images/")


@lru_cache(maxsize=1)
def embedded_xp_script() -> str:
    return (REPO / "scripts" / "xp-calculator.js").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def embedded_reference_script() -> str:
    return (REPO / "scripts" / "reference-tables.js").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def reference_tables() -> dict[str, dict]:
    tables = {}
    for path in sorted((REPO / "compendium").glob("**/tables.json")):
        for record in json.loads(path.read_text(encoding="utf-8")):
            if record["name"] in tables:
                raise ValueError(f"duplicate reference table: {record['name']}")
            tables[record["name"]] = record
    return tables


def full_table(name: str) -> str:
    record = reference_tables()[name]
    return (
        f'<a class="ops-exit-link" href="/table/{html.escape(record["slug"])}">'
        f'<span>Open Full Table</span><strong>{html.escape(name)}</strong></a>'
    )


def roll_table_link(name: str) -> str:
    record = reference_tables()[name]
    if "rollable" not in record.get("tags", []):
        raise ValueError(f"Operations Center roller is not a roll table: {name}")
    source = record["sources"][0]
    attribution = source["name"]
    if source.get("page"):
        attribution += f" p. {source['page']}"
    formula = record["columns"][0]["name"]
    return (
        f'<a href="/table-roll/{html.escape(record["slug"])}">'
        f'<strong>{html.escape(name)}</strong>'
        f'<span>Roll {html.escape(formula)} · {html.escape(attribution)}</span></a>'
    )


def roll_table_group(title: str, description: str, names: list[str]) -> str:
    links = "".join(roll_table_link(name) for name in names)
    return f"""
  <details class="ops-disclosure ops-action-disclosure">
    <summary><span>{html.escape(title)}</span><span>{len(names)} rollers</span></summary>
    <p>{html.escape(description)}</p>
    <div class="ops-link-list">{links}</div>
  </details>"""


def reference_picker(title: str, table_names: list[str], initial_level: str = "1") -> str:
    """One source-backed row at a time; usable in a narrow bookmark panel."""
    selected = [reference_tables()[name] for name in table_names]
    first = selected[0]
    levels = [row[0] for row in first["rows"]]
    if initial_level not in levels:
        raise ValueError(f"{title}: initial level {initial_level} missing")
    if any([row[0] for row in table["rows"]] != levels for table in selected):
        raise ValueError(f"{title}: tables do not share level rows")
    initial_row = next(row for row in first["rows"] if row[0] == initial_level)
    fields = "".join(
        f'<div class="ops-ref-row"><strong>{html.escape(column["name"])}</strong>'
        f'<span>{html.escape(value.replace("**", ""))}</span></div>'
        for column, value in zip(first["columns"][1:], initial_row[1:])
    )
    level_options = "".join(
        f'<option value="{html.escape(level)}"{(" selected" if level == initial_level else "")}>{html.escape(level)}</option>'
        for level in levels
    )
    stat_control = ""
    if len(selected) > 1:
        options = "".join(
            f'<option value="{index}">{html.escape(table["name"].removeprefix("Creature Building — "))}</option>'
            for index, table in enumerate(selected)
        )
        stat_control = f'<label>Statistic<select data-ops-stat>{options}</select></label>'
    payload = json.dumps(
        [{
            "name": table["name"],
            "slug": table["slug"],
            "source": f"{table['sources'][0]['name']} p. {table['sources'][0]['page']}",
            "headers": [column["name"] for column in table["columns"]],
            "rows": table["rows"],
        } for table in selected],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if "</script" in payload.casefold():
        raise ValueError(f"unsafe table content in {title}")
    return f"""
  <section class="ops-ref-picker" data-ops-reference>
    <h2>{html.escape(title)}</h2>
    <div class="ops-ref-controls"><label>Level<select data-ops-level>{level_options}</select></label>{stat_control}</div>
    <div class="ops-ref-values" data-ops-values aria-live="polite">{fields}</div>
    <p class="ops-ref-source" data-ops-source>{html.escape(first['sources'][0]['name'])} p. {first['sources'][0]['page']}</p>
    <a class="ops-ref-full" data-ops-full href="/table/{html.escape(first['slug'])}">Open full {html.escape(first['name'])} table</a>
    <script type="application/json" data-ops-payload>{payload}</script>
  </section>"""


def link(slug: str, label: str, *, kind: str = "page") -> str:
    return f'<a href="/{kind}/{html.escape(slug)}">{html.escape(label)}</a>'


def card(slug: str, title: str, text: str, eyebrow: str = "QUICK GUIDE") -> str:
    return f"""
      <a class="ops-card" href="/page/{slug}">
        <span class="ops-card-kicker">{html.escape(eyebrow)}</span>
        <strong>{html.escape(title)}</strong>
        <span>{html.escape(text)}</span>
      </a>"""


def full_rule(slug: str, label: str) -> str:
    return (
        f'<a class="ops-exit-link" href="/rule/{slug}">'
        f'<span>Open Full Rule</span><strong>{html.escape(label)}</strong></a>'
    )


def full_entry(kind: str, slug: str, label: str) -> str:
    entry_label = {
        "action": "Action",
        "condition": "Condition",
        "item": "Item",
        "spell": "Spell",
    }.get(kind, "Entry")
    return (
        f'<a class="ops-exit-link" href="/{kind}/{html.escape(slug)}">'
        f'<span>Open Full {entry_label}</span><strong>{html.escape(label)}</strong></a>'
    )


def action_cost(value: str) -> str:
    value = {
        "1 action": "one",
        "2 actions": "two",
        "3 actions": "three",
    }.get(value, value)
    if value in {"one", "two", "three", "reaction", "free"}:
        label = {
            "one": "1 action",
            "two": "2 actions",
            "three": "3 actions",
            "reaction": "Reaction",
            "free": "Free action",
        }[value]
        return f'<span class="ops-action-cost"><img src="icons/actions/{value}.png" alt=""><span>{label}</span></span>'
    return html.escape(value)


TRAINED_SKILL_ACTIONS = frozenset(
    {
        "borrow-an-arcane-spell-player-core",
        "cover-tracks-player-core",
        "craft-player-core",
        "create-forgery-player-core",
        "decipher-writing-player-core",
        "disable-a-device-player-core",
        "disarm-player-core",
        "earn-income-player-core",
        "feint-player-core",
        "identify-alchemy-player-core",
        "identify-magic-player-core",
        "learn-a-spell-player-core",
        "maneuver-in-flight-player-core",
        "pick-a-lock-player-core",
        "squeeze-player-core",
        "track-player-core",
        "treat-disease-player-core",
        "treat-poison-player-core",
        "treat-wounds-player-core",
    }
)

UNTRAINED_SKILL_ACTIONS = frozenset(
    {
        "administer-first-aid-player-core",
        "balance-player-core",
        "climb-player-core",
        "coerce-player-core",
        "command-an-animal-player-core",
        "conceal-an-object-player-core",
        "create-a-diversion-player-core",
        "demoralize-player-core",
        "force-open-player-core",
        "gather-information-player-core",
        "grapple-player-core",
        "hide-player-core",
        "high-jump-player-core",
        "impersonate-player-core",
        "lie-player-core",
        "long-jump-player-core",
        "make-an-impression-player-core",
        "palm-an-object-player-core",
        "perform-player-core",
        "recall-knowledge-player-core",
        "repair-player-core",
        "reposition-player-core",
        "request-player-core",
        "seek-player-core",
        "sense-direction-player-core",
        "sense-motive-player-core",
        "shove-player-core",
        "sneak-player-core",
        "steal-player-core",
        "subsist-player-core",
        "swim-player-core",
        "trip-player-core",
        "tumble-through-player-core",
    }
)

# These actions either gate harder tasks behind higher proficiency or improve
# their effect with rank. The full action remains the source for exact DCs and
# thresholds; the finder only needs a compact warning that rank matters.
RANK_SENSITIVE_SKILL_ACTIONS = frozenset(
    {
        "balance-player-core",
        "climb-player-core",
        "craft-player-core",
        "decipher-writing-player-core",
        "disable-a-device-player-core",
        "earn-income-player-core",
        "force-open-player-core",
        "gather-information-player-core",
        "maneuver-in-flight-player-core",
        "perform-player-core",
        "repair-player-core",
        "sense-direction-player-core",
        "squeeze-player-core",
        "subsist-player-core",
        "swim-player-core",
        "track-player-core",
        "treat-wounds-player-core",
    }
)


def action_table(
    title: str,
    rows: list[tuple[str, str, str, str, str]],
    *,
    show_proficiency: bool = False,
) -> str:
    rendered = []
    for name, slug, skill, cost, use in rows:
        proficiency = ""
        if show_proficiency:
            if slug in TRAINED_SKILL_ACTIONS:
                training_label = "Trained only"
                training_class = "ops-proficiency-trained"
            elif slug in UNTRAINED_SKILL_ACTIONS:
                training_label = "Untrained"
                training_class = "ops-proficiency-untrained"
            else:
                raise ValueError(f"Missing proficiency classification for skill action: {slug}")
            rank_badge = (
                '<strong class="ops-proficiency ops-proficiency-rank">Rank matters</strong>'
                if slug in RANK_SENSITIVE_SKILL_ACTIONS
                else ""
            )
            proficiency = (
                '<span class="ops-action-training">'
                f'<strong class="ops-proficiency {training_class}">{training_label}</strong>'
                f"{rank_badge}</span>"
            )
        rendered.append(
            "<tr>"
            f"<th>{html.escape(name)}<small>{html.escape(skill)}</small></th>"
            f'<td><span class="ops-action-meta">{action_cost(cost)}{proficiency}</span></td>'
            f"<td>{html.escape(use)}</td>"
            f'<td><a class="ops-table-link" href="/action/{html.escape(slug)}">Open full action</a></td>'
            "</tr>"
        )
    return f"""
  <details class="ops-disclosure ops-action-disclosure">
    <summary><span>{html.escape(title)}</span><span>{len(rows)} entries</span></summary>
    <div class="ops-table-wrap"><table class="ops-table ops-action-table">
      <thead><tr><th>Action & skill</th><th>{'Time & training' if show_proficiency else 'Time'}</th><th>Use it to…</th><th>Details</th></tr></thead>
      <tbody>{''.join(rendered)}</tbody>
    </table></div>
  </details>"""


def breadcrumbs(items: list[tuple[str, str]]) -> str:
    crumbs = [f'<a href="/page/{HOME}">Home</a>']
    for label, slug in items:
        crumbs.append(f'<a href="/page/{slug}">{html.escape(label)}</a>')
    return '<nav class="ops-breadcrumbs" aria-label="Breadcrumb">' + "<span>›</span>".join(crumbs) + "</nav>"


def related(cards: list[tuple[str, str, str]]) -> str:
    return """
    <section class="ops-related">
      <h2>Related quick guides</h2>
      <div class="ops-link-list">%s</div>
    </section>""" % "".join(
        f'<a href="/page/{slug}"><strong>{html.escape(title)}</strong><span>{html.escape(text)}</span></a>'
        for slug, title, text in cards
    )


def landing_page(
    name: str,
    slug: str,
    parent: str,
    subtitle: str,
    intro: str,
    cards: list[tuple[str, str, str, str]],
) -> Page:
    rendered = "".join(card(*item) for item in cards)
    body = f"""
  <section class="ops-intro ops-callout"><strong>Start from the question at the table.</strong><span>{html.escape(intro)}</span></section>
  <section class="ops-section"><div class="ops-section-heading"><div><p class="ops-kicker">CHOOSE A TASK</p><h2>{html.escape(name)}</h2></div></div><div class="ops-grid">{rendered}</div></section>"""
    return Page(name, slug, parent, 0, shell(name, subtitle, body, [(name, slug)]))


def condition_table(title: str, rows: list[tuple[str, str, str]]) -> str:
    rendered = "".join(
        "<tr>"
        f"<th>{html.escape(name)}</th>"
        f"<td>{html.escape(summary)}</td>"
        f'<td><a class="ops-table-link" href="/condition/{html.escape(slug)}">Open full condition</a></td>'
        "</tr>"
        for name, slug, summary in rows
    )
    return f"""
  <details class="ops-disclosure ops-action-disclosure">
    <summary><span>{html.escape(title)}</span><span>{len(rows)} entries</span></summary>
    <div class="ops-table-wrap"><table class="ops-table ops-condition-table"><thead><tr><th>Condition</th><th>Fast reminder</th><th>Details</th></tr></thead><tbody>{rendered}</tbody></table></div>
  </details>"""


def shell(
    title: str,
    subtitle: str,
    body: str,
    trail: list[tuple[str, str]] | None = None,
    page_class: str = "",
    extra_styles: str = "",
    trailing_html: str = "",
) -> str:
    crumb = breadcrumbs(trail or []) if title != "PF2E Operations Center" else ""
    classes = "pf2e-ops" + (f" {page_class}" if page_class else "")
    return f"""<style data-pf2e-operations-center>
{extra_styles}
{embedded_styles()}
</style>
<div class="{classes}">
  {crumb}
  <header class="ops-header">
    <p class="ops-overline">GAME MASTER OPERATIONS CENTER</p>
    <h1>{html.escape(title)}</h1>
    <p>{html.escape(subtitle)}</p>
  </header>
  {body}
</div>
{trailing_html}"""


@dataclass(frozen=True)
class Page:
    name: str
    slug: str
    parent: str
    rank: int
    content: str

    def record(self) -> dict[str, object]:
        return {
            "id": stable_id("page", self.slug),
            "name": self.name,
            "slug": self.slug,
            "content": self.content.strip(),
            "parentId": stable_id("group", self.parent),
            "rank": self.rank,
        }


def home_page() -> Page:
    quick = "".join(
        [
            card("pf2e-ops-encounter-sequence", "Encounter sequence", "From initiative through ending the encounter.", "RUN NOW"),
            card("pf2e-ops-turns-actions", "Turns & actions", "Three actions, reactions, free actions, and MAP.", "AT THE TABLE"),
            card("pf2e-ops-cover-visibility", "Cover & visibility", "Cover bonuses, detection states, targeting, and line of effect.", "AT THE TABLE"),
            card("pf2e-ops-dcs", "DCs at a glance", "Simple DCs, level-based DCs, and difficulty adjustments.", "QUICK TABLE"),
            card("pf2e-ops-random-tables", "Random tables", "Open a sourced table and use Encounter+'s native roller.", "ROLL & GENERATE"),
            card("pf2e-ops-skill-actions", "Skill actions", "Find the right action by what the character is trying to do.", "ACTION FINDER"),
            card("pf2e-ops-xp-difficulty", "XP & encounter threat", "Build for party size, judge threat, and award XP.", "PLAN & AWARD"),
            card("pf2e-ops-recovery", "Dying & recovery", "Recovery checks, dying changes, wounded, and Hero Points.", "URGENT"),
        ]
    )
    categories = "".join(
        [
            card(
                ENCOUNTERS,
                "Encounters & Combat",
                "Prepare difficulty, start initiative, run turns, adjudicate the map, and close the encounter.",
                "RUN THE GAME",
            ),
            card(
                CHECKS,
                "Checks, DCs & Skill Actions",
                "Choose a DC, resolve the degree, find an action, and handle secret information.",
                "ADJUDICATE",
            ),
            card(CONDITIONS, "Conditions, Damage & Recovery", "Track conditions, persistent damage, afflictions, defenses, and recovery.", "RESOLVE EFFECTS"),
            card(EXPLORATION, "Exploration, Travel & Environment", "Assign exploration activities, measure travel, rest, and resolve environmental danger.", "BETWEEN ROUNDS"),
            card(DOWNTIME, "Downtime, Crafting & Services", "Run shopping, Crafting, Earn Income, Retraining, and longer projects.", "BETWEEN ADVENTURES"),
            card(CREATURES, "Creatures & Hazards", "Identify creatures, read stat blocks, adjust opponents, and operate hazards.", "RUN OPPOSITION"),
            card(MAGIC, "Magic, Counteracting & Rituals", "Resolve spell targets and areas, counteract effects, and adjudicate rituals.", "RESOLVE MAGIC"),
            card(EQUIPMENT, "Equipment, Treasure & Rewards", "Handle Bulk, item use, shields, treasure budgets, and rewards.", "MANAGE RESOURCES"),
            card(PARTY, "Party, Advancement & Hero Points", "Track XP, level advancement, rarity, access, and Hero Points.", "MANAGE THE PARTY"),
            card(SUBSYSTEMS, "GM Subsystems & Campaign Tools", "Choose Victory Points, chases, research, infiltration, reputation, or hexploration.", "STRUCTURE SCENES"),
            card(INDEX, "A–Z Quick-Guide Index", "Find every Operations Center page alphabetically.", "FIND ANYTHING"),
        ]
    )
    body = f"""
  <section class="ops-intro ops-callout">
    <strong>Fast answers first. Full rules remain one tap away.</strong>
    <span>Bookmark this page to open it as a compact panel over your game. Every tile below stays inside this center.</span>
  </section>
  <section class="ops-section" aria-labelledby="quick-reference">
    <div class="ops-section-heading"><div><p class="ops-kicker">IN THE MOMENT</p><h2 id="quick-reference">Quick Reference</h2></div><span>1 tap</span></div>
    <div class="ops-grid ops-grid-quick">{quick}</div>
  </section>
  <section class="ops-section" aria-labelledby="run-the-game">
    <div class="ops-section-heading"><div><p class="ops-kicker">GUIDED PROCEDURES</p><h2 id="run-the-game">Run the Game</h2></div><span>Browse by task</span></div>
    <div class="ops-grid">{categories}</div>
  </section>
  <footer class="ops-footer">PF2E Remaster • Internal quick guides</footer>"""
    return Page("PF2E Operations Center", HOME, "pf2e-operations-center", 0, shell("PF2E Operations Center", "Fast, table-focused Pathfinder Second Edition Remaster guidance for the GM.", body, page_class="ops-home"))


def encounter_landing() -> Page:
    prepare = "".join(
        [
            card("pf2e-ops-xp-difficulty", "Build & rate an encounter", "XP budgets, party-size adjustments, creatures, and hazards.", "BEFORE PLAY"),
            card("pf2e-ops-dcs", "Set DCs", "Pick a simple or level-based DC, then adjust only when needed.", "BEFORE OR DURING"),
        ]
    )
    run = "".join(
        [
            card("pf2e-ops-encounter-sequence", "Encounter sequence", "A round-by-round procedure from initiative to resolution.", "START HERE"),
            card("pf2e-ops-initiative", "Initiative", "Choose skills, place ties, handle stealth, and batch similar foes.", "STEP 1"),
            card("pf2e-ops-turns-actions", "Turns & actions", "Action economy, triggers, activities, and multiple attacks.", "STEP 2"),
            card("pf2e-ops-attacks-damage", "Attacks & damage", "Resolve checks, degrees of success, damage, and basic saves.", "RESOLVE"),
            card("pf2e-ops-movement-positioning", "Movement & positioning", "Squares, terrain, forced movement, and flanking.", "ON THE MAP"),
            card("pf2e-ops-cover-visibility", "Cover & visibility", "Lesser, standard, and greater cover plus detection states.", "ADJUDICATE"),
            card("pf2e-ops-recovery", "Dying & recovery", "Dropping to 0 HP, recovery checks, wounded, and stabilization.", "WHEN A PC FALLS"),
            card("pf2e-ops-ending-encounters", "End the encounter", "Decide when encounter mode ends and handle the immediate aftermath.", "CLOSE"),
        ]
    )
    body = f"""
  <section class="ops-section"><div class="ops-section-heading"><div><p class="ops-kicker">PREPARE</p><h2>Before initiative</h2></div></div><div class="ops-grid">{prepare}</div></section>
  <section class="ops-section"><div class="ops-section-heading"><div><p class="ops-kicker">RUN</p><h2>At the table</h2></div></div><div class="ops-grid">{run}</div></section>
  <aside class="ops-callout"><strong>Need the shortest path?</strong><span>Open Encounter sequence. It links to each decision exactly where it occurs.</span></aside>"""
    return Page("Encounters & Combat", ENCOUNTERS, "encounters-combat", 0, shell("Encounters & Combat", "Prepare the threat, run the round, adjudicate the map, and finish cleanly.", body, [("Encounters & Combat", ENCOUNTERS)]))


def encounter_sequence() -> Page:
    body = """
  <ol class="ops-procedure">
    <li><span>1</span><div><strong>Roll initiative</strong><p>Each participant rolls Perception unless another skill fits what they were doing when the encounter began. Put results in descending order; PCs win ties against enemies, then use modifiers or a roll-off for remaining ties.</p><a href="/page/pf2e-ops-initiative">Initiative quick guide</a></div></li>
    <li><span>2</span><div><strong>Run each turn</strong><p>At the start, apply start-of-turn effects and regain 3 actions plus 1 reaction. The creature spends actions in any order, then resolve end-of-turn effects.</p><a href="/page/pf2e-ops-turns-actions">Turns & actions quick guide</a></div></li>
    <li><span>3</span><div><strong>Begin the next round</strong><p>After everyone acts, return to the highest initiative. Do not reroll unless a specific rule tells you to.</p></div></li>
    <li><span>4</span><div><strong>End encounter mode</strong><p>Stop using initiative when moment-to-moment action order no longer matters. Resolve urgent consequences before returning to exploration.</p><a href="/page/pf2e-ops-ending-encounters">Ending encounters quick guide</a></div></li>
  </ol>
  <aside class="ops-callout ops-callout-warn"><strong>Pause before skipping initiative</strong><span>If timing, positioning, hazards, or reactions could change the outcome, stay in encounter mode.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("step-1-roll-initiative-rules-2423", "Step 1: Roll Initiative") + full_rule("step-2-play-a-round-rules-2424", "Step 2: Play a Round") + full_rule("step-4-end-the-encounter-rules-2426", "Step 4: End the Encounter"),
        related([
            ("pf2e-ops-cover-visibility", "Cover & visibility", "When line of sight or line of effect matters."),
            ("pf2e-ops-recovery", "Dying & recovery", "When a combatant reaches 0 HP."),
        ]),
    )
    return Page("Encounter Sequence", "pf2e-ops-encounter-sequence", "encounters-combat", 1, shell("Encounter Sequence", "The reliable four-step loop for encounter mode.", body, [("Encounters & Combat", ENCOUNTERS), ("Encounter Sequence", "pf2e-ops-encounter-sequence")]))


def initiative_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Choose the roll that matches the fiction</h2><p>Perception is the default. Use Stealth for someone Avoiding Notice, Deception for a social feint that starts the conflict, or another skill only when that activity genuinely determined readiness.</p></section>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Situation</th><th>GM ruling</th></tr></thead><tbody>
    <tr><th>PC and enemy tie</th><td>The PC goes first.</td></tr>
    <tr><th>Two enemies tie</th><td>Higher initiative modifier first; if still tied, decide or roll.</td></tr>
    <tr><th>Two PCs tie</th><td>They choose their order; otherwise use modifiers, then roll.</td></tr>
    <tr><th>Hidden participant</th><td>Use Stealth when appropriate and compare it with observers’ Perception DCs to determine detection separately from turn order.</td></tr>
    <tr><th>Many identical enemies</th><td>Batch initiative can reduce overhead; separate important leaders or tactically distinct groups.</td></tr>
  </tbody></table></div>
  <aside class="ops-callout"><strong>Initiative is not detection</strong><span>A high Stealth initiative does not automatically make a creature unnoticed. Resolve observed, hidden, or undetected status against each observer.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("alternative-initiative-skills-rules-2540", "Alternative Initiative Skills") + full_rule("initiative-with-stealth-rules-2541", "Initiative with Stealth") + full_rule("batch-initiative-rules-2542", "Batch Initiative"),
        related([
            ("pf2e-ops-encounter-sequence", "Encounter sequence", "Return to the complete round procedure."),
            ("pf2e-ops-cover-visibility", "Cover & visibility", "Resolve who can detect and target whom."),
        ]),
    )
    return Page("Initiative", "pf2e-ops-initiative", "encounters-combat", 2, shell("Initiative", "Set the order, then resolve detection as a separate question.", body, [("Encounters & Combat", ENCOUNTERS), ("Initiative", "pf2e-ops-initiative")]))


def actions_page() -> Page:
    body = """
  <section class="ops-symbol-row" aria-label="Action symbols">
    <div><img src="icons/actions/one.png" alt="One action"><strong>1 action</strong><span>Most basic actions</span></div>
    <div><img src="icons/actions/two.png" alt="Two actions"><strong>2 actions</strong><span>One activity</span></div>
    <div><img src="icons/actions/three.png" alt="Three actions"><strong>3 actions</strong><span>One activity</span></div>
    <div><img src="icons/actions/reaction.png" alt="Reaction"><strong>Reaction</strong><span>Needs a trigger</span></div>
    <div><img src="icons/actions/free.png" alt="Free action"><strong>Free action</strong><span>May need a trigger</span></div>
  </section>
  <section class="ops-answer"><h2>Turn checklist</h2><ol><li>Resolve start-of-turn effects; regain 3 actions and 1 reaction.</li><li>Spend actions in any order. An activity must be completed as a unit.</li><li>Use reactions or triggered free actions only when their trigger occurs.</li><li>Resolve end-of-turn effects.</li></ol></section>
  <aside class="ops-callout ops-callout-warn"><strong>Multiple attack penalty</strong><span>Your second attack on a turn is normally −5 and later attacks are −10. Agile attacks normally use −4 and −8. MAP applies to attack-trait actions, not only Strikes, and resets when the turn ends.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("actions-rules-2335", "Actions") + full_rule("basic-actions-rules-2343", "Basic Actions") + full_rule("turns-rules-2427", "Turns") + full_rule("multiple-attack-penalty-rules-2289", "Multiple Attack Penalty"),
        related([
            ("pf2e-ops-attacks-damage", "Attacks & damage", "Resolve attack checks and their results."),
            ("pf2e-ops-movement-positioning", "Movement & positioning", "Stride, Step, terrain, and flanking."),
        ]),
    )
    return Page("Turns & Actions", "pf2e-ops-turns-actions", "encounters-combat", 3, shell("Turns & Actions", "Keep the economy visible and the ruling focused on triggers.", body, [("Encounters & Combat", ENCOUNTERS), ("Turns & Actions", "pf2e-ops-turns-actions")]))


def attacks_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Resolve a check</h2><p>Roll d20 + modifier against the DC. The result is a success on a tie. A natural 20 improves the degree by one step; a natural 1 worsens it by one step.</p></section>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Result</th><th>Typical attack outcome</th><th>Basic save outcome</th></tr></thead><tbody>
    <tr><th>Critical success</th><td>Double damage and apply the critical effect.</td><td>No damage.</td></tr>
    <tr><th>Success</th><td>Normal damage and success effect.</td><td>Half damage.</td></tr>
    <tr><th>Failure</th><td>No damage unless the ability says otherwise.</td><td>Full damage.</td></tr>
    <tr><th>Critical failure</th><td>No damage unless the ability says otherwise.</td><td>Double damage.</td></tr>
  </tbody></table></div>
  <section class="ops-answer"><h2>Damage order</h2><ol><li>Roll the listed damage and apply increases or reductions.</li><li>Apply immunities, then weaknesses, then resistances to each applicable damage instance.</li><li>Subtract the final amount from Hit Points and resolve reaching 0 HP.</li></ol></section>
  <aside class="ops-callout"><strong>Keep bonuses typed</strong><span>For the same check or DC, use only the highest circumstance bonus, highest status bonus, and highest item bonus; likewise use only the worst penalty of each type. Untyped modifiers stack unless stated otherwise.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("attack-rolls-rules-2288", "Attack Rolls") + full_rule("damage-rules-2274", "Damage") + full_rule("basic-saving-throws-rules-2297", "Basic Saving Throws"),
        related([
            ("pf2e-ops-turns-actions", "Turns & actions", "Check MAP before making another attack."),
            ("pf2e-ops-recovery", "Dying & recovery", "Resolve a creature dropping to 0 HP."),
        ]),
    )
    return Page("Attacks & Damage", "pf2e-ops-attacks-damage", "encounters-combat", 4, shell("Attacks & Damage", "Checks, degrees of success, damage, and the basic-save shortcut.", body, [("Encounters & Combat", ENCOUNTERS), ("Attacks & Damage", "pf2e-ops-attacks-damage")]))


def movement_page() -> Page:
    body = """
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Question</th><th>Quick ruling</th></tr></thead><tbody>
    <tr><th>Normal movement</th><td>A Stride moves up to Speed. Measure the path square by square.</td></tr>
    <tr><th>Diagonal squares</th><td>Count the first diagonal as 5 feet, the second as 10 feet, then alternate.</td></tr>
    <tr><th>Difficult terrain</th><td>Each square costs 5 extra feet of movement. Greater difficult terrain costs 10 extra feet.</td></tr>
    <tr><th>Step</th><td>Move 5 feet without triggering reactions caused by move actions or leaving a square; normally not into difficult terrain.</td></tr>
    <tr><th>Forced movement</th><td>It normally does not trigger reactions based on movement and cannot force a creature into a space it could not occupy, unless the effect says otherwise.</td></tr>
    <tr><th>Flanking</th><td>Two allies on opposite sides who can act and threaten the target make it off-guard to their melee attacks.</td></tr>
  </tbody></table></div>
  <aside class="ops-callout"><strong>Decide from the creature’s space</strong><span>For large creatures, use occupied squares and draw the relevant lines. One ally can flank only from one position at a time.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("movement-rules-2345", "Movement") + full_rule("difficult-terrain-rules-2366", "Difficult Terrain") + full_rule("flanking-rules-2375", "Flanking"),
        related([
            ("pf2e-ops-cover-visibility", "Cover & visibility", "Draw lines and adjudicate obstacles."),
            ("pf2e-ops-turns-actions", "Turns & actions", "Check the action cost and reaction triggers."),
        ]),
    )
    return Page("Movement & Positioning", "pf2e-ops-movement-positioning", "encounters-combat", 5, shell("Movement & Positioning", "Fast map rulings for distance, terrain, forced movement, and flanking.", body, [("Encounters & Combat", ENCOUNTERS), ("Movement & Positioning", "pf2e-ops-movement-positioning")]))


def cover_page() -> Page:
    body = """
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Cover</th><th>Bonus</th><th>Typical situation</th></tr></thead><tbody>
    <tr><th>Lesser</th><td>+1 circumstance to AC</td><td>A creature or small obstruction is in the way.</td></tr>
    <tr><th>Standard</th><td>+2 circumstance to AC, Reflex saves against area effects, and Stealth checks to Hide</td><td>A substantial obstacle blocks part of the creature.</td></tr>
    <tr><th>Greater</th><td>+4 instead of +2</td><td>Most of the creature is protected.</td></tr>
  </tbody></table></div>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Detection state</th><th>What it means at the table</th></tr></thead><tbody>
    <tr><th>Observed</th><td>You know the exact space and can perceive the creature clearly.</td></tr>
    <tr><th>Hidden</th><td>You know the space; targeting normally requires a DC 11 flat check.</td></tr>
    <tr><th>Undetected</th><td>You do not know the space. Choose a space, then normally make the DC 11 flat check; the GM rolls privately and conceals whether the space was correct.</td></tr>
    <tr><th>Unnoticed</th><td>You do not know the creature is present.</td></tr>
    <tr><th>Concealed</th><td>You can locate it, but targeting normally requires a DC 5 flat check.</td></tr>
  </tbody></table></div>
  <aside class="ops-callout ops-callout-warn"><strong>Ask two separate questions</strong><span>Can the acting creature perceive the target well enough to choose it? Is there an unblocked line of effect? A target can be visible but still protected by cover or blocked from an effect.</span></aside>
  <section class="ops-rule-links"><h2>Full rules & tables</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("cover-rules-2372", "Cover") + full_rule("hidden-rules-2416", "Hidden") + full_rule("undetected-rules-2417", "Undetected") + full_rule("line-of-effect-rules-2382", "Line of Effect") + full_table("Cover") + full_table("Detection and Targeting"),
        related([
            ("pf2e-ops-initiative", "Initiative", "Separate Stealth initiative from detection."),
            ("pf2e-ops-movement-positioning", "Movement & positioning", "Resolve spaces, lines, and flanking."),
        ]),
    )
    return Page("Cover & Visibility", "pf2e-ops-cover-visibility", "encounters-combat", 6, shell("Cover & Visibility", "Cover, detection, targeting, and line of effect without hunting across chapters.", body, [("Encounters & Combat", ENCOUNTERS), ("Cover & Visibility", "pf2e-ops-cover-visibility")]))


def recovery_page() -> Page:
    body = """
  <section class="ops-answer"><h2>When a PC reaches 0 HP</h2><ol><li>Move their initiative to immediately before the turn that reduced them to 0 HP.</li><li>Gain dying 1, or dying 2 if the effect was a critical success by the attacker or the PC’s critical failure. Add wounded value to dying.</li><li>Fall unconscious, drop held items, and apply the normal unconscious effects.</li></ol></section>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Recovery result</th><th>Change</th></tr></thead><tbody>
    <tr><th>Critical success</th><td>Reduce dying by 2.</td></tr>
    <tr><th>Success</th><td>Reduce dying by 1.</td></tr>
    <tr><th>Failure</th><td>Increase dying by 1.</td></tr>
    <tr><th>Critical failure</th><td>Increase dying by 2.</td></tr>
  </tbody></table></div>
  <aside class="ops-callout"><strong>Recovery DC = 10 + dying value</strong><span>On losing dying, increase wounded by 1. If dying reaches 4, the character dies. A Hero Point can prevent death by spending all remaining Hero Points to lose dying and stabilize.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("dying-rules-2325", "Dying") + full_rule("recovery-checks-rules-2326", "Recovery Checks") + full_rule("hero-points-rules-2333", "Hero Points"),
        related([
            ("pf2e-ops-ending-encounters", "Ending encounters", "Handle immediate danger before exploration."),
            ("pf2e-ops-encounter-sequence", "Encounter sequence", "Return to round order."),
        ]),
    )
    return Page("Dying & Recovery", "pf2e-ops-recovery", "encounters-combat", 7, shell("Dying & Recovery", "The urgent sequence for 0 HP, recovery checks, wounded, and stabilization.", body, [("Encounters & Combat", ENCOUNTERS), ("Dying & Recovery", "pf2e-ops-recovery")]))


def ending_page() -> Page:
    body = """
  <section class="ops-answer"><h2>End encounter mode when exact turn order stops mattering</h2><p>Enemies might surrender, flee beyond meaningful pursuit, become unable to threaten the party, or agree to talk. The GM decides when the encounter is resolved; it need not continue until every opponent reaches 0 HP.</p></section>
  <ul class="ops-checklist">
    <li><strong>Resolve urgent effects</strong><span>Persistent damage, dying creatures, hazards, short durations, and active environmental threats.</span></li>
    <li><strong>Clarify the opposition</strong><span>Who escaped, surrendered, died, or remains a future threat?</span></li>
    <li><strong>Award and record</strong><span>Use encounter XP and any accomplishment award; note consumables, conditions, and treasure.</span></li>
    <li><strong>Return to exploration</strong><span>Ask for the party’s next activity rather than assuming they immediately Treat Wounds or Search.</span></li>
  </ul>
  <section class="ops-rule-links"><h2>Full rules & tools</h2><div class="ops-grid">%s%s</div></section>
  %s""" % (
        full_rule("ending-the-encounter-rules-2570", "Ending the Encounter"),
        '<a class="ops-exit-link ops-tool-link" href="/page/pf2e-ops-xp-planner"><span>Open Internal Tool</span><strong>Compact XP Planner</strong></a>',
        related([
            ("pf2e-ops-xp-difficulty", "XP & encounter threat", "Confirm the award and party adjustment."),
            ("pf2e-ops-recovery", "Dying & recovery", "Resolve fallen creatures before leaving rounds."),
        ]),
    )
    return Page("Ending Encounters", "pf2e-ops-ending-encounters", "encounters-combat", 8, shell("Ending Encounters", "Close the scene when turn order no longer changes the outcome.", body, [("Encounters & Combat", ENCOUNTERS), ("Ending Encounters", "pf2e-ops-ending-encounters")]))


def xp_page() -> Page:
    body = """
  <div class="ops-table-wrap"><table class="ops-table ops-number-table"><thead><tr><th>Creature level vs party</th><th>−4</th><th>−3</th><th>−2</th><th>−1</th><th>Equal</th><th>+1</th><th>+2</th><th>+3</th><th>+4</th></tr></thead><tbody><tr><th>XP</th><td>10</td><td>15</td><td>20</td><td>30</td><td>40</td><td>60</td><td>80</td><td>120</td><td>160</td></tr></tbody></table></div>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Threat</th><th>4-PC budget</th><th>Adjust per PC</th><th>Use</th></tr></thead><tbody>
    <tr><th>Trivial</th><td>40 XP</td><td>±10 XP</td><td>Low danger; usually a warm-up or story beat.</td></tr>
    <tr><th>Low</th><td>60 XP</td><td>±20 XP</td><td>Some resources; little risk with sound play.</td></tr>
    <tr><th>Moderate</th><td>80 XP</td><td>±20 XP</td><td>A serious, fair challenge.</td></tr>
    <tr><th>Severe</th><td>120 XP</td><td>±30 XP</td><td>Dangerous; best for important moments.</td></tr>
    <tr><th>Extreme</th><td>160 XP</td><td>±40 XP</td><td>Even odds against a fully prepared party; use sparingly.</td></tr>
  </tbody></table></div>
  <aside class="ops-callout"><strong>Party size changes the budget, not the award</strong><span>Add the adjustment for each PC above four or subtract it for each PC below four. The XP awarded is based on the unadjusted creature and hazard XP.</span></aside>
  <section class="ops-launch"><div><p class="ops-kicker">INTERACTIVE</p><h2>Calculate the exact encounter</h2><p>Add creatures and hazards, apply weak or elite adjustments, and copy the final value into Encounter+’s native XP award sheet.</p></div><a href="/page/pf2e-ops-xp-planner">Open Compact Planner</a></section>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("xp-budget-rules-2717", "XP Budget") + full_rule("choosing-creatures-rules-2718", "Choosing Creatures") + full_rule("different-party-sizes-rules-2719", "Different Party Sizes") + full_rule("xp-awards-rules-2649", "XP Awards") + full_table("Encounter XP Budget") + full_table("Creature XP and Role"),
        related([
            ("pf2e-ops-dcs", "DCs at a glance", "Choose improvised and level-based DCs."),
            ("pf2e-ops-ending-encounters", "Ending encounters", "Close the scene and award XP."),
        ]),
    )
    return Page("XP & Encounter Difficulty", "pf2e-ops-xp-difficulty", "encounters-combat", 9, shell("XP & Encounter Difficulty", "Build for the actual party, judge the threat, then hand off the award.", body, [("Encounters & Combat", ENCOUNTERS), ("XP & Encounter Difficulty", "pf2e-ops-xp-difficulty")]))


def compact_xp_planner_page() -> Page:
    body = """
  <section class="xp-calculator" data-xp-calculator>
    <section class="xp-setup" aria-labelledby="xp-party-heading">
      <h2 id="xp-party-heading">Party Setup</h2>
      <div class="xp-field-grid">
        <label>Party level<input type="number" min="1" max="20" step="1" value="1" data-xp-party-level></label>
        <label>Number of PCs<input type="number" min="1" max="12" step="1" value="4" data-xp-party-size></label>
        <label>Additional award XP<input type="number" min="0" step="1" value="0" data-xp-additional><small>Accomplishments or other awards; not part of encounter threat.</small></label>
      </div>
    </section>

    <section class="xp-results" aria-live="polite">
      <div class="xp-result-card"><span>Encounter XP</span><strong data-xp-total>0</strong></div>
      <div class="xp-result-card xp-threat-card" data-xp-threat-card><span>Threat</span><strong data-xp-threat>Trivial</strong></div>
      <div class="xp-result-card"><span>Award total</span><strong data-xp-award>0</strong></div>
    </section>

    <section class="xp-roster" aria-labelledby="xp-roster-heading">
      <div class="xp-section-heading"><div><h2 id="xp-roster-heading">Encounter Entries</h2><p>Complex hazards use creature XP. Simple hazards use one-fifth.</p></div><button type="button" class="xp-button" data-xp-add-entry>Add entry</button></div>
      <div class="table-responsive"><table class="xp-entry-table"><thead><tr><th>Name</th><th>Type</th><th>Level</th><th>Adjustment</th><th>Quantity</th><th>XP override</th><th>XP each</th><th>Total</th><th><span class="visually-hidden">Remove</span></th></tr></thead><tbody data-xp-entries></tbody></table></div>
      <p class="xp-warning" data-xp-warning hidden></p>
      <div class="xp-actions"><button type="button" class="xp-button secondary" data-xp-reset>Reset planner</button></div>
    </section>

    <section class="xp-native-handoff" aria-labelledby="xp-native-heading">
      <div><h2 id="xp-native-heading">Award with Encounter+</h2><p>Copy the total, close this panel, open <strong>Experience</strong>, paste into <strong>Total Experience</strong>, choose the creatures, and tap <strong>Award</strong>.</p><p class="xp-native-note">Party size changes the budget, not the XP awarded to each PC.</p></div>
      <div class="xp-native-action"><button type="button" class="xp-button xp-copy-native" data-xp-copy-native data-copy-value="0">Copy 0 XP</button><span class="xp-copy-status" data-xp-copy-status role="status" aria-live="polite"></span></div>
    </section>

    <details class="xp-budget-panel ops-disclosure">
      <summary>Adjusted Encounter Budgets</summary>
      <div class="table-responsive"><table class="xp-budget-table"><thead><tr><th>Threat</th><th>Trivial</th><th>Low</th><th>Moderate</th><th>Severe</th><th>Extreme</th></tr></thead><tbody><tr><th>XP target</th><td data-xp-budget="trivial">40</td><td data-xp-budget="low">60</td><td data-xp-budget="moderate">80</td><td data-xp-budget="severe">120</td><td data-xp-budget="extreme">160</td></tr></tbody></table></div>
      <p class="xp-interpretation" data-xp-interpretation></p>
    </details>
  </section>
  <div class="ops-link-list"><a href="/page/pf2e-ops-xp-difficulty"><strong>XP rules & difficulty guide</strong><span>Budgets, party-size adjustments, and full-rule links.</span></a></div>"""
    script = f"<script>\n{embedded_xp_script()}\n</script>"
    return Page(
        "Compact XP Planner",
        "pf2e-ops-xp-planner",
        "encounters-combat",
        10,
        shell(
            "Compact XP Planner",
            "Build the encounter inside this bookmarked panel, then copy the award into Encounter+.",
            body,
            [("Encounters & Combat", ENCOUNTERS), ("XP Planner", "pf2e-ops-xp-planner")],
            page_class="ops-xp-page",
            extra_styles=embedded_xp_styles(),
            trailing_html=script,
        ),
    )


def dcs_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Pick the table from the question</h2><p>Use a simple DC when proficiency is the main question. Use a level-based DC when a creature, item, spell, hazard, or other leveled subject sets the difficulty.</p></section>
  <div class="ops-columns"><div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Proficiency</th><th>Simple DC</th></tr></thead><tbody><tr><th>Untrained</th><td>10</td></tr><tr><th>Trained</th><td>15</td></tr><tr><th>Expert</th><td>20</td></tr><tr><th>Master</th><td>30</td></tr><tr><th>Legendary</th><td>40</td></tr></tbody></table></div>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Adjustment</th><th>DC change</th></tr></thead><tbody><tr><th>Incredibly easy</th><td>−10</td></tr><tr><th>Very easy</th><td>−5</td></tr><tr><th>Easy</th><td>−2</td></tr><tr><th>Hard</th><td>+2</td></tr><tr><th>Very hard</th><td>+5</td></tr><tr><th>Incredibly hard</th><td>+10</td></tr></tbody></table></div></div>
  %s
  <aside class="ops-callout ops-callout-warn"><strong>Adjust for circumstance, not twice for the same fact</strong><span>Start with the correct base DC. Apply a rarity adjustment or difficulty adjustment only when the situation truly differs from the baseline; avoid stacking several labels for one reason.</span></aside>
  <section class="ops-rule-links"><h2>Full rules & table</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        reference_picker("Level-Based DC", ["DCs by Level"]),
        full_rule("simple-dcs-rules-2628", "Simple DCs") + full_rule("level-based-dcs-rules-2629", "Level-Based DCs") + full_rule("adjusting-difficulty-rules-2630", "Adjusting Difficulty") + full_table("Spell Rank DCs"),
        related([
            ("pf2e-ops-xp-difficulty", "XP & encounter threat", "Build an encounter around the party."),
            ("pf2e-ops-attacks-damage", "Attacks & damage", "Apply degrees of success to checks."),
        ]),
    )
    return Page("DCs at a Glance", "pf2e-ops-dcs", "checks-dcs-actions", 1, shell("DCs at a Glance", "Choose the correct base, then make one deliberate adjustment.", body, [("Checks, DCs & Skill Actions", "pf2e-ops-checks-dcs-actions"), ("DCs at a Glance", "pf2e-ops-dcs")], trailing_html=f"<script>\n{embedded_reference_script()}\n</script>"))


def checks_landing() -> Page:
    cards = "".join(
        [
            card("pf2e-ops-dcs", "Choose a DC", "Simple and level-based DCs with deliberate difficulty adjustments.", "SET THE TARGET"),
            card("pf2e-ops-check-results", "Resolve a check", "Bonuses, penalties, natural 20 and 1, and degrees of success.", "READ THE ROLL"),
            card("pf2e-ops-skill-actions", "Find a skill action", "Browse by intent: move, influence, investigate, hide, or recover.", "ACTION FINDER"),
            card("pf2e-ops-secret-checks", "Secret checks", "Preserve uncertainty without hiding meaningful choices from players.", "GM ROLLS"),
            card("pf2e-ops-recall-knowledge", "Recall Knowledge", "Choose the skill and DC, then reveal useful, actionable information.", "REVEAL INFO"),
            card("pf2e-ops-aid", "Aid & teamwork", "Prepare help, resolve the reaction, and apply the proficiency-scaled bonus.", "TEAMWORK"),
        ]
    )
    body = f"""
  <section class="ops-intro ops-callout"><strong>Start with the character’s intent.</strong><span>Pick the action that matches what they are attempting, then choose the DC and resolve the result. Do not begin with a skill name if the fiction points to a different action.</span></section>
  <section class="ops-section"><div class="ops-section-heading"><div><p class="ops-kicker">ADJUDICATE</p><h2>From intent to outcome</h2></div><span>Choose a task</span></div><div class="ops-grid">{cards}</div></section>
  <aside class="ops-callout ops-callout-warn"><strong>No action exactly fits?</strong><span>Use the closest structure, set a DC from the subject’s level or required proficiency, state the stakes, and keep the ruling consistent for comparable attempts.</span></aside>"""
    return Page("Checks, DCs & Skill Actions", "pf2e-ops-checks-dcs-actions", "checks-dcs-actions", 0, shell("Checks, DCs & Skill Actions", "The table path from player intent to a clear, consistent outcome.", body, [("Checks, DCs & Skill Actions", "pf2e-ops-checks-dcs-actions")]))


def check_results_page() -> Page:
    body = """
  <section class="ops-answer"><h2>The four-step check</h2><ol><li>Roll d20 and add the relevant modifier.</li><li>Apply the applicable bonuses and penalties.</li><li>Compare the total with the DC; a tie succeeds.</li><li>Adjust the degree one step for a natural 20 or natural 1.</li></ol></section>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Total</th><th>Starting degree</th></tr></thead><tbody>
    <tr><th>DC + 10 or more</th><td>Critical success</td></tr>
    <tr><th>At least the DC</th><td>Success</td></tr>
    <tr><th>Below the DC</th><td>Failure</td></tr>
    <tr><th>DC − 10 or less</th><td>Critical failure</td></tr>
  </tbody></table></div>
  <aside class="ops-callout"><strong>Typed modifiers do not all stack</strong><span>For each type, apply only the highest circumstance, status, and item bonus, plus only the worst penalty of each type. Untyped modifiers usually stack unless a rule says otherwise.</span></aside>
  <aside class="ops-callout ops-callout-warn"><strong>Flat checks are different</strong><span>Roll an unmodified d20 against the flat-check DC. No bonuses, penalties, or difficulty adjustments apply unless the specific rule explicitly says so.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("checks-rules-2278", "Checks") + full_rule("step-4-degree-of-success-rules-2286", "Degree of Success") + full_rule("bonuses-rules-2281", "Bonuses") + full_rule("penalties-rules-2282", "Penalties"),
        related([
            ("pf2e-ops-dcs", "DCs at a glance", "Choose the number the check must meet."),
            ("pf2e-ops-skill-actions", "Skill actions", "Find the action and its result structure."),
        ]),
    )
    return Page("Resolve a Check", "pf2e-ops-check-results", "checks-dcs-actions", 2, shell("Resolve a Check", "Build the total, compare it with the DC, then adjust the degree.", body, [("Checks, DCs & Skill Actions", "pf2e-ops-checks-dcs-actions"), ("Resolve a Check", "pf2e-ops-check-results")]))


def skill_actions_page() -> Page:
    move = [
        ("Balance", "balance-player-core", "Acrobatics", "1 action", "Cross a narrow or unstable surface without falling."),
        ("Maneuver in Flight", "maneuver-in-flight-player-core", "Acrobatics", "1 action", "Attempt a difficult aerial maneuver."),
        ("Squeeze", "squeeze-player-core", "Acrobatics", "Exploration", "Move through a space that barely fits."),
        ("Tumble Through", "tumble-through-player-core", "Acrobatics", "1 action", "Move through an enemy’s space."),
        ("Climb", "climb-player-core", "Athletics", "1 action", "Move up, down, or across an incline."),
        ("Force Open", "force-open-player-core", "Athletics", "1 action", "Break or wrench open an obstacle; has attack trait."),
        ("Grapple", "grapple-player-core", "Athletics", "1 action", "Grab or restrain a creature against Fortitude DC."),
        ("High Jump", "high-jump-player-core", "Athletics", "2 actions", "Leap vertically after a Stride."),
        ("Long Jump", "long-jump-player-core", "Athletics", "2 actions", "Leap horizontally after a Stride."),
        ("Reposition", "reposition-player-core", "Athletics", "1 action", "Move a grabbed or restrained target."),
        ("Shove", "shove-player-core", "Athletics", "1 action", "Push a creature away against Fortitude DC."),
        ("Swim", "swim-player-core", "Athletics", "1 action", "Move through water or another liquid."),
        ("Trip", "trip-player-core", "Athletics", "1 action", "Knock a creature prone against Reflex DC."),
        ("Disarm", "disarm-player-core", "Athletics", "1 action", "Compromise or remove a held item against Reflex DC."),
    ]
    influence = [
        ("Create a Diversion", "create-a-diversion-player-core", "Deception", "1 action", "Become hidden briefly through distraction."),
        ("Feint", "feint-player-core", "Deception", "1 action", "Make a foe off-guard to your next melee attack."),
        ("Impersonate", "impersonate-player-core", "Deception", "Exploration", "Pass yourself off as another identity."),
        ("Lie", "lie-player-core", "Deception", "Varies", "Convince someone of a falsehood; GM rolls secretly."),
        ("Gather Information", "gather-information-player-core", "Diplomacy", "Exploration", "Learn about a topic by talking to people."),
        ("Make an Impression", "make-an-impression-player-core", "Diplomacy", "Exploration", "Improve a creature’s attitude toward you."),
        ("Request", "request-player-core", "Diplomacy", "1 action", "Ask a friendly or helpful creature for something."),
        ("Coerce", "coerce-player-core", "Intimidation", "Exploration", "Force short-term cooperation through threats."),
        ("Demoralize", "demoralize-player-core", "Intimidation", "1 action", "Frighten a creature against its Will DC."),
        ("Perform", "perform-player-core", "Performance", "1 action", "Make a brief performance for an audience."),
    ]
    investigate = [
        ("Recall Knowledge", "recall-knowledge-player-core", "Knowledge skill", "1 action", "Remember useful information; GM rolls secretly."),
        ("Decipher Writing", "decipher-writing-player-core", "Knowledge skill", "Exploration", "Understand difficult or coded text."),
        ("Identify Magic", "identify-magic-player-core", "Tradition skill", "Exploration", "Determine the nature of a magical effect or item."),
        ("Identify Alchemy", "identify-alchemy-player-core", "Crafting", "Exploration", "Determine the nature of an alchemical item."),
        ("Learn a Spell", "learn-a-spell-player-core", "Tradition skill", "Exploration", "Add or retrain a spell from another source."),
        ("Borrow an Arcane Spell", "borrow-an-arcane-spell-player-core", "Arcana", "Exploration", "Prepare from another arcane spellbook."),
        ("Create Forgery", "create-forgery-player-core", "Society", "Downtime", "Create a false document or signature."),
        ("Craft", "craft-player-core", "Crafting", "Downtime", "Create an item from materials and formulas."),
        ("Repair", "repair-player-core", "Crafting", "Exploration", "Restore an item’s Hit Points; the amount scales with proficiency."),
        ("Earn Income", "earn-income-player-core", "Crafting, Lore, Performance", "Downtime", "Work a task to earn money."),
    ]
    notice = [
        ("Seek", "seek-player-core", "Perception", "1 action", "Scan an area for hidden creatures or objects."),
        ("Sense Motive", "sense-motive-player-core", "Perception", "1 action", "Notice whether behavior seems deceptive."),
        ("Conceal an Object", "conceal-an-object-player-core", "Stealth", "1 action", "Hide a small object on your person."),
        ("Hide", "hide-player-core", "Stealth", "1 action", "Become hidden while you have cover or concealment."),
        ("Sneak", "sneak-player-core", "Stealth", "1 action", "Move while remaining undetected."),
        ("Palm an Object", "palm-an-object-player-core", "Thievery", "1 action", "Take or place a small object unnoticed."),
        ("Steal", "steal-player-core", "Thievery", "1 action", "Take an object from another creature unnoticed."),
        ("Disable a Device", "disable-a-device-player-core", "Thievery", "2 actions", "Disarm a trap or disable a mechanism."),
        ("Pick a Lock", "pick-a-lock-player-core", "Thievery", "2 actions", "Open a lock using thieves’ tools."),
    ]
    survive = [
        ("Administer First Aid", "administer-first-aid-player-core", "Medicine", "2 actions", "Stabilize a dying creature or stop persistent bleed."),
        ("Treat Disease", "treat-disease-player-core", "Medicine", "Downtime", "Help a patient recover from disease."),
        ("Treat Poison", "treat-poison-player-core", "Medicine", "1 action", "Help a creature resist a poison."),
        ("Treat Wounds", "treat-wounds-player-core", "Medicine", "Exploration", "Restore Hit Points outside immediate combat."),
        ("Command an Animal", "command-an-animal-player-core", "Nature", "1 action", "Direct an animal to perform an action."),
        ("Sense Direction", "sense-direction-player-core", "Survival", "Exploration", "Determine direction in the wild."),
        ("Subsist", "subsist-player-core", "Society or Survival", "Downtime", "Find food and shelter without paying."),
        ("Cover Tracks", "cover-tracks-player-core", "Survival", "Exploration", "Obscure your trail while moving at half travel Speed."),
        ("Track", "track-player-core", "Survival", "Exploration", "Follow signs left by a moving creature."),
    ]
    body = """
  <section class="ops-intro ops-callout"><strong>Browse by intent, not by character sheet.</strong><span><b>Untrained</b> actions can be attempted by anyone. <b>Trained only</b> actions require trained proficiency or better. <b>Rank matters</b> flags actions whose harder uses, available options, or results change at higher ranks. Open the complete action for exact requirements and outcomes. Attack-trait skill actions contribute to multiple attack penalty.</span></section>
  %s%s%s%s%s
  %s""" % (
        action_table("Move & maneuver", move, show_proficiency=True),
        action_table("Influence & deceive", influence, show_proficiency=True),
        action_table("Investigate, identify & create", investigate, show_proficiency=True),
        action_table("Notice, hide & bypass", notice, show_proficiency=True),
        action_table("Survive, recover & direct", survive, show_proficiency=True),
        related([
            ("pf2e-ops-dcs", "DCs at a glance", "Set the target for an improvised or leveled task."),
            ("pf2e-ops-secret-checks", "Secret checks", "Handle hidden information and uncertainty."),
            ("pf2e-ops-recall-knowledge", "Recall Knowledge", "Reveal information that changes player decisions."),
        ]),
    )
    return Page("Skill Actions", "pf2e-ops-skill-actions", "checks-dcs-actions", 3, shell("Skill Actions", "An intent-first finder for the core Remaster skill and Perception actions.", body, [("Checks, DCs & Skill Actions", "pf2e-ops-checks-dcs-actions"), ("Skill Actions", "pf2e-ops-skill-actions")]))


def secret_checks_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Use a secret check when knowing the die would reveal the truth</h2><p>The player still chooses the action and supplies the modifier. The GM rolls privately, applies the outcome, and describes only what the character can perceive or conclude.</p></section>
  <ul class="ops-checklist">
    <li><strong>State the decision first</strong><span>Confirm the action, target, method, and relevant resources before rolling.</span></li>
    <li><strong>Use the correct modifier</strong><span>Ask for the value if needed without implying whether the check is necessary or whether danger exists.</span></li>
    <li><strong>Record uncertainty</strong><span>For long investigations, note what was checked so repeated attempts do not accidentally reveal a failed secret check.</span></li>
    <li><strong>Describe evidence, not the die</strong><span>Give the character’s observation or belief. Do not announce “you failed a secret check.”</span></li>
  </ul>
  <aside class="ops-callout ops-callout-warn"><strong>Do not remove meaningful agency</strong><span>Secret means the roll is hidden, not the decision. Tell players the apparent risks and costs their characters could reasonably understand.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("secret-checks-rules-2139", "Secret Checks") + full_rule("secret-checks-rules-2489", "GM Guidance for Secret Checks"),
        related([
            ("pf2e-ops-recall-knowledge", "Recall Knowledge", "Give accurate, useful, or misleading information."),
            ("pf2e-ops-skill-actions", "Skill actions", "Find actions marked with the secret trait."),
        ]),
    )
    return Page("Secret Checks", "pf2e-ops-secret-checks", "checks-dcs-actions", 4, shell("Secret Checks", "Preserve uncertainty while keeping the player’s decision visible.", body, [("Checks, DCs & Skill Actions", "pf2e-ops-checks-dcs-actions"), ("Secret Checks", "pf2e-ops-secret-checks")]))


def recall_knowledge_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Give information that changes a decision</h2><p>Choose the most relevant skill, set a level-based or simple DC, and adjust for rarity when appropriate. A useful answer names a capability, defense, weakness, behavior, or clue the party can act on.</p></section>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Subject</th><th>Common skills</th></tr></thead><tbody>
    <tr><th>Arcane theory and constructs</th><td>Arcana</td></tr>
    <tr><th>Nature, animals, plants, and primal creatures</th><td>Nature</td></tr>
    <tr><th>Occult mysteries and aberrant phenomena</th><td>Occultism</td></tr>
    <tr><th>Divine tradition, undead, and religious matters</th><td>Religion</td></tr>
    <tr><th>People, culture, history, and institutions</th><td>Society</td></tr>
    <tr><th>Trade, region, creature, or specialist knowledge</th><td>The most specific applicable Lore</td></tr>
  </tbody></table></div>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Result</th><th>Information to give</th></tr></thead><tbody>
    <tr><th>Critical success</th><td>Accurate information plus additional useful information or context.</td></tr>
    <tr><th>Success</th><td>Accurate information or a useful clue.</td></tr>
    <tr><th>Failure</th><td>No information; further attempts about the same topic can become harder.</td></tr>
    <tr><th>Critical failure</th><td>Erroneous information or a misleading clue that remains plausible.</td></tr>
  </tbody></table></div>
  <aside class="ops-callout"><strong>For creatures, lead with the table-relevant fact</strong><span>If the player asks a focused question, answer that question when the skill applies. Otherwise reveal a signature ability, strongest defense, exploitable weakness, or important behavior before less actionable lore.</span></aside>
  <section class="ops-rule-links"><h2>Full rules & action</h2><div class="ops-grid">%s<a class="ops-exit-link" href="/action/recall-knowledge-player-core"><span>Open Full Action</span><strong>Recall Knowledge</strong></a></div></section>
  %s""" % (
        full_rule("recall-knowledge-rules-2638", "GM Guidance: Recall Knowledge") + full_rule("specific-actions-rules-2633", "Specific Action DCs"),
        related([
            ("pf2e-ops-dcs", "DCs at a glance", "Choose the base DC and rarity adjustment."),
            ("pf2e-ops-secret-checks", "Secret checks", "Roll privately without removing the choice."),
        ]),
    )
    return Page("Recall Knowledge", "pf2e-ops-recall-knowledge", "checks-dcs-actions", 5, shell("Recall Knowledge", "Turn a secret knowledge check into information players can use.", body, [("Checks, DCs & Skill Actions", "pf2e-ops-checks-dcs-actions"), ("Recall Knowledge", "pf2e-ops-recall-knowledge")]))


def aid_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Two moments: prepare, then react</h2><ol><li>The helper explains how they will assist and prepares on their turn, usually spending 1 action.</li><li>When the ally attempts the chosen check, the helper uses the Aid reaction and rolls the skill or attack the GM approved.</li></ol></section>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Aid result</th><th>Effect on ally</th></tr></thead><tbody>
    <tr><th>Critical success</th><td>+2 circumstance bonus; +3 if the helper is a master, or +4 if legendary, in the check used to Aid.</td></tr>
    <tr><th>Success</th><td>+1 circumstance bonus.</td></tr>
    <tr><th>Failure</th><td>No effect.</td></tr>
    <tr><th>Critical failure</th><td>−1 circumstance penalty.</td></tr>
  </tbody></table></div>
  <aside class="ops-callout"><strong>Default DC 15</strong><span>The GM can adjust the DC for an especially easy, hard, or poorly matched method. The helper must be able to meaningfully contribute, and Aid normally applies to one specified check.</span></aside>
  <section class="ops-rule-links"><h2>Full rules & action</h2><div class="ops-grid">%s<a class="ops-exit-link" href="/action/aid-player-core"><span>Open Full Action</span><strong>Aid</strong></a></div></section>
  %s""" % (
        full_rule("aid-rules-2552", "GM Guidance: Aid"),
        related([
            ("pf2e-ops-check-results", "Resolve a check", "Apply the circumstance bonus and read the degree."),
            ("pf2e-ops-skill-actions", "Skill actions", "Find other ways to contribute."),
        ]),
    )
    return Page("Aid & Teamwork", "pf2e-ops-aid", "checks-dcs-actions", 6, shell("Aid & Teamwork", "Make help concrete, approve the method, then resolve the reaction.", body, [("Checks, DCs & Skill Actions", "pf2e-ops-checks-dcs-actions"), ("Aid & Teamwork", "pf2e-ops-aid")]))


def conditions_landing() -> Page:
    return landing_page(
        "Conditions, Damage & Recovery",
        CONDITIONS,
        "conditions-damage",
        "Find the active effect, apply it in the right order, and know when it ends.",
        "Use the condition finder for a reminder, then open the full condition when exact wording matters. Damage defenses and afflictions have their own procedures.",
        [
            ("pf2e-ops-condition-finder", "Condition finder", "Plain-language reminders with direct links to every core condition.", "LOOK UP"),
            ("pf2e-ops-persistent-damage", "Persistent damage", "Apply damage, assistance, recovery flat checks, and stacking.", "END OF TURN"),
            ("pf2e-ops-afflictions", "Afflictions", "Onset, stages, intervals, saves, duration, and removal.", "POISON & DISEASE"),
            ("pf2e-ops-damage-defenses", "Immunity, weakness & resistance", "Resolve a damage instance in the correct order.", "DAMAGE ORDER"),
            ("pf2e-ops-recovery", "Dying & recovery", "Dropping to 0 HP, recovery checks, wounded, and Hero Points.", "URGENT"),
        ],
    )


def condition_finder_page() -> Page:
    awareness = [
        ("Blinded", "blinded-player-core", "You can’t see; terrain is difficult and visual actions can fail."),
        ("Concealed", "concealed-player-core", "You can be located, but targeting normally needs a DC 5 flat check."),
        ("Dazzled", "dazzled-player-core", "Everything is concealed to you."),
        ("Deafened", "deafened-player-core", "Auditory actions and initiative using Perception are impaired."),
        ("Hidden", "hidden-player-core", "The observer knows your space; targeting normally needs DC 11."),
        ("Invisible", "invisible-player-core", "You can’t be seen; detection still depends on other senses and actions."),
        ("Observed", "observed-player-core", "The observer perceives you clearly and knows your space."),
        ("Undetected", "undetected-player-core", "The observer doesn’t know your space and must guess before targeting."),
        ("Unnoticed", "unnoticed-player-core", "The observer doesn’t know you are present."),
    ]
    control = [
        ("Confused", "confused-player-core", "You treat everyone as a target and act without normal control."),
        ("Controlled", "controlled-player-core", "Another creature dictates your actions within the effect’s limits."),
        ("Fascinated", "fascinated-player-core", "You focus on one subject and take penalties to unrelated actions."),
        ("Fleeing", "fleeing-player-core", "On your turn, you must spend actions escaping the source."),
        ("Paralyzed", "paralyzed-player-core", "You are frozen in place and severely limited in physical actions."),
        ("Quickened", "quickened-player-core", "Gain 1 extra action each turn, restricted by the effect that granted it."),
        ("Slowed", "slowed-player-core", "Regain fewer actions at the start of each turn."),
        ("Stunned", "stunned-player-core", "Lose actions, then reduce stunned by the actions lost."),
        ("Unconscious", "unconscious-player-core", "You can’t act, take major perception penalties, and are off-guard."),
    ]
    body_state = [
        ("Clumsy", "clumsy-player-core", "Status penalty to Dexterity-based checks and DCs, including AC."),
        ("Doomed", "doomed-player-core", "Reduce the dying value at which you die."),
        ("Drained", "drained-player-core", "Status penalty to Constitution-based checks and lose maximum HP."),
        ("Dying", "dying-player-core", "Make recovery checks; dying 4 normally means death."),
        ("Encumbered", "encumbered-player-core", "Clumsy 1 and a Speed penalty from carrying too much Bulk."),
        ("Enfeebled", "enfeebled-player-core", "Status penalty to Strength-based checks and DCs."),
        ("Fatigued", "fatigued-player-core", "Penalty to AC and saves and restrictions on exploration activities."),
        ("Frightened", "frightened-player-core", "Status penalty to all checks and DCs; normally decreases each turn."),
        ("Sickened", "sickened-player-core", "Status penalty to checks and DCs; retch to reduce it."),
        ("Stupefied", "stupefied-player-core", "Status penalty to mental checks and DCs; spellcasting can fail."),
        ("Wounded", "wounded-player-core", "Raises dying gained the next time you fall to 0 HP."),
    ]
    position = [
        ("Grabbed", "grabbed-player-core", "Off-guard and immobilized; manipulate actions can fail."),
        ("Immobilized", "immobilized-player-core", "You can’t use move actions unless you first escape the restraint."),
        ("Off-Guard", "off-guard-player-core", "−2 circumstance penalty to AC."),
        ("Petrified", "petrified-player-core", "Turned to stone and unable to act; usually treated as an object."),
        ("Prone", "prone-player-core", "Off-guard on the ground; Stand to recover and attacks are impaired."),
        ("Restrained", "restrained-player-core", "You are immobilized and can’t use most attack or manipulate actions."),
    ]
    objects = [("Broken", "broken-player-core", "An item can’t be used normally and imposes its listed broken penalties.")]
    attitudes = [
        ("Helpful", "helpful-player-core", "Willing to help, within reasonable limits."),
        ("Friendly", "friendly-player-core", "Has a good attitude and may accept reasonable Requests."),
        ("Indifferent", "indifferent-player-core", "Has no strong opinion; the default attitude for many NPCs."),
        ("Unfriendly", "unfriendly-player-core", "Dislikes you and resists helping."),
        ("Hostile", "hostile-player-core", "Actively seeks to harm or oppose you, though not always with violence."),
    ]
    body = (
        '<section class="ops-intro ops-callout"><strong>The reminder is not the full rule.</strong><span>Condition values usually replace lower values of the same condition rather than stacking. Open the linked condition for exact interactions and removal.</span></section>'
        + condition_table("Awareness & detection", awareness)
        + condition_table("Control & actions", control)
        + condition_table("Body & statistics", body_state)
        + condition_table("Position & restraint", position)
        + condition_table("Objects", objects)
        + condition_table("NPC attitudes", attitudes)
        + related([
            ("pf2e-ops-persistent-damage", "Persistent damage", "Resolve recurring damage at the end of a turn."),
            ("pf2e-ops-recovery", "Dying & recovery", "Use the complete 0 HP procedure."),
        ])
    )
    return Page("Condition Finder", "pf2e-ops-condition-finder", "conditions-damage", 1, shell("Condition Finder", "Core Remaster conditions grouped by the kind of ruling they change.", body, [("Conditions, Damage & Recovery", CONDITIONS), ("Condition Finder", "pf2e-ops-condition-finder")]))


def persistent_damage_page() -> Page:
    body = """
  <section class="ops-answer"><h2>At the end of the affected creature’s turn</h2><ol><li>Roll and apply each type of persistent damage.</li><li>After the damage, attempt a DC 15 flat check for each type. On a success, that persistent damage ends.</li><li>Apply any effect that changes the flat check or automatically ends the condition.</li></ol></section>
  <ul class="ops-checklist">
    <li><strong>Same damage type</strong><span>Do not add multiple instances together. Keep the higher amount; if their details differ, the GM decides which applies.</span></li>
    <li><strong>Different damage types</strong><span>Track and resolve each type separately.</span></li>
    <li><strong>Assisted recovery</strong><span>A suitable action can grant an immediate flat check and commonly reduces that check to DC 10. The assistance must fit the damage.</span></li>
    <li><strong>Damage defenses</strong><span>Apply immunity, weakness, and resistance to the damage each time it is dealt.</span></li>
  </ul>
  <aside class="ops-callout ops-callout-warn"><strong>Do not roll the recovery check before damage</strong><span>The damage happens first. Persistent damage can therefore still knock out or kill a creature on the turn when it ends.</span></aside>
  <section class="ops-rule-links"><h2>Full rules & condition</h2><div class="ops-grid">%s%s</div></section>
  %s""" % (
        full_rule("persistent-damage-rules-2306", "Persistent Damage"),
        full_entry("condition", "persistent-damage-player-core", "Persistent Damage"),
        related([("pf2e-ops-damage-defenses", "Damage defenses", "Apply immunity, weakness, and resistance."), ("pf2e-ops-recovery", "Dying & recovery", "If the damage reduces a PC to 0 HP.")]),
    )
    return Page("Persistent Damage", "pf2e-ops-persistent-damage", "conditions-damage", 2, shell("Persistent Damage", "Deal it first, then check whether each damage type ends.", body, [("Conditions, Damage & Recovery", CONDITIONS), ("Persistent Damage", "pf2e-ops-persistent-damage")]))


def afflictions_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Run an affliction as a timeline</h2><ol><li>On exposure, attempt the listed saving throw. A successful initial save normally prevents the affliction.</li><li>If it takes hold, observe any onset before applying stage 1.</li><li>At each listed interval, attempt a new save and move stages according to the degree of success.</li><li>End it when it reaches stage 0, its maximum duration expires, or another effect removes it.</li></ol></section>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Ongoing save</th><th>Stage change</th></tr></thead><tbody>
    <tr><th>Critical success</th><td>Reduce the stage by 2.</td></tr><tr><th>Success</th><td>Reduce the stage by 1.</td></tr><tr><th>Failure</th><td>Increase the stage by 1.</td></tr><tr><th>Critical failure</th><td>Increase the stage by 2.</td></tr>
  </tbody></table></div>
  <aside class="ops-callout"><strong>Never go beyond the listed stages</strong><span>If a change would move past the highest stage, remain at the highest. If it reaches stage 0, the affliction ends. Virulent afflictions modify the normal recovery pattern—open that rule when the trait appears.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("afflictions-rules-2389", "Afflictions") + full_rule("virulent-afflictions-rules-2398", "Virulent Afflictions") + full_rule("removing-afflictions-rules-2399", "Removing Afflictions"),
        related([("pf2e-ops-condition-finder", "Condition finder", "Open conditions imposed by an affliction."), ("pf2e-ops-downtime-crafting", "Downtime & services", "Find recovery, treatment, and purchased services.")]),
    )
    return Page("Afflictions", "pf2e-ops-afflictions", "conditions-damage", 3, shell("Afflictions", "Track onset, stage, interval, saves, and maximum duration separately.", body, [("Conditions, Damage & Recovery", CONDITIONS), ("Afflictions", "pf2e-ops-afflictions")]))


def damage_defenses_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Apply each damage instance in this order</h2><ol><li><strong>Immunity:</strong> ignore the applicable damage, effect, or condition.</li><li><strong>Weaknesses:</strong> add each distinct applicable weakness once.</li><li><strong>Resistances:</strong> subtract each distinct applicable resistance once, to a minimum of 0.</li><li>Reduce Hit Points by the final total.</li></ol></section>
  <aside class="ops-callout"><strong>One effect can activate several distinct defenses</strong><span>Apply each applicable weakness or resistance once. If the creature has multiple entries for the same type, use only one, usually the highest. A broad resistance that covers several damage types in one effect applies to only one of those types.</span></aside>
  <aside class="ops-callout ops-callout-warn"><strong>Critical-hit immunity is special</strong><span>An immune creature takes normal rather than doubled damage from the critical hit. Other critical-success effects still apply unless another immunity prevents them.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("immunity-weakness-and-resistance-rules-2312", "Immunity, Weakness, and Resistance") + full_rule("step-3-apply-immunities-weaknesses-and-resistances-rules-2309", "Applying Defenses to Damage"),
        related([("pf2e-ops-attacks-damage", "Attacks & damage", "Return to the full attack-resolution order."), ("pf2e-ops-persistent-damage", "Persistent damage", "Apply defenses to each recurring instance.")]),
    )
    return Page("Damage Defenses", "pf2e-ops-damage-defenses", "conditions-damage", 4, shell("Immunity, Weakness & Resistance", "Use one clear order for every instance of damage.", body, [("Conditions, Damage & Recovery", CONDITIONS), ("Damage Defenses", "pf2e-ops-damage-defenses")]))


def exploration_landing() -> Page:
    return landing_page(
        "Exploration, Travel & Environment",
        EXPLORATION,
        "exploration-travel",
        "Move from room-scale decisions to journeys without losing who is doing what.",
        "Assign each PC an exploration activity, advance time deliberately, and interrupt with scenes whenever choices or immediate danger matter.",
        [
            ("pf2e-ops-exploration-activities", "Exploration activities", "Choose what each character is doing while the party moves.", "ASSIGN ROLES"),
            ("pf2e-ops-travel-speed", "Travel speed & time", "Convert Speed into miles per hour and daily progress.", "MOVE THE PARTY"),
            ("pf2e-ops-environment", "Environmental danger", "Falling, drowning, temperature, terrain, and environmental damage.", "ADJUDICATE"),
            ("pf2e-ops-rest-preparations", "Rest & daily preparations", "Recover, reset daily resources, and prepare for the next day.", "RESET THE DAY"),
            ("pf2e-ops-cover-visibility", "Detection & visibility", "Observed, hidden, undetected, cover, and line of effect.", "NOTICE DANGER"),
        ],
    )


def exploration_activities_page() -> Page:
    rows = [
        ("Avoid Notice", "avoid-notice-player-core", "Stealth", "Exploration", "Move stealthily and normally roll Stealth for initiative."),
        ("Defend", "defend-player-core", "Shield", "Exploration", "Travel with a shield raised when an encounter begins."),
        ("Detect Magic", "detect-magic-player-core", "Magic", "Exploration", "Cast detect magic repeatedly while moving."),
        ("Follow the Expert", "follow-the-expert-player-core", "Varies", "Exploration", "Use an ally’s expertise to improve a repeated task."),
        ("Hustle", "hustle-player-core", "Movement", "Exploration", "Move at twice travel speed for a limited duration."),
        ("Investigate", "investigate-player-core", "Knowledge", "Exploration", "Recall Knowledge repeatedly for clues while traveling."),
        ("Repeat a Spell", "repeat-a-spell-player-core", "Magic", "Exploration", "Repeatedly cast the same spell or cantrip."),
        ("Scout", "scout-player-core", "Perception", "Exploration", "Grant the party +1 circumstance to initiative."),
        ("Search", "search-player-core", "Perception", "Exploration", "Seek carefully for hidden doors, hazards, and creatures."),
        ("Track", "track-player-core", "Survival", "Exploration", "Follow tracks while moving at a suitable pace."),
    ]
    body = """
  <section class="ops-intro ops-callout"><strong>Ask every player for one current activity.</strong><span>Some activities prevent full-speed travel; fatigue can prevent exploration activities entirely. When an encounter begins, apply only benefits earned by what the character was actually doing.</span></section>
  %s
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        action_table("Core exploration activities", rows),
        full_rule("exploration-activities-rules-2442", "Exploration Activities") + full_rule("running-exploration-rules-2573", "Running Exploration"),
        related([("pf2e-ops-travel-speed", "Travel speed & time", "Determine how quickly the group advances."), ("pf2e-ops-initiative", "Initiative", "Turn the current activity into encounter setup.")]),
    )
    return Page("Exploration Activities", "pf2e-ops-exploration-activities", "exploration-travel", 1, shell("Exploration Activities", "Keep party roles explicit so encounter benefits feel earned.", body, [("Exploration, Travel & Environment", EXPLORATION), ("Exploration Activities", "pf2e-ops-exploration-activities")]))


def travel_speed_page() -> Page:
    body = """
  <div class="ops-table-wrap"><table class="ops-table ops-number-table"><thead><tr><th>Speed</th><th>Feet/minute</th><th>Miles/hour</th><th>Miles/day</th></tr></thead><tbody>
    <tr><th>10 ft.</th><td>100</td><td>1</td><td>8</td></tr><tr><th>15 ft.</th><td>150</td><td>1½</td><td>12</td></tr><tr><th>20 ft.</th><td>200</td><td>2</td><td>16</td></tr><tr><th>25 ft.</th><td>250</td><td>2½</td><td>20</td></tr><tr><th>30 ft.</th><td>300</td><td>3</td><td>24</td></tr><tr><th>35 ft.</th><td>350</td><td>3½</td><td>28</td></tr><tr><th>40 ft.</th><td>400</td><td>4</td><td>32</td></tr><tr><th>50 ft.</th><td>500</td><td>5</td><td>40</td></tr><tr><th>60 ft.</th><td>600</td><td>6</td><td>48</td></tr>
  </tbody></table></div>
  <aside class="ops-callout"><strong>Use the slowest relevant traveler</strong><span>The daily column assumes 8 hours of travel. Terrain, weather, vehicles, mounts, Hustle, and exploration activities can change the result.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("travel-speed-rules-2441", "Travel Speed") + full_rule("exploration-activities-rules-2442", "Exploration Activities"),
        related([("pf2e-ops-exploration-activities", "Exploration activities", "Decide what each traveler does en route."), ("pf2e-ops-environment", "Environmental danger", "Adjust for terrain, weather, and hazards.")]),
    )
    return Page("Travel Speed & Time", "pf2e-ops-travel-speed", "exploration-travel", 2, shell("Travel Speed & Time", "Convert a movement Speed into table-ready journey progress.", body, [("Exploration, Travel & Environment", EXPLORATION), ("Travel Speed & Time", "pf2e-ops-travel-speed")]))


def environment_page() -> Page:
    body = """
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Danger</th><th>First ruling</th><th>Then check</th></tr></thead><tbody>
    <tr><th>Falling</th><td>Take bludgeoning damage equal to half the distance fallen, to the listed maximum, and land prone.</td><td>Grab an Edge can prevent or reduce the fall when a valid edge is available.</td></tr>
    <tr><th>Drowning or suffocation</th><td>Track remaining air in rounds, then begin Fortitude saves once it runs out.</td><td>Actions that consume air accelerate the countdown.</td></tr>
    <tr><th>Temperature</th><td>Determine severity and exposure interval.</td><td>Apply saves, fatigue, and damage at the rule’s cadence.</td></tr>
    <tr><th>Hazardous terrain</th><td>Deal the listed damage for entering or moving through affected squares.</td><td>Forced movement can expose a creature if the effect allows that destination.</td></tr>
    <tr><th>Difficult terrain</th><td>Charge 5 extra feet per square; greater difficult terrain charges 10 extra.</td><td>Some movement types or abilities ignore specific terrain.</td></tr>
  </tbody></table></div>
  <aside class="ops-callout ops-callout-warn"><strong>Make the cadence visible</strong><span>Tell players whether danger checks happen per round, minute, hour, or day. Most confusion comes from tracking the DC but not the interval.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("environment-rules-2768", "Environment") + full_rule("environmental-damage-rules-2769", "Environmental Damage") + full_rule("falling-rules-2352", "Falling") + full_rule("drowning-and-suffocating-rules-2439", "Drowning and Suffocating") + full_rule("temperature-rules-2820", "Temperature") + full_table("Environmental Damage") + full_table("Environmental Features"),
        related([("pf2e-ops-travel-speed", "Travel speed & time", "Move from exposure time to journey progress."), ("pf2e-ops-creatures-hazards", "Creatures & hazards", "Run discrete traps and environmental hazards.")]),
    )
    return Page("Environmental Danger", "pf2e-ops-environment", "exploration-travel", 3, shell("Environmental Danger", "Identify the danger, its interval, the defense, and its consequence.", body, [("Exploration, Travel & Environment", EXPLORATION), ("Environmental Danger", "pf2e-ops-environment")]))


def rest_page() -> Page:
    body = """
  <section class="ops-answer"><h2>After a full 8 hours of rest</h2><ul><li>Recover Hit Points equal to Constitution modifier (minimum 1) × level.</li><li>Reduce fatigued if the rest was suitable.</li><li>Do not repeat the recovery more than once in 24 hours.</li></ul></section>
  <section class="ops-answer"><h2>Daily preparations</h2><ol><li>Prepare spells, daily-use abilities, and other resources.</li><li>Invest up to 10 worn magic items unless an ability changes the limit.</li><li>Refresh Focus Points and other resources that specify daily preparations.</li><li>Confirm marching order and initial exploration activities.</li></ol></section>
  <aside class="ops-callout"><strong>Rest is not automatically safe</strong><span>Location, watches, exposure, and interruptions remain part of the fiction. Long-term rest is a separate downtime option for faster recovery over complete days.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("rest-and-daily-preparations-rules-2443", "Rest and Daily Preparations") + full_rule("long-term-rest-rules-2446", "Long-Term Rest") + full_rule("daily-preparations-rules-2575", "Daily Preparations"),
        related([("pf2e-ops-exploration-activities", "Exploration activities", "Assign roles when travel resumes."), ("pf2e-ops-equipment-treasure", "Equipment & treasure", "Check invested items and carried resources.")]),
    )
    return Page("Rest & Daily Preparations", "pf2e-ops-rest-preparations", "exploration-travel", 4, shell("Rest & Daily Preparations", "Close one adventuring day and deliberately prepare the next.", body, [("Exploration, Travel & Environment", EXPLORATION), ("Rest & Daily Preparations", "pf2e-ops-rest-preparations")]))


def downtime_landing() -> Page:
    return landing_page(
        "Downtime, Crafting & Services",
        DOWNTIME,
        "downtime-crafting",
        "Turn days between adventures into clear choices, costs, checks, and progress.",
        "Establish how many days are available, what facilities the settlement provides, and which activities deserve a check instead of automatic resolution.",
        [
            ("pf2e-ops-shopping-services", "Shopping & services", "Availability, settlement level, costs, and specialist help.", "BUY & HIRE"),
            ("pf2e-ops-crafting-repair", "Crafting & repair", "Requirements, setup time, materials, completion, and broken items.", "MAKE & FIX"),
            ("pf2e-ops-earn-income", "Earn Income", "Choose a task level, resolve the check, and record daily earnings.", "WORK"),
            ("pf2e-ops-retraining", "Retraining & long projects", "Price time honestly and preserve character choices.", "CHANGE & DEVELOP"),
            ("pf2e-ops-rest-preparations", "Rest & recovery", "Daily rest, preparations, and long-term rest.", "RECOVER"),
        ],
    )


def shopping_services_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Three questions settle most purchases</h2><ol><li><strong>Is it available?</strong> Compare item level and rarity with the settlement, seller, and character’s access.</li><li><strong>What does it cost?</strong> Common goods normally use the listed Price; scarcity or special procurement should be signaled before commitment.</li><li><strong>Does buying it need a scene?</strong> Routine common purchases can be immediate. Use checks only when access, negotiation, secrecy, or risk matters.</li></ol></section>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Need</th><th>Useful ruling</th></tr></thead><tbody>
    <tr><th>Common item at or below settlement level</th><td>Usually available for its listed Price.</td></tr>
    <tr><th>Higher-level item</th><td>Usually unavailable without a special supplier, travel, or story access.</td></tr>
    <tr><th>Uncommon or rare option</th><td>Require access or make discovery and permission part of play.</td></tr>
    <tr><th>Spellcasting service</th><td>Availability depends on rank, tradition, settlement, and the NPC’s willingness; use the service prices as guidance.</td></tr>
    <tr><th>Information or influence</th><td>Use a social or research scene when the outcome is uncertain and meaningful.</td></tr>
  </tbody></table></div>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("shopping-and-crafting-rules-2451", "Shopping and Crafting") + full_rule("services-rules-2215", "Services") + full_rule("rarity-rules-2530", "Rarity"),
        related([("pf2e-ops-equipment-treasure", "Equipment & treasure", "Judge item level, Bulk, and rewards."), ("pf2e-ops-retraining", "Retraining", "Use downtime for character changes.")]),
    )
    return Page("Shopping & Services", "pf2e-ops-shopping-services", "downtime-crafting", 1, shell("Shopping & Services", "Resolve routine trade quickly and spotlight only meaningful scarcity.", body, [("Downtime, Crafting & Services", DOWNTIME), ("Shopping & Services", "pf2e-ops-shopping-services")]))


def crafting_repair_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Craft an item</h2><ol><li>Confirm level, rarity or access, required proficiency, tools or workshop, and any special feat.</li><li>Supply raw materials worth at least half the Price.</li><li>Spend 2 setup days, or 1 day with the formula, then attempt the Crafting check.</li><li>On success, pay the remainder immediately or spend more days reducing it using Earn Income values.</li></ol></section>
  <section class="ops-answer"><h2>Repair an item</h2><p>With a repair kit, spend 10 minutes and attempt the item’s Repair DC. A success restores Hit Points based on Crafting proficiency; a critical failure damages the item. An item above its Broken Threshold stops being broken.</p></section>
  <aside class="ops-callout"><strong>Formula means speed, not permission</strong><span>A formula reduces setup time, but the crafter still needs access to an uncommon or rarer item and must meet every other requirement.</span></aside>
  %s
  <section class="ops-rule-links"><h2>Full rules & actions</h2><div class="ops-grid">%s%s%s</div></section>
  %s""" % (
        roll_table_group("Optional crafting inspiration", "Use these only when the relevant rule calls for a random downtime event or quirk.", ["Crafting Downtime Event", "Signature Crafting Quirk"]),
        full_rule("crafting-items-rules-3157", "Crafting Items"),
        full_entry("action", "craft-player-core", "Craft"),
        full_entry("action", "repair-player-core", "Repair"),
        related([("pf2e-ops-earn-income", "Earn Income", "Use the same table for daily Crafting progress."), ("pf2e-ops-shields-items", "Shields & item damage", "Apply Hardness, HP, and Broken Threshold.")]),
    )
    return Page("Crafting & Repair", "pf2e-ops-crafting-repair", "downtime-crafting", 2, shell("Crafting & Repair", "Check requirements first, then track setup, materials, progress, and completion.", body, [("Downtime, Crafting & Services", DOWNTIME), ("Crafting & Repair", "pf2e-ops-crafting-repair")]))


def earn_income_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Run the job</h2><ol><li>Choose a task level based on the available work—not automatically the character’s level.</li><li>Choose an applicable skill, normally Crafting, Lore, or Performance, and set the DC from the task level.</li><li>Resolve the initial check and read the daily amount from the Income Earned table.</li><li>Multiply by days worked, rerolling only when the task or circumstances change as the action specifies.</li></ol></section>
  <aside class="ops-callout"><strong>Settlement level limits opportunity</strong><span>A small settlement might not offer high-level tasks even to a legendary expert. A specialized employer, patron, or unusual event can justify an exception.</span></aside>
  <aside class="ops-callout ops-callout-warn"><strong>Crafting uses the crafter’s level for progress</strong><span>When reducing the remaining material cost after a successful Craft, use the crafter’s level rather than a local job’s task level.</span></aside>
  <section class="ops-rule-links"><h2>Full rules & action</h2><div class="ops-grid">%s%s</div></section>
  %s""" % (
        full_rule("earning-income-rules-2445", "Earning Income"),
        full_entry("action", "earn-income-player-core", "Earn Income"),
        related([("pf2e-ops-dcs", "DCs at a glance", "Set the task DC from its level."), ("pf2e-ops-crafting-repair", "Crafting & repair", "Translate income into material-cost reduction.")]),
    )
    return Page("Earn Income", "pf2e-ops-earn-income", "downtime-crafting", 3, shell("Earn Income", "Match the opportunity to the settlement, then record one clear daily rate.", body, [("Downtime, Crafting & Services", DOWNTIME), ("Earn Income", "pf2e-ops-earn-income")]))


def retraining_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Approve retraining when the new choice could have been legal</h2><p>A character can normally retrain feats, skill increases, spells, and some class choices over downtime. They cannot use retraining to ignore prerequisites, change inherent facts, or create a character build that was illegal at an earlier level.</p></section>
  <ul class="ops-checklist">
    <li><strong>Confirm the target</strong><span>Identify exactly what is being replaced and what the replacement will be.</span></li>
    <li><strong>Check prerequisites over time</strong><span>The character must remain legal at every level affected by the change.</span></li>
    <li><strong>Set the teacher and time</strong><span>Use the normal retraining time as a baseline; major story changes may need a special opportunity.</span></li>
    <li><strong>Update dependent choices</strong><span>If another feature depends on the old choice, retrain or resolve it at the same time.</span></li>
  </ul>
  <aside class="ops-callout"><strong>Long projects need visible progress</strong><span>State the total days, cost, required access, and what interrupts or advances the work. For uncertain projects, use a Victory Point track rather than repeated identical checks.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("retraining-rules-2447", "Retraining") + full_rule("running-downtime-rules-2604", "Running Downtime") + full_rule("longer-periods-of-downtime-rules-2613", "Longer Periods of Downtime"),
        related([("pf2e-ops-gm-subsystems", "GM subsystems", "Turn a complex long-term project into visible progress."), ("pf2e-ops-party-advancement", "Party & advancement", "Check legality, level, access, and rarity.")]),
    )
    return Page("Retraining & Long Projects", "pf2e-ops-retraining", "downtime-crafting", 4, shell("Retraining & Long Projects", "Make the outcome, legality, time, and dependencies explicit before advancing days.", body, [("Downtime, Crafting & Services", DOWNTIME), ("Retraining & Long Projects", "pf2e-ops-retraining")]))


def creatures_landing() -> Page:
    return landing_page(
        "Creatures & Hazards",
        CREATURES,
        "creatures-hazards",
        "Read only what matters now, reveal useful knowledge, and operate opposition consistently.",
        "For a creature, establish its role and signature ability before combat. For a hazard, establish how it is noticed, triggered, disabled, and reset.",
        [
            ("pf2e-ops-creature-statblocks", "Read & run a creature", "A scan order for defenses, offense, reactions, and signature abilities.", "AT THE TABLE"),
            ("pf2e-ops-creature-identification", "Identify creatures", "Choose Recall Knowledge skills and reveal actionable facts.", "REVEAL INFO"),
            ("pf2e-ops-adjust-creatures", "Elite, weak & custom adjustments", "Change difficulty without losing the creature’s role.", "TUNE OPPOSITION"),
            ("pf2e-ops-creature-benchmarks", "Creature-building benchmarks", "Pick a level and statistic; read only that row.", "LEVEL PICKER"),
            ("pf2e-ops-hazards", "Run hazards", "Detect, trigger, disable, damage, reset, and award XP.", "OPERATE"),
            ("pf2e-ops-xp-difficulty", "Encounter difficulty", "Combine creatures and hazards for the actual party size.", "BUILD"),
        ],
    )


def creature_statblocks_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Scan in the order decisions occur</h2><ol><li><strong>Identity:</strong> level, rarity, traits, perception, senses, languages, and skills.</li><li><strong>Survival:</strong> AC, saves, HP, immunities, weaknesses, resistances, and defensive reactions.</li><li><strong>Position:</strong> Speed and movement types, reach, auras, and terrain advantages.</li><li><strong>Turn:</strong> Strikes, action costs, spell DC, limited-use abilities, and likely opening routine.</li><li><strong>Triggers:</strong> reactions, free actions, death abilities, and recharge or frequency limits.</li></ol></section>
  <aside class="ops-callout"><strong>Choose a purpose, not a perfect script</strong><span>Before play, mark one signature ability, one preferred target or position, and one retreat or surrender condition. Let the battlefield change the exact turn.</span></aside>
  <ul class="ops-checklist"><li><strong>Start of turn</strong><span>Ongoing conditions, aura effects, recharge or duration checks.</span></li><li><strong>During turn</strong><span>Use its defining ability early enough that the players can experience it.</span></li><li><strong>End of turn</strong><span>Persistent damage, recovery checks, durations, and reactions for the next round.</span></li></ul>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("reading-creature-statistics-rules-3260", "Reading Creature Statistics") + full_rule("choosing-creatures-rules-2718", "Choosing Creatures"),
        related([("pf2e-ops-turns-actions", "Turns & actions", "Check action economy and multiple attack penalty."), ("pf2e-ops-condition-finder", "Condition finder", "Interpret active effects quickly.")]),
    )
    return Page("Read & Run a Creature", "pf2e-ops-creature-statblocks", "creatures-hazards", 1, shell("Read & Run a Creature", "A practical scan order that follows the creature’s decisions at the table.", body, [("Creatures & Hazards", CREATURES), ("Read & Run a Creature", "pf2e-ops-creature-statblocks")]))


def creature_identification_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Use Recall Knowledge, then reveal a decision-changing fact</h2><p>Set the DC from the creature’s level and rarity. Choose a skill that matches its nature; a specific applicable Lore can use an easier DC. On success, answer a focused question or reveal the most useful signature fact.</p></section>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Creature family</th><th>Typical skill</th></tr></thead><tbody>
    <tr><th>Construct, dragon, magical beast</th><td>Arcana</td></tr><tr><th>Animal, beast, fey, fungus, plant</th><td>Nature</td></tr><tr><th>Aberration, astral, dream, ethereal</th><td>Occultism</td></tr><tr><th>Celestial, fiend, monitor, spirit, undead</th><td>Religion</td></tr><tr><th>Humanoid</th><td>Society</td></tr><tr><th>Specific profession, region, or creature</th><td>Applicable Lore</td></tr>
  </tbody></table></div>
  <aside class="ops-callout"><strong>Good first revelations</strong><span>A dangerous reaction, strongest defense, meaningful weakness, unusual movement, regeneration shutdown, signature offensive ability, or behavior the party can exploit.</span></aside>
  <section class="ops-rule-links"><h2>Full rules & action</h2><div class="ops-grid">%s%s</div></section>
  %s""" % (
        full_rule("creature-identification-rules-2641", "Creature Identification"),
        full_entry("action", "recall-knowledge-player-core", "Recall Knowledge"),
        related([("pf2e-ops-recall-knowledge", "Recall Knowledge", "Resolve degrees and communicate information."), ("pf2e-ops-dcs", "DCs at a glance", "Apply level and rarity deliberately.")]),
    )
    return Page("Creature Identification", "pf2e-ops-creature-identification", "creatures-hazards", 2, shell("Creature Identification", "Reward knowledge checks with information that changes tactics.", body, [("Creatures & Hazards", CREATURES), ("Creature Identification", "pf2e-ops-creature-identification")]))


def adjust_creatures_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Use elite or weak for a fast one-level shift</h2><p>Apply the complete template—not only HP. The adjustment changes level, checks and DCs, AC and saves, attacks, damage, and Hit Points. At the lowest levels, follow the special guidance in the full rule.</p></section>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Need</th><th>Best tool</th></tr></thead><tbody>
    <tr><th>About one level harder</th><td>Elite adjustment.</td></tr><tr><th>About one level easier</th><td>Weak adjustment.</td></tr><tr><th>Different combat role</th><td>Choose a different creature or rebuild with the creature-building tables.</td></tr><tr><th>More bodies, same theme</th><td>Add lower-level creatures and recalculate the encounter budget.</td></tr><tr><th>Solo opponent</th><td>Use terrain, objectives, movement, and support carefully; a level shift alone does not fix action economy.</td></tr>
  </tbody></table></div>
  <aside class="ops-callout ops-callout-warn"><strong>Recalculate XP from the adjusted level</strong><span>Elite and weak change the creature’s effective level. Update both encounter threat and XP before play.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("adjusting-creatures-rules-3262", "Adjusting Creatures") + full_rule("building-creatures-rules-2874", "Building Creatures"),
        related([("pf2e-ops-creature-benchmarks", "Creature-building benchmarks", "Compare one statistic at a selected level."), ("pf2e-ops-xp-difficulty", "XP & encounter threat", "Recalculate from adjusted levels."), ("pf2e-ops-creature-statblocks", "Read & run a creature", "Preserve the creature’s tactical identity.")]),
    )
    return Page("Adjust Creatures", "pf2e-ops-adjust-creatures", "creatures-hazards", 3, shell("Elite, Weak & Custom Adjustments", "Change the challenge while preserving the creature’s tactical purpose.", body, [("Creatures & Hazards", CREATURES), ("Adjust Creatures", "pf2e-ops-adjust-creatures")]))


def creature_benchmarks_page() -> Page:
    names = [
        "Creature Building — Attribute Modifiers",
        "Creature Building — Perception",
        "Creature Building — Skills",
        "Creature Building — Armor Class",
        "Creature Building — Saving Throws",
        "Creature Building — Hit Points",
        "Creature Building — Resistances and Weaknesses",
        "Creature Building — Strike Attack Bonus",
        "Creature Building — Strike Damage",
        "Creature Building — Spell DC and Attack",
        "Creature Building — Area Damage",
    ]
    body = (
        '<section class="ops-answer"><h2>Choose one benchmark</h2><p>These are building guidelines, not automatic changes to a creature. Pick its level and the statistic you need; the values below come from the GM Core tables.</p></section>'
        + reference_picker("Benchmark at This Level", names)
        + '<aside class="ops-callout">High, moderate, and low are alternatives for that statistic. Choose a value that fits the creature’s role; do not apply every column at once.</aside>'
        + '<section class="ops-rule-links"><h2>Full rule</h2><div class="ops-grid">'
        + full_rule("building-creatures-rules-2874", "Building Creatures")
        + '</div></section>'
        + related([("pf2e-ops-adjust-creatures", "Elite & weak", "Adjust an existing creature."), ("pf2e-ops-xp-difficulty", "Encounter difficulty", "Check what this level costs.")])
    )
    return Page("Creature-Building Benchmarks", "pf2e-ops-creature-benchmarks", "creatures-hazards", 4,
        shell("Creature-Building Benchmarks", "One level and one statistic at a time in the compact panel.", body,
              [("Creatures & Hazards", CREATURES), ("Creature-Building Benchmarks", "pf2e-ops-creature-benchmarks")],
              trailing_html=f"<script>\n{embedded_reference_script()}\n</script>"))


def hazards_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Hazard operating loop</h2><ol><li><strong>Detect:</strong> compare the hazard’s Stealth DC with the searching character’s Perception, including any minimum proficiency.</li><li><strong>Trigger:</strong> when the listed trigger occurs, resolve its reaction or begin encounter mode.</li><li><strong>Respond:</strong> characters use listed Disable checks, damage valid components, counteract magical hazards, or escape the area.</li><li><strong>Reset:</strong> apply the reset entry; many hazards cannot simply trigger again immediately.</li><li><strong>Award:</strong> grant hazard XP when the party overcomes it, whether by disabling, surviving, bypassing, or another valid solution.</li></ol></section>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Type</th><th>How it runs</th><th>XP</th></tr></thead><tbody><tr><th>Simple</th><td>Acts once through its reaction, then is normally done until reset.</td><td>One-fifth the XP of a creature of its level.</td></tr><tr><th>Complex</th><td>Rolls initiative and uses a routine on its turns until disabled or destroyed.</td><td>Creature XP for its level.</td></tr></tbody></table></div>
  <aside class="ops-callout"><strong>Do not hide every clue behind one roll</strong><span>Describe visible signs and consequences. The hidden check determines recognition, not whether players are allowed to make informed choices from obvious fiction.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("hazards-rules-2846", "Hazards") + full_rule("detecting-a-hazard-rules-2847", "Detecting a Hazard") + full_rule("disabling-a-hazard-rules-2852", "Disabling a Hazard") + full_rule("hazards-in-combat-rules-2729", "Hazards in Combat"),
        related([("pf2e-ops-xp-difficulty", "XP & encounter threat", "Combine hazard and creature XP."), ("pf2e-ops-environment", "Environmental danger", "Handle broader terrain and exposure risks.")]),
    )
    return Page("Run Hazards", "pf2e-ops-hazards", "creatures-hazards", 5, shell("Run Hazards", "Detect, trigger, respond, reset, and award without losing the fiction.", body, [("Creatures & Hazards", CREATURES), ("Run Hazards", "pf2e-ops-hazards")]))


def magic_landing() -> Page:
    return landing_page(
        "Magic, Counteracting & Rituals",
        MAGIC,
        "magic-rituals",
        "Resolve a magical effect from action cost through targets, degree, duration, and ending conditions.",
        "Read the spell or ritual first. Use these pages for the shared procedures that entries assume rather than adding requirements that the effect does not state.",
        [
            ("pf2e-ops-casting-spells", "Cast & resolve a spell", "Action cost, traits, targets, defenses, degrees, duration, and sustain.", "CAST"),
            ("pf2e-ops-spell-areas", "Ranges, areas & targets", "Choose legal targets and place bursts, cones, emanations, and lines.", "PLACE EFFECT"),
            ("pf2e-ops-counteracting", "Counteracting", "Find rank, modifier, DC, degree, and maximum counteract rank.", "END EFFECT"),
            ("pf2e-ops-rituals", "Rituals", "Primary and secondary casters, checks, time, cost, and outcome.", "LONG MAGIC"),
            ("pf2e-ops-attacks-damage", "Spell attacks & basic saves", "Resolve degrees of success and damage.", "ROLL RESULTS"),
        ],
    )


def casting_spells_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Spell resolution checklist</h2><ol><li>Confirm the spell is prepared or in the repertoire and that its rank and slot or Focus Point are available.</li><li>Pay the listed action cost and satisfy components implied by the concentrate and manipulate traits.</li><li>Choose legal targets, origin, range, area, and line of effect.</li><li>Roll the spell attack or saving throw and apply the exact degree of success.</li><li>Mark duration, sustained status, ongoing conditions, and any frequency or immunity.</li></ol></section>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Entry says…</th><th>Resolve with…</th></tr></thead><tbody><tr><th>Spell attack</th><td>Caster rolls against the target’s AC; the attack trait contributes to MAP.</td></tr><tr><th>Saving throw</th><td>Target rolls the named save against spell DC.</td></tr><tr><th>Basic save</th><td>Critical success none, success half, failure full, critical failure double damage.</td></tr><tr><th>Sustained</th><td>Use Sustain once per round unless the effect says otherwise; track its maximum duration.</td></tr><tr><th>Dismissible</th><td>The caster can use Dismiss when the spell permits it.</td></tr></tbody></table></div>
  <aside class="ops-callout ops-callout-warn"><strong>Do not infer targeting permission</strong><span>A creature, object, willing target, ally, and point in space are different target types. The spell’s target line controls what can be chosen.</span></aside>
  <section class="ops-rule-links"><h2>Full rules & actions</h2><div class="ops-grid">%s%s%s</div></section>
  %s""" % (
        full_rule("casting-spells-rules-2233", "Casting Spells"),
        full_entry("action", "cast-a-spell-player-core", "Cast a Spell"),
        full_entry("action", "sustain-player-core", "Sustain"),
        related([("pf2e-ops-spell-areas", "Ranges, areas & targets", "Place the effect and check line of effect."), ("pf2e-ops-counteracting", "Counteracting", "End or suppress an opposing effect.")]),
    )
    return Page("Cast & Resolve a Spell", "pf2e-ops-casting-spells", "magic-rituals", 1, shell("Cast & Resolve a Spell", "Follow the entry from resource and actions to targets, degree, and duration.", body, [("Magic, Counteracting & Rituals", MAGIC), ("Cast & Resolve a Spell", "pf2e-ops-casting-spells")]))


def spell_areas_page() -> Page:
    body = """
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Shape</th><th>Place it from…</th><th>Table reminder</th></tr></thead><tbody>
    <tr><th>Burst</th><td>A chosen grid intersection or point in range.</td><td>Extends in every direction to its radius.</td></tr><tr><th>Cone</th><td>An edge or corner of the caster’s space.</td><td>Widens as it extends; use the template or count squares by the area rules.</td></tr><tr><th>Emanation</th><td>All sides of the subject’s space.</td><td>The subject can normally choose whether to include itself unless the effect says otherwise.</td></tr><tr><th>Line</th><td>An edge or corner of the origin space.</td><td>Extends along a straight path with its listed length and width.</td></tr><tr><th>Wall</th><td>A path in range.</td><td>Follow the spell’s limits for length, shape, and continuity.</td></tr>
  </tbody></table></div>
  <aside class="ops-callout"><strong>Range reaches the origin; area reaches beyond it</strong><span>For an area effect, the chosen origin must be in range. The area can extend beyond the spell’s range unless the spell states otherwise.</span></aside>
  <aside class="ops-callout ops-callout-warn"><strong>Line of effect still applies</strong><span>A solid barrier can block part or all of an area. Cover and line of sight are separate questions from whether the effect can physically reach the target.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("ranges-areas-and-targets-rules-2237", "Ranges, Areas, and Targets") + full_rule("line-of-effect-rules-2241", "Line of Effect") + full_rule("targets-rules-2240", "Targets") + full_rule("walls-rules-2253", "Walls"),
        related([("pf2e-ops-cover-visibility", "Cover & visibility", "Resolve sight, detection, and obstacles."), ("pf2e-ops-casting-spells", "Cast & resolve a spell", "Return to the complete spell checklist.")]),
    )
    return Page("Ranges, Areas & Targets", "pf2e-ops-spell-areas", "magic-rituals", 2, shell("Ranges, Areas & Targets", "Place the origin, apply the shape, then check legal targets and line of effect.", body, [("Magic, Counteracting & Rituals", MAGIC), ("Ranges, Areas & Targets", "pf2e-ops-spell-areas")]))


def counteracting_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Build the counteract check</h2><ol><li>Find the counteract rank of your effect—normally its spell rank or half its item level rounded up.</li><li>Roll the listed counteract modifier against the target’s DC. If none is stated, use the source’s spell DC or an appropriate level-based DC.</li><li>Read the result below to find the highest target rank you can counteract.</li></ol></section>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Result</th><th>Counteract a target of…</th></tr></thead><tbody><tr><th>Critical success</th><td>Your counteract rank + 3 or lower.</td></tr><tr><th>Success</th><td>Your counteract rank + 1 or lower.</td></tr><tr><th>Failure</th><td>Your counteract rank − 1 or lower.</td></tr><tr><th>Critical failure</th><td>Nothing.</td></tr></tbody></table></div>
  <aside class="ops-callout"><strong>A failed check can still counteract a weaker effect</strong><span>Always compare ranks after determining the degree. “Failure” is not automatically no effect.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("counteracting-rules-2250", "Counteracting") + full_table("Counteract Results by Rank"),
        related([("pf2e-ops-dcs", "DCs at a glance", "Choose a level-based DC when no source DC exists."), ("pf2e-ops-casting-spells", "Cast & resolve a spell", "Track the effect that remains or ends.")]),
    )
    return Page("Counteracting", "pf2e-ops-counteracting", "magic-rituals", 3, shell("Counteracting", "Find rank, modifier, DC, degree, and the maximum rank affected.", body, [("Magic, Counteracting & Rituals", MAGIC), ("Counteracting", "pf2e-ops-counteracting")]))


def rituals_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Before the ritual begins</h2><ol><li>Confirm the primary caster knows the ritual and meets its minimum proficiency.</li><li>Assign the required number of secondary casters and their checks.</li><li>Confirm casting time, site, targets, range, cost, and any special requirements.</li><li>Record the ritual DC and every modifier before anyone commits the cost.</li></ol></section>
  <section class="ops-answer"><h2>Resolve in order</h2><ol><li>Secondary casters attempt their checks, modifying the primary check as described by the ritual rules.</li><li>The primary caster attempts the primary check.</li><li>Apply the ritual’s exact degree of success, including its critical failure.</li><li>Consume costs and record ongoing duration or consequences as specified.</li></ol></section>
  <aside class="ops-callout ops-callout-warn"><strong>Rituals are not ordinary spellcasting</strong><span>They use skill checks rather than spell attacks or saves, do not require spell slots, and can be attempted by non-spellcasters who meet the ritual’s requirements.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("rituals-rules-2255", "Rituals") + full_rule("casting-rituals-rules-2256", "Casting Rituals") + full_rule("learning-rituals-rules-2257", "Learning Rituals"),
        related([("pf2e-ops-dcs", "DCs at a glance", "Check level-based and difficulty adjustments."), ("pf2e-ops-downtime-crafting", "Downtime & services", "Schedule long casting and obtain requirements.")]),
    )
    return Page("Rituals", "pf2e-ops-rituals", "magic-rituals", 4, shell("Rituals", "Prepare every participant and cost before resolving the primary check.", body, [("Magic, Counteracting & Rituals", MAGIC), ("Rituals", "pf2e-ops-rituals")]))


def equipment_landing() -> Page:
    return landing_page(
        "Equipment, Treasure & Rewards",
        EQUIPMENT,
        "equipment-treasure",
        "Keep carried resources, item actions, durability, and campaign rewards legible.",
        "Use item entries for exact abilities. These guides handle the shared questions: whether it is available, how it is carried or activated, how it breaks, and how much treasure the party should receive.",
        [
            ("pf2e-ops-bulk", "Bulk & encumbrance", "Convert light items, check limits, and account for creature size.", "CARRY"),
            ("pf2e-ops-using-items", "Wearing, investing & activating", "Ready an item, invest it, and pay the exact activation cost.", "USE ITEMS"),
            ("pf2e-ops-shields-items", "Shields & item damage", "Hardness, Hit Points, Broken Threshold, Repair, and destruction.", "DAMAGE OBJECTS"),
            ("pf2e-ops-treasure-rewards", "Treasure & rewards", "Budget treasure by level and adjust for party needs.", "AWARD"),
            ("pf2e-ops-shopping-services", "Shopping & services", "Settlement availability, access, rarity, and costs.", "ACQUIRE"),
        ],
    )


def bulk_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Fast calculation</h2><ol><li>Add all whole-Bulk items.</li><li>Combine light items: every 10 light items become 1 Bulk; ignore the remaining fraction.</li><li>Compare the total with the creature’s limits, after size conversions and special abilities.</li></ol></section>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Total carried Bulk</th><th>Result</th></tr></thead><tbody><tr><th>Up to 5 + Strength modifier</th><td>No encumbrance from Bulk.</td></tr><tr><th>Above 5 + Strength modifier</th><td>Encumbered: clumsy 1 and a Speed penalty.</td></tr><tr><th>Above 10 + Strength modifier</th><td>Too much to carry normally.</td></tr></tbody></table></div>
  <aside class="ops-callout"><strong>Size changes effective Bulk</strong><span>Items sized for larger or smaller creatures and creatures being carried use the size-conversion rules. Do the conversion before comparing with the carrier’s limits.</span></aside>
  <section class="ops-rule-links"><h2>Full rules & condition</h2><div class="ops-grid">%s%s</div></section>
  %s""" % (
        full_rule("bulk-rules-2153", "Bulk") + full_rule("bulk-limits-rules-2154", "Bulk Limits") + full_rule("bulk-conversions-for-different-sizes-rules-2164", "Bulk for Different Sizes"),
        full_entry("condition", "encumbered-player-core", "Encumbered"),
        related([("pf2e-ops-using-items", "Using items", "Determine whether an item is held, worn, invested, or stowed."), ("pf2e-ops-travel-speed", "Travel speed", "Apply Speed changes to journey progress.")]),
    )
    return Page("Bulk & Encumbrance", "pf2e-ops-bulk", "equipment-treasure", 1, shell("Bulk & Encumbrance", "Total whole Bulk, convert light items, then compare with two limits.", body, [("Equipment, Treasure & Rewards", EQUIPMENT), ("Bulk & Encumbrance", "pf2e-ops-bulk")]))


def using_items_page() -> Page:
    body = """
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Item state</th><th>What it permits</th></tr></thead><tbody>
    <tr><th>Held</th><td>In a hand and ready for held-item actions; changing grip or drawing usually needs Interact.</td></tr><tr><th>Worn</th><td>On the body and readily accessible, but not automatically invested or active.</td></tr><tr><th>Stowed</th><td>Inside a container and normally requires retrieval before use.</td></tr><tr><th>Invested</th><td>Activated during daily preparations and counts toward the normal limit of 10 invested items.</td></tr>
  </tbody></table></div>
  <section class="ops-answer"><h2>Activation checklist</h2><ol><li>Confirm the item is held, worn, affixed, or otherwise ready as its Usage requires.</li><li>Check that it is invested if it has the invested trait.</li><li>Pay the listed actions and satisfy command, envision, Interact, or other components.</li><li>Apply frequency, charges, activation traits, target, and duration exactly as written.</li></ol></section>
  <aside class="ops-callout ops-callout-warn"><strong>Owning is not readying</strong><span>An item in a backpack is not automatically available for an activation. Track hand use and retrieval only when timing matters.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("activating-items-rules-3139", "Activating Items") + full_rule("investing-magic-items-rules-3138", "Investing Magic Items") + full_rule("carrying-items-rules-2148", "Carrying Items"),
        related([("pf2e-ops-bulk", "Bulk & encumbrance", "Account for carried and worn equipment."), ("pf2e-ops-casting-spells", "Cast & resolve a spell", "Resolve spells produced by an item.")]),
    )
    return Page("Wearing, Investing & Activating", "pf2e-ops-using-items", "equipment-treasure", 2, shell("Wearing, Investing & Activating", "Separate where the item is from whether it is ready, invested, and activated.", body, [("Equipment, Treasure & Rewards", EQUIPMENT), ("Using Items", "pf2e-ops-using-items")]))


def shields_items_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Shield Block</h2><ol><li>Raise the shield before the attack; Shield Block needs the reaction and its trigger.</li><li>Subtract the shield’s Hardness from the triggering physical damage.</li><li>Apply the remaining damage to both the character and the shield.</li><li>At or below Broken Threshold, the shield is broken and cannot be used normally. At 0 HP, it is destroyed.</li></ol></section>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Object statistic</th><th>Meaning</th></tr></thead><tbody><tr><th>Hardness</th><td>Reduces applicable damage before HP are lost.</td></tr><tr><th>Hit Points</th><td>Remaining structural integrity.</td></tr><tr><th>Broken Threshold</th><td>At or below this HP, the object is broken and takes its listed limitations.</td></tr><tr><th>0 HP</th><td>Destroyed rather than merely broken.</td></tr></tbody></table></div>
  <aside class="ops-callout"><strong>Repair restores HP; it does not raise maximum HP</strong><span>Once restored above its Broken Threshold, an item stops being broken. A destroyed item generally cannot be repaired by the normal Repair action.</span></aside>
  <section class="ops-rule-links"><h2>Full rules & actions</h2><div class="ops-grid">%s%s%s</div></section>
  %s""" % (
        full_rule("shields-rules-2180", "Shields") + full_rule("item-damage-rules-2160", "Item Damage") + full_table("Material Hardness, HP, and BT"),
        full_entry("action", "raise-a-shield-player-core", "Raise a Shield"),
        full_entry("action", "repair-player-core", "Repair"),
        related([("pf2e-ops-crafting-repair", "Crafting & repair", "Run the complete Repair and Craft procedures."), ("pf2e-ops-damage-defenses", "Damage defenses", "Apply immunity, weakness, and resistance.")]),
    )
    return Page("Shields & Item Damage", "pf2e-ops-shields-items", "equipment-treasure", 3, shell("Shields & Item Damage", "Apply Hardness once, damage shield and bearer, then check the threshold.", body, [("Equipment, Treasure & Rewards", EQUIPMENT), ("Shields & Item Damage", "pf2e-ops-shields-items")]))


def treasure_rewards_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Budget across a level, not one room at a time</h2><ol><li>Use Treasure by Level for the party’s expected permanent items, consumables, and currency.</li><li>Place rewards where they make sense in the adventure: carried, guarded, granted, discovered, or earned.</li><li>Track what the party actually receives and adjust later rewards if they miss, sell, or cannot use major items.</li><li>Keep story access and rare options separate from raw gp value.</li></ol></section>
  %s
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Reward type</th><th>Use it for…</th></tr></thead><tbody><tr><th>Permanent item</th><td>Meaningful capability that remains part of the party’s toolkit.</td></tr><tr><th>Consumable</th><td>Flexible short-term power and experimentation without permanent build pressure.</td></tr><tr><th>Currency</th><td>Player choice, services, formulas, crafting materials, and routine purchases.</td></tr><tr><th>Access, favors, or property</th><td>Narrative rewards whose value is not captured only by a price.</td></tr><tr><th>Accomplishment XP</th><td>Progress for goals and discoveries independent of defeating creatures.</td></tr></tbody></table></div>
  <aside class="ops-callout"><strong>Adjust for party size</strong><span>The published treasure table assumes four PCs. Add or remove treasure proportionally and favor useful choices over exact coin-by-coin correction.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        reference_picker("Party Treasure at This Level", ["Party Treasure by Level"]),
        full_rule("treasure-by-level-rules-2656", "Treasure by Level") + full_rule("adjusting-treasure-rules-2764", "Adjusting Treasure") + full_rule("treasure-for-new-characters-rules-2662", "Treasure for New Characters") + full_rule("rewards-rules-2647", "Rewards"),
        related([("pf2e-ops-random-tables", "Random treasure tables", "Roll gems, art objects, and other sourced random results."), ("pf2e-ops-shopping-services", "Shopping & services", "Turn currency and access into purchases."), ("pf2e-ops-advancement", "Advancement", "Award encounter and accomplishment XP.")]),
    )
    return Page("Treasure & Rewards", "pf2e-ops-treasure-rewards", "equipment-treasure", 4, shell("Treasure & Rewards", "Track the level-wide budget while placing rewards where the fiction supports them.", body, [("Equipment, Treasure & Rewards", EQUIPMENT), ("Treasure & Rewards", "pf2e-ops-treasure-rewards")], trailing_html=f"<script>\n{embedded_reference_script()}\n</script>"))


def party_landing() -> Page:
    return landing_page(
        "Party, Advancement & Hero Points",
        PARTY,
        "party-advancement",
        "Keep party-wide resources, progression, and option access consistent between sessions.",
        "Use one party record for XP and campaign decisions, while HP, conditions, Hero Points, and character resources stay attached to the individual who owns them.",
        [
            ("pf2e-ops-party-checklist", "Session & party checklist", "Start, pause, and end a session without losing important state.", "TRACK STATE"),
            ("pf2e-ops-hero-points", "Hero Points", "Starting points, awards, rerolls, avoiding death, and the cap.", "REWARD HEROISM"),
            ("pf2e-ops-advancement", "XP & advancement", "Encounter XP, accomplishment XP, 1,000-XP levels, and milestones.", "LEVEL UP"),
            ("pf2e-ops-rarity-access", "Rarity & access", "Decide what is normally available and what needs permission.", "CURATE OPTIONS"),
            ("pf2e-ops-xp-difficulty", "Encounter threat", "Build and adjust encounters for the current party.", "PLAN CHALLENGE"),
        ],
    )


def party_checklist_page() -> Page:
    body = """
  <details class="ops-disclosure ops-action-disclosure"><summary><span>Start of session</span><span>3 checks</span></summary><ul class="ops-checklist"><li><strong>Party state</strong><span>Level, XP or milestone, current location, date, and active objectives.</span></li><li><strong>Character state</strong><span>HP, conditions, Hero Points, Focus Points, invested items, spell preparation, and daily abilities.</span></li><li><strong>Table state</strong><span>Marching order, exploration activities, visibility, and any effects continuing from last session.</span></li></ul></details>
  <details class="ops-disclosure ops-action-disclosure"><summary><span>Before a risky scene</span><span>3 checks</span></summary><ul class="ops-checklist"><li><strong>Position</strong><span>Who is where, what is visible, and what is in hand?</span></li><li><strong>Intent</strong><span>What is each character doing immediately before initiative?</span></li><li><strong>Persistent resources</strong><span>Mark durations, charges, ammunition, consumables, and once-per-day abilities only when relevant.</span></li></ul></details>
  <details class="ops-disclosure ops-action-disclosure"><summary><span>End of session</span><span>3 checks</span></summary><ul class="ops-checklist"><li><strong>Save state</strong><span>HP, conditions, Hero Points, resources, inventory changes, and initiative if stopping mid-encounter.</span></li><li><strong>Award</strong><span>XP, treasure, accomplishments, reputation, and downtime earned.</span></li><li><strong>Next start</strong><span>Record the immediate situation and the decisions waiting for the players.</span></li></ul></details>
  %s""" % related([("pf2e-ops-rest-preparations", "Rest & daily preparations", "Reset only the resources the rules refresh."), ("pf2e-ops-hero-points", "Hero Points", "Award and spend the party’s visible heroic resource.")])
    return Page("Session & Party Checklist", "pf2e-ops-party-checklist", "party-advancement", 1, shell("Session & Party Checklist", "Preserve the state that matters without turning the game into accounting.", body, [("Party, Advancement & Hero Points", PARTY), ("Session & Party Checklist", "pf2e-ops-party-checklist")]))


def hero_points_page() -> Page:
    body = """
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Moment</th><th>Hero Point rule</th></tr></thead><tbody><tr><th>Session begins</th><td>Each PC starts with 1 Hero Point.</td></tr><tr><th>Heroic play</th><td>The GM awards points during play, roughly one per hour after the first across the group as a pacing guideline.</td></tr><tr><th>Maximum</th><td>A character can hold at most 3 Hero Points.</td></tr><tr><th>Reroll</th><td>Spend 1 and use the second result; this is a fortune effect.</td></tr><tr><th>Avoid death</th><td>Spend all remaining Hero Points to lose dying and stabilize, following the full rule.</td></tr><tr><th>Session ends</th><td>Unspent Hero Points normally do not carry into the next session.</td></tr></tbody></table></div>
  <aside class="ops-callout"><strong>Reward decisions, courage, and contribution</strong><span>Hero Points work best when awards are visible and spread across different kinds of play—not only damage or lucky rolls.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("hero-points-rules-2333", "Hero Points") + full_rule("hero-points-rules-2654", "Awarding Hero Points"),
        related([("pf2e-ops-recovery", "Dying & recovery", "Use Hero Points at the moment death would occur."), ("pf2e-ops-party-checklist", "Session checklist", "Record starting and ending resources.")]),
    )
    return Page("Hero Points", "pf2e-ops-hero-points", "party-advancement", 2, shell("Hero Points", "Keep the resource visible, reward varied heroism, and remember the cap.", body, [("Party, Advancement & Hero Points", PARTY), ("Hero Points", "pf2e-ops-hero-points")]))


def advancement_page() -> Page:
    body = """
  <section class="ops-answer"><h2>XP advancement</h2><ol><li>Award the same encounter XP to each participating PC; party size changes encounter budget, not the earned award.</li><li>Add minor, moderate, or major accomplishment XP for meaningful goals and discoveries.</li><li>At 1,000 XP, increase level by 1 and subtract 1,000 XP, carrying any excess forward.</li><li>Apply every class, ancestry, skill, feat, spell, and statistic change for the new level.</li></ol></section>
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Advancement style</th><th>Use when…</th></tr></thead><tbody><tr><th>XP</th><td>The group enjoys visible progress and rewards for varied encounters and accomplishments.</td></tr><tr><th>Milestone</th><td>The campaign’s structure has clear story thresholds and the group prefers less accounting.</td></tr></tbody></table></div>
  <aside class="ops-callout ops-callout-warn"><strong>Do not mix the promises accidentally</strong><span>If using milestones, tell the group what kinds of progress matter. If using XP, award accomplishment XP so noncombat success advances the campaign too.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("experience-points-rules-2648", "Experience Points") + full_rule("leveling-up-rules-2065", "Leveling Up") + full_rule("advancement-table-rules-2104", "Advancement Table") + full_rule("accomplishments-rules-2651", "Accomplishments"),
        related([("pf2e-ops-xp-difficulty", "XP & encounter threat", "Calculate encounter XP and party adjustment."), ("pf2e-ops-treasure-rewards", "Treasure & rewards", "Keep treasure progression aligned with level.")]),
    )
    return Page("XP & Advancement", "pf2e-ops-advancement", "party-advancement", 3, shell("XP & Advancement", "Award progress consistently, then apply every part of the new level.", body, [("Party, Advancement & Hero Points", PARTY), ("XP & Advancement", "pf2e-ops-advancement")]))


def rarity_access_page() -> Page:
    body = """
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Rarity</th><th>Default campaign meaning</th></tr></thead><tbody><tr><th>Common</th><td>Generally available when level, price, and other prerequisites are met.</td></tr><tr><th>Uncommon</th><td>Needs access, GM permission, or discovery in the story.</td></tr><tr><th>Rare</th><td>Exceptional and campaign-shaping; include deliberately.</td></tr><tr><th>Unique</th><td>One specific option or entity; available only through its story circumstances.</td></tr></tbody></table></div>
  <section class="ops-answer"><h2>Access answers “may this character take it?”</h2><p>An access entry makes an uncommon or rare option available to a character who meets it; it does not remove level, feat, price, proficiency, or other prerequisites.</p></section>
  <aside class="ops-callout"><strong>Rarity is a campaign control, not a power rating</strong><span>Use it to protect setting assumptions, story discoveries, cultural access, and complex options. Discuss broad availability changes before characters depend on them.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("rarity-rules-2530", "Rarity") + full_rule("rarity-and-power-rules-2532", "Rarity and Power"),
        related([("pf2e-ops-shopping-services", "Shopping & services", "Apply rarity to settlements and sellers."), ("pf2e-ops-retraining", "Retraining", "Confirm legal replacement choices and access.")]),
    )
    return Page("Rarity & Access", "pf2e-ops-rarity-access", "party-advancement", 4, shell("Rarity & Access", "Use rarity to curate the campaign and access to grant specific permission.", body, [("Party, Advancement & Hero Points", PARTY), ("Rarity & Access", "pf2e-ops-rarity-access")]))


def subsystems_landing() -> Page:
    return landing_page(
        "GM Subsystems & Campaign Tools",
        SUBSYSTEMS,
        "gm-subsystems",
        "Choose a structure that makes progress visible without replacing ordinary roleplay.",
        "Use a subsystem when several decisions and checks contribute toward one uncertain outcome. For a single obstacle, one check or a short encounter is usually clearer.",
        [
            ("pf2e-ops-choose-subsystem", "Choose a subsystem", "Match the dramatic question to the lightest useful structure.", "START HERE"),
            ("pf2e-ops-victory-points", "Victory Points", "Create thresholds, opportunities, setbacks, and a visible finish line.", "GENERAL ENGINE"),
            ("pf2e-ops-chases", "Chases", "Run moving obstacles, simultaneous pressure, and pursuit progress.", "PURSUIT"),
            ("pf2e-ops-research-infiltration", "Research & infiltration", "Use discovery thresholds or preparation and Awareness.", "COMPLEX OBJECTIVE"),
            ("pf2e-ops-reputation", "Reputation", "Track a group’s evolving relationship over the campaign.", "RELATIONSHIPS"),
            ("pf2e-ops-hexploration-vehicles", "Hexploration & vehicles", "Structure journeys, exploration days, pilots, and moving encounters.", "TRAVEL"),
            ("pf2e-ops-random-tables", "Random tables", "Open only genuine dice-result tables in Encounter+'s native roller.", "ROLL & GENERATE"),
        ],
    )


def choose_subsystem_page() -> Page:
    body = """
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>The dramatic question is…</th><th>Use…</th></tr></thead><tbody><tr><th>Can the group accumulate enough progress before consequences?</th><td>Victory Points.</td></tr><tr><th>Can one side catch or escape the other through changing obstacles?</th><td>Chase.</td></tr><tr><th>Can the party uncover enough information from several sources?</th><td>Research.</td></tr><tr><th>Can the party prepare for and penetrate a protected location?</th><td>Infiltration.</td></tr><tr><th>How does a faction’s long-term attitude change?</th><td>Reputation.</td></tr><tr><th>What does the party discover across a region day by day?</th><td>Hexploration.</td></tr><tr><th>How do moving vessels act and collide in encounter mode?</th><td>Vehicles.</td></tr></tbody></table></div>
  <aside class="ops-callout"><strong>Use the lightest structure that exposes meaningful choices</strong><span>If there is one obvious approach and one immediate consequence, use a normal check. A subsystem earns its table time when players can choose different approaches, spend resources, recover from setbacks, and see progress.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("deciding-to-use-a-subsystem-rules-3027", "Deciding to Use a Subsystem") + full_rule("chapter-4-subsystems-rules-3026", "Subsystems"),
        related([("pf2e-ops-victory-points", "Victory Points", "Use the general progress engine."), ("pf2e-ops-dcs", "DCs at a glance", "Set fair DCs for subsystem opportunities.")]),
    )
    return Page("Choose a Subsystem", "pf2e-ops-choose-subsystem", "gm-subsystems", 1, shell("Choose a Subsystem", "Match one dramatic question to the simplest structure that makes progress visible.", body, [("GM Subsystems & Campaign Tools", SUBSYSTEMS), ("Choose a Subsystem", "pf2e-ops-choose-subsystem")]))


def victory_points_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Build the track before rolling</h2><ol><li>Name what the points represent and whether they accumulate or diminish.</li><li>Set thresholds and state what changes at each one.</li><li>Create several approaches with relevant skills, DCs, time, costs, and consequences.</li><li>Decide how critical successes, failures, and critical failures change progress.</li><li>End when a threshold, deadline, or consequence resolves the dramatic question.</li></ol></section>
  <aside class="ops-callout"><strong>Reveal enough of the track to guide choices</strong><span>Players need not know every number, but they should understand whether they are making progress, what pressure is rising, and which approaches remain viable.</span></aside>
  <aside class="ops-callout ops-callout-warn"><strong>Do not let one best skill become mandatory</strong><span>Offer different approaches or let a good idea change the skill, DC, cost, or consequence. The subsystem should widen decisions, not narrow them to repeated rolls.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("victory-points-rules-3028", "Victory Points") + full_rule("victory-point-subsystem-structures-rules-3030", "Victory Point Structures") + full_rule("running-your-subsystem-rules-3038", "Running Your Subsystem"),
        related([("pf2e-ops-chases", "Chases", "Use a specialized moving VP structure."), ("pf2e-ops-research-infiltration", "Research & infiltration", "Use specialized discovery or preparation tracks.")]),
    )
    return Page("Victory Points", "pf2e-ops-victory-points", "gm-subsystems", 2, shell("Victory Points", "Define progress, thresholds, approaches, and consequences before the first check.", body, [("GM Subsystems & Campaign Tools", SUBSYSTEMS), ("Victory Points", "pf2e-ops-victory-points")]))


def chases_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Prepare a chain of moving obstacles</h2><ol><li>State who is pursuing whom and the starting lead.</li><li>Create obstacles with more than one plausible skill or approach.</li><li>At each obstacle, let participants choose actions and resolve Chase Point progress.</li><li>Advance the opposition, pressure, or deadline according to the chase structure.</li><li>End with escape, capture, a final encounter, or a changed situation—not an endless loop.</li></ol></section>
  <aside class="ops-callout"><strong>Keep everyone in the same moving scene</strong><span>Failure should usually cost time, position, resources, or exposure rather than removing a character from play. Describe the obstacle changing as each participant acts.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("chases-rules-3049", "Chases") + full_rule("building-a-chase-rules-3051", "Building a Chase") + full_rule("running-a-chase-rules-3056", "Running a Chase") + full_rule("ending-chases-rules-3054", "Ending Chases"),
        related([("pf2e-ops-victory-points", "Victory Points", "Return to the general subsystem structure."), ("pf2e-ops-skill-actions", "Skill actions", "Find the action that matches an obstacle approach.")]),
    )
    return Page("Chases", "pf2e-ops-chases", "gm-subsystems", 3, shell("Chases", "Make position and pressure move through varied obstacles until the situation changes.", body, [("GM Subsystems & Campaign Tools", SUBSYSTEMS), ("Chases", "pf2e-ops-chases")]))


def research_infiltration_page() -> Page:
    body = """
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Subsystem</th><th>Prepare</th><th>Track</th><th>Reveal or resolve</th></tr></thead><tbody><tr><th>Research</th><td>Libraries or sources, skills, DCs, and research checks.</td><td>Research Points and time.</td><td>Information at thresholds; consequences for delay or poor methods.</td></tr><tr><th>Infiltration</th><td>Objective, obstacles, opportunities, preparation activities, and complications.</td><td>Infiltration Points, Edge Points, and Awareness Points as the rules assign them.</td><td>Pass obstacles, spend preparation advantages, and trigger consequences when awareness rises.</td></tr></tbody></table></div>
  <aside class="ops-callout"><strong>Information should change the next decision</strong><span>Research thresholds work best when each revelation opens an approach, rules out a false path, exposes a cost, or reframes the objective.</span></aside>
  <aside class="ops-callout"><strong>Preparation should pay off visibly</strong><span>In infiltration, connect every Edge Point or advantage to a concrete earlier choice so the payoff feels earned rather than abstract.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("research-rules-3045", "Research") + full_rule("building-a-research-challenge-rules-3046", "Building a Research Challenge") + full_rule("infiltration-rules-3059", "Infiltration") + full_rule("building-an-infiltration-rules-3060", "Building an Infiltration"),
        related([("pf2e-ops-secret-checks", "Secret checks", "Preserve uncertainty without hiding choices."), ("pf2e-ops-victory-points", "Victory Points", "Tune thresholds and progress.")]),
    )
    return Page("Research & Infiltration", "pf2e-ops-research-infiltration", "gm-subsystems", 4, shell("Research & Infiltration", "Use thresholds for discovery and preparation for penetrating protected objectives.", body, [("GM Subsystems & Campaign Tools", SUBSYSTEMS), ("Research & Infiltration", "pf2e-ops-research-infiltration")]))


def reputation_page() -> Page:
    body = """
  <section class="ops-answer"><h2>Track the relationship with a group, not every individual</h2><ol><li>Name the faction and its current reputation level.</li><li>Award or remove Reputation Points for actions the faction notices and cares about.</li><li>Apply the benefits, complications, or access tied to each threshold.</li><li>Use individual NPC attitudes separately when a person differs from the faction.</li></ol></section>
  <aside class="ops-callout"><strong>Make consequences legible</strong><span>Tell players when an action affected reputation and why, unless secrecy is itself important. Reputation is useful when it changes access, support, prices, information, or opposition.</span></aside>
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        full_rule("reputation-rules-3072", "Reputation") + full_rule("reputations-rules-3075", "Reputations") + full_rule("running-reputation-rules-3083", "Running Reputation"),
        related([("pf2e-ops-condition-finder", "NPC attitudes", "Distinguish individual attitude from faction reputation."), ("pf2e-ops-victory-points", "Victory Points", "Structure a shorter influence objective.")]),
    )
    return Page("Reputation", "pf2e-ops-reputation", "gm-subsystems", 5, shell("Reputation", "Let noticed choices change a faction’s long-term access, support, and opposition.", body, [("GM Subsystems & Campaign Tools", SUBSYSTEMS), ("Reputation", "pf2e-ops-reputation")]))


def hexploration_vehicles_page() -> Page:
    body = """
  <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>Mode</th><th>Track first</th><th>Switch modes when…</th></tr></thead><tbody><tr><th>Hexploration</th><td>Day, hex, travel Speed, hexploration activities, terrain, weather, supplies, and discoveries.</td><td>A location, encounter, hazard, or meaningful local choice needs scene-level play.</td></tr><tr><th>Vehicle travel</th><td>Pilot, vehicle Speed, heading, passengers, cargo, HP, Broken Threshold, and collision risks.</td><td>Precise position, attacks, boarding, collisions, or loss of control makes initiative matter.</td></tr></tbody></table></div>
  <section class="ops-answer"><h2>Journey rhythm</h2><ol><li>Choose route and daily activities.</li><li>Advance time and position.</li><li>Apply terrain, weather, supply, and navigation consequences.</li><li>Reveal discoveries and switch to a focused scene.</li><li>Return to the journey only after immediate choices are resolved.</li></ol></section>
  %s
  <section class="ops-rule-links"><h2>Full rules</h2><div class="ops-grid">%s</div></section>
  %s""" % (
        roll_table_group("Travel generators", "Roll only when uncertainty improves the journey; authored terrain and encounters still take priority.", ["Random Encounter Type", "Random Terrain Type", "Random Terrain Feature"]),
        full_rule("hexploration-rules-3103", "Hexploration") + full_rule("running-hexploration-rules-3110", "Running Hexploration") + full_rule("vehicles-rules-3116", "Vehicles") + full_rule("vehicles-in-combat-rules-3132", "Vehicles in Combat"),
        related([("pf2e-ops-travel-speed", "Travel speed", "Convert movement into hourly and daily progress."), ("pf2e-ops-environment", "Environmental danger", "Apply terrain, weather, and exposure.")]),
    )
    return Page("Hexploration & Vehicles", "pf2e-ops-hexploration-vehicles", "gm-subsystems", 6, shell("Hexploration & Vehicles", "Track day-scale movement, then zoom into scenes when precise choices matter.", body, [("GM Subsystems & Campaign Tools", SUBSYSTEMS), ("Hexploration & Vehicles", "pf2e-ops-hexploration-vehicles")]))


def random_tables_page() -> Page:
    body = """
  <section class="ops-intro ops-callout"><strong>These are genuine random-result tables.</strong><span>Select a table to open Encounter+'s native roller and roll history. Static references such as DCs, encounter budgets, and treasure by level remain look-up tables elsewhere in the Operations Center.</span></section>
  %s%s%s%s%s
  %s""" % (
        roll_table_group("Travel & exploration", "Generate an encounter category, terrain type, or terrain feature when the journey needs an uncertain prompt.", ["Random Encounter Type", "Random Terrain Type", "Random Terrain Feature"]),
        roll_table_group("Treasure", "Generate a specific gem or art object from the value tier already chosen for the reward.", ["Lesser Semiprecious Stones", "Moderate Semiprecious Stones", "Greater Semiprecious Stones", "Lesser Precious Stones", "Moderate Precious Stones", "Greater Precious Stones", "Minor Art Object", "Lesser Art Object", "Moderate Art Object", "Greater Art Object", "Major Art Object"]),
        roll_table_group("Downtime & inspiration", "Resolve published random crafting events, quirks, and war-situation prompts.", ["Crafting Downtime Event", "Signature Crafting Quirk", "Deviant Ability Quirk", "War Situation — Strategic", "War Situation — Operational", "War Situation — Tactical"]),
        roll_table_group("Abilities, spells & creatures", "Use the die result required by the named ability, spell, or creature effect.", ["Eerie Proclamation Failure", "Portents of the Haruspex Damage", "Protean Warpwave Effect", "Creative Splash Color", "Chthonian Wrath Realm", "Rainbow Fumarole Color"]),
        roll_table_group("Magic items", "Resolve the random effect or selection specified by the item.", ["Madcap Top Effect", "Lucky Draw Bandolier Ammunition", "Pistol of Wonder Effect", "Octopus Potion Added Effect"]),
        related([("pf2e-ops-hexploration-vehicles", "Hexploration & vehicles", "Use travel generators in the context of a journey."), ("pf2e-ops-treasure-rewards", "Treasure & rewards", "Choose a level-appropriate reward before rolling its details."), ("pf2e-ops-crafting-repair", "Crafting & repair", "Use crafting events and quirks with the complete procedure.")]),
    )
    return Page("Random Tables", "pf2e-ops-random-tables", "gm-subsystems", 7, shell("Random Tables", "Open a sourced PF2E table in Encounter+'s native roller.", body, [("GM Subsystems & Campaign Tools", SUBSYSTEMS), ("Random Tables", "pf2e-ops-random-tables")]))


def index_page(indexed_pages: list[Page]) -> Page:
    entries = sorted((page for page in indexed_pages if page.slug != HOME), key=lambda page: page.name.casefold())
    grouped: dict[str, list[Page]] = {}
    for page in entries:
        grouped.setdefault(page.name[0].upper(), []).append(page)
    sections = []
    for letter, letter_pages in grouped.items():
        links = "".join(
            f'<a href="/page/{page.slug}"><strong>{html.escape(page.name)}</strong><span>Open quick guide</span></a>'
            for page in letter_pages
        )
        sections.append(f'<details class="ops-disclosure ops-index-disclosure"><summary><span>{letter}</span><span>{len(letter_pages)} guides</span></summary><div class="ops-link-list">{links}</div></details>')
    body = '<section class="ops-intro ops-callout"><strong>Can’t guess the category?</strong><span>Use this alphabetical list. Every result stays inside the Operations Center, and every page includes a Home breadcrumb.</span></section>' + "".join(sections)
    return Page("A–Z Quick-Guide Index", INDEX, "pf2e-operations-center", 1, shell("A–Z Quick-Guide Index", "Every Operations Center guide in one predictable alphabetical list.", body, [("A–Z Index", INDEX)]))


def pages() -> list[Page]:
    primary = [
        home_page(),
        encounter_landing(),
        encounter_sequence(),
        initiative_page(),
        actions_page(),
        attacks_page(),
        movement_page(),
        cover_page(),
        recovery_page(),
        ending_page(),
        xp_page(),
        compact_xp_planner_page(),
        checks_landing(),
        dcs_page(),
        check_results_page(),
        skill_actions_page(),
        secret_checks_page(),
        recall_knowledge_page(),
        aid_page(),
        conditions_landing(),
        condition_finder_page(),
        persistent_damage_page(),
        afflictions_page(),
        damage_defenses_page(),
        exploration_landing(),
        exploration_activities_page(),
        travel_speed_page(),
        environment_page(),
        rest_page(),
        downtime_landing(),
        shopping_services_page(),
        crafting_repair_page(),
        earn_income_page(),
        retraining_page(),
        creatures_landing(),
        creature_statblocks_page(),
        creature_identification_page(),
        adjust_creatures_page(),
        creature_benchmarks_page(),
        hazards_page(),
        magic_landing(),
        casting_spells_page(),
        spell_areas_page(),
        counteracting_page(),
        rituals_page(),
        equipment_landing(),
        bulk_page(),
        using_items_page(),
        shields_items_page(),
        treasure_rewards_page(),
        party_landing(),
        party_checklist_page(),
        hero_points_page(),
        advancement_page(),
        rarity_access_page(),
        subsystems_landing(),
        choose_subsystem_page(),
        victory_points_page(),
        chases_page(),
        research_infiltration_page(),
        reputation_page(),
        hexploration_vehicles_page(),
        random_tables_page(),
    ]
    return [*primary, index_page(primary)]


def groups() -> list[dict[str, object]]:
    root = "pf2e-operations-center"
    return [
        {"id": stable_id("group", root), "name": "PF2E Operations Center", "slug": root, "parentId": "", "rank": 0},
        {"id": stable_id("group", "encounters-combat"), "name": "Encounters & Combat", "slug": "encounters-combat", "parentId": stable_id("group", root), "rank": 0},
        {"id": stable_id("group", "checks-dcs-actions"), "name": "Checks, DCs & Skill Actions", "slug": "checks-dcs-actions", "parentId": stable_id("group", root), "rank": 1},
        {"id": stable_id("group", "conditions-damage"), "name": "Conditions, Damage & Recovery", "slug": "conditions-damage", "parentId": stable_id("group", root), "rank": 2},
        {"id": stable_id("group", "exploration-travel"), "name": "Exploration, Travel & Environment", "slug": "exploration-travel", "parentId": stable_id("group", root), "rank": 3},
        {"id": stable_id("group", "downtime-crafting"), "name": "Downtime, Crafting & Services", "slug": "downtime-crafting", "parentId": stable_id("group", root), "rank": 4},
        {"id": stable_id("group", "creatures-hazards"), "name": "Creatures & Hazards", "slug": "creatures-hazards", "parentId": stable_id("group", root), "rank": 5},
        {"id": stable_id("group", "magic-rituals"), "name": "Magic, Counteracting & Rituals", "slug": "magic-rituals", "parentId": stable_id("group", root), "rank": 6},
        {"id": stable_id("group", "equipment-treasure"), "name": "Equipment, Treasure & Rewards", "slug": "equipment-treasure", "parentId": stable_id("group", root), "rank": 7},
        {"id": stable_id("group", "party-advancement"), "name": "Party, Advancement & Hero Points", "slug": "party-advancement", "parentId": stable_id("group", root), "rank": 8},
        {"id": stable_id("group", "gm-subsystems"), "name": "GM Subsystems & Campaign Tools", "slug": "gm-subsystems", "parentId": stable_id("group", root), "rank": 9},
    ]


@lru_cache(maxsize=1)
def available_entry_slugs() -> dict[str, set[str]]:
    """Index bundled compendium targets used by Operations Center exit links."""
    route_files = {"rule": "rules.json", "action": "actions.json", "condition": "conditions.json", "table": "tables.json"}
    available = {route: set() for route in route_files}
    for route, filename in route_files.items():
        for path in sorted((REPO / "compendium").glob(f"**/{filename}")):
            records = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(records, list):
                continue
            available[route].update(str(record.get("slug") or "") for record in records)
        available[route].discard("")
    return available


def validate(page_records: list[dict[str, object]], group_records: list[dict[str, object]]) -> None:
    errors: list[str] = []
    page_slugs = {str(page["slug"]) for page in page_records}
    group_ids = {str(group["id"]) for group in group_records}
    ids = [str(record["id"]) for record in page_records + group_records]
    if len(ids) != len(set(ids)):
        errors.append("duplicate page/group id")
    if len(page_slugs) != len(page_records):
        errors.append("duplicate page slug")

    internal_pattern = re.compile(r'href="/page/([^"]+)"')
    entry_pattern = re.compile(r'href="/(rule|action|condition|table)/([^"]+)"')
    roll_table_pattern = re.compile(r'href="/table-roll/([^"]+)"')
    entry_slugs = available_entry_slugs()
    for page in page_records:
        slug = str(page["slug"])
        content = str(page["content"])
        if str(page["parentId"]) not in group_ids:
            errors.append(f"{slug}: unknown group")
        for target in internal_pattern.findall(content):
            if target not in page_slugs:
                errors.append(f"{slug}: unresolved internal page {target}")
        for route, target in entry_pattern.findall(content):
            if target not in entry_slugs[route]:
                errors.append(f"{slug}: unresolved {route} entry {target}")
        for target in roll_table_pattern.findall(content):
            if target not in entry_slugs["table"]:
                errors.append(f"{slug}: unresolved roll table {target}")
        if slug != HOME and f'href="/page/{HOME}"' not in content:
            errors.append(f"{slug}: missing Home breadcrumb")
        for match in re.finditer(r'<a class="ops-card"[^>]+href="([^"]+)"', content):
            if not match.group(1).startswith("/page/"):
                errors.append(f"{slug}: quick card exits Operations Center")
        if "http://" in content or "https://" in content:
            errors.append(f"{slug}: external URL in page content")

    if errors:
        raise ValueError("Operations Center validation failed:\n- " + "\n- ".join(errors))


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    page_records = [page.record() for page in pages()]
    group_records = groups()
    validate(page_records, group_records)
    write_json(REPO / "pages.json", page_records)
    write_json(REPO / "groups.json", group_records)
    print(json.dumps({"pages": len(page_records), "groups": len(group_records), "home": HOME}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
