"""Regression: a corrected re-import must not leave the stale record standing silently.

Found in a real ledger: candidate `cand-bbd8d17348fa` carried record_id
`doi:10.1126/science.146.3642.347` — Platt 1964, "Strong inference" — under the title
"On the use of biological measures in health psychology…", a different paper entirely.
Re-importing the corrected record reported `already_in_prior_intake` and changed nothing:
dedupe matches on identifier, so the corrected record found the candidate already on file
and stopped there. Re-linking from the corrected batch didn't refresh it either, and short
of `txn-undo` there was no way to fix it.

Two halves, deliberately separate:

* **Linking reports the divergence and changes nothing.** A candidate's title is what a
  rater read; refreshing it automatically would rewrite the record of what was judged, on
  the strength of an import.
* **`candidate-refresh` applies the correction as an audited event** carrying every field's
  old and new value, so the previous text stays recoverable from the chain instead of being
  replaced without trace — and it names any human ratings made before it.

Offline: fake provider, no network.
"""

from __future__ import annotations

import json

from citevahti.claims import CandidateService, ClaimService, ClaimSupportEngine
from citevahti.cli import main
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore
from citevahti.state.store import StateError

_DOI = "10.1126/science.146.3642.347"
_WRONG = "On the use of biological measures in health psychology: A multilevel perspective."
_RIGHT = "Strong inference"


class _Provider:
    name = "pubmed"

    def __init__(self, hits):
        self._hits = hits

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=self._hits, count=len(self._hits),
                                    email_present=True, rate_tier="3rps")


def _batch(store, hits, question_id):
    return IntakeService(store, provider=_Provider(hits),
                         library_index=StaticLibraryIndex()).literature_search(
                             "strong inference", question_id=question_id)


def _seed(tmp_path):
    """A claim whose candidate carries the WRONG title, and a corrected batch."""
    store = CiteVahtiStore(str(tmp_path))
    store.init()
    claim = ClaimService(store).add_claim("Strong inference speeds a field.", "other")
    stale = _batch(store, [ProviderHit(doi=_DOI, title=_WRONG, year=1999)], "q1")
    CandidateService(store).link_from_intake(claim.claim_id, stale.batch_id)
    fixed = _batch(store, [ProviderHit(doi=_DOI, title=_RIGHT, year=1964,
                                       journal="Science")], "q2")
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    return store, claim.claim_id, cand_id, fixed.batch_id


def _title(store, claim_id, cand_id):
    return next(c.title for c in store.load_candidates(claim_id).candidates
                if c.candidate_id == cand_id)


# ---- linking reports, never repairs ---------------------------------------------------

def test_relinking_a_corrected_batch_reports_the_divergence(tmp_path):
    store, claim_id, cand_id, fixed = _seed(tmp_path)
    rep = CandidateService(store).link_from_intake(claim_id, fixed)

    assert rep.linked == 0 and rep.skipped_duplicates == 1     # dedupe still matched
    fields = {d.field: d for d in rep.divergences}
    assert fields["title"].current == _WRONG
    assert fields["title"].incoming == _RIGHT
    assert fields["year"].current == "1999" and fields["year"].incoming == "1964"
    assert fields["journal"].current is None                   # a gap, not a contradiction
    assert fields["title"].candidate_id == cand_id


def test_linking_changes_nothing_on_its_own(tmp_path):
    """The report is a report. The rater's record is untouched until someone says so."""
    store, claim_id, cand_id, fixed = _seed(tmp_path)
    CandidateService(store).link_from_intake(claim_id, fixed)
    assert _title(store, claim_id, cand_id) == _WRONG


def test_an_unchanged_record_reports_no_divergence(tmp_path):
    store, claim_id, cand_id, _ = _seed(tmp_path)
    same = _batch(store, [ProviderHit(doi=_DOI, title=_WRONG, year=1999)], "q3")
    assert CandidateService(store).link_from_intake(claim_id, same.batch_id).divergences == []


# ---- the audited repair ---------------------------------------------------------------

def test_refresh_corrects_the_record(tmp_path):
    store, claim_id, cand_id, fixed = _seed(tmp_path)
    rep = CandidateService(store).refresh_from_intake(claim_id, cand_id, fixed)

    assert _title(store, claim_id, cand_id) == _RIGHT
    corrected = {d.field: (d.current, d.incoming) for d in rep.corrected}
    assert corrected["title"] == (_WRONG, _RIGHT)
    assert corrected["year"] == ("1999", "1964")
    assert corrected["journal"] == (None, "Science")


def test_the_correction_is_audited_with_the_old_values(tmp_path):
    """`txn-undo` was the only escape before this. The chain must record what the record
    used to say, so the correction is recoverable rather than a silent overwrite."""
    store, claim_id, cand_id, fixed = _seed(tmp_path)
    before = len(store.audit.entries())
    CandidateService(store).refresh_from_intake(claim_id, cand_id, fixed)

    entries = store.audit.entries()
    assert len(entries) == before + 1
    event = entries[-1]
    assert event.event == "candidate.correct"          # legible AS a correction
    fields = {f["field"]: f for f in event.payload["fields"]}
    assert fields["title"]["from"] == _WRONG and fields["title"]["to"] == _RIGHT
    assert store.audit.verify()                        # chain still intact


def test_provenance_is_never_rewritten_by_a_later_import(tmp_path):
    """How the paper entered consideration is the record of a past event, not metadata."""
    store, claim_id, cand_id, fixed = _seed(tmp_path)
    before = next(c for c in store.load_candidates(claim_id).candidates
                  if c.candidate_id == cand_id)
    query, source, batch = before.retrieval_query, before.retrieval_source, before.intake_batch_id
    CandidateService(store).refresh_from_intake(claim_id, cand_id, fixed)

    after = next(c for c in store.load_candidates(claim_id).candidates
                 if c.candidate_id == cand_id)
    assert (after.retrieval_query, after.retrieval_source) == (query, source)
    assert after.intake_batch_id == batch and after.candidate_id == cand_id


def test_a_repair_names_the_ratings_made_before_it(tmp_path):
    """Someone judged this paper as the record then described it. The repair is still
    right — but it says so, and stamps it into the audit payload."""
    store, claim_id, cand_id, fixed = _seed(tmp_path)
    eng = ClaimSupportEngine(store)
    rating = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rating.rating_id, "directly_supports", committed_by="reviewer-1")

    rep = CandidateService(store).refresh_from_intake(claim_id, cand_id, fixed)

    assert rep.human_rated_before == 1
    assert store.audit.entries()[-1].payload["human_rated_before"] == 1
    assert _title(store, claim_id, cand_id) == _RIGHT    # not blocked; the record should be right


def test_refusing_a_batch_that_is_not_the_same_paper(tmp_path):
    """A correction matches on identifier. Anything else is an overwrite wearing its hat."""
    store, claim_id, cand_id, _ = _seed(tmp_path)
    other = _batch(store, [ProviderHit(doi="10.9999/unrelated", title="Something else")], "q9")
    try:
        CandidateService(store).refresh_from_intake(claim_id, cand_id, other.batch_id)
        raise AssertionError("expected a refusal")
    except StateError as exc:
        assert "no record matching" in str(exc)
    assert _title(store, claim_id, cand_id) == _WRONG


def test_repairing_twice_is_a_no_op_and_writes_nothing(tmp_path):
    store, claim_id, cand_id, fixed = _seed(tmp_path)
    svc = CandidateService(store)
    svc.refresh_from_intake(claim_id, cand_id, fixed)
    entries = len(store.audit.entries())

    again = svc.refresh_from_intake(claim_id, cand_id, fixed)
    assert again.corrected == []
    assert len(store.audit.entries()) == entries


# ---- the CLI --------------------------------------------------------------------------

def test_cli_refresh_reports_what_changed(tmp_path, capsys):
    store, claim_id, cand_id, fixed = _seed(tmp_path)
    capsys.readouterr()
    rc = main(["--root", str(tmp_path), "candidate-refresh", "--claim-id", claim_id,
               "--candidate-id", cand_id, "--intake-batch-id", fixed, "--json"])
    res = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert res["candidate_id"] == cand_id
    assert {d["field"] for d in res["corrected"]} >= {"title", "year"}
    assert res["audit_event_id"]


def test_cli_link_points_at_the_repair_command(tmp_path, capsys):
    """A divergence is useless if the person reading it can't act on it."""
    store, claim_id, cand_id, fixed = _seed(tmp_path)
    capsys.readouterr()
    main(["--root", str(tmp_path), "claim-link-candidates", "--claim-id", claim_id,
          "--intake-batch-id", fixed])
    out = capsys.readouterr().out

    assert "differ from the record already on file" in out
    assert "nothing was changed" in out
    assert "candidate-refresh" in out
