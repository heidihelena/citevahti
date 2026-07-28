"""Bulk claim import: one JSONL file -> claims, candidates, open rating slots.

Loading a real corpus (30 claims / 61 candidate pairs) took ~90 lines of scripting across
`import-results`, `claim-add`, `claim-link-candidates` and `claim-support-start`, plumbing
ids between every step. Agents are how most corpora will be loaded, and every id hop was
somewhere to drop one.

Resumable, NOT atomic — CiteVahti has no general ledger transaction (`ZoteroTransaction` /
`txn-undo` cover Zotero writes only), so the guarantee on offer is convergence: re-run the
same file and nothing duplicates. These tests pin that down, and pin down that the import
records no judgement: it opens rating slots and stops.

Offline: no provider, no network, no AI.
"""

from __future__ import annotations

import json

from citevahti.claims.bulk import ClaimsImportError, ClaimsImportService
from citevahti.cli import main
from citevahti.state import CiteVahtiStore

_ROWS = [
    {"claim_text": "LDCT screening reduces lung-cancer mortality.",
     "location": "p3 ¶2", "claim_type": "effectiveness",
     "sources": [{"doi": "10.1056/NEJMoa1102873", "title": "NLST", "year": 2011},
                 {"pmid": "31995683", "title": "NELSON", "year": 2020}]},
    {"claim_text": "Strong inference speeds a field.",
     "location": "p1 ¶1", "claim_type": "background",
     "sources": [{"doi": "10.1126/science.146.3642.347", "title": "Strong inference"}]},
]


def _store(tmp_path):
    store = CiteVahtiStore(str(tmp_path))
    store.init()
    return store


def _write(tmp_path, rows):
    path = tmp_path / "corpus.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


# ---- the load ------------------------------------------------------------------------

def test_one_file_becomes_claims_candidates_and_open_slots(tmp_path):
    store = _store(tmp_path)
    rep = ClaimsImportService(store).import_rows(_ROWS)

    assert rep.rows == 2
    assert rep.claims_created == 2 and rep.claims_matched == 0
    assert rep.candidates_linked == 3
    assert rep.ratings_opened == 3
    assert rep.intake_batch_id                       # one staged batch, one import event
    assert len(store.list_claims()) == 2
    assert len(store.list_support_ratings()) == 3


def test_every_id_the_caller_needs_comes_back(tmp_path):
    """The point of the command: no re-listing to find what it just made."""
    store = _store(tmp_path)
    rep = ClaimsImportService(store).import_rows(_ROWS)

    first = rep.claims[0]
    assert first.row == 1 and first.claim_id
    assert {s.identifier for s in first.sources} == {"doi:10.1056/nejmoa1102873", "pmid:31995683"}
    assert all(s.candidate_id and s.rating_id for s in first.sources)


def test_the_import_records_no_judgement(tmp_path):
    """It opens slots. Every support value is still a human's to give."""
    store = _store(tmp_path)
    ClaimsImportService(store).import_rows(_ROWS)

    for rid in store.list_support_ratings():
        rec = store.load_support_rating(rid)
        assert rec.human_rating is None
        assert rec.ai_rating is None
        assert rec.adjudication.final_value is None


# ---- resumability --------------------------------------------------------------------

def test_rerunning_the_same_file_converges(tmp_path):
    """The property offered in place of atomicity. An interrupted load is re-run whole."""
    store = _store(tmp_path)
    svc = ClaimsImportService(store)
    first = svc.import_rows(_ROWS)
    again = svc.import_rows(_ROWS)

    assert again.claims_created == 0 and again.claims_matched == 2
    assert again.candidates_linked == 0 and again.candidates_already_linked == 3
    assert len(store.list_claims()) == 2
    assert len(store.list_support_ratings()) == 3          # not 6
    assert [c.claim_id for c in again.claims] == [c.claim_id for c in first.claims]
    # the same open slots, not fresh ones beside them
    assert ([s.rating_id for c in again.claims for s in c.sources]
            == [s.rating_id for c in first.claims for s in c.sources])


def test_a_resumed_load_completes_the_rows_it_missed(tmp_path):
    """The interrupted case: half the file landed, the rest is still to do."""
    store = _store(tmp_path)
    svc = ClaimsImportService(store)
    svc.import_rows(_ROWS[:1])
    rep = svc.import_rows(_ROWS)

    assert rep.claims_matched == 1 and rep.claims_created == 1
    assert len(store.list_claims()) == 2


def test_the_same_sentence_in_two_places_is_two_claims(tmp_path):
    """Matching is text AND location: one sentence asserted twice has two source sets."""
    store = _store(tmp_path)
    rows = [dict(_ROWS[1]), {**_ROWS[1], "location": "p9 ¶4"}]
    rep = ClaimsImportService(store).import_rows(rows)
    assert rep.claims_created == 2


def test_claim_matching_ignores_incidental_text_differences(tmp_path):
    """It uses the shared claim_text_hash normalization, as every other surface does."""
    store = _store(tmp_path)
    svc = ClaimsImportService(store)
    svc.import_rows(_ROWS[1:])
    rep = svc.import_rows([{**_ROWS[1],
                            "claim_text": "  Strong   inference SPEEDS a field.  "}])
    assert rep.claims_matched == 1 and rep.claims_created == 0


# ---- validation happens before any write ---------------------------------------------

def test_a_bad_row_stops_the_load_before_anything_is_written(tmp_path):
    """A typo on the last row must not leave the earlier ones half-loaded."""
    store = _store(tmp_path)
    rows = _ROWS + [{"claim_text": "Bad type.", "claim_type": "nonsense", "sources": []}]
    try:
        ClaimsImportService(store).import_rows(rows)
        raise AssertionError("expected a refusal")
    except ClaimsImportError as exc:
        assert "row 3" in str(exc) and "claim_type" in str(exc)
    assert store.list_claims() == []
    assert store.list_intake() == []


def test_a_misspelled_field_is_refused_not_silently_dropped(tmp_path):
    store = _store(tmp_path)
    rows = [{"claim_text": "x", "sources": [{"DOI": "10.1/x"}]}]
    try:
        ClaimsImportService(store).import_rows(rows)
        raise AssertionError("expected a refusal")
    except ClaimsImportError as exc:
        assert "row 1 source 1" in str(exc) and "DOI" in str(exc)


def test_a_blank_claim_is_refused(tmp_path):
    store = _store(tmp_path)
    try:
        ClaimsImportService(store).import_rows([{"claim_text": "   ", "sources": []}])
        raise AssertionError("expected a refusal")
    except ClaimsImportError as exc:
        assert "claim_text" in str(exc)


def test_a_title_only_source_is_named_as_undedupable(tmp_path):
    """Invariant 11: title is never dedupe truth. Such a source can't be matched to the
    same paper cited elsewhere — say so rather than let the count imply it was."""
    store = _store(tmp_path)
    rep = ClaimsImportService(store).import_rows(
        [{"claim_text": "A claim.", "sources": [{"title": "A book chapter"}]}])

    assert rep.title_only_sources == 1
    assert any("title only" in w for w in rep.warnings)
    assert rep.claims[0].sources[0].identifier is None


# ---- dry run -------------------------------------------------------------------------

def test_a_dry_run_writes_nothing(tmp_path):
    store = _store(tmp_path)
    rep = ClaimsImportService(store).import_rows(_ROWS, dry_run=True)

    assert rep.dry_run and rep.intake_batch_id is None
    assert rep.claims_created == 2
    assert all(c.status == "would_create" for c in rep.claims)
    assert store.list_claims() == [] and store.list_intake() == []
    assert store.list_support_ratings() == []


# ---- the CLI --------------------------------------------------------------------------

def test_cli_imports_a_file_and_reports_the_ids(tmp_path, capsys):
    _store(tmp_path)
    path = _write(tmp_path, _ROWS)
    capsys.readouterr()
    rc = main(["--root", str(tmp_path), "claims-import", "--jsonl", str(path), "--json"])
    rep = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert rep["claims_created"] == 2 and rep["ratings_opened"] == 3
    assert all(s["rating_id"] for c in rep["claims"] for s in c["sources"])


def test_cli_names_the_line_that_is_not_json(tmp_path, capsys):
    """A 60-row file with one bad line is a typo to fix, not a file to re-derive."""
    _store(tmp_path)
    path = tmp_path / "corpus.jsonl"
    path.write_text(json.dumps(_ROWS[0]) + "\n{not json}\n", encoding="utf-8")
    rc = main(["--root", str(tmp_path), "claims-import", "--jsonl", str(path)])

    assert rc == 2
    assert "line 2" in capsys.readouterr().err
    assert CiteVahtiStore(str(tmp_path)).list_claims() == []      # nothing written


def test_cli_dry_run_says_so_and_writes_nothing(tmp_path, capsys):
    _store(tmp_path)
    path = _write(tmp_path, _ROWS)
    capsys.readouterr()
    main(["--root", str(tmp_path), "claims-import", "--jsonl", str(path), "--dry-run"])
    out = capsys.readouterr().out

    assert "dry run" in out
    assert CiteVahtiStore(str(tmp_path)).list_claims() == []
