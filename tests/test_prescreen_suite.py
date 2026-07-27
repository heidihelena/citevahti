"""prescreen-benchmark suite.py: the held-out suite export and submission contract.

The export is the security-relevant half. In these seeds the stratum IS the
anchor (A=supports, B=contrasts, C=not_relevant, D=unclear) and ids are A01/B03,
so "held out" means re-identifying and reordering — not just dropping a column.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

SUITE = (Path(__file__).resolve().parents[1]
         / ".claude/skills/prescreen-benchmark/scripts/suite.py")

VOCAB = ["supports", "contrasts", "unclear", "not_relevant"]
STRATUM_ANCHOR = {"A": "supports", "B": "contrasts", "C": "not_relevant", "D": "unclear"}


def seed(n_per_stratum=3):
    pairs = []
    for st, anchor in STRATUM_ANCHOR.items():
        for i in range(1, n_per_stratum + 1):
            pairs.append({"id": f"{st}{i:02d}", "stratum": st,
                          "claim": f"claim {st}{i}", "snippet": f"snippet {st}{i}",
                          "source": f"Source {st}{i}", "ref_status": anchor,
                          "anchor_basis": "the abstract says so",
                          "claude_status": None, "claude_rationale": None})
    return {"theme": "a-theme", "vocabulary": VOCAB,
            "anchor_provenance": "constructed_by_design", "pairs": pairs}


def run(*args, expect=0):
    proc = subprocess.run([sys.executable, str(SUITE), *map(str, args)],
                          capture_output=True, text=True)
    assert proc.returncode == expect, f"rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    return proc


def export(tmp_path, suite_id="t@v1"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "seed.json"
    src.write_text(json.dumps(seed()))
    run("export", src, suite_id, tmp_path)
    return (json.loads((tmp_path / f"suite_{suite_id}.json").read_text()),
            json.loads((tmp_path / f"key_{suite_id}.json").read_text()))


def test_public_suite_carries_no_anchor_in_any_form(tmp_path):
    suite, key = export(tmp_path)
    blob = json.dumps(suite)
    for field in ("ref_status", "anchor", "stratum", "anchor_basis", "claude_status"):
        assert f'"{field}"' not in blob, f"{field} leaked into the public suite"
    # the seed ids are themselves the key — they must not survive either
    seed_ids = {p["id"] for p in seed()["pairs"]}
    assert not seed_ids & {i["item_id"] for i in suite["items"]}
    assert all(i["item_id"].startswith("i") for i in suite["items"])
    # the key still maps back, and keeps the anchors
    assert {k["seed_id"] for k in key["items"]} == seed_ids
    assert {k["anchor"] for k in key["items"]} == set(STRATUM_ANCHOR.values())


def test_export_reorders_so_position_does_not_leak_the_anchor(tmp_path):
    """Publishing A01..A03 then B01..B03 in seed order leaks the key by position."""
    suite, key = export(tmp_path)
    by_item = {k["item_id"]: k["seed_id"] for k in key["items"]}
    published = [by_item[i["item_id"]][0] for i in suite["items"]]   # stratum letters in order
    assert published != sorted(published), "items are still grouped by stratum"


def test_publication_order_cannot_be_recomputed_from_public_data(tmp_path):
    """The whole held-out design rests on this.

    An attacker holds only the public suite file. From it they get suite_id and the
    published item order. The seed id scheme (A01…/B02…) and the stratum→anchor
    mapping are documented in this skill's own seeds, so the id set is enumerable.
    If the ordering is a pure function of those two public things, they replay it,
    zip it against the published order, and read off every anchor.
    """
    suite, key = export(tmp_path)
    sid = suite["suite_id"]
    guessable_ids = [p["id"] for p in seed()["pairs"]]
    predicted = sorted(guessable_ids,
                       key=lambda i: hashlib.sha256(f"{sid}\x00{i}".encode()).hexdigest())
    by_item = {k["item_id"]: k["seed_id"] for k in key["items"]}
    published = [by_item[i["item_id"]] for i in suite["items"]]
    assert predicted != published, (
        "publication order is recomputable from suite_id + seed ids alone — "
        "the anchors are not held out")


def test_the_ordering_secret_never_reaches_the_public_suite(tmp_path):
    suite, key = export(tmp_path)
    assert key.get("salt"), "the key must carry the secret that fixes the order"
    assert "salt" not in json.dumps(suite), "the ordering secret leaked into the public file"


def test_re_export_is_reproducible_but_a_fresh_export_is_not_predictable(tmp_path):
    """Re-running an export must reproduce the published suite byte for byte, or a
    lost file could never be regenerated. That reproducibility comes from the salt
    stored in the key — NOT from the public inputs, so a fresh export elsewhere
    (no key to reuse) must land on a different order."""
    a, ka = export(tmp_path / "one", suite_id="t@v1")
    again, ka2 = export(tmp_path / "one", suite_id="t@v1")     # same dir: key present
    assert a == again, "re-export with the key present must be identical"
    assert ka["salt"] == ka2["salt"]

    fresh, kb = export(tmp_path / "two", suite_id="t@v1")      # same id, no key to reuse
    assert kb["salt"] != ka["salt"]
    assert [i["claim"] for i in fresh["items"]] != [i["claim"] for i in a["items"]], (
        "a fresh export reproduced the order without the salt — it is still predictable")


def submission(tmp_path, suite, verdicts):
    vf = tmp_path / "verdicts.jsonl"
    vf.write_text("".join(json.dumps(v) + "\n" for v in verdicts))
    run("pack", vf, tmp_path / f"suite_{suite['suite_id']}.json",
        "--out", tmp_path / "submission.json", "--rater", "gpt-5",
        "--rater-kind", "hosted_api", "--prompt-id", "prescreen-v1",
        "--prompt-hash", "abc123")
    return tmp_path / "submission.json", vf


def good_verdicts(suite):
    return [{"item_id": i["item_id"], "verdict": "supports", "latency_ms": 10}
            for i in suite["items"]]


def test_validate_accepts_a_well_formed_submission(tmp_path):
    suite, _ = export(tmp_path)
    sp, vf = submission(tmp_path, suite, good_verdicts(suite))
    out = run("validate", sp, vf, tmp_path / "suite_t@v1.json")
    assert "ok:" in out.stdout


def test_validate_rejects_a_missing_item(tmp_path):
    suite, _ = export(tmp_path)
    sp, vf = submission(tmp_path, suite, good_verdicts(suite)[:-1])
    err = run("validate", sp, vf, tmp_path / "suite_t@v1.json", expect=1).stderr
    assert "no verdict" in err and "explicit null" in err


def test_validate_rejects_a_label_outside_the_frozen_vocabulary(tmp_path):
    suite, _ = export(tmp_path)
    v = good_verdicts(suite)
    v[0]["verdict"] = "probably_supports"
    sp, vf = submission(tmp_path, suite, v)
    err = run("validate", sp, vf, tmp_path / "suite_t@v1.json", expect=1).stderr
    assert "outside the frozen vocabulary" in err


def test_validate_rejects_edited_verdicts(tmp_path):
    """The manifest is content-bound: editing verdicts after packing must not pass."""
    suite, _ = export(tmp_path)
    sp, vf = submission(tmp_path, suite, good_verdicts(suite))
    rows = [json.loads(x) for x in vf.read_text().splitlines()]
    rows[0]["verdict"] = "contrasts"
    vf.write_text("".join(json.dumps(r) + "\n" for r in rows))
    err = run("validate", sp, vf, tmp_path / "suite_t@v1.json", expect=1).stderr
    assert "verdicts_sha256" in err


def test_validate_rejects_a_submission_carrying_the_answer_key(tmp_path):
    suite, key = export(tmp_path)
    anchors = {k["item_id"]: k["anchor"] for k in key["items"]}
    v = [{"item_id": i["item_id"], "verdict": "supports", "anchor": anchors[i["item_id"]]}
         for i in suite["items"]]
    sp, vf = submission(tmp_path, suite, v)
    err = run("validate", sp, vf, tmp_path / "suite_t@v1.json", expect=1).stderr
    assert "anchor field" in err


def test_validate_rejects_a_run_against_an_edited_item_set(tmp_path):
    suite, _ = export(tmp_path)
    sp, vf = submission(tmp_path, suite, good_verdicts(suite))
    edited = tmp_path / "suite_t@v1.json"
    payload = json.loads(edited.read_text())
    payload["items"][0]["claim"] = "a different claim"
    edited.write_text(json.dumps(payload))
    err = run("validate", sp, vf, edited, expect=1).stderr
    assert "does not match its claim_text_hash" in err
