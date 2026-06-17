#!/usr/bin/env python3
"""Score a FILLED claim-check validation ledger.

Measures TWO detectors against the human-adjudicated `relation`:
  * support detector       — predicts support  iff status == supported_candidate
  * contradiction detector — predicts contra   iff status == contradiction_candidate
Each is scored on precision / recall / F1. Inter-rater Cohen's kappa is reported
FIRST: if the humans don't agree, there is no ground truth and the metrics are
void. The (optional) LLM advisor is scored against the SAME human gold, never
against claim-check, and the correlated-error count is shown so agreement is not
mistaken for accuracy.

    python validation/claimcheck/score_ledger.py validation/claimcheck/ledger.jsonl

stdlib only. Tolerates a partially-filled ledger (reports what is missing).
"""
from __future__ import annotations
import json, os, sys


def rel(x):
    return x.get("relation") if isinstance(x, dict) else None


def load(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def kappa(pairs):
    n = len(pairs)
    if not n:
        return None
    cats = sorted({c for p in pairs for c in p})
    idx = {c: i for i, c in enumerate(cats)}
    po = sum(1 for a, b in pairs if a == b) / n
    # expected agreement
    ma = [0] * len(cats); mb = [0] * len(cats)
    for a, b in pairs:
        ma[idx[a]] += 1; mb[idx[b]] += 1
    pe = sum((ma[i] / n) * (mb[i] / n) for i in range(len(cats)))
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def prf(items, pred_pos, gold_pos):
    tp = fp = fn = tn = 0
    for r in items:
        p, g = pred_pos(r), gold_pos(r)
        if p and g: tp += 1
        elif p and not g: fp += 1
        elif not p and g: fn += 1
        else: tn += 1
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = (2 * prec * rec / (prec + rec)) if prec and rec else None
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, prec=prec, rec=rec, f1=f1)


def fmt(x):
    return "n/a" if x is None else f"{x:.3f}"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "ledger.jsonl")
    recs = load(path)
    n = len(recs)
    h1 = sum(1 for r in recs if rel(r.get("rater1")))
    h2 = sum(1 for r in recs if rel(r.get("rater2")))
    adj = sum(1 for r in recs if rel(r.get("adjudicated")))
    llm = sum(1 for r in recs if rel(r.get("llm_advisor")))
    print(f"records: {n}")
    print(f"labels present — rater1: {h1}/{n}  rater2: {h2}/{n}  adjudicated: {adj}/{n}  llm: {llm}/{n}")

    both = [r for r in recs if rel(r.get("rater1")) and rel(r.get("rater2"))]
    if both:
        k = kappa([(rel(r["rater1"]), rel(r["rater2"])) for r in both])
        agree = sum(1 for r in both if rel(r["rater1"]) == rel(r["rater2"]))
        print(f"\n=== inter-rater reliability (n={len(both)}) ===")
        print(f"  raw agreement {100*agree/len(both):.0f}%   Cohen's kappa {k:.3f}"
              f"   {'OK (>=0.6)' if k>=0.6 else 'WEAK — sharpen the rubric before trusting metrics'}")
    else:
        print("\n(no records with BOTH human raters — fill rater1 & rater2 for kappa)")

    gold = [r for r in recs if rel(r.get("adjudicated"))]
    if not gold:
        print("\n(no adjudicated ground truth yet — fill 'adjudicated.relation' to get precision/recall)")
        return

    print(f"\n=== claim-check vs human ground truth (n={len(gold)}) ===")
    sup = prf(gold, lambda r: r["claimcheck"]["status"] == "supported_candidate",
              lambda r: rel(r["adjudicated"]) == "supports")
    con = prf(gold, lambda r: r["claimcheck"]["status"] == "contradiction_candidate",
              lambda r: rel(r["adjudicated"]) == "contradicts")
    print(f"  SUPPORT detector       precision {fmt(sup['prec'])}  recall {fmt(sup['rec'])}  F1 {fmt(sup['f1'])}"
          f"   (TP {sup['tp']} FP {sup['fp']} FN {sup['fn']})")
    print(f"  CONTRADICTION detector precision {fmt(con['prec'])}  recall {fmt(con['rec'])}  F1 {fmt(con['f1'])}"
          f"   (TP {con['tp']} FP {con['fp']} FN {con['fn']})")
    # the bug we fixed: a contradiction returned as support
    leak = [r for r in gold if r["claimcheck"]["status"] == "supported_candidate"
            and rel(r["adjudicated"]) == "contradicts"]
    print(f"  contradictions leaking into SUPPORT: {len(leak)}  (the bug; should be 0)")

    if llm:
        g2 = [r for r in gold if rel(r.get("llm_advisor"))]
        lsup = prf(g2, lambda r: rel(r["llm_advisor"]) == "supports",
                   lambda r: rel(r["adjudicated"]) == "supports")
        print(f"\n=== LLM advisor vs human ground truth (n={len(g2)}) ===")
        print(f"  SUPPORT precision {fmt(lsup['prec'])}  recall {fmt(lsup['rec'])}  F1 {fmt(lsup['f1'])}")
        co = sum(1 for r in g2
                 if (r["claimcheck"]["status"] == "supported_candidate") == (rel(r["llm_advisor"]) == "supports")
                 and (r["claimcheck"]["status"] == "supported_candidate") != (rel(r["adjudicated"]) == "supports"))
        print(f"  correlated errors (claim-check & LLM wrong together): {co}/{len(g2)}"
              f"  — agreement here is NOT reassurance")

    # provisional sanity (pre-adjudication, not a result)
    by = {}
    for r in recs:
        by.setdefault(r.get("provisional_relation", "?"), []).append(r["claimcheck"]["status"])
    print("\n=== claim-check status by provisional relation (sanity, pre-adjudication) ===")
    for k in sorted(by):
        from collections import Counter
        c = Counter(by[k])
        print(f"  {k:12} " + "  ".join(f"{s}:{c[s]}" for s in sorted(c)))


if __name__ == "__main__":
    main()
