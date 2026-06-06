"""Intake validators: provenance, exact query, decision-null, provider, dedupe ids."""

import pytest

from citevahti.schemas.common import Provenance
from citevahti.schemas.intake import IntakeHit, IntakeRecord
from citevahti.validators.intake import IntakeError, validate_intake


def prov():
    return Provenance(tool="literature_search", tool_version="0.7.0",
                      ran_at="2026-06-02T00:00:00+00:00", config_hash="abc")


def hit(record_id="pmid:1", dedupe_status="new", decision=None):
    return IntakeHit(record_id=record_id, title="t", dedupe_status=dedupe_status, decision=decision)


def record(**kw):
    base = dict(batch_id="b1", provider="pubmed", exact_query="q", provenance=prov(), hits=[])
    base.update(kw)
    return IntakeRecord(**base)


def test_valid_pubmed_record_passes():
    validate_intake(record(hits=[hit()]))


def test_rejects_pubmed_without_exact_query():
    with pytest.raises(IntakeError):
        validate_intake(record(exact_query=None))


def test_rejects_non_null_decision():
    with pytest.raises(IntakeError):
        validate_intake(record(hits=[hit(decision="include")]))


def test_rejects_unsupported_provider():
    with pytest.raises(IntakeError):
        validate_intake(record(provider="scopus"))


def test_rejects_unsupported_dedupe_status():
    with pytest.raises(IntakeError):
        validate_intake(record(hits=[hit(dedupe_status="maybe")]))


def test_rejects_missing_provenance():
    with pytest.raises(IntakeError):
        validate_intake(record(provenance=None))


def test_rejects_duplicate_ids_unless_duplicate_in_run():
    with pytest.raises(IntakeError):
        validate_intake(record(hits=[hit(record_id="pmid:1"), hit(record_id="pmid:1")]))
    # allowed when the second is explicitly a within-run duplicate
    validate_intake(record(hits=[hit(record_id="pmid:1"),
                                 hit(record_id="pmid:1", dedupe_status="duplicate_in_run")]))


def test_require_audit_flag():
    rec = record(hits=[hit()])
    with pytest.raises(IntakeError):
        validate_intake(rec, require_audit=True)   # no audit_event_id yet
    rec.audit_event_id = "deadbeef"
    validate_intake(rec, require_audit=True)


def test_manual_record_without_exact_query_is_ok():
    validate_intake(record(provider="manual", exact_query=None, source_label="x"))
