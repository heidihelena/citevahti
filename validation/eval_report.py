#!/usr/bin/env python3
"""Assemble CiteVahti's published evaluation page from the numbers it actually has.

This is the *publishing* surface for ADR-0009's three evaluation objects. It does
NOT invent a whole-system accuracy figure — there isn't one yet, and this page says
so plainly. It gathers what is measured (the automatic lexical-layer eval, from the
frozen baseline) and describes the mechanisms whose numbers accrue from real use
(the per-model complementary-catch scoreboard) and later from the pooled corpus
(AtlasVahti). Honest by construction: the gaps are named, not hidden.

    python validation/eval_report.py            # print the page
    python validation/eval_report.py --write     # write docs/EVALUATION.md

Deterministic (no timestamps) so `tests/test_eval_report.py` can golden-check that
the committed page matches the frozen baseline — the page can't drift silently.
stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os

_HERE = os.path.dirname(__file__)
_REPO = os.path.abspath(os.path.join(_HERE, ".."))
_BASELINE = os.path.join(_HERE, "claimcheck", "lexicon_baseline.json")
_DOC = os.path.join(_REPO, "docs", "EVALUATION.md")


def _fmt(x) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def build(baseline: dict) -> str:
    b = baseline
    lines: list[str] = []
    add = lines.append

    add("# CiteVahti — evaluation results")
    add("")
    add("> _Generated from `validation/claimcheck/lexicon_baseline.json` by "
        "`validation/eval_report.py`. Do not edit by hand — re-run the generator._")
    add("")
    add("CiteVahti holds itself to the evidence standards it promotes. Per "
        "[ADR-0009](adr/0009-evaluation-and-model-quality.md), evaluation has **three "
        "objects**, measured differently. This page reports each one honestly — including "
        "what is **not** yet measured.")
    add("")

    add("## 1. Claim-lexicon eval (automatic, measured now)")
    add("")
    add("The deterministic lexical detector, scored against a curated, author-labelled "
        f"set of **{b['n']}** `(claim, passage)` cases "
        "(`validation/claimcheck/lexicon_cases.jsonl`). Precision is floored in CI; recall "
        "is published, not chased (the inverted-U — over-flagging is worse than "
        "under-flagging). Advisory flags (population, certainty) are surfaced for the "
        "human/AI layer to adjudicate, never as verdicts.")
    add("")
    add("| Detector | Precision | Recall |")
    add("|---|---|---|")
    add(f"| Support | {_fmt(b['support_precision'])} | {_fmt(b['support_recall'])} |")
    add(f"| Contradiction | {_fmt(b['contradiction_precision'])} | {_fmt(b['contradiction_recall'])} |")
    add(f"| Population-mismatch flag | {_fmt(b.get('population_precision'))} | {_fmt(b.get('population_recall'))} |")
    add(f"| Certainty/overclaim flag | {_fmt(b.get('certainty_precision'))} | {_fmt(b.get('certainty_recall'))} |")
    add("")
    add(f"Negated-contradiction leaks (a negated finding served as support): "
        f"**{b['negation_leaks']}** — a hard-zero invariant. The remaining recall gaps are "
        "genuine synonymy/paraphrase, which is the AI-model layer's job, not the lexicon's "
        "(the eval names those holes rather than hiding them). These are the "
        "**lexical-layer** numbers — not the whole system's accuracy.")
    add("")

    add("## 2. Model rating (continuous, accrues from use)")
    add("")
    add("Each identifiable AI second-rater model earns a **complementary-catch** score: a "
        "*validated divergence* — the model disagreed with the human and the human's "
        "adjudicated final matched the AI (the model was right where the human's first take "
        "was not). Agreement scores nothing (the cheese-hole principle: a model that only "
        "agrees adds no defence). This is computed **read-only** from a project's own "
        "rating ledger by `agreement_report`; there is no fixed number to publish — it is a "
        "per-project, per-model tally that grows with real use.")
    add("")

    add("## 3. Pooled Atlas scoreboard + divergence maps (roadmap)")
    add("")
    add("Across contributors, object 2 aggregates into a model scoreboard and divergence "
        "maps, and confidence tiers scale with the count of independent assessors "
        "([ADR-0008](adr/0008-evidence-confidence-tiers.md): ≥5 → review, ~8+ → guideline). "
        "Emergent and real-world; built when AtlasVahti ships.")
    add("")

    add("## What is NOT yet measured")
    add("")
    add("- **No whole-system accuracy benchmark.** The numbers above are the *lexical "
        "layer's*. Human inter-rater reliability, human↔AI agreement, and end-to-end "
        "system accuracy have not been measured and published — see "
        "[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md). The pre-registered human ground-truth "
        "protocol exists (`validation/claimcheck/`) but its rater columns are unfilled; the "
        "model-rating data (object 2) accrues only as pilots use the tool.")
    add("- Treat CiteVahti as a disciplined **workflow**, not a validated **oracle**. Every "
        "number here is a *layer's* number, never a certification of a citation.")
    add("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write docs/EVALUATION.md")
    args = ap.parse_args()
    with open(_BASELINE) as f:
        baseline = json.load(f)
    page = build(baseline)
    if args.write:
        with open(_DOC, "w") as f:
            f.write(page)
        print(f"wrote {_DOC}")
    else:
        print(page, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
