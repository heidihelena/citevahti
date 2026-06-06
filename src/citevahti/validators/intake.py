"""Intake validators (step 5). Pre-decision candidate records only."""

from __future__ import annotations

from ..schemas.intake import DEDUPE_STATUSES, PROVIDERS, IntakeRecord
from .errors import ValidationError


class IntakeError(ValidationError):
    code = "intake_invalid"


def validate_intake(record: IntakeRecord, *, require_audit: bool = False) -> None:
    if record.provenance is None:
        raise IntakeError("intake record is missing provenance")
    if record.provider not in PROVIDERS:
        raise IntakeError(f"unsupported provider {record.provider!r}")
    if record.provider == "pubmed" and record.status == "ok" and not record.exact_query:
        raise IntakeError("PubMed intake must record the exact query string")

    seen_ids: dict[str, str] = {}
    for hit in record.hits:
        if hit.decision is not None:
            raise IntakeError(
                f"hit {hit.record_id!r} has a non-null decision; intake is pre-decision in step 5")
        if hit.dedupe_status not in DEDUPE_STATUSES:
            raise IntakeError(f"unsupported dedupe_status {hit.dedupe_status!r}")
        # duplicate record_ids allowed only when explicitly a within-run duplicate
        if hit.record_id in seen_ids and hit.dedupe_status != "duplicate_in_run":
            raise IntakeError(
                f"duplicate record_id {hit.record_id!r} not marked duplicate_in_run")
        seen_ids.setdefault(hit.record_id, hit.dedupe_status)

    if require_audit and not record.audit_event_id:
        raise IntakeError("staged intake file must carry an audit_event_id")
