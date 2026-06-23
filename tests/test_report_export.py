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
                         "claims.json", "methods.md", "README.txt"}
        assert "LDCT reduces lung-cancer mortality." in z.read("citation-integrity-report.md").decode()
        assert z.read("citation-integrity-report.html").decode().startswith("<!DOCTYPE html>")
        # the structured trail carries the claim + provenance
        assert "LDCT reduces lung-cancer mortality." in z.read("claims.json").decode()
        # the submission-ready methods paragraph is auto-filled with this ledger's values
        methods = z.read("methods.md").decode()
        assert "Methods statement" in methods and "blinded dual-rating workflow" in methods
        assert "claude-opus-4-8" in methods                    # the pinned model id


def test_methods_statement_is_honest_about_missing_data(tmp_path):
    # no dual-rated pairs yet → agreement/κ are marked n/a, never invented
    from citevahti.report import build_methods_markdown
    s, _ = _store(tmp_path)
    md = build_methods_markdown(s)
    assert "Of 0 comparable human–AI pairs" in md
    assert "n/a" in md                                          # raw agreement / κ not fabricated
    assert "No comparable human–AI pairs yet" in md            # the before-you-submit note
    # PRISMA identification disclosure: human-found claims + staged candidate refs,
    # explicitly stating NO LLM claim proposal was used (honest by default).
    assert "for PRISMA / systematic reviews" in md
    assert "No large-language-model claim proposal was used." in md


def test_methods_documents_llm_assisted_discovery_when_used(tmp_path):
    # When the LLM proposed claims (extracted_by="ai"), the methods statement must
    # disclose it under PRISMA identification — model named, role bounded to "leads".
    from citevahti.report import build_methods_markdown
    s, _ = _store(tmp_path)
    ClaimService(s).add_claim("Adjuvant therapy improves DFS.", "effectiveness",
                              extracted_by="ai", extraction_model="claude-opus-4-8")
    md = build_methods_markdown(s)
    assert "assistance of a large language model" in md
    assert "claude-opus-4-8" in md
    assert "snapshot 2026-05-01" in md                          # reproducible: version pinned, not id-only
    assert "made no eligibility or inclusion decision" in md     # role bounded
    assert "is not automated screening" in md
    assert "1 was model-proposed" in md                          # honest count, verb agrees


# ---- Word (.docx) bridge — needs the optional 'docx' extra -----------------
def test_render_docx_contains_the_claim(tmp_path):
    import pytest
    docx = pytest.importorskip("docx")          # skip cleanly without the extra
    from io import BytesIO

    from citevahti.report import render_docx
    s, _ = _store(tmp_path)
    rep = ClaimReportService(s).report()
    data = render_docx(rep)
    assert isinstance(data, bytes) and data[:2] == b"PK"   # a .docx is a zip
    doc = docx.Document(BytesIO(data))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "LDCT reduces lung-cancer mortality." in (text + "".join(
        c.text for t in doc.tables for r in t.rows for c in r.cells))


def test_export_report_docx_writes_a_file(tmp_path):
    import pytest
    pytest.importorskip("docx")
    _store(tmp_path)
    res = engine.export_report_docx(root=str(tmp_path))
    assert res["claim_count"] == 1 and res["output_file"].endswith(".docx")
    assert zipfile.is_zipfile(res["output_file"])


def test_docx_import_round_trips_to_markdown(tmp_path):
    import pytest
    docx = pytest.importorskip("docx")
    import base64
    from io import BytesIO

    d = docx.Document()
    d.add_heading("My Manuscript", level=1)
    d.add_paragraph("LDCT reduces lung-cancer mortality in high-risk adults.")
    buf = BytesIO(); d.save(buf)
    out = engine.import_manuscript_docx(base64.b64encode(buf.getvalue()).decode())
    assert out["markdown"].startswith("# My Manuscript")
    assert "LDCT reduces lung-cancer mortality" in out["markdown"]
