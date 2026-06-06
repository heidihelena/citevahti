"""Deterministic regex rules for the step-4 extraction fields.

Each rule returns ``(value, match_start)`` for the first match, or None. Rules
are intentionally conservative: when nothing matches, the field is reported
``unverifiable`` rather than guessed.
"""

from __future__ import annotations

import re
from typing import Callable, Optional

I = re.IGNORECASE

# (compiled pattern, value-builder). value-builder receives the match and
# returns the normalized field value.
_Rule = tuple[re.Pattern, Callable[[re.Match], str]]


def _g1(m: re.Match) -> str:
    return re.sub(r"\s+", " ", m.group(1)).strip(" .,;:")


def _const(value: str) -> Callable[[re.Match], str]:
    return lambda m: value


def _whole(m: re.Match) -> str:
    return re.sub(r"\s+", " ", m.group(0)).strip(" .,;:")


_RULES: dict[str, list[_Rule]] = {
    "design": [
        (re.compile(r"randomi[sz]ed[ ,]+(?:double-?blind[ ,]+)?(?:placebo-?controlled[ ,]+)?"
                    r"(?:controlled[ ,]+)?trial", I), _const("randomized controlled trial")),
        (re.compile(r"randomi[sz]ed controlled trial", I), _const("randomized controlled trial")),
        (re.compile(r"\bRCT\b"), _const("randomized controlled trial")),
        (re.compile(r"(?:prospective |retrospective )?cohort study", I), _const("cohort study")),
        (re.compile(r"case[- ]control study", I), _const("case-control study")),
        (re.compile(r"cross[- ]sectional (?:study|survey)", I), _const("cross-sectional study")),
        (re.compile(r"systematic review", I), _const("systematic review")),
        (re.compile(r"meta[- ]analysis", I), _const("meta-analysis")),
    ],
    "sample_size": [
        (re.compile(r"\bn\s*=\s*(\d{1,7})", I), _g1),
        (re.compile(r"(\d{1,7})\s+(?:patients|participants|subjects|individuals|"
                    r"adults|women|men|children)\b", I), _g1),
        (re.compile(r"enrol?led\s+(\d{1,7})", I), _g1),
        (re.compile(r"randomi[sz]ed\s+(\d{1,7})", I), _g1),
        (re.compile(r"total of\s+(\d{1,7})", I), _g1),
    ],
    "population": [
        (re.compile(r"(?:patients|participants|adults|children|individuals|women|men)\s+with\s+"
                    r"([A-Za-z0-9 ,'-]+?)(?:[.;]| who | were | aged )", I), _g1),
    ],
    "intervention": [
        (re.compile(r"(?:treated with|received|assigned to|randomi[sz]ed to(?: receive)?|"
                    r"intervention(?: group)? (?:was|received))\s+"
                    r"([A-Za-z0-9 ()%./-]+?)(?:[.,;]| versus | compared | or )", I), _g1),
    ],
    "comparator": [
        (re.compile(r"(?:compared (?:with|to)|versus|vs\.?|control group received|relative to)\s+"
                    r"([A-Za-z0-9 ()%./-]+?)(?:[.,;]| in | among | for )", I), _g1),
        (re.compile(r"\b(placebo)\b", I), _g1),
    ],
    "outcome": [
        (re.compile(r"primary (?:outcome|endpoint)(?: measure)?\s+(?:was|were|:)\s+"
                    r"([A-Za-z0-9 ()%./-]+?)(?:[.,;]| at | over | during )", I), _g1),
        (re.compile(r"primary (?:outcome|endpoint)\s+of\s+([A-Za-z0-9 ()%./-]+?)(?:[.,;])", I), _g1),
    ],
    "effect_estimate": [
        (re.compile(r"(?:hazard ratio|risk ratio|odds ratio|rate ratio|mean difference|"
                    r"relative risk)[^.;]*?\d[\d.]*[^.;]*?\(95%[^)]*\)", I), _whole),
        (re.compile(r"\b(?:HR|RR|OR|MD)\s*[=:]?\s*\d[\d.]*(?:\s*\(95%[^)]*\))?", I), _whole),
    ],
    "follow_up": [
        (re.compile(r"(?:median |mean )?follow[- ]up (?:(?:of|was|period of)\s+)?"
                    r"(\d+[\d.]*\s*(?:years?|months?|weeks?|days?))", I), _g1),
        (re.compile(r"followed (?:up )?for\s+"
                    r"(\d+[\d.]*\s*(?:years?|months?|weeks?|days?))", I), _g1),
    ],
    "setting": [
        (re.compile(r"\b(multicent(?:er|re)|single[- ]cent(?:er|re)|primary care|tertiary care|"
                    r"outpatient|inpatient|intensive care unit|ICU|community|"
                    r"emergency department)\b", I), _g1),
    ],
}


def extract_field(field: str, text: str) -> Optional[tuple[str, int]]:
    """Return (value, match_start) for the first rule that matches, else None."""
    for pattern, build in _RULES.get(field, []):
        m = pattern.search(text)
        if m:
            return build(m), m.start()
    return None
