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
