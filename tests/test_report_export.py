"""Report exports for the Word world: print-ready HTML + a review-packet .zip.

Both are pure-Python / stdlib (no docx/pdf deps): render_html mirrors the Markdown
report from the structured ClaimReport; export_review_packet zips the report
(Markdown + HTML) plus the structured evidence/audit trail.
"""

from __future__ import annotations

import zipfile

from citevahti import tools as engine
from citevahti.claims import ClaimService
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.report import ClaimReportService, render_html
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
    cfg = s.load_config()
    cfg.ai_provenance.model_id = "claude-opus-4-8"
    cfg.ai_provenance.model_snapshot = "2026-05-01"
    s.save_config(cfg)
    claim = ClaimService(s).add_claim("LDCT reduces lung-cancer mortality.", "effectiveness")
    batch = IntakeService(s, provider=_Provider([ProviderHit(pmid="1", doi="10.1/a", title="NLST")]),
                          library_index=StaticLibraryIndex()).literature_search("q", question_id="q1")
    from citevahti.claims import CandidateService
    CandidateService(s).link_from_intake(claim.claim_id, batch.batch_id)
    return s, claim.claim_id


def test_render_html_is_standalone_and_covers_the_claim(tmp_path):
    s, _ = _store(tmp_path)
    rep = ClaimReportService(s).report()
    html = render_html(rep)
    assert html.startswith("<!DOCTYPE html>") and "</html>" in html
    assert "Citation-Integrity Report" in html
    assert "LDCT reduces lung-cancer mortality." in html      # the claim is present
    assert "Scope &amp; limitations" in html                  # footer + HTML-escaped


def test_review_packet_zips_report_and_trail(tmp_path):
    s, _ = _store(tmp_path)
    res = engine.export_review_packet(root=str(tmp_path))
    assert res["claim_count"] == 1
    with zipfile.ZipFile(res["output_file"]) as z:
        names = set(z.namelist())
        assert names == {"citation-integrity-report.md", "citation-integrity-report.html",
                         "claims.json", "README.txt"}
        assert "LDCT reduces lung-cancer mortality." in z.read("citation-integrity-report.md").decode()
        assert z.read("citation-integrity-report.html").decode().startswith("<!DOCTYPE html>")
        # the structured trail carries the claim + provenance
        assert "LDCT reduces lung-cancer mortality." in z.read("claims.json").decode()
