"""Unit tests for the claim-check ledger fill tool (validation/claimcheck/fill_ledger.py).

The interactive loop is thin; the testable core is the pure label/IO/integrity
helpers that keep κ-first measurement honest (valid relations only, blinding via
per-rater columns, hash integrity, atomic round-trip).
"""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parents[1] / "validation" / "claimcheck" / "fill_ledger.py"
_spec = importlib.util.spec_from_file_location("fill_ledger", _MOD)
fl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fl)


def _seed(claim="Drug X reduced mortality", citekey="smith2020",
          passage="Drug X reduced mortality.", status="supported_candidate"):
    cc = {"version": "claimcheck-polarity-1", "coverage": 1.0,
          "polarity_conflict": False, "status": status}
    rec = {"record_id": "cc-001", "claim_text": claim, "citekey": citekey,
           "passage_quote": passage, "claimcheck": cc, "llm_advisor": None,
           "rater1": None, "rater2": None, "adjudicated": None,
           "provisional_relation": "supports"}
    rec["record_hash"] = fl.expected_hash(rec)
    return rec


def test_set_label_shapes_and_validates():
    rec = _seed()
    fl.set_label(rec, "rater1", "supports", notes="clear")
    assert rec["rater1"] == {"relation": "supports", "notes": "clear"}
    fl.set_label(rec, "adjudicated", "contradicts")
    assert rec["adjudicated"] == {"relation": "contradicts"}   # no notes on ground truth
    with pytest.raises(ValueError):
        fl.set_label(rec, "rater1", "maybe")                   # not in vocabulary
    with pytest.raises(ValueError):
        fl.set_label(rec, "rater9", "supports")                # unknown column


def test_hash_integrity_detects_tampering():
    rec = _seed()
    assert fl.hash_ok(rec)
    rec["passage_quote"] = "Drug X did NOT reduce mortality."   # seed text changed
    assert not fl.hash_ok(rec)
    assert fl.expected_hash(rec) == hashlib.sha256(
        json.dumps({"claim": rec["claim_text"], "citekey": rec["citekey"],
                    "passage": rec["passage_quote"], "claimcheck": rec["claimcheck"]},
                   sort_keys=True).encode()).hexdigest()[:16]


def test_counts_and_selection_helpers():
    a, b = _seed(), _seed()
    b["record_id"] = "cc-002"
    fl.set_label(a, "rater1", "supports"); fl.set_label(a, "rater2", "supports")
    fl.set_label(b, "rater1", "supports"); fl.set_label(b, "rater2", "contradicts")
    recs = [a, b]
    c = fl.fill_counts(recs)
    assert c == {"total": 2, "rater1": 2, "rater2": 2, "adjudicated": 0, "llm": 0}
    assert fl.needs_label(a, "adjudicated") and not fl.needs_label(a, "rater1")
    assert fl.ready_to_adjudicate(a) and fl.ready_to_adjudicate(b)
    dis = fl.disagreements(recs)
    assert [r["record_id"] for r in dis] == ["cc-002"]          # only the mismatch


def test_save_load_roundtrip_one_record_per_line(tmp_path):
    a, b = _seed(), _seed(); b["record_id"] = "cc-002"
    fl.set_label(a, "rater1", "neither", notes="off-topic")
    p = tmp_path / "ledger.jsonl"
    fl.save_ledger(str(p), [a, b])
    assert len(p.read_text().splitlines()) == 2                 # one record per line
    back = fl.load_ledger(str(p))
    assert back[0]["rater1"] == {"relation": "neither", "notes": "off-topic"}
    assert [r["record_id"] for r in back] == ["cc-001", "cc-002"]


def test_full_workflow_seed_rate_adjudicate(tmp_path):
    a, b = _seed(), _seed(); b["record_id"] = "cc-002"
    p = tmp_path / "ledger.jsonl"
    fl.save_ledger(str(p), [a, b])
    # rater pass
    recs = fl.load_ledger(str(p))
    for r in recs:
        fl.set_label(r, "rater1", "supports"); fl.set_label(r, "rater2", "supports")
    fl.save_ledger(str(p), recs)
    # adjudicate
    recs = fl.load_ledger(str(p))
    for r in recs:
        assert fl.ready_to_adjudicate(r)
        fl.set_label(r, "adjudicated", "supports")
    fl.save_ledger(str(p), recs)
    assert fl.fill_counts(fl.load_ledger(str(p)))["adjudicated"] == 2
