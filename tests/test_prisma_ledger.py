"""prisma_ledger: human-only decisions, reasons, AI-vote references, counts, export."""

import pytest

from citevahti.prisma import PrismaLedgerService
from citevahti.state import CiteVahtiStore
from citevahti.validators.prisma import PrismaError


def svc(tmp_path):
    store = CiteVahtiStore(tmp_path)
    store.init()
    return PrismaLedgerService(store), store


def ta(record_id="r1", decision="include", **kw):
    base = dict(record_id=record_id, stage="title_abstract", decision=decision, decider="human")
    base.update(kw)
    return base


def test_initializes_ledger(tmp_path):
    s, store = svc(tmp_path)
    rec = s.prisma_ledger("q1", "init")
    assert rec.status == "ok" and store.prisma_exists("q1")


def test_records_human_title_abstract_decision(tmp_path):
    s, _ = svc(tmp_path)
    s.prisma_ledger("q1", "init")
    rec = s.prisma_ledger("q1", "record_decision", ta("r1", "include"))
    assert len(rec.decisions) == 1 and rec.decisions[0].decider == "human"


def test_records_full_text_exclusion_with_reason(tmp_path):
    s, _ = svc(tmp_path)
    s.prisma_ledger("q1", "init")
    rec = s.prisma_ledger("q1", "record_decision",
                          dict(record_id="r2", stage="full_text", decision="exclude",
                               reason="wrong population", decider="human"))
    assert rec.excluded_reasons.get("wrong population") == 1


def test_rejects_exclusion_without_reason(tmp_path):
    s, _ = svc(tmp_path)
    s.prisma_ledger("q1", "init")
    with pytest.raises(PrismaError):
        s.prisma_ledger("q1", "record_decision",
                        dict(record_id="r3", stage="full_text", decision="exclude", decider="human"))


def test_rejects_ai_as_decider(tmp_path):
    s, _ = svc(tmp_path)
    s.prisma_ledger("q1", "init")
    with pytest.raises(PrismaError):
        s.prisma_ledger("q1", "record_decision", ta("r4", "include", decider="ai"))


def test_ai_vote_referenced_by_rating_id_only(tmp_path):
    s, _ = svc(tmp_path)
    s.prisma_ledger("q1", "init")
    rec = s.prisma_ledger("q1", "record_decision", {"ai_vote_rating_id": "rt-123"})
    assert rec.ai_vote_refs == ["rt-123"] and rec.decisions == []


def test_update_counts_derives_and_validates(tmp_path):
    s, _ = svc(tmp_path)
    s.prisma_ledger("q1", "init")
    s.prisma_ledger("q1", "record_decision", ta("r1", "include"))
    rec = s.prisma_ledger("q1", "update_counts", {"identified": 100})
    assert rec.counts["identified"] == 100 and rec.counts["screened"] == 1
    rec2 = s.prisma_ledger("q1", "update_counts", {"screened": 999})   # derived -> ignored
    assert rec2.counts["screened"] == 1
    assert any("screened" in w for w in rec2.warnings)


def test_export_writes_json_and_markdown(tmp_path):
    s, store = svc(tmp_path)
    s.prisma_ledger("q1", "init")
    s.prisma_ledger("q1", "record_decision", ta("r1", "include"))
    rec = s.prisma_ledger("q1", "export")
    assert len(rec.generated_files) == 2
    from pathlib import Path
    assert all(Path(f).exists() for f in rec.generated_files)
    assert any(f.endswith(".md") for f in rec.generated_files)


def test_audit_event_and_verify(tmp_path):
    s, store = svc(tmp_path)
    s.prisma_ledger("q1", "init")
    rec = s.prisma_ledger("q1", "record_decision", ta("r1", "include"))
    assert rec.audit_event_id is not None
    assert "prisma.write" in [e.event for e in store.audit.entries()]
    assert store.audit.verify() is True
