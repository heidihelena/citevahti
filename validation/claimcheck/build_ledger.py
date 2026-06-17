#!/usr/bin/env python3
"""Seed a claim-check VALIDATION ledger from a curated (claim, citekey, passage)
set, using CiteVahti's OWN lexical functions (coverage_score + polarity_conflict).

The unit is a (claim, passage) pair — the thing claim-check actually decides —
NOT an auto-mined abstract. Each record carries the deterministic decision and
leaves the HUMAN columns blank. The human-adjudicated `relation` is the ground
truth; the support- and contradiction-detectors are measured AGAINST it, never
against each other (see score_ledger.py).

    python validation/claimcheck/build_ledger.py        # defaults to this repo
    python validation/claimcheck/build_ledger.py --repo /path/to/citevahti

stdlib only; imports the repo's text.py directly so the seed reflects the real,
patched decision logic.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os

SUPPORT_THRESHOLD = 0.5  # mirror ClaimCheckService._SUPPORT_THRESHOLD

# default to THIS repo (validation/claimcheck/ -> repo root), so it runs in place
_REPO_DEFAULT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def load_text_module(repo: str):
    path = os.path.join(repo, "src", "citevahti", "retrieval", "text.py")
    spec = importlib.util.spec_from_file_location("cv_text", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def decide(t, claim: str, passage: str) -> dict:
    """Replicate ClaimCheckService's per-passage decision, deterministically."""
    cov = t.coverage_score(claim, passage)
    conflict = t.polarity_conflict(claim, passage)
    if cov < SUPPORT_THRESHOLD:
        status = "no_support_found"
    elif conflict:
        status = "contradiction_candidate"
    else:
        status = "supported_candidate"
    return {"version": "claimcheck-polarity-1", "coverage": round(cov, 3),
            "polarity_conflict": conflict, "status": status}


# Curated seed: (claim, citekey, passage, provisional_relation). provisional_*
# is the SEED AUTHOR's hypothesis to orient raters, NOT ground truth. relation in
# {supports, contradicts, neither}.
SEED = [
    ("Drug X reduced mortality in patients", "smith2020",
     "Drug X reduced mortality significantly in the treatment arm.", "supports"),
    ("Drug X reduced mortality in patients", "jones2019",
     "Drug X did not reduce mortality compared with placebo.", "contradicts"),
    ("Drug X reduced mortality in patients", "lee2021",
     "Drug X lowered the death rate substantially.", "supports"),          # paraphrase
    ("Drug X reduced mortality in patients", "kim2018",
     "The study examined dosing schedules for Drug X.", "neither"),
    ("Smoking increases lung cancer risk", "who2018",
     "Smoking was strongly associated with increased lung cancer incidence.", "supports"),
    ("Smoking increases lung cancer risk", "novak2020",
     "No association was found between smoking and lung cancer in this cohort.", "contradicts"),
    ("Vitamin D supplementation prevents fractures", "garcia2022",
     "Vitamin D did not prevent fractures in community-dwelling adults.", "contradicts"),
    ("Vitamin D supplementation prevents fractures", "park2021",
     "Vitamin D supplementation reduced fracture incidence.", "supports"),
    ("Screening reduces colorectal cancer mortality", "rct2019",
     "Screening significantly reduced colorectal cancer mortality.", "supports"),
    ("Screening reduces colorectal cancer mortality", "bg2020",
     "Colorectal cancer is a leading cause of cancer death worldwide.", "neither"),  # background
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=_REPO_DEFAULT, help="path to citevahti checkout")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "ledger.jsonl"))
    args = ap.parse_args()

    t = load_text_module(args.repo)
    recs = []
    for i, (claim, citekey, passage, prov_rel) in enumerate(SEED):
        cc = decide(t, claim, passage)
        rec = {
            "record_id": f"cc-{i+1:03d}",
            "claim_text": claim,
            "citekey": citekey,
            "passage_quote": passage,
            "claimcheck": cc,
            "llm_advisor": None,   # {relation, rationale} — ADVISORY, fill later
            "rater1": None,        # human #1 blinded: {relation, notes}
            "rater2": None,        # human #2 blinded: {relation, notes}
            "adjudicated": None,   # consensus = GROUND TRUTH: {relation}
            "provisional_relation": prov_rel,  # seed author's hypothesis, NOT truth
        }
        rec["record_hash"] = hashlib.sha256(
            json.dumps({"claim": claim, "citekey": citekey, "passage": passage,
                        "claimcheck": cc}, sort_keys=True).encode()).hexdigest()[:16]
        recs.append(rec)

    with open(args.out, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    flagged = sum(1 for r in recs if r["claimcheck"]["status"] == "supported_candidate")
    contra = sum(1 for r in recs if r["claimcheck"]["status"] == "contradiction_candidate")
    print(f"wrote {len(recs)} records -> {args.out}")
    print(f"claim-check: {flagged} supported_candidate, {contra} contradiction_candidate "
          f"(human columns blank — awaiting adjudication)")


if __name__ == "__main__":
    main()
