#!/usr/bin/env python3
"""Render Foundry inline directives as readable, system-neutral text.

Foundry directives may contain nested square brackets (most notably damage
types inside ``@Damage``). Regular expressions stop at the first closing
bracket and leave fragments such as ``|options:area-damage]`` in published
text. This module uses a small balanced-delimiter scanner instead.
"""

from __future__ import annotations

import ast
import math
import operator
import re


DIRECTIVE = re.compile(r"@([A-Za-z]+)\[")


def title_from_code(value: str) -> str:
    text = value.rsplit(".", 1)[-1].replace("-", " ").replace("_", " ")
    return " ".join(word.capitalize() for word in text.split())


def _balanced_end(text: str, start: int, opening: str, closing: str) -> int | None:
    depth = 1
    index = start
    while index < len(text):
        if text[index] == opening:
            depth += 1
        elif text[index] == closing:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _split_top_level(value: str, separator: str = "|") -> list[str]:
    result: list[str] = []
    start = 0
    square = round_ = curly = 0
    for index, character in enumerate(value):
        if character == "[":
            square += 1
        elif character == "]":
            square = max(0, square - 1)
        elif character == "(":
            round_ += 1
        elif character == ")":
            round_ = max(0, round_ - 1)
        elif character == "{":
            curly += 1
        elif character == "}":
            curly = max(0, curly - 1)
        elif character == separator and square == round_ == curly == 0:
            result.append(value[start:index])
            start = index + 1
    result.append(value[start:])
    return result


def _humanize_variables(value: str) -> str:
    replacements = {
        "@actor.system.attributes.classOrSpellDC.value": "class or spell DC",
        "@actor.system.skills.intimidation.rank": "Intimidation proficiency rank",
        "@actor.system.skills.medicine.rank": "Medicine proficiency rank",
        "@actor.abilities.str.mod": "Strength modifier",
        "@item.rank": "spell rank",
        "@item.level": "item level",
        "@item.badge.value": "condition value",
        "@actor.level": "level",
        "@actor.system.details.level.value": "level",
    }
    for source, label in sorted(replacements.items(), key=lambda item: -len(item[0])):
        value = value.replace(source, label)

    def fallback(match: re.Match[str]) -> str:
        parts = match.group(0).split(".")
        return title_from_code(parts[-1]).casefold() or "value"

    return re.sub(r"@(actor|item|target)(?:\.[A-Za-z0-9_-]+)+", fallback, value)


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS = {
    "abs": abs,
    "ceil": math.ceil,
    "eq": lambda left, right: left == right,
    "floor": math.floor,
    "gt": lambda left, right: left > right,
    "gte": lambda left, right: left >= right,
    "lt": lambda left, right: left < right,
    "lte": lambda left, right: left <= right,
    "max": max,
    "min": min,
    "ternary": lambda condition, when_true, when_false: when_true if condition else when_false,
}


def _evaluate_node(node: ast.AST) -> int | float | bool:
    if isinstance(node, ast.Expression):
        return _evaluate_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, bool)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        return _BINARY_OPERATORS[type(node.op)](_evaluate_node(node.left), _evaluate_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_evaluate_node(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS:
        return _FUNCTIONS[node.func.id](*[_evaluate_node(argument) for argument in node.args])
    raise ValueError("unsupported formula")


def _evaluate_formula(value: str, variables: dict[str, int | float]) -> str:
    expression = value.strip()
    for source, number in sorted(variables.items(), key=lambda item: -len(item[0])):
        expression = expression.replace(source, str(number))
    if "@" in expression:
        return value
    try:
        result = _evaluate_node(ast.parse(expression, mode="eval"))
    except (SyntaxError, TypeError, ValueError, ZeroDivisionError):
        return value
    if isinstance(result, bool):
        return str(result)
    if isinstance(result, float) and result.is_integer():
        return str(int(result))
    return str(result)


def _resolve_known_functions(value: str, variables: dict[str, int | float]) -> str:
    functions = re.compile(r"\b(?:abs|ceil|eq|floor|gt|gte|lt|lte|max|min|ternary)\(")
    for _ in range(20):
        changed = False
        matches = list(functions.finditer(value))
        for match in reversed(matches):
            closing = _balanced_end(value, match.end(), "(", ")")
            if closing is None:
                continue
            expression = value[match.start():closing + 1]
            evaluated = _evaluate_formula(expression, variables)
            if evaluated != expression:
                value = value[:match.start()] + evaluated + value[closing + 1:]
                changed = True
        if not changed:
            break
    return value


def _evaluate_damage_term(value: str, variables: dict[str, int | float]) -> str:
    if "@actor.system.skills.intimidation.rank" in value and "ternary(" in value:
        return "1d4"
    if "@actor.system.skills.medicine.rank" in value and "2d8" in value:
        return "2d8"
    if "@actor.abilities.str.mod" in value and "floor((10+" in value.replace(" ", ""):
        return "Strength modifier + 1d6 per 10 feet thrown"
    value = _resolve_known_functions(value, variables)
    if value.startswith("(") and value.endswith(")"):
        closing = _balanced_end(value, 1, "(", ")")
        if closing == len(value) - 1:
            value = value[1:-1].strip()
    die = re.search(r"d\d+", value, flags=re.I)
    if die:
        coefficient = value[:die.start()].strip()
        if coefficient:
            evaluated = _evaluate_formula(coefficient, variables)
            if evaluated != coefficient or not re.search(r"[A-Za-z@]", coefficient):
                return evaluated + value[die.start():]
        return value
    return _evaluate_formula(value, variables)


def _render_damage(
    body: str,
    label: str,
    variables: dict[str, int | float] | None = None,
) -> str:
    if label:
        return label
    formula = _split_top_level(body)[0].strip()
    variables = variables or {}
    terms: list[str] = []
    for term in _split_top_level(formula, ","):
        annotations = re.findall(r"\[([^\[\]]+)\]", term)
        base = re.sub(r"\[([^\[\]]+)\]", "", term).strip()
        base = _evaluate_damage_term(base, variables)
        flavor = " ".join(
            annotation.replace(",", " ").replace("-", " ")
            for annotation in annotations
        )
        terms.append(" ".join(part for part in (base, flavor) if part))
    formula = ", ".join(terms)
    formula = _humanize_variables(formula)
    formula = re.sub(r"(?<=\w)\s*\+\s*0\b", "", formula)
    formula = re.sub(r"\s+", " ", formula).strip()
    if formula.startswith("(") and formula.endswith(")"):
        formula = formula[1:-1].strip()
    return formula


def _render_template(body: str, label: str) -> str:
    if label:
        return label
    parts = [part.strip() for part in _split_top_level(body) if part.strip()]
    shape = title_from_code(parts[0]).casefold() if parts else "area"
    if parts and ":" in parts[0]:
        key, value = parts[0].split(":", 1)
        if key.casefold() in {"shape", "type"}:
            shape = title_from_code(value).casefold()
    properties = {
        key.casefold(): _humanize_variables(value.strip())
        for part in parts[1:]
        if ":" in part
        for key, value in [part.split(":", 1)]
    }
    distance = properties.get("distance") or properties.get("length")
    width = properties.get("width")
    if distance and re.fullmatch(r"\d+(?:\.\d+)?", distance):
        distance = f"{distance}-foot"
    pieces = [value for value in (distance, shape) if value]
    rendered = " ".join(pieces) or "area"
    if width:
        rendered += f" ({width}-foot wide)" if width.isdigit() else f" ({width} wide)"
    return rendered


def _render_check(body: str, label: str) -> str:
    if label:
        return label
    parts = [part.strip() for part in _split_top_level(body) if part.strip()]
    statistic = title_from_code(parts[0]) if parts else "Check"
    dc = next((part.split(":", 1)[1] for part in parts[1:] if part.startswith("dc:")), "")
    basic = "basic " if any(part.casefold() == "basic" for part in parts[1:]) else ""
    if "classOrSpellDC.value" in dc and "max(37" in dc.replace(" ", ""):
        return f"{basic}{statistic} DC 37 or your class/spell DC, whichever is higher".strip()
    if dc.startswith("resolve(") and dc.endswith(")"):
        dc = dc[len("resolve("):-1]
    if basic and dc:
        return f"DC {_humanize_variables(dc)} basic {statistic}"
    return f"{basic}{statistic}{' DC ' + _humanize_variables(dc) if dc else ''}".strip()


def _render_directive(
    name: str,
    body: str,
    label: str,
    variables: dict[str, int | float] | None = None,
) -> str:
    folded = name.casefold()
    if folded == "damage":
        return _render_damage(body, label, variables)
    if folded == "template":
        return _render_template(body, label)
    if folded == "check":
        return _render_check(body, label)
    if folded == "uuid":
        return label or title_from_code(body)
    if folded == "embed":
        return label
    if folded == "localize":
        return label or title_from_code(body)
    return label or body


def _replace_foundry_rolls(
    value: str, variables: dict[str, int | float] | None = None
) -> str:
    """Render ``[[/r ...]]`` and ``[[/act ...]]`` with nested damage tags."""
    output: list[str] = []
    cursor = 0
    while True:
        start = value.find("[[/", cursor)
        if start < 0:
            output.append(value[cursor:])
            break
        output.append(value[cursor:start])
        depth = 2
        index = start + 3
        end: int | None = None
        while index < len(value):
            if value[index] == "[":
                depth += 1
            elif value[index] == "]":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
            index += 1
        if end is None:
            output.append(value[start:])
            break

        body = value[start + 2:end - 2].strip()
        label = ""
        cursor = end
        if cursor < len(value) and value[cursor] == "{":
            label_end = _balanced_end(value, cursor + 1, "{", "}")
            if label_end is not None:
                label = value[cursor + 1:label_end]
                cursor = label_end + 1

        action = re.match(r"/act\s+([a-z0-9-]+)", body, flags=re.I)
        if action:
            rendered = label or title_from_code(action.group(1))
            dc = re.search(r"(?:^|\s)dc=([^\s]+)", body, flags=re.I)
            if dc and not re.search(rf"\bDC\s+{re.escape(dc.group(1))}\b", rendered, re.I):
                rendered += f" (DC {dc.group(1)})" if label else f" DC {dc.group(1)}"
            output.append(rendered)
            continue
        if label:
            output.append(label)
            continue
        roll = re.match(r"/(?:r|gmr)\s+(.+)", body, flags=re.I | re.S)
        if roll:
            formula = roll.group(1).split("#", 1)[0].strip()
            output.append(_render_damage(formula, "", variables))
            continue
        output.append("")
    return "".join(output)


def replace_foundry_directives(
    value: str, variables: dict[str, int | float] | None = None
) -> str:
    """Replace balanced ``@Name[...]`` directives without losing nested data."""
    output: list[str] = []
    cursor = 0
    while True:
        match = DIRECTIVE.search(value, cursor)
        if match is None:
            output.append(value[cursor:])
            break
        output.append(value[cursor:match.start()])
        bracket_end = _balanced_end(value, match.end(), "[", "]")
        if bracket_end is None:
            output.append(value[match.start():])
            break
        body = value[match.end():bracket_end]
        end = bracket_end + 1
        label = ""
        if end < len(value) and value[end] == "{":
            label_end = _balanced_end(value, end + 1, "{", "}")
            if label_end is not None:
                label = value[end + 1:label_end]
                end = label_end + 1
        output.append(_render_directive(match.group(1), body, label, variables))
        cursor = end
    return _humanize_variables(_replace_foundry_rolls("".join(output), variables))


CONVERSION_ARTIFACT = re.compile(
    r"(?:\|options:[^\s\]]+\]|\bcurrent value\b|\ba area\b|\b\d+-foot type:(?:burst|cone|line|emanation)\b|\b(?:persistent[ ,])?(?:acid|bleed|bludgeoning|cold|electricity|fire|force|healing|mental|piercing|poison|slashing|sonic|spirit|untyped|vitality|void)\](?!\()|\b(?:floor|ceil|ternary|gte|max|resolve)\()",
    flags=re.I,
)


def has_conversion_artifact(value: str) -> bool:
    return bool(CONVERSION_ARTIFACT.search(value))
