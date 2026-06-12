"""Report provenance: the limitations the artifact itself must carry (audit #5,
persona review). Audit head + chain state, the completeness denominator, and
retraction status must reach the report a supervisor/editor actually reads —
not just developer docs.
"""

from citevahti import tools as engine
from citevahti.claims import CandidateService, ClaimService
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.report import ClaimReportService, render_markdown, render_test_report
from citevahti.state import CiteVahtiStore


class _Provider:
    name = "pubmed"

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=self.hits, count=len(self.hits),
                                    email_present=True, rate_tier="3rps")


def _store(tmp_path):
    s = CiteVahtiStore(tmp_path)
    s.init()
    return s


def _claim_with_candidate(store, text="LDCT reduces mortality.", pmid="1", doi="10.1/a"):
    claim = ClaimService(store).add_claim(text, "effectiveness")
    batch = IntakeService(store, provider=_Provider([ProviderHit(pmid=pmid, doi=doi, title="P")]),
                          library_index=StaticLibraryIndex()).literature_search("q", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    return claim.claim_id


class _RetractedClient:
    def is_retracted(self, doi=None, pmid=None):
        return True


# ---- provenance block ------------------------------------------------------
def test_report_binds_audit_head_and_chain_state(tmp_path):
    store = _store(tmp_path)
    _claim_with_candidate(store)
    rep = ClaimReportService(store).report()
    p = rep.provenance
    assert p is not None
    assert p.audit_head_hash == store.audit.last_hash()
    assert p.audit_entries == len(store.audit.entries()) and p.audit_entries > 0
    assert p.audit_chain_intact is True
    assert p.ledger_claims_total == 1


def test_subset_report_keeps_full_ledger_denominator(tmp_path):
    store = _store(tmp_path)
    c1 = _claim_with_candidate(store, text="Claim one.")
    _claim_with_candidate(store, text="Claim two.", pmid="2", doi="10.2/b")
    rep = ClaimReportService(store).report(claim_ids=[c1])
    assert rep.total == 1
    assert rep.provenance.ledger_claims_total == 2   # cherry-pick is visible


def test_retraction_scan_timestamp_reaches_provenance(tmp_path):
    store = _store(tmp_path)
    _claim_with_candidate(store)
    rep = ClaimReportService(store).report()
    assert rep.provenance.last_retraction_scan_at is None  # never scanned: say so
    engine.scan_retractions(root=str(tmp_path), client=_RetractedClient())
    rep2 = ClaimReportService(store).report()
    assert rep2.provenance.last_retraction_scan_at is not None
    assert store.audit.verify()                       # scan event extends, not breaks, the chain


# ---- retraction status in rows and rendered output -------------------------
def test_retracted_candidate_flagged_in_report_rows(tmp_path):
    store = _store(tmp_path)
    claim_id = _claim_with_candidate(store)
    engine.scan_retractions(root=str(tmp_path), client=_RetractedClient())
    rep = ClaimReportService(store).report()
    row = next(r for r in rep.rows if r.claim_id == claim_id)
    assert row.evidence[0].retracted is True


def test_renderers_surface_retraction_and_count(tmp_path):
    store = _store(tmp_path)
    _claim_with_candidate(store)
    engine.scan_retractions(root=str(tmp_path), client=_RetractedClient())
    rep = ClaimReportService(store).report()
    for out in (render_markdown(rep), render_test_report(rep)):
        assert "RETRACTED" in out
        assert "1 linked candidate(s) are flagged as retracted" in out


# ---- limitations footer ----------------------------------------------------
def test_limitations_footer_in_both_renderers(tmp_path):
    store = _store(tmp_path)
    _claim_with_candidate(store)
    rep = ClaimReportService(store).report()
    head = (rep.provenance.audit_head_hash or "")[:16]
    for out in (render_markdown(rep), render_test_report(rep)):
        assert "Scope & limitations" in out
        assert "covers 1 of the 1 claim(s)" in out          # completeness denominator
        assert "not cryptographically signed" in out         # forgeability disclosed in-artifact
        assert head in out                                   # audit head printed
        assert "last scan: never" in out                     # unscanned must not look scanned
        assert "not clinical or scientific truth" in out
