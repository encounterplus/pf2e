#!/usr/bin/env python3
"""Derive safe Encounter+ area templates from unambiguous PF2E area text."""

from __future__ import annotations

import re
from typing import Any


SHAPE_PATTERNS = (
    (re.compile(r"\bburst\b", re.I), "sphere"),
    (re.compile(r"\bemanation\b", re.I), "sphere"),
    (re.compile(r"\bcone\b", re.I), "cone"),
    (re.compile(r"\bline\b", re.I), "line"),
    (re.compile(r"\bcube\b", re.I), "cube"),
    (re.compile(r"\bcylinder\b", re.I), "cylinder"),
    (re.compile(r"\bsquare\b", re.I), "square"),
)
FOOT_MEASURE = re.compile(r"\b(\d+(?:\.\d+)?)\s*-?\s*foot\b", re.I)


def parse_spell_area(area: str) -> tuple[str, int | float] | None:
    """Return one supported shape/size only when the source text is unequivocal.

    PF2E bursts and emanations both use Encounter+'s radius geometry. Text with
    multiple shapes, multiple dimensions, non-foot units, or no supported shape
    intentionally returns ``None`` so the spell behaves like an area-less spell.
    """

    shapes = [shape for pattern, shape in SHAPE_PATTERNS for _ in pattern.finditer(area)]
    measures = [float(value) for value in FOOT_MEASURE.findall(area)]
    unique_measures = set(measures)
    if len(shapes) != 1 or len(unique_measures) != 1:
        return None

    size = unique_measures.pop()
    return shapes[0], int(size) if size.is_integer() else size


def configure_spell_area_template(entity: dict[str, Any]) -> bool:
    """Apply or remove derived template fields without altering official area text."""

    data = entity.get("data")
    if not isinstance(data, dict):
        return False

    parsed = parse_spell_area(str(data.get("area") or "").strip())
    if parsed is None:
        data.pop("areaEffectShape", None)
        data.pop("areaEffectSize", None)
        return False

    data["areaEffectShape"], data["areaEffectSize"] = parsed
    return True
