"""De-identified validation warehouse (ADR-0001 step 6) — opt-in, default-off.

Turns the *workflow itself* into reusable labels: when enabled, a final decision
(plus its claim-support rating) becomes one append-only, de-identified
ValidationRecord — claim_type + one-way claim-text hash + public paper id +
AI/human/final ratings + PICO fit + agreement. It NEVER writes identity,
manuscript text, Zotero keys, or project-internal ids. Claim text itself is the
top-sensitivity tier, stored only on a second explicit opt-in. The warehouse is
default-off and purgeable per project (consent withdrawal).
"""

from __future__ import annotations

import uuid
from typing import Optional

from .schemas.validation_record import ValidationRecord, WarehouseReport
from .util import claim_text_hash as _claim_text_hash
from .util import utc_now_iso


class ValidationWarehouseService:
    def __init__(self, store, config=None) -> None:
        self.store = store
        self.config = config or store.load_config()
        self.cfg = self.config.validation_warehouse

    # ---- status / export / purge ----------------------------------------
    def status(self) -> WarehouseReport:
        return WarehouseReport(enabled=self.cfg.enabled,
                               include_claim_text=self.cfg.include_claim_text,
                               record_count=self.store.count_validation_records())

    def purge(self) -> WarehouseReport:
        removed = self.store.purge_validation()
        return WarehouseReport(enabled=self.cfg.enabled,
                               include_claim_text=self.cfg.include_claim_text,
                               record_count=0, skipped_reason=f"purged {removed} record(s)")

    def export(self, output_path: Optional[str] = None) -> WarehouseReport:
        import json
        from pathlib import Path

        records = self.store.read_validation_records()
        out = (Path(output_path) if output_path
               else self.store.validation_dir() / "export.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps([r.model_dump() for r in records], indent=2, ensure_ascii=False),
                       encoding="utf-8")
        return WarehouseReport(enabled=self.cfg.enabled,
                               include_claim_text=self.cfg.include_claim_text,
                               record_count=len(records), output_file=out.as_posix())

    # ---- emit ------------------------------------------------------------
    def _support_rating_for(self, claim_id: str, candidate_id: str):
        match = None
        for rid in self.store.list_support_ratings():
            r = self.store.load_support_rating(rid)
            if r.claim_id == claim_id and r.candidate_id == candidate_id:
                match = r       # keep last (most recently listed)
        return match

    def emit_for_decision(self, claim_id: str, candidate_id: str) -> WarehouseReport:
        if not self.cfg.enabled:
            return WarehouseReport(enabled=False, skipped_reason="warehouse_disabled")

        claim = self.store.load_claim(claim_id)
        cc = self.store.load_candidates(claim_id)
        candidate = next((c for c in cc.candidates if c.candidate_id == candidate_id), None)
        if candidate is None:
            return WarehouseReport(enabled=True, skipped_reason="candidate_not_found")
        try:
            decision = self.store.load_decision(f"dec-{candidate_id}")
        except Exception:  # noqa: BLE001
            return WarehouseReport(enabled=True, skipped_reason="no_final_decision")

        rating = self._support_rating_for(claim_id, candidate_id)
        human = rating.human_rating if rating else None
        ai = rating.ai_rating if rating else None
        fit = (human.fit if human else (ai.fit if ai else None))

        record = ValidationRecord(
            record_id=f"vr-{uuid.uuid4().hex[:12]}", created_at=utc_now_iso(),
            claim_type=claim.claim_type, claim_text_hash=_claim_text_hash(claim.claim_text),
            claim_text=(claim.claim_text if self.cfg.include_claim_text else None),
            domain=self.cfg.domain or claim.claim_type,
            pmid=candidate.pmid, doi=candidate.doi, study_type=None,
            ai_support_rating=(ai.value if ai else None),
            ai_confidence=(ai.confidence if ai else None),
            human_support_rating=(human.value if human else None),
            final_support_status=decision.final_support_status,
            final_decision=decision.final_decision,
            agreement_status=decision.agreement_status,
            population_fit=(fit.population_fit if fit else None),
            intervention_fit=(fit.intervention_fit if fit else None),
            outcome_fit=(fit.outcome_fit if fit else None),
            claim_fit=(fit.claim_fit if fit else None))
        entry = self.store.append_validation_record(record)
        return WarehouseReport(
            enabled=True, include_claim_text=self.cfg.include_claim_text,
            record_count=self.store.count_validation_records(), emitted=record.record_id,
            audit_event_id=entry.hash)
