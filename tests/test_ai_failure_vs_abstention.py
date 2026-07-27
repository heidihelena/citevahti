"""A failed AI call is NOT an abstention — end to end, adapter to methods statement.

Regression guard for the 2026-07-26 finding. The raters collapsed transport and parse
failures into ``abstained=True``, so the ledger recorded "the model read this and declined
to rate it" for events where the model never spoke at all. Measured on a 44-pair corpus:
qwen3:14b recorded 15 abstentions — 13 unparseable replies and 2 timeouts, and **zero**
genuine abstentions. On the 5 items where the adapter worked it scored 5/5. That misreading
propagated into the audit trail and into the auto-filled methods paragraph, which told a
journal reader the abstentions were excluded from the agreement denominator — language a
reader takes to mean the model exercised judgement.

These tests lock the separation at every layer it has to survive: the rater emits a typed
failure, the engine persists it, the comparison gets its own status, the validators refuse
to merge the two, and the report counts and describes them apart. Offline throughout.
"""

from __future__ import annotations

import json

import pytest

from citevahti.claims import CandidateService, ClaimService, ClaimSupportEngine
from citevahti.claims.support import SupportAiOutput
from citevahti.export import AgreementReportService
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.rating.ai import failure_reason
from citevahti.report.methods import build_methods_markdown
from citevahti.schemas.claim_support import SupportAIRating
from citevahti.schemas.frame import Frame, Level, Outcome, Scheme
from citevahti.schemas.rating import (
    AI_FAILURE_KINDS,
    Adjudication,
    AIProvenance,
    AIRating,
    Comparison,
    HumanRating,
    RatingRecord,
    Subject,
)
from citevahti.state import CiteVahtiStore
from citevahti.validators.claim_support import ClaimSupportError, validate_claim_support_record


class _Rater:
    """A rater that returns exactly one prepared outcome, so each test states the event
    it is about instead of simulating an HTTP shape (that lives in the rater's own tests)."""

    name = "prepared_rater"

    def __init__(self, out):
        self._out = out

    def rate(self, *, claim, candidate, task_type):
        return self._out


def _store(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    cfg = store.load_config()
    cfg.ai_provenance.model_id = "qwen3:14b"
    cfg.ai_provenance.model_snapshot = "sha256:abc"
    cfg.ai_provenance.prompt_template_version = "v1"
    store.save_config(cfg)
    return store


class _Provider:
    name = "pubmed"

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=self.hits, count=len(self.hits),
                                    email_present=True, rate_tier="3rps")


def _pair(store, n=1):
    claim = ClaimService(store).add_claim(f"Claim {n} about mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider(
        [ProviderHit(pmid=f"1000000{n}", doi=f"10.1000/t{n}", title=f"Trial {n}")]),
        library_index=StaticLibraryIndex()).literature_search(f"q{n}", question_id=f"q{n}")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    return claim.claim_id, cand_id


def _rated(store, out, human="directly_supports", n=1):
    claim_id, cand_id = _pair(store, n)
    eng = ClaimSupportEngine(store, rater=_Rater(out))
    rec = eng.support_start(claim_id, cand_id)
    rec = eng.support_run_ai(rec.rating_id)
    if human:
        eng.support_commit_human(rec.rating_id, human)
    return eng.support_compare(rec.rating_id)


def _prov():
    return AIProvenance(provider="ollama", model_id="qwen3:14b", model_snapshot="sha256:abc",
                        prompt_template_version="v1", prompt_hash="ph", config_hash="ch",
                        rated_at="2026-07-26T00:00:00+00:00")


# --- the ledger records which event happened ---------------------------------

@pytest.mark.parametrize("kind", AI_FAILURE_KINDS)
def test_every_failure_kind_is_recorded_as_a_failure_not_an_abstention(tmp_path, kind):
    rec = _rated(_store(tmp_path), SupportAiOutput(failure=kind,
                                                   domain_reasoning=failure_reason(kind)))
    assert rec.ai_rating.failure == kind
    assert rec.ai_rating.abstained is False        # the model did not decline; it never spoke
    assert rec.ai_rating.value is None             # and no value was ever fabricated
    assert rec.comparison.status == "ai_failed"


def test_a_genuine_abstention_is_still_an_abstention(tmp_path):
    """The narrowed meaning has to keep working for the event it is now reserved for."""
    rec = _rated(_store(tmp_path),
                 SupportAiOutput(abstained=True, domain_reasoning="no outcome in the abstract"))
    assert rec.ai_rating.abstained is True and rec.ai_rating.failure is None
    assert rec.comparison.status == "ai_abstained"


def test_a_failed_call_is_never_recorded_as_a_disagreement(tmp_path):
    """The trap in the old comparison order: a failed rating carries value=None, so a
    comparison that checks `human != ai` before checking the failure manufactures a
    discordance between the human and a model that never answered — and a discordance
    demands adjudication, dragging a human into resolving a disagreement that never existed."""
    rec = _rated(_store(tmp_path), SupportAiOutput(failure="provider_error"),
                 human="contradicts")
    assert rec.comparison.status == "ai_failed"
    assert rec.adjudication.final_value is None and rec.adjudication.event is None


def test_provenance_is_recorded_for_a_failed_call_too(tmp_path):
    """A failure is still an event that happened with a specific model — the record has to
    say which one, or the ledger cannot show that a given model's adapter was broken."""
    rec = _rated(_store(tmp_path), SupportAiOutput(failure="unparseable_reply"))
    assert rec.ai_rating.provenance.model_id == "qwen3:14b"
    assert rec.ai_rating.provenance.model_snapshot == "sha256:abc"


# --- the two states can never merge again ------------------------------------

def test_a_record_cannot_claim_both_an_abstention_and_a_failure():
    rec = _support_record(abstained=True, failure="unparseable_reply")
    with pytest.raises(ClaimSupportError, match="cannot be both"):
        validate_claim_support_record(rec)


def test_a_failed_rating_cannot_carry_a_value():
    rec = _support_record(failure="out_of_vocab_value", value="directly_supports")
    with pytest.raises(ClaimSupportError, match="must have value=None"):
        validate_claim_support_record(rec)


def test_a_valueless_rating_must_say_why():
    """Neither abstained nor failed and no value: the record would assert that an AI rating
    exists while saying nothing about what happened. That is the ambiguity being removed."""
    rec = _support_record()
    with pytest.raises(ClaimSupportError, match="must say why"):
        validate_claim_support_record(rec)


def _support_record(*, abstained=False, failure=None, value=None):
    from citevahti.schemas.claim_support import ClaimSupportRating
    return ClaimSupportRating(
        rating_id="cs-1", claim_id="c1", candidate_id="cand1",
        ai_rating=SupportAIRating(value=value, abstained=abstained, failure=failure,
                                  provenance=_prov()))


# --- the report tells a reader which event it is counting --------------------

GRADE_LEVELS = [Level(value="High", ordinal=4), Level(value="Moderate", ordinal=3),
                Level(value="Low", ordinal=2), Level(value="Very Low", ordinal=1)]


def _add_rating(store, frame, rid, outcome, *, human, ai=None, abstained=False, failure=None):
    """A rating record as ``rating_run_ai`` + ``rating_compare`` would leave it."""
    ai_rating = AIRating(value=ai, abstained=abstained, failure=failure,
                         provenance=_prov(), task_type="assess")
    if failure is not None:
        status = "ai_failed"
    elif abstained:
        status = "ai_abstained"
    else:
        status = "concordant" if ai == human else "discordant"
    adj = (Adjudication(final_value=human, event="accepted", decided_at="2026-07-26T01:00:00+00:00")
           if status == "concordant" else Adjudication())
    rec = RatingRecord(
        rating_id=rid, frame_id=frame.frame_id, frame_version=frame.frame_version,
        scheme_id="grade", subject=Subject(outcome_id=outcome),
        human_rating=HumanRating(value=human, committed_at="2026-07-26T00:30:00+00:00",
                                 committed_by="rater_a", locked=True),
        ai_rating=ai_rating, comparison=Comparison(status=status), adjudication=adj)
    store.save_rating(rec, frame=frame)


def _mixed_ledger(tmp_path, *, with_failures=True):
    """One of each: a comparable pair, a genuine abstention, and two failed calls.

    The agreement report reads scheme rating records, so the mix is built there — the
    claim-support path is covered by the ledger tests above.
    """
    store = _store(tmp_path)
    frame = Frame(frame_id="F", frame_version="1.0.0", created_at="2026-07-26T00:00:00+00:00",
                  outcomes=[Outcome(outcome_id=f"o{i}", label=f"O{i}") for i in range(1, 5)],
                  schemes=[Scheme(scheme_id="grade", kind="GRADE", unit="outcome",
                                  levels=GRADE_LEVELS)])
    store.save_frame(frame)
    _add_rating(store, frame, "r1", "o1", human="Moderate", ai="Moderate")
    _add_rating(store, frame, "r2", "o2", human="Low", abstained=True)
    if with_failures:
        _add_rating(store, frame, "r3", "o3", human="Low", failure="unparseable_reply")
        _add_rating(store, frame, "r4", "o4", human="High", failure="truncated_reply")
    return store


def test_agreement_report_counts_failures_apart_from_abstentions(tmp_path):
    store = _mixed_ledger(tmp_path)
    rep = AgreementReportService(store).report(persist=False)
    assert rep.overall.ai_abstained == 1          # only the model's own declining
    assert rep.overall.ai_failed == 2
    assert rep.overall.ai_failure_kinds == {"unparseable_reply": 1, "truncated_reply": 1}
    # neither kind ever enters the denominator — that part of the contract is unchanged
    assert rep.overall.comparable_pairs == 1


def test_methods_statement_does_not_call_a_failed_call_an_abstention(tmp_path):
    """The published sentence is the whole point: a reader takes "the AI abstained" to mean
    the model exercised judgement, so a broken adapter must not be reported in those words."""
    md = build_methods_markdown(_mixed_ledger(tmp_path))
    assert "AI abstentions (1)" in md                       # the one that really abstained
    assert "read and declined to rate" in md                # what an abstention now means
    assert "the model call itself failed" in md             # and what the other 2 were
    assert "unparseable_reply" in md and "truncated_reply" in md
    assert "were recorded as failed AI calls rather than abstentions" in md


def test_methods_statement_flags_failed_calls_before_submission(tmp_path):
    md = build_methods_markdown(_mixed_ledger(tmp_path))
    before_you_submit = md.split("**Before you submit:**")[1]
    assert "failed rather than abstained" in before_you_submit
    assert "not evidence about the claims" in before_you_submit


def test_methods_statement_stays_quiet_when_nothing_failed(tmp_path):
    """No failures: no clause, no note. An honest report does not manufacture a caveat."""
    md = build_methods_markdown(_mixed_ledger(tmp_path, with_failures=False))
    assert "AI abstentions (1)" in md
    assert "failed" not in md.lower()


def test_model_scoreboard_does_not_credit_a_broken_adapter_as_caution(tmp_path):
    """A model whose calls keep failing must not accumulate a tally that reads as a
    careful rater — the scoreboard is what the model advisor ranks on."""
    rep = AgreementReportService(_mixed_ledger(tmp_path)).report(persist=False)
    scores = {(m.model_id): m for m in rep.model_scoreboard}
    assert scores["qwen3:14b"].abstained == 1
    assert scores["qwen3:14b"].failed == 2


def test_agreement_summary_reports_both_counts(tmp_path):
    rep = AgreementReportService(_mixed_ledger(tmp_path)).report(persist=False)
    md = rep.method_transparency_markdown
    assert "abstentions (1)" in md and "Failed AI calls**: 2" in md
    assert "These are **not** abstentions" in md
    assert json.dumps(rep.ai_provenance_summary).count("failure_kinds") == 1
