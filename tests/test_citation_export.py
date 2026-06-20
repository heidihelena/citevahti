"""Cite-stable export: a durable [@citekey] for each accepted claim + a matching .bib.

The embedded key is the citation's portable form — it survives copy-paste and a
Pandoc Markdown→Word conversion. These tests pin that acceptance drives injection,
that it is idempotent, that non-accepted / reworded claims are NOT silently cited,
and that the bibliography is built from the accepted papers' identifiers.
"""

from citevahti.claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
    DecisionService,
    FakeClaimSupportRater,
)
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.report.citation_export import (
    CitationExportService,
    bib_entry,
    mint_citekey,
)
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


CLAIM = "LDCT reduces lung-cancer mortality."


def _store_with_accepted(tmp_path, claim_text=CLAIM, pmid="21714641",
                         doi="10.1056/NEJMoa1102873"):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_config(_pin(store.load_config()))
    claim = ClaimService(store).add_claim(claim_text, "effectiveness")
    batch = IntakeService(
        store, provider=_Provider([ProviderHit(pmid=pmid, doi=doi, title="NLST",
                                               journal="N Engl J Med", year=2011)]),
        library_index=StaticLibraryIndex()).literature_search("ldct", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="directly_supports"))
    rec = eng.support_start(claim.claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.support_compare(rec.rating_id)
    DecisionService(store).decide(claim.claim_id, cand_id, "accept", "supports",
                                  rating_id=rec.rating_id)
    return store, claim


# ---- unit: key + bib -------------------------------------------------------
def test_mint_citekey_prefers_pmid_then_doi_else_none():
    assert mint_citekey("21714641", "10.1/x") == "pmid21714641"
    assert mint_citekey(None, "10.1056/NEJMoa1102873") == "doi101056nejmoa1102873"
    assert mint_citekey(None, None) is None              # never invents a key


def test_bib_entry_has_key_and_identifier():
    e = bib_entry("pmid21714641", title="NLST", journal="NEJM", year=2011,
                  doi="10.1/x", pmid="21714641")
    assert e.startswith("@article{pmid21714641,")
    assert "doi = {10.1/x}" in e and "PMID: 21714641" in e


# ---- injection -------------------------------------------------------------
def test_injects_citation_for_accepted_claim_and_builds_bib(tmp_path):
    store, _ = _store_with_accepted(tmp_path)
    md = f"Background. {CLAIM} Further discussion follows."
    res = CitationExportService(store).export(md)
    assert res.injected == 1 and res.skipped == 0
    assert f"{CLAIM} [@pmid21714641]" in res.annotated_markdown
    assert "@article{pmid21714641," in res.bibtex
    assert res.entries[0].status == "injected"


def test_injection_is_idempotent(tmp_path):
    store, _ = _store_with_accepted(tmp_path)
    md = f"{CLAIM}"
    once = CitationExportService(store).export(md).annotated_markdown
    twice = CitationExportService(store).export(once)
    assert twice.annotated_markdown == once                 # no second [@key]
    assert once.count("[@pmid21714641]") == 1
    assert twice.entries[0].status == "already_present"
    assert twice.injected == 1                              # still counts as present


def test_unaccepted_claim_is_not_cited(tmp_path):
    # a claim with candidates but no accepting decision must not be cited
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_config(_pin(store.load_config()))
    ClaimService(store).add_claim(CLAIM, "effectiveness")
    res = CitationExportService(store).export(f"Intro. {CLAIM}")
    assert res.injected == 0
    assert "[@" not in res.annotated_markdown and res.bibtex == ""


def test_claim_text_absent_from_manuscript_warns_and_skips(tmp_path):
    store, _ = _store_with_accepted(tmp_path)
    res = CitationExportService(store).export("A manuscript that never states the claim.")
    assert res.injected == 0 and res.entries[0].status == "not_located"
    assert any("not found in the manuscript" in w for w in res.warnings)


class _FakeBbt:
    """Stands in for the Better BibTeX JSON-RPC client (item.search)."""

    def __init__(self, items):
        self.items = items

    def jsonrpc(self, method, params):
        return self.items


def test_bbt_keyed_mode_uses_the_users_own_citekey(tmp_path):
    from citevahti.report.citation_export import BbtCitekeySource
    store, _ = _store_with_accepted(tmp_path)
    src = BbtCitekeySource(_FakeBbt([
        {"citekey": "andersen2011nlst", "DOI": "10.1056/NEJMoa1102873"}]))
    res = CitationExportService(store).export(CLAIM, citekey_source=src)
    assert "[@andersen2011nlst]" in res.annotated_markdown      # the user's key, not minted
    assert res.entries[0].key_source == "bbt"
    assert "@article{andersen2011nlst," in res.bibtex


def test_bbt_no_confirmed_match_falls_back_to_minted(tmp_path):
    from citevahti.report.citation_export import BbtCitekeySource
    store, _ = _store_with_accepted(tmp_path)
    src = BbtCitekeySource(_FakeBbt([]))                         # BBT confirms nothing
    res = CitationExportService(store).export(CLAIM, citekey_source=src)
    assert "[@pmid21714641]" in res.annotated_markdown
    assert res.entries[0].key_source == "minted"


def test_write_outputs_writes_md_and_bib(tmp_path):
    from citevahti.report.citation_export import write_outputs
    store, _ = _store_with_accepted(tmp_path)
    ms = tmp_path / "draft.md"
    ms.write_text(f"Intro. {CLAIM} End.")
    res = CitationExportService(store).export(ms.read_text())
    info = write_outputs(res, str(ms), make_docx=True)
    assert (tmp_path / "draft.cited.md").exists()
    assert (tmp_path / "references.bib").exists() and info["bib_path"]
    assert info["docx_status"] is not None        # attempted (ok / pandoc_not_found / failed)


def test_reworded_claim_is_not_silently_cited(tmp_path):
    # The honesty differentiator: a citation accepted against the OLD wording must not
    # silently follow the claim after it's reworded (stale bond).
    store, claim = _store_with_accepted(tmp_path)
    c = store.load_claim(claim.claim_id)
    c.claim_text = "LDCT cuts lung-cancer deaths in a high-risk screening population."
    store.save_claim(c)
    res = CitationExportService(store).export(c.claim_text)
    assert res.injected == 0 and res.entries[0].status == "stale"
    assert "[@" not in res.annotated_markdown
    assert any("reworded" in w for w in res.warnings)
