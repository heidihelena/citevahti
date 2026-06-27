"""--json on the claim spine: ids must flow machine-readably end-to-end
(power-user persona finding: no stdout scraping)."""

import json

from citevahti.claims import ClaimService
from citevahti.cli import main
from citevahti.state import CiteVahtiStore


def _store(tmp_path):
    s = CiteVahtiStore(tmp_path)
    s.init()
    return s


def _out(capsys):
    return json.loads(capsys.readouterr().out)


_CLAIM_STATES = {"supported_candidate", "contradiction_candidate",
                 "no_support_found", "unverifiable"}


def test_claim_check_json_is_a_stable_verifier_contract(tmp_path, capsys):
    """`claim-check --json` is the machine-readable contract an external citation reviewer
    (e.g. forskai's CITATION_VERIFIER=citevahti adapter) parses. Offline there's no Zotero
    text, so the honest result is `unverifiable` — but the SHAPE must be stable: the 4-state
    status (never a truth/'valid' verdict), per-citekey detail, and provenance."""
    _store(tmp_path)
    main(["--root", str(tmp_path), "claim-check",
          "--claim", "Aspirin reduces cardiovascular events.",
          "--citekey", "smith2020", "--json"])
    res = _out(capsys)
    assert set(res) >= {"claim_text", "aggregate_status", "per_citekey", "warnings", "provenance"}
    assert res["aggregate_status"] in _CLAIM_STATES        # never a binary pass/fail
    pc = res["per_citekey"][0]
    assert pc["citekey"] == "smith2020"
    assert pc["status"] in _CLAIM_STATES
    assert res["provenance"]["tool"] == "claim_check"      # callers can audit what produced it


def test_claim_verify_offline_text_is_a_stable_contract(tmp_path, capsys):
    """`claim-verify` checks a claim against PROVIDED text — offline, no Zotero — the seam an
    external reviewer that already has the source text uses. Stable JSON; never a verdict."""
    main(["claim-verify", "--claim", "Aspirin reduces cardiovascular events",
          "--text", "In the randomized trial, aspirin reduced cardiovascular events.", "--json"])
    res = _out(capsys)
    assert res["available"] is True
    assert res["status"] in {"terms_present", "terms_missing"}
    assert "aspirin" in res["present"]
    assert res["contradiction"] is False


def test_claim_verify_flags_polarity_conflict_not_a_verdict(tmp_path, capsys):
    """A sentence with the claim's terms but the opposite polarity surfaces as an inspectable
    'may contradict' cue — never auto-judged true or false."""
    main(["claim-verify", "--claim", "Aspirin reduces cardiovascular events",
          "--text", "Aspirin did not reduce cardiovascular events in this cohort.", "--json"])
    res = _out(capsys)
    assert res["contradiction"] is True
    assert res["polarity_cue"]            # the negation word is inspectable, not hidden


def test_claim_add_json_roundtrip(tmp_path, capsys):
    _store(tmp_path)
    main(["--root", str(tmp_path), "claim-add", "--text", "LDCT reduces mortality.",
          "--type", "effectiveness", "--json"])
    claim = _out(capsys)
    assert claim["claim_id"].startswith("claim-")
    assert claim["claim_type"] == "effectiveness"

    main(["--root", str(tmp_path), "claim-list", "--json"])
    claims = _out(capsys)
    assert [c["claim_id"] for c in claims] == [claim["claim_id"]]


def test_claim_untestable_json(tmp_path, capsys):
    store = _store(tmp_path)
    c = ClaimService(store).add_claim("Cites a monograph.", "other")
    main(["--root", str(tmp_path), "claim-untestable", c.claim_id,
          "--reason", "1992 monograph", "--json"])
    claim = _out(capsys)
    assert claim["untestable_reason"] == "1992 monograph"


def test_candidate_list_json_empty(tmp_path, capsys):
    store = _store(tmp_path)
    c = ClaimService(store).add_claim("A claim.", "background")
    main(["--root", str(tmp_path), "candidate-list", "--claim-id", c.claim_id, "--json"])
    cc = _out(capsys)
    assert cc["claim_id"] == c.claim_id and cc["candidates"] == []
