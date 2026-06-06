"""De-identified validation warehouse (ADR-0001 step 6): opt-in, bounded, append-only.

Hard guarantees: nothing is collected unless explicitly enabled; records carry no
identity / manuscript text / Zotero keys / project ids; claim text appears only on
a second opt-in; records are append-only; the warehouse can be purged.
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
from citevahti.state import CiteVahtiStore
from citevahti.warehouse import ValidationWarehouseService


class _Provider:
    name = "pubmed"

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=self.hits, count=len(self.hits),
                                    email_present=True, rate_tier="3rps")


CLAIM_TEXT = "Low-dose CT screening reduces lung-cancer mortality in high-risk adults."


def _setup(tmp_path, *, enabled=False, include_claim_text=False, auto_emit=False):
    store = CiteVahtiStore(tmp_path)
    store.init()
    cfg = store.load_config()
    cfg.validation_warehouse.enabled = enabled
    cfg.validation_warehouse.include_claim_text = include_claim_text
    cfg.validation_warehouse.auto_emit = auto_emit
    store.save_config(cfg)
    claim = ClaimService(store).add_claim(CLAIM_TEXT, "effectiveness")
    batch = IntakeService(store, provider=_Provider(
        [ProviderHit(pmid="21714641", doi="10.1056/NEJMoa1102873", title="NLST")]),
        library_index=StaticLibraryIndex()).literature_search("ldct", question_id="q1")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id
    eng = ClaimSupportEngine(store, rater=FakeClaimSupportRater(value="directly_supports"))
    rec = eng.support_start(claim.claim_id, cand_id)
    eng.support_commit_human(rec.rating_id, "directly_supports")
    eng.support_compare(rec.rating_id)
    DecisionService(store).decide(claim.claim_id, cand_id, "accept", "supports",
                                  rating_id=rec.rating_id)
    return store, claim.claim_id, cand_id


# ---- opt-in / default off --------------------------------------------------
def test_disabled_by_default_emits_nothing(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, enabled=False)
    rep = ValidationWarehouseService(store).emit_for_decision(claim_id, cand_id)
    assert rep.enabled is False and rep.skipped_reason == "warehouse_disabled"
    assert store.count_validation_records() == 0


def test_enabled_emits_a_record(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, enabled=True)
    rep = ValidationWarehouseService(store).emit_for_decision(claim_id, cand_id)
    assert rep.emitted and rep.record_count == 1
    rec = store.read_validation_records()[0]
    assert rec.final_decision == "accept"
    assert rec.final_support_status == "directly_supports"
    assert rec.human_support_rating == "directly_supports"
    assert rec.pmid == "21714641" and rec.doi == "10.1056/NEJMoa1102873"
    assert rec.claim_type == "effectiveness"


# ---- privacy boundary ------------------------------------------------------
def test_record_is_deidentified_no_claim_text_by_default(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, enabled=True, include_claim_text=False)
    ValidationWarehouseService(store).emit_for_decision(claim_id, cand_id)
    rec = store.read_validation_records()[0]
    blob = rec.model_dump_json()
    assert rec.claim_text is None                      # top-sensitivity tier withheld
    assert CLAIM_TEXT not in blob                      # the text never appears
    assert rec.claim_text_hash                          # but a one-way hash is kept
    # no project-internal ids / zotero keys leak into the reusable record
    assert claim_id not in blob and cand_id not in blob


def test_claim_text_included_only_on_second_optin(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, enabled=True, include_claim_text=True)
    ValidationWarehouseService(store).emit_for_decision(claim_id, cand_id)
    rec = store.read_validation_records()[0]
    assert rec.claim_text == CLAIM_TEXT


# ---- append-only + purge ---------------------------------------------------
def test_records_are_append_only(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, enabled=True)
    svc = ValidationWarehouseService(store)
    svc.emit_for_decision(claim_id, cand_id)
    svc.emit_for_decision(claim_id, cand_id)           # a correction appends, never rewrites
    assert store.count_validation_records() == 2
    ids = [r.record_id for r in store.read_validation_records()]
    assert len(set(ids)) == 2


def test_purge_erases_and_audits(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, enabled=True)
    ValidationWarehouseService(store).emit_for_decision(claim_id, cand_id)
    rep = ValidationWarehouseService(store).purge()
    assert store.count_validation_records() == 0
    assert "purged" in rep.skipped_reason
    assert "validation.purge" in [e.event for e in store.audit.entries()]


def test_emit_is_audited_and_chain_verifies(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, enabled=True)
    ValidationWarehouseService(store).emit_for_decision(claim_id, cand_id)
    assert "validation.record" in [e.event for e in store.audit.entries()]
    assert store.audit.verify() is True


def test_export_writes_records(tmp_path):
    store, claim_id, cand_id = _setup(tmp_path, enabled=True)
    ValidationWarehouseService(store).emit_for_decision(claim_id, cand_id)
    rep = ValidationWarehouseService(store).export()
    assert rep.output_file and rep.record_count == 1


# ---- auto-emit via the tools layer -----------------------------------------
def test_auto_emit_on_decide_when_enabled(tmp_path):
    import citevahti.tools as tools
    store, claim_id, cand_id = _setup(tmp_path, enabled=True, auto_emit=True)
    rid = store.list_support_ratings()[0]
    before = store.count_validation_records()
    # re-deciding through the tools layer triggers an auto-emit
    tools.decide(claim_id, cand_id, "accept", "still supports", rating_id=rid, root=str(tmp_path))
    assert store.count_validation_records() == before + 1


def test_no_auto_emit_when_warehouse_disabled(tmp_path):
    import citevahti.tools as tools
    store, claim_id, cand_id = _setup(tmp_path, enabled=False, auto_emit=True)
    rid = store.list_support_ratings()[0]
    tools.decide(claim_id, cand_id, "accept", "supports", rating_id=rid, root=str(tmp_path))
    assert store.count_validation_records() == 0       # disabled wins over auto_emit
