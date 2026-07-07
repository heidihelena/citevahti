#!/usr/bin/env python3
"""Automatic evaluation of the claim-check LEXICAL layer — a run you (the AI) can
execute on demand and in CI, with no human-rater dependency.

The lexical detector (`src/citevahti/retrieval/text.py`) is ONE slice of a
defence-in-depth stack (ADR-0009): a transparent, auditable floor with *known*
holes — paraphrase/synonymy it can't see, and antonym contradictions carrying no
negation cue. This eval measures the slice honestly and **names its holes** rather
than hiding them; the holes are what the AI-model layer and the human are there to
cover. It does NOT try to make the lexical layer complete.

Ground truth is the author-labelled `expected` relation in `lexicon_cases.jsonl`
(supports / contradicts / neither) — author gold, which is what makes this
automatic. The two detectors are scored against it:

  * support detector       — predicts support  iff status == supported_candidate
  * contradiction detector — predicts contra   iff status == contradiction_candidate

Usage:
  python validation/claimcheck/eval_lexicon.py                  # score + per-tag report
  python validation/claimcheck/eval_lexicon.py --write-baseline # freeze current scores
  python validation/claimcheck/eval_lexicon.py --check          # CI gate: exit 1 on regression

stdlib only; imports the repo's real text.py so the numbers reflect shipped logic.
"""
from __future__ import annotations
import argparse, importlib.util, json, os, sys
from collections import Counter, defaultdict

_HERE = os.path.dirname(__file__)
_REPO_DEFAULT = os.path.abspath(os.path.join(_HERE, "..", ".."))
_CASES = os.path.join(_HERE, "lexicon_cases.jsonl")
_BASELINE = os.path.join(_HERE, "lexicon_baseline.json")

SUPPORT_THRESHOLD = 0.5  # mirror ClaimCheckService._SUPPORT_THRESHOLD / build_ledger

# Hole categories: the lexical layer is EXPECTED to miss these; they are reported,
# not gated. Only negated_contradiction is a hard regression guard (the polarity
# guard must catch explicit negation — tests/test_claimcheck_polarity.py).
HOLE_TAGS = {"antonym_contradiction", "paraphrase_support", "semantic_contradiction"}


def load_text_module(repo: str):
    path = os.path.join(repo, "src", "citevahti", "retrieval", "text.py")
    spec = importlib.util.spec_from_file_location("cv_text", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def decide(t, claim: str, passage: str) -> str:
    cov = t.coverage_score(claim, passage)
    if cov < SUPPORT_THRESHOLD:
        return "no_support_found"
    return "contradiction_candidate" if t.polarity_conflict(claim, passage) else "supported_candidate"


def load_cases(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def prf(items, pred_pos, gold_pos) -> dict:
    tp = fp = fn = 0
    for r in items:
        p, g = pred_pos(r), gold_pos(r)
        if p and g: tp += 1
        elif p and not g: fp += 1
        elif g and not p: fn += 1
    prec = tp / (tp + fp) if (tp + fp) else None
    rec = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * prec * rec / (prec + rec)) if prec and rec else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec, "f1": f1}


def fmt(x) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def score(cases: list[dict], t) -> dict:
    for c in cases:
        c["status"] = decide(t, c["claim"], c["passage"])

    support = prf(cases, lambda r: r["status"] == "supported_candidate",
                  lambda r: r["expected"] == "supports")
    contra = prf(cases, lambda r: r["status"] == "contradiction_candidate",
                 lambda r: r["expected"] == "contradicts")

    # HARD guard: an explicitly-negated contradiction returned as support.
    negation_leaks = [c for c in cases if c["tag"] == "negated_contradiction"
                      and c["status"] == "supported_candidate"]
    # Reported (not gated): every contradiction the layer served as support,
    # including the known antonym/semantic holes.
    all_leaks = [c for c in cases if c["expected"] == "contradicts"
                 and c["status"] == "supported_candidate"]

    return {
        "n": len(cases),
        "support": support,
        "contradiction": contra,
        "negation_leaks": len(negation_leaks),
        "contradiction_as_support_total": len(all_leaks),
        "negation_leak_ids": [c["id"] for c in negation_leaks],
    }


def by_tag(cases: list[dict]) -> dict:
    out = defaultdict(Counter)
    for c in cases:
        out[c["tag"]][c["status"]] += 1
    return {k: dict(v) for k, v in sorted(out.items())}


def report(s: dict, tags: dict) -> None:
    print(f"records: {s['n']}\n")
    print("=== claim-check LEXICAL layer vs author gold ===")
    su, co = s["support"], s["contradiction"]
    print(f"  SUPPORT detector        precision {fmt(su['precision'])}  recall {fmt(su['recall'])}"
          f"  F1 {fmt(su['f1'])}   (TP {su['tp']} FP {su['fp']} FN {su['fn']})")
    print(f"  CONTRADICTION detector  precision {fmt(co['precision'])}  recall {fmt(co['recall'])}"
          f"  F1 {fmt(co['f1'])}   (TP {co['tp']} FP {co['fp']} FN {co['fn']})")
    print(f"\n  negated contradictions served as SUPPORT (HARD, must be 0): {s['negation_leaks']}"
          + (f"  -> {s['negation_leak_ids']}" if s['negation_leaks'] else ""))
    print(f"  all contradictions served as SUPPORT (incl. known antonym/semantic holes): "
          f"{s['contradiction_as_support_total']}")
    print("\n=== status by phenomenon (where the holes are) ===")
    for tag, counts in tags.items():
        marker = "  [known hole — covered by the AI/human layers]" if tag in HOLE_TAGS else ""
        pretty = "  ".join(f"{k}:{v}" for k, v in sorted(counts.items()))
        print(f"  {tag:24} {pretty}{marker}")


def baseline_view(s: dict) -> dict:
    """The regression-relevant slice, rounded for stable diffs."""
    def r(x):
        return None if x is None else round(x, 3)
    return {
        "n": s["n"],
        "support_precision": r(s["support"]["precision"]),
        "support_recall": r(s["support"]["recall"]),
        "contradiction_precision": r(s["contradiction"]["precision"]),
        "contradiction_recall": r(s["contradiction"]["recall"]),
        "negation_leaks": s["negation_leaks"],
    }


# Regression policy (ADR-0009 / acceptance-thresholds.md): precision must not fall,
# recall must not fall, and negated-contradiction leaks must stay at zero. Recall on
# the KNOWN-HOLE categories is reported but not gated — chasing it in the lexical
# layer is the wrong layer's job.
_EPS = 1e-9


def regressions(cur: dict, base: dict) -> list[str]:
    out = []
    if cur["negation_leaks"] > 0:
        out.append(f"negation leak count {cur['negation_leaks']} (must be 0)")
    for key in ("support_precision", "contradiction_precision",
                "support_recall", "contradiction_recall"):
        b, c = base.get(key), cur.get(key)
        if b is not None and c is not None and c < b - 1e-3:
            out.append(f"{key} fell {b:.3f} -> {c:.3f}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=_REPO_DEFAULT)
    ap.add_argument("--cases", default=_CASES)
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--check", action="store_true", help="exit 1 on regression vs baseline")
    args = ap.parse_args()

    t = load_text_module(args.repo)
    cases = load_cases(args.cases)
    s = score(cases, t)
    tags = by_tag(cases)
    report(s, tags)

    cur = baseline_view(s)

    if args.write_baseline:
        with open(_BASELINE, "w") as f:
            json.dump(cur, f, indent=2, sort_keys=True)
            f.write("\n")
        print(f"\nwrote baseline -> {_BASELINE}")
        return 0

    if args.check:
        if not os.path.exists(_BASELINE):
            print("\nno baseline to check against — run --write-baseline first")
            return 1
        with open(_BASELINE) as f:
            base = json.load(f)
        regs = regressions(cur, base)
        if regs:
            print("\nREGRESSION vs baseline:")
            for r in regs:
                print(f"  - {r}")
            return 1
        print("\nno regression vs baseline — OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
