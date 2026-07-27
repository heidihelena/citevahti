"""The agreement report reads the CLAIM-SUPPORT ledger, not only study-quality ratings.

``AgreementReportService`` loaded ``store.list_ratings()`` alone, so a ledger of compared
claim–candidate support pairs — CiteVahti's core asset, and the path the prescreen work
actually runs — produced an all-zero agreement report and an empty model scoreboard. The
methods statement, built on the same service, then said "Of 0 comparable human–AI pairs"
and "No comparable human–AI pairs yet" in a document whose own evidence-basis line and
PRISMA table counted those same pairs. One generated document, two contradictory answers.

The fix has two halves, and both are load-bearing:
  * the report SEES claim-support ratings (projected onto a reserved scheme id), so the
    counts, kappa and model scoreboard describe the work that was done;
  * it never POOLS them with study-quality ratings into one agreement figure — two
    instruments on two units are not one number — and it refuses ordinal weighted kappa
    for a vocabulary that has no ordinal ranking rather than inventing one.

Offline throughout.
"""

from __future__ import annotations

import pytest

from citevahti.claims import CandidateService, ClaimService, ClaimSupportEngine
from citevahti.claims.support import SupportAiOutput
from citevahti.export import AgreementReportService
from citevahti.export.agreement import CLAIM_SUPPORT_SCHEME_ID
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.rating import FakeAiRater, RatingEngine
from citevahti.report.methods import build_methods_markdown
from citevahti.schemas.common import ItemRef
from citevahti.schemas.frame import Frame, Level, Outcome, Scheme, Study
from citevahti.schemas.rating import Subject
from citevahti.state import CiteVahtiStore


class _Provider:
    name = "pubmed"

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=self.hits, count=len(self.hits),
                                    email_present=True, rate_tier="3rps")


class _Rater:
    name = "prepared_rater"

    def __init__(self, out):
        self._out = out

    def rate(self, *, claim, candidate, task_type):
        return self._out


GRADE = [Level(value="High", ordinal=4), Level(value="Moderate", ordinal=3),
         Level(value="Low", ordinal=2), Level(value="Very Low", ordinal=1)]


def _store(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    cfg = store.load_config()
    cfg.ai_provenance.model_id = "qwen3:14b"
    cfg.ai_provenance.model_snapshot = "sha256:abc"
    cfg.ai_provenance.prompt_template_version = "v1"
    store.save_config(cfg)
    return store


def _support_pair(store, human, ai, n):
    """One fully dual-rated, compared claim-support pair."""
    claim = ClaimService(store).add_claim(f"Claim {n} about mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider(
        [ProviderHit(pmid=f"1000000{n}", doi=f"10.1000/t{n}", title=f"Trial {n}")]),
        library_index=StaticLibraryIndex()).literature_search(f"q{n}", question_id=f"q{n}")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    eng = ClaimSupportEngine(store, rater=_Rater(SupportAiOutput(value=ai)))
    rec = eng.support_run_ai(eng.support_start(claim.claim_id, cand_id).rating_id)
    eng.support_commit_human(rec.rating_id, human)
    return eng.support_compare(rec.rating_id)


def _support_ledger(tmp_path):
    """4 concordant, 2 discordant — raw agreement 4/6."""
    store = _store(tmp_path)
    for i, (h, a) in enumerate([("directly_supports", "directly_supports"),
                                ("directly_supports", "directly_supports"),
                                ("does_not_support", "does_not_support"),
                                ("contradicts", "contradicts"),
                                ("directly_supports", "overstated"),
                                ("unclear", "does_not_support")], 1):
        _support_pair(store, h, a, i)
    return store


def _add_grade_rating(store, human, ai):
    """One study-quality rating through the real engine, for the mixed-ledger cases."""
    if not store.list_frames():
        store.save_frame(Frame(
            frame_id="F", frame_version="1.0.0", created_at="2026-07-27T00:00:00+00:00",
            outcomes=[Outcome(outcome_id=f"o{i}", label=f"O{i}") for i in range(1, 9)],
            studies=[Study(study_id="s1", item=ItemRef(zotero_key="K1", citekey="c1"))],
            schemes=[Scheme(scheme_id="grade", kind="GRADE", unit="outcome", levels=GRADE)]))
    n = len(store.list_ratings()) + 1
    eng = RatingEngine(store, ai_rater=FakeAiRater(ai))
    rid = eng.rating_start("F", "grade", Subject(outcome_id=f"o{n}")).rating_id
    eng.rating_commit_human(rid, human)
    eng.rating_run_ai(rid, "assess")
    return eng.rating_compare(rid)


# --- the report sees the work that was done ----------------------------------

def test_agreement_report_counts_claim_support_pairs(tmp_path):
    rep = AgreementReportService(_support_ledger(tmp_path)).report(persist=False)
    assert rep.overall.comparable_pairs == 6
    assert rep.overall.agreements == 4 and rep.overall.disagreements == 2


def test_kappa_is_computed_for_the_claim_support_vocabulary(tmp_path):
    rep = AgreementReportService(_support_ledger(tmp_path)).report(
        metrics=["raw_agreement", "cohen_kappa"], persist=False)
    grp = next(g for g in rep.groups if g.scheme_id == CLAIM_SUPPORT_SCHEME_ID)
    assert grp.metrics["raw_agreement"] == pytest.approx(4 / 6)
    ck = grp.metrics["cohen_kappa"]
    assert ck["value"] is not None and not ck.get("error")


def test_model_scoreboard_covers_claim_support_ratings(tmp_path):
    """The scoreboard feeds the model advisor. Blind to claim-support, it stayed silent
    about exactly the ratings CiteVahti mostly produces."""
    rep = AgreementReportService(_support_ledger(tmp_path)).report(persist=False)
    board = {m.model_id: m for m in rep.model_scoreboard}
    assert board["qwen3:14b"].concordant == 4 and board["qwen3:14b"].discordant == 2


def test_methods_statement_reports_the_claim_support_numbers(tmp_path):
    """The paragraph's every sentence is about claim–candidate support, so its numbers
    have to come from that ledger — this is the contradiction that started the fix."""
    md = build_methods_markdown(_support_ledger(tmp_path))
    assert "Of 6 comparable human–AI pairs, 4 were concordant and 2 discordant" in md
    assert "Of 0 comparable" not in md
    assert "No comparable human–AI **claim-support** pairs yet" not in md   # they exist


def test_methods_statement_and_prisma_table_agree(tmp_path):
    """The two halves of one document must not contradict each other: the evidence-basis
    line and the PRISMA table already counted these pairs while the paragraph said zero."""
    md = build_methods_markdown(_support_ledger(tmp_path))
    assert "Of 6 comparable human–AI pairs" in md          # the paragraph
    assert "Of 6 rated claim–candidate pair(s)" in md      # the evidence-basis line
    assert "| Claim–evidence pairs assessed (human-rated) | 6 |" in md   # the PRISMA table


# --- but the two instruments are never pooled --------------------------------

def test_weighted_kappa_is_refused_rather_than_given_an_invented_order(tmp_path):
    """The support vocabulary has no ordinal ranking — 'overstated' and 'unclear' are not
    points on a strength scale. Ordering it to satisfy an ordinal statistic would invent a
    scale the instrument does not have, so the metric is refused with its reason stated."""
    rep = AgreementReportService(_support_ledger(tmp_path)).report(
        metrics=["cohen_kappa", "weighted_kappa"], persist=False)
    grp = next(g for g in rep.groups if g.scheme_id == CLAIM_SUPPORT_SCHEME_ID)
    assert grp.metrics["weighted_kappa"] == {"value": None, "error": "no_ordinal_scale"}
    assert any("invent a scale" in w for w in grp.warnings)
    assert grp.metrics["cohen_kappa"]["value"] is not None       # the nominal one stands


def test_kappa_is_refused_across_the_two_instruments(tmp_path):
    """Agreement on claim support and agreement on study quality are two measurements of
    two things. Pooling them into one kappa would report a number that describes neither."""
    store = _support_ledger(tmp_path)
    _add_grade_rating(store, "Moderate", "Moderate")
    rep = AgreementReportService(store).report(metrics=["cohen_kappa"], persist=False)
    grp = rep.groups[0]
    assert grp.scheme_id is None                                 # mixed → no single scheme
    assert any("mixed schemes" in w for w in grp.warnings)
    assert "cohen_kappa" not in grp.metrics


def test_grouping_by_scheme_separates_the_two_instruments(tmp_path):
    """Grouped, each instrument gets its own honest kappa."""
    store = _support_ledger(tmp_path)
    for h, a in [("Moderate", "Moderate"), ("Low", "Low"), ("High", "Low")]:
        _add_grade_rating(store, h, a)
    rep = AgreementReportService(store).report(
        filters={"group_by": ["scheme_id"]}, metrics=["raw_agreement", "cohen_kappa"],
        persist=False)
    by_scheme = {g.scheme_id: g for g in rep.groups}
    assert set(by_scheme) == {CLAIM_SUPPORT_SCHEME_ID, "grade"}
    assert by_scheme[CLAIM_SUPPORT_SCHEME_ID].counts.comparable_pairs == 6
    assert by_scheme["grade"].counts.comparable_pairs == 3


def test_methods_statement_does_not_pool_study_quality_ratings(tmp_path):
    """A GRADE rating in the same ledger must not inflate a claim-support paragraph — and
    must not be silently dropped either: the reader is told it exists and where it lives."""
    store = _support_ledger(tmp_path)
    _add_grade_rating(store, "Moderate", "Moderate")
    md = build_methods_markdown(store)
    assert "Of 6 comparable human–AI pairs" in md            # 6, not 7
    assert "also holds 1 study-quality rating(s)" in md
    assert "never pooled into one agreement figure" in md


def test_a_study_quality_only_ledger_reports_zero_claim_support_pairs(tmp_path):
    """Honest in the other direction too: the paragraph describes claim support, so a
    ledger with none says so plainly rather than borrowing another instrument's numbers."""
    store = _store(tmp_path)
    _add_grade_rating(store, "Moderate", "Moderate")
    md = build_methods_markdown(store)
    assert "Of 0 comparable human–AI pairs" in md
    assert "No comparable human–AI **claim-support** pairs yet" in md
    assert "also holds 1 study-quality rating(s)" in md       # not silently dropped
