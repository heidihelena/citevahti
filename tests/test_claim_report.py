"""Citation-integrity report: the 4-state derivation (the "unit-test results")."""

from citevahti.claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
    DecisionService,
    FakeClaimSupportRater,
)
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.report import ClaimReportService
from citevahti.state import CiteVahtiStore


class _Provider:
    name = "pubmed"

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=self.hits, count=len(self.hits),
                                    email_present=True, rate_tier="3rps")


def _pin(cfg):
    cfg.ai_provenance.model_id = "claude-opus-4-8"
    cfg.ai_provenance.model_snapshot = "2026-05-01"
    cfg.ai_provenance.prompt_template_version = "v1"
    return cfg


def _store(tmp_path):
    s = CiteVahtiStore(tmp_path)
    s.init()
    s.save_config(_pin(s.load_config()))
    return s


def _claim_with_candidate(store, text="LDCT reduces mortality.", pmid="1", doi="10.1/a"):
    claim = ClaimService(store).add_claim(text, "effectiveness")
    batch = IntakeService(store, provider=_Provider([ProviderHit(pmid=pmid, doi=doi, title="P")]),
                          library_index=StaticLibraryIndex()).literature_search("q", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    return claim.claim_id, cand_id


def _row(store, claim_id):
    rep = ClaimReportService(store).report()
    return next(r for r in rep.rows if r.claim_id == claim_id)


# ---- the four states -------------------------------------------------------
def test_claim_with_no_candidates_is_needs_support(tmp_path):
    store = _store(tmp_path)
    claim = ClaimService(store).add_claim("An unsupported assertion.", "background")
    row = _row(store, claim.claim_id)
    assert row.state == "needs_support" and row.code == "o " and row.candidate_count == 0


def test_linked_but_unrated_candidate_is_needs_support(tmp_path):
    store = _store(tmp_path)
    claim_id, _cand = _claim_with_candidate(store)
    row = _row(store, claim_id)
    assert row.state == "needs_support" and row.candidate_count == 1


def test_accepted_supporting_candidate_is_verified(tmp_path):
    store = _store(tmp_path)
    claim_id, cand_id = _claim_with_candidate(store)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.support_compare(rec.rating_id)
    DecisionService(store).decide(claim_id, cand_id, "accept", "ok", rating_id=rec.rating_id)
    row = _row(store, claim_id)
    assert row.state == "verified" and row.code == "oo" and row.accepted_count == 1
    assert row.evidence[0].pmid == "1" and row.evidence[0].final_decision == "accept"


def test_unresolved_discordance_is_review_needed(tmp_path):
    store = _store(tmp_path)
    claim_id, cand_id = _claim_with_candidate(store)
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="does_not_support"))
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.support_run_ai(rec.rating_id)
    eng.support_compare(rec.rating_id)                  # discordant, unadjudicated
    row = _row(store, claim_id)
    assert row.state == "review_needed" and row.code == "r "


def test_needs_second_review_decision_is_review_needed(tmp_path):
    store = _store(tmp_path)
    claim_id, cand_id = _claim_with_candidate(store)
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="does_not_support"))
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.support_run_ai(rec.rating_id)
    eng.support_compare(rec.rating_id)
    DecisionService(store).decide(claim_id, cand_id, "needs_second_review", "hold",
                                  rating_id=rec.rating_id)
    assert _row(store, claim_id).state == "review_needed"


def test_all_rejected_is_decision_recorded(tmp_path):
    store = _store(tmp_path)
    claim_id, cand_id = _claim_with_candidate(store)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "does_not_support")
    eng.support_compare(rec.rating_id)
    DecisionService(store).decide(claim_id, cand_id, "reject", "off-topic", rating_id=rec.rating_id)
    row = _row(store, claim_id)
    assert row.state == "decision_recorded" and row.code == "d " and row.accepted_count == 0


# ---- summary + read-only ---------------------------------------------------
def test_report_counts_and_is_read_only(tmp_path):
    store = _store(tmp_path)
    ClaimService(store).add_claim("no-cite claim", "background")        # needs_support
    c2, k2 = _claim_with_candidate(store, text="supported claim", pmid="2", doi="10.1/b")
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(c2, k2)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.support_compare(rec.rating_id)
    DecisionService(store).decide(c2, k2, "accept", "ok", rating_id=rec.rating_id)

    before = store.load_evidence_map().model_dump()
    rep = ClaimReportService(store).report()
    assert rep.total == 2
    assert rep.counts["verified"] == 1 and rep.counts["needs_support"] == 1
    assert store.load_evidence_map().model_dump() == before            # no mutation


def test_evidence_carries_rating_id_and_blinds_ai_until_human_rates(tmp_path):
    store = _store(tmp_path)
    claim_id, cand_id = _claim_with_candidate(store)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)
    eng.submit_ai_rating(rec.rating_id, "directly_supports")   # AI only, human not yet
    ev = _row(store, claim_id).evidence[0]
    assert ev.rating_id == rec.rating_id
    assert ev.human_support is None and ev.ai_support == "hidden"   # blinded
    # once the human rates, the AI value is shown
    eng.support_commit_human(rec.rating_id, "partially_supports")
    ev2 = _row(store, claim_id).evidence[0]
    assert ev2.human_support == "partially_supports" and ev2.ai_support == "directly_supports"


def test_evidence_surfaces_human_fit_and_excerpt_only_after_rating(tmp_path):
    from citevahti.schemas.claim_support import FitScores
    from citevahti.schemas.common import ItemRef, PassageRef
    store = _store(tmp_path)
    claim_id, cand_id = _claim_with_candidate(store)
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(claim_id, cand_id)

    # Before the human commits: no fit, no excerpt (blinding-consistent).
    ev0 = _row(store, claim_id).evidence[0]
    assert ev0.fit is None and ev0.fit_total is None and ev0.excerpt is None

    passage = PassageRef(item=ItemRef(zotero_key="ZK1"), quote="LDCT cut mortality vs CXR.")
    eng.support_commit_human(
        rec.rating_id, "directly_supports",
        fit=FitScores(population_fit=2, intervention_fit=2, outcome_fit=2, claim_fit=1),
        source_passages=[passage])

    ev = _row(store, claim_id).evidence[0]
    assert ev.fit is not None and ev.fit.population_fit == 2 and ev.fit.claim_fit == 1
    assert ev.fit_total == 7                              # 2+2+2+1
    assert ev.excerpt == "LDCT cut mortality vs CXR."


def test_agent_verify_claims_is_read_only_and_on_the_surface(tmp_path):
    from citevahti import agent
    assert "verify_claims" in agent.TOOLS
    store = _store(tmp_path)
    _claim_with_candidate(store)
    out = agent.tools.verify_claims(root=str(tmp_path))
    assert out["total"] == 1 and "counts" in out and out["claims"][0]["code"] in ("oo", "o", "r", "d")


# ---- editor mode: Markdown report export -----------------------------------
def test_markdown_report_has_sections_and_evidence(tmp_path):
    from citevahti.report import ClaimReportService, render_markdown
    store = _store(tmp_path)
    ClaimService(store).add_claim("An uncited assertion.", "background")        # needs_support
    c2, k2 = _claim_with_candidate(store, text="LDCT reduces mortality.", pmid="21714641")
    eng = ClaimSupportEngine(store)
    rec = eng.support_start(c2, k2)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.support_compare(rec.rating_id)
    DecisionService(store).decide(c2, k2, "accept", "ok", rating_id=rec.rating_id)

    md = render_markdown(ClaimReportService(store).report())
    assert md.startswith("# Citation-Integrity Report")
    assert "## Claims needing attention" in md and "## Verified claims" in md
    assert "need attention" in md and "PMID 21714641" in md
    assert "does not assert truth" in md          # the non-overclaim footer


def test_cli_claim_report_md_to_file(tmp_path, capsys):
    from citevahti.cli import main
    store = _store(tmp_path)
    ClaimService(store).add_claim("A claim.", "background")
    out = tmp_path / "report.md"
    main(["--root", str(tmp_path), "claim-report", "--format", "md", "--output", str(out)])
    assert out.exists() and out.read_text().startswith("# Citation-Integrity Report")
    assert "wrote md report" in capsys.readouterr().out
