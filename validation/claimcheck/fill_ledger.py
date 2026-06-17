#!/usr/bin/env python3
"""Fill the human columns of the claim-check ledger — interactively, blinded.

Step 2 of the workflow (README): two raters label each (claim, passage) pair,
then a third pass adjudicates. Hand-editing JSONL is error-prone and quietly
breaks blinding (you see the other rater and claim-check's own guess). This tool
makes κ-first measurement actually happen:

  python validation/claimcheck/fill_ledger.py rater1      # blinded: claim+passage only
  python validation/claimcheck/fill_ledger.py rater2      # blinded, independent
  python validation/claimcheck/fill_ledger.py adjudicate  # reveals both raters
  python validation/claimcheck/fill_ledger.py status      # progress, no editing
  python validation/claimcheck/fill_ledger.py score       # -> score_ledger.py

Blinding is the whole point: while rating, you NEVER see claim-check's status,
the LLM advisor, the provisional hypothesis, or the other rater — otherwise the
inter-rater κ is contaminated and the ground truth is worthless. Each answer is
saved immediately, so the pass is resumable and crash-safe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile

RELATIONS = ("supports", "contradicts", "neither")
_KEY = {"s": "supports", "c": "contradicts", "n": "neither"}
_DEFAULT_LEDGER = os.path.join(os.path.dirname(__file__), "ledger.jsonl")


# ---- pure helpers (unit-tested) --------------------------------------------
def load_ledger(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def save_ledger(path: str, recs: list[dict]) -> None:
    """Atomic rewrite, one record per line — same encoding as build_ledger.py."""
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def expected_hash(rec: dict) -> str:
    """Recompute the pair fingerprint the same way build_ledger.py stamped it."""
    return hashlib.sha256(
        json.dumps({"claim": rec["claim_text"], "citekey": rec["citekey"],
                    "passage": rec["passage_quote"], "claimcheck": rec["claimcheck"]},
                   sort_keys=True).encode()).hexdigest()[:16]


def hash_ok(rec: dict) -> bool:
    h = rec.get("record_hash")
    return h is None or h == expected_hash(rec)


def relation_of(cell) -> str | None:
    return cell.get("relation") if isinstance(cell, dict) else None


def set_label(rec: dict, who: str, relation: str, notes: str = "") -> dict:
    """Set rater1 / rater2 / adjudicated on a record (in place). Validates the
    relation against the controlled vocabulary; never invents a label."""
    if who not in ("rater1", "rater2", "adjudicated"):
        raise ValueError(f"unknown column {who!r}")
    if relation not in RELATIONS:
        raise ValueError(f"relation must be one of {RELATIONS}, got {relation!r}")
    rec[who] = {"relation": relation} if who == "adjudicated" else {"relation": relation, "notes": notes}
    return rec


def fill_counts(recs: list[dict]) -> dict:
    n = len(recs)
    return {"total": n,
            "rater1": sum(1 for r in recs if relation_of(r.get("rater1"))),
            "rater2": sum(1 for r in recs if relation_of(r.get("rater2"))),
            "adjudicated": sum(1 for r in recs if relation_of(r.get("adjudicated"))),
            "llm": sum(1 for r in recs if relation_of(r.get("llm_advisor")))}


def needs_label(rec: dict, who: str) -> bool:
    return relation_of(rec.get(who)) is None


def ready_to_adjudicate(rec: dict) -> bool:
    return bool(relation_of(rec.get("rater1")) and relation_of(rec.get("rater2")))


def disagreements(recs: list[dict]) -> list[dict]:
    return [r for r in recs if ready_to_adjudicate(r)
            and relation_of(r["rater1"]) != relation_of(r["rater2"])]


# ---- interactive loop ------------------------------------------------------
def _ask_relation(prompt: str, *, default: str | None = None) -> str | None:
    """Return a relation, None to skip, or raises KeyboardInterrupt-like 'quit'."""
    hint = "[s]upports / [c]ontradicts / [n]either / [?]skip / [q]save+quit"
    if default:
        hint += f"  (Enter = {default})"
    while True:
        raw = input(f"{prompt}\n  {hint}: ").strip().lower()
        if raw == "" and default:
            return default
        if raw in ("?", ""):
            return None
        if raw == "q":
            raise _Quit()
        if raw in _KEY:
            return _KEY[raw]
        if raw in RELATIONS:
            return raw
        print("  (didn't catch that)")


class _Quit(Exception):
    pass


def _rate_pass(path: str, who: str, do_all: bool) -> int:
    recs = load_ledger(path)
    todo = [r for r in recs if do_all or needs_label(r, who)]
    if not todo:
        print(f"{who}: nothing to do (all {len(recs)} records already labelled). "
              "Use --all to relabel.")
        return 0
    print(f"\n{who} — BLINDED rating. You see only the claim and the passage. "
          f"{len(todo)} record(s) to label.\n")
    done = 0
    for rec in todo:
        if not hash_ok(rec):
            print(f"  ⚠ {rec['record_id']}: pair text changed since seeding — skipping "
                  "(re-run build_ledger.py).")
            continue
        print(f"── {rec['record_id']} ──────────────────────────────────────────")
        print(f"  CLAIM:   {rec['claim_text']}")
        print(f"  PASSAGE: {rec['passage_quote']}")
        try:
            rel = _ask_relation("  Does the passage support, contradict, or neither?")
        except _Quit:
            print(f"\nsaved. {who}: {done} labelled this session.")
            return done
        if rel is None:
            print("  (skipped)\n")
            continue
        notes = input("  notes (optional): ").strip()
        set_label(rec, who, rel, notes)
        save_ledger(path, recs)        # save after every answer — resumable
        done += 1
        print(f"  ✓ {who} = {rel}\n")
    print(f"\ndone. {who}: {done} labelled this session.")
    return done


def _adjudicate_pass(path: str, do_all: bool) -> int:
    recs = load_ledger(path)
    ready = [r for r in recs if ready_to_adjudicate(r)]
    todo = [r for r in ready if do_all or needs_label(r, "adjudicated")]
    missing = sum(1 for r in recs if not ready_to_adjudicate(r))
    if missing:
        print(f"note: {missing} record(s) lack both rater1 & rater2 — fill those first.")
    if not todo:
        print("adjudicate: nothing to do (every dual-rated record already adjudicated). "
              "Use --all to revise.")
        return 0
    print(f"\nadjudicate — both raters revealed. {len(todo)} record(s); "
          f"{len(disagreements(recs))} are disagreements.\n")
    done = 0
    for rec in todo:
        r1, r2 = relation_of(rec["rater1"]), relation_of(rec["rater2"])
        agree = r1 == r2
        print(f"── {rec['record_id']} ──────────────────────────────────────────")
        print(f"  CLAIM:   {rec['claim_text']}")
        print(f"  PASSAGE: {rec['passage_quote']}")
        print(f"  rater1 = {r1}    rater2 = {r2}    {'(agree)' if agree else '⚠ DISAGREE'}")
        try:
            rel = _ask_relation("  Adjudicated ground truth?", default=(r1 if agree else None))
        except _Quit:
            print(f"\nsaved. adjudicated {done} this session.")
            return done
        if rel is None:
            print("  (skipped)\n")
            continue
        set_label(rec, "adjudicated", rel)
        save_ledger(path, recs)
        done += 1
        print(f"  ✓ adjudicated = {rel}\n")
    print(f"\ndone. adjudicated {done} this session.")
    return done


def _print_status(path: str) -> None:
    recs = load_ledger(path)
    c = fill_counts(recs)
    n = c["total"]
    print(f"ledger: {path}")
    print(f"  records:     {n}")
    print(f"  rater1:      {c['rater1']}/{n}")
    print(f"  rater2:      {c['rater2']}/{n}")
    print(f"  adjudicated: {c['adjudicated']}/{n}")
    print(f"  llm advisor: {c['llm']}/{n}")
    dis = disagreements(recs)
    both = sum(1 for r in recs if ready_to_adjudicate(r))
    print(f"  dual-rated:  {both}/{n}   disagreements: {len(dis)}")
    bad = [r["record_id"] for r in recs if not hash_ok(r)]
    if bad:
        print(f"  ⚠ pair text changed (re-seed): {', '.join(bad)}")
    if c["rater1"] and c["rater2"]:
        print("\n  → run `score` (or score_ledger.py) for Cohen's κ and precision/recall.")
    else:
        print("\n  → fill rater1 and rater2 to get Cohen's κ.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fill the claim-check validation ledger (blinded).")
    ap.add_argument("mode", choices=("rater1", "rater2", "adjudicate", "status", "score"))
    ap.add_argument("--ledger", default=_DEFAULT_LEDGER, help="path to ledger.jsonl")
    ap.add_argument("--all", action="store_true",
                    help="revisit already-labelled records (default: only blank ones)")
    args = ap.parse_args(argv)

    if not os.path.exists(args.ledger):
        print(f"no ledger at {args.ledger} — run build_ledger.py first.", file=sys.stderr)
        return 2

    if args.mode == "status":
        _print_status(args.ledger)
        return 0
    if args.mode == "score":
        import subprocess
        return subprocess.call([sys.executable,
                                os.path.join(os.path.dirname(__file__), "score_ledger.py"),
                                args.ledger])
    if args.mode in ("rater1", "rater2"):
        _rate_pass(args.ledger, args.mode, args.all)
    else:
        _adjudicate_pass(args.ledger, args.all)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
