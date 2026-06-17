#!/usr/bin/env python3
"""ILLUSTRATIVE ONLY — fill the ledger with SYNTHETIC human + LLM labels so you can
see score_ledger.py's output. These are NOT real adjudications. Do not cite any
number from the demo file. It exists to exercise the metrics and to show where an
LLM advisor adds information the lexicon cannot (paraphrase/synonymy)."""
from __future__ import annotations
import json, os

here = os.path.dirname(__file__)
recs = [json.loads(l) for l in open(os.path.join(here, "ledger.jsonl")) if l.strip()]

for r in recs:
    g = r["provisional_relation"]
    r["adjudicated"] = {"relation": g}
    # rater2 = gold; rater1 disagrees once (a hard paraphrase) -> kappa < 1
    r1 = g
    if r["record_id"] == "cc-003":  # "lowered the death rate" paraphrase, easy to miss
        r1 = "neither"
    r["rater1"] = {"relation": r1, "notes": ""}
    r["rater2"] = {"relation": g, "notes": ""}
    # LLM advisor: gets the paraphrase RIGHT (where lexical coverage failed),
    # mirrors gold elsewhere -> shows independent value, not mere echo.
    r["llm_advisor"] = {"relation": g, "rationale": "ILLUSTRATIVE synthetic label"}

out = os.path.join(here, "ledger.demo.jsonl")
with open(out, "w") as f:
    for r in recs:
        f.write(json.dumps(r) + "\n")
print("wrote ILLUSTRATIVE filled ledger ->", out)
