"""The ``.citevahti/`` typed state store.

Owns the on-disk layout, atomic JSON writes, the audit log, and the invariants
that must hold at the storage boundary -- chiefly: a locked human value is never
overwritten, and every rating saved is validated against its frame.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from ..schemas.config import Config
from ..schemas.evidence_map import EvidenceMap
from ..schemas.frame import Frame
from ..schemas.rating import RatingRecord
from ..validators.rating import assert_human_value_unchanged, validate_rating_record
from .audit import AuditLog

STATE_DIRNAME = ".citevahti"


class StateError(Exception):
    code = "state_error"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)  # atomic on POSIX; never corrupts the target
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _dump(model) -> str:
    # by_alias so Link's ``from`` serializes correctly; round-trip safe.
    return json.dumps(model.model_dump(by_alias=True), ensure_ascii=False, indent=2)


class CiteVahtiStore:
    """Filesystem-backed state store rooted at ``<root>/.citevahti``."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.dir = self.root / STATE_DIRNAME
        self.audit = AuditLog(self.dir / "audit_log.jsonl")

    # ---- paths -----------------------------------------------------------
    @property
    def config_path(self) -> Path:
        return self.dir / "config.json"

    @property
    def evidence_map_path(self) -> Path:
        return self.dir / "evidence_map.json"

    def frames_dir(self) -> Path:
        return self.dir / "frames"

    def ratings_dir(self) -> Path:
        return self.dir / "ratings"

    def _subdir(self, name: str) -> Path:
        return self.dir / name

    # ---- lifecycle -------------------------------------------------------
    def exists(self) -> bool:
        return self.config_path.exists()

    def init(self, config: Optional[Config] = None) -> Config:
        """Create the layout and write a config + genesis audit entry.

        Idempotent: refuses to clobber an existing config.
        """
        if self.exists():
            raise StateError(f"{self.dir} already initialized")
        for sub in ("frames", "ratings", "snapshots", "intake", "prisma", "claims",
                    "candidates", "claim_support", "decisions", "transactions", "validation"):
            (self.dir / sub).mkdir(parents=True, exist_ok=True)
        cfg = config or Config.default()
        _atomic_write(self.config_path, _dump(cfg))
        _atomic_write(self.evidence_map_path, _dump(EvidenceMap()))
        self.audit.append("store.init", {"schema_version": cfg.schema_version})
        return cfg

    # ---- config ----------------------------------------------------------
    def load_config(self) -> Config:
        if not self.config_path.exists():
            raise StateError("config.json not found; run init() first")
        return Config.model_validate_json(self.config_path.read_text(encoding="utf-8"))

    def save_config(self, config: Config) -> None:
        _atomic_write(self.config_path, _dump(config))
        self.audit.append("config.save", {"schema_version": config.schema_version})

    # ---- frames ----------------------------------------------------------
    def save_frame(self, frame: Frame) -> None:
        path = self.frames_dir() / f"{frame.frame_id}.json"
        _atomic_write(path, _dump(frame))
        self.audit.append(
            "frame.save",
            {"frame_id": frame.frame_id, "frame_version": frame.frame_version},
        )

    def load_frame(self, frame_id: str) -> Frame:
        path = self.frames_dir() / f"{frame_id}.json"
        if not path.exists():
            raise StateError(f"frame {frame_id!r} not found")
        return Frame.model_validate_json(path.read_text(encoding="utf-8"))

    def list_frames(self) -> list[str]:
        d = self.frames_dir()
        return sorted(p.stem for p in d.glob("*.json")) if d.exists() else []

    # ---- ratings ---------------------------------------------------------
    def load_rating(self, rating_id: str) -> RatingRecord:
        path = self.ratings_dir() / f"{rating_id}.json"
        if not path.exists():
            raise StateError(f"rating {rating_id!r} not found")
        return RatingRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def save_rating(self, record: RatingRecord, frame: Optional[Frame] = None) -> None:
        """Validate and persist a rating record.

        - Validates structural + cross-field invariants (and frame keying when a
          frame is supplied or resolvable from disk).
        - Refuses to overwrite a locked, committed human value.
        """
        if frame is None:
            try:
                frame = self.load_frame(record.frame_id)
            except StateError:
                frame = None
        validate_rating_record(record, frame=frame)

        path = self.ratings_dir() / f"{record.rating_id}.json"
        if path.exists():
            existing = self.load_rating(record.rating_id)
            assert_human_value_unchanged(existing, record)
        _atomic_write(path, _dump(record))
        self.audit.append(
            "rating.save",
            {
                "rating_id": record.rating_id,
                "frame_id": record.frame_id,
                "scheme_id": record.scheme_id,
                "comparison_status": record.comparison.status,
                "has_final": record.adjudication.final_value is not None,
            },
        )

    def list_ratings(self) -> list[str]:
        d = self.ratings_dir()
        return sorted(p.stem for p in d.glob("*.json")) if d.exists() else []

    # ---- evidence map ----------------------------------------------------
    def load_evidence_map(self) -> EvidenceMap:
        if not self.evidence_map_path.exists():
            return EvidenceMap()
        return EvidenceMap.model_validate_json(
            self.evidence_map_path.read_text(encoding="utf-8")
        )

    def save_evidence_map(self, emap: EvidenceMap) -> None:
        _atomic_write(self.evidence_map_path, _dump(emap))
        self.audit.append(
            "evidence_map.save",
            {"nodes": len(emap.nodes), "links": len(emap.links),
             "attachments": len(emap.attachments)},
        )

    # ---- intake ----------------------------------------------------------
    def intake_dir(self) -> Path:
        return self.dir / "intake"

    def save_intake(self, record):
        """Validate, audit, and atomically write an intake batch.

        The audit event is appended first so its id is embedded in the staged
        file (a staged file always carries an audit_event_id).
        """
        from ..validators.intake import validate_intake

        validate_intake(record)
        entry = self.audit.append("intake.write",
                                  {"batch_id": record.batch_id, "provider": record.provider,
                                   "hits": len(record.hits)})
        record.audit_event_id = entry.hash
        path = self.intake_dir() / f"{record.batch_id}.json"
        _atomic_write(path, _dump(record))
        validate_intake(record, require_audit=True)
        return record

    def load_intake(self, batch_id: str):
        from ..schemas.intake import IntakeRecord

        path = self.intake_dir() / f"{batch_id}.json"
        if not path.exists():
            raise StateError(f"intake {batch_id!r} not found")
        return IntakeRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list_intake(self) -> list[str]:
        d = self.intake_dir()
        return sorted(p.stem for p in d.glob("*.json")) if d.exists() else []

    # ---- claims (ADR-0001, step 1) ---------------------------------------
    def claims_dir(self) -> Path:
        return self.dir / "claims"

    def save_claim(self, claim):
        """Validate, audit, and atomically write a claim.

        Audit-before-write (like intake): the event id is embedded in the file,
        so a persisted claim always carries its audit_event_id.
        """
        from ..validators.claim import validate_claim

        validate_claim(claim)
        entry = self.audit.append("claim.write",
                                  {"claim_id": claim.claim_id, "claim_type": claim.claim_type,
                                   "extracted_by": claim.extracted_by})
        claim.audit_event_id = entry.hash
        _atomic_write(self.claims_dir() / f"{claim.claim_id}.json", _dump(claim))
        validate_claim(claim, require_audit=True)
        return claim

    def load_claim(self, claim_id: str):
        from ..schemas.claim import Claim

        path = self.claims_dir() / f"{claim_id}.json"
        if not path.exists():
            raise StateError(f"claim {claim_id!r} not found")
        return Claim.model_validate_json(path.read_text(encoding="utf-8"))

    def list_claims(self) -> list[str]:
        d = self.claims_dir()
        return sorted(p.stem for p in d.glob("*.json")) if d.exists() else []

    # ---- claim ↔ paper candidates (ADR-0001, step 2) ---------------------
    def candidates_dir(self) -> Path:
        return self.dir / "candidates"

    def _commit_candidates(self, cc, event: str, payload: dict):
        """The one write path for a claim's candidate set: validate, audit, write
        atomically, then re-validate that the audit stamp landed. Both link and
        unlink go through here so the audit invariants can never drift apart."""
        from ..validators.candidate import validate_claim_candidates

        validate_claim_candidates(cc)
        cc.audit_event_id = self.audit.append(event, payload).hash
        _atomic_write(self.candidates_dir() / f"{cc.claim_id}.json", _dump(cc))
        validate_claim_candidates(cc, require_audit=True)
        return cc

    def save_candidates(self, cc):
        """Validate, audit, and atomically write a claim's candidate set."""
        return self._commit_candidates(cc, "candidate.link",
                                       {"claim_id": cc.claim_id, "candidates": len(cc.candidates)})

    def load_candidates(self, claim_id: str):
        from ..schemas.candidate import ClaimCandidates

        path = self.candidates_dir() / f"{claim_id}.json"
        if not path.exists():
            raise StateError(f"no candidates for claim {claim_id!r}")
        return ClaimCandidates.model_validate_json(path.read_text(encoding="utf-8"))

    def candidates_exist(self, claim_id: str) -> bool:
        return (self.candidates_dir() / f"{claim_id}.json").exists()

    def unlink_candidate(self, claim_id: str, candidate_id: str):
        """Drop one candidate from a claim's set, recording the removal in the
        audit chain. Non-destructive: the hash chain only grows. Only allowed
        BEFORE a verdict is recorded — a candidate with a final decision (and so
        possibly a Zotero write) must have that decision undone first, otherwise
        the decision/write would be left orphaned and the claim would still
        render its decided colour from the now-missing candidate."""
        cc = self.load_candidates(claim_id)
        if not any(c.candidate_id == candidate_id for c in cc.candidates):
            err = StateError(f"candidate {candidate_id!r} is not linked to claim {claim_id!r}")
            err.code = "candidate_not_linked"
            raise err
        if (self.decisions_dir() / f"dec-{candidate_id}.json").exists():
            err = StateError(
                f"candidate {candidate_id!r} has a recorded decision — undo the decision "
                "(and any Zotero write) before unlinking the paper")
            err.code = "candidate_decided"
            raise err
        cc.candidates = [c for c in cc.candidates if c.candidate_id != candidate_id]
        return self._commit_candidates(cc, "candidate.unlink",
                                       {"claim_id": claim_id, "candidate_id": candidate_id,
                                        "remaining": len(cc.candidates)})

    # ---- claim-support ratings (ADR-0001, step 3) ------------------------
    def claim_support_dir(self) -> Path:
        return self.dir / "claim_support"

    def save_support_rating(self, record):
        """Validate, refuse to overwrite a locked human value, audit, and write."""
        from ..validators.claim_support import (
            assert_support_human_unchanged,
            validate_claim_support_record,
        )

        validate_claim_support_record(record)
        path = self.claim_support_dir() / f"{record.rating_id}.json"
        if path.exists():
            assert_support_human_unchanged(self.load_support_rating(record.rating_id), record)
        entry = self.audit.append(
            "claim_support.save",
            {"rating_id": record.rating_id, "claim_id": record.claim_id,
             "candidate_id": record.candidate_id,
             "comparison_status": record.comparison.status,
             "has_final": record.adjudication.final_value is not None})
        record.audit_event_id = entry.hash
        _atomic_write(path, _dump(record))
        validate_claim_support_record(record, require_audit=True)
        return record

    def load_support_rating(self, rating_id: str):
        from ..schemas.claim_support import ClaimSupportRating

        path = self.claim_support_dir() / f"{rating_id}.json"
        if not path.exists():
            raise StateError(f"claim-support rating {rating_id!r} not found")
        return ClaimSupportRating.model_validate_json(path.read_text(encoding="utf-8"))

    def list_support_ratings(self) -> list[str]:
        d = self.claim_support_dir()
        return sorted(p.stem for p in d.glob("*.json")) if d.exists() else []

    # ---- final decisions (ADR-0001, step 4) ------------------------------
    def decisions_dir(self) -> Path:
        return self.dir / "decisions"

    def save_decision(self, record):
        """Validate (incl. the mission invariant), audit, and write a final decision.

        One final decision per (claim, candidate); a revision overwrites it and
        appends a new audit event (history lives in the audit log)."""
        from ..validators.decision import validate_final_decision

        validate_final_decision(record)
        entry = self.audit.append(
            "decision.final",
            {"decision_id": record.decision_id, "claim_id": record.claim_id,
             "candidate_id": record.candidate_id, "final_decision": record.final_decision,
             "final_support_status": record.final_support_status,
             "agreement_status": record.agreement_status})
        record.audit_event_id = entry.hash
        _atomic_write(self.decisions_dir() / f"{record.decision_id}.json", _dump(record))
        validate_final_decision(record, require_audit=True)
        return record

    def load_decision(self, decision_id: str):
        from ..schemas.decision import FinalDecision

        path = self.decisions_dir() / f"{decision_id}.json"
        if not path.exists():
            raise StateError(f"final decision {decision_id!r} not found")
        return FinalDecision.model_validate_json(path.read_text(encoding="utf-8"))

    def list_decisions(self) -> list[str]:
        d = self.decisions_dir()
        return sorted(p.stem for p in d.glob("*.json")) if d.exists() else []

    # ---- Zotero write transactions (ADR-0001, step 5) --------------------
    def transactions_dir(self) -> Path:
        return self.dir / "transactions"

    def save_transaction(self, txn, *, event: str = None):
        """Validate (incl. the §6 chain), audit, and write a write-transaction."""
        from ..validators.transaction import validate_transaction

        validate_transaction(txn)
        entry = self.audit.append(
            event or f"zotero.transaction.{txn.status}",
            {"transaction_id": txn.transaction_id, "kind": txn.kind, "validated": txn.validated,
             "status": txn.status, "decision_id": txn.decision_id,
             "created": len((txn.result or {}).get("created_keys") or [])})
        txn.audit_event_id = entry.hash
        _atomic_write(self.transactions_dir() / f"{txn.transaction_id}.json", _dump(txn))
        validate_transaction(txn, require_audit=True)
        return txn

    def load_transaction(self, transaction_id: str):
        from ..schemas.transaction import ZoteroTransaction

        path = self.transactions_dir() / f"{transaction_id}.json"
        if not path.exists():
            raise StateError(f"transaction {transaction_id!r} not found")
        return ZoteroTransaction.model_validate_json(path.read_text(encoding="utf-8"))

    def list_transactions(self) -> list[str]:
        d = self.transactions_dir()
        return sorted(p.stem for p in d.glob("*.json")) if d.exists() else []

    # ---- de-identified validation warehouse (ADR-0001, step 6) -----------
    def validation_dir(self) -> Path:
        return self.dir / "validation"

    def validation_records_path(self) -> Path:
        return self.validation_dir() / "records.jsonl"

    def append_validation_record(self, record):
        """Append a de-identified record (append-only; never rewrites prior lines)."""
        path = self.validation_records_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.model_dump(by_alias=True), ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        entry = self.audit.append(
            "validation.record",
            {"record_id": record.record_id, "has_claim_text": record.claim_text is not None})
        return entry

    def read_validation_records(self) -> list:
        from ..schemas.validation_record import ValidationRecord

        path = self.validation_records_path()
        if not path.exists():
            return []
        out = []
        for ln in path.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln:
                out.append(ValidationRecord.model_validate_json(ln))
        return out

    def count_validation_records(self) -> int:
        path = self.validation_records_path()
        if not path.exists():
            return 0
        return sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())

    def purge_validation(self) -> int:
        """Erase the warehouse (consent withdrawal). Returns the number removed."""
        n = self.count_validation_records()
        path = self.validation_records_path()
        if path.exists():
            path.unlink()
        self.audit.append("validation.purge", {"removed": n})
        return n

    # ---- snapshots -------------------------------------------------------
    def snapshots_dir(self) -> Path:
        return self.dir / "snapshots"

    def save_snapshot(self, record):
        entry = self.audit.append("snapshot.write",
                                  {"snapshot_id": record.snapshot_id, "items": len(record.items)})
        record.audit_event_id = entry.hash
        path = self.snapshots_dir() / f"{record.snapshot_id}.json"
        _atomic_write(path, _dump(record))
        return record

    def load_snapshot(self, snapshot_id: str):
        from ..schemas.snapshot import SnapshotRecord

        path = self.snapshots_dir() / f"{snapshot_id}.json"
        if not path.exists():
            raise StateError(f"snapshot {snapshot_id!r} not found")
        return SnapshotRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list_snapshots(self) -> list[str]:
        d = self.snapshots_dir()
        return sorted(p.stem for p in d.glob("*.json")) if d.exists() else []

    # ---- prisma ----------------------------------------------------------
    def prisma_dir(self) -> Path:
        return self.dir / "prisma"

    def save_prisma(self, record):
        from ..validators.prisma import validate_ledger

        validate_ledger(record)
        entry = self.audit.append("prisma.write",
                                  {"question_id": record.question_id,
                                   "decisions": len(record.decisions)})
        record.audit_event_id = entry.hash
        path = self.prisma_dir() / f"{record.question_id}.json"
        _atomic_write(path, _dump(record))
        return record

    def load_prisma(self, question_id: str):
        from ..schemas.prisma import PrismaLedgerRecord

        path = self.prisma_dir() / f"{question_id}.json"
        if not path.exists():
            raise StateError(f"prisma ledger {question_id!r} not found")
        return PrismaLedgerRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def prisma_exists(self, question_id: str) -> bool:
        return (self.prisma_dir() / f"{question_id}.json").exists()

    # ---- generic json (snapshots / intake / prisma) ----------------------
    def write_json(self, subdir: str, name: str, payload: dict[str, Any]) -> Path:
        if subdir not in ("snapshots", "intake", "prisma"):
            raise StateError(f"unknown subdir {subdir!r}")
        path = self._subdir(subdir) / f"{name}.json"
        _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2))
        self.audit.append(f"{subdir}.save", {"name": name})
        return path

    def read_json(self, subdir: str, name: str) -> dict[str, Any]:
        path = self._subdir(subdir) / f"{name}.json"
        if not path.exists():
            raise StateError(f"{subdir}/{name} not found")
        return json.loads(path.read_text(encoding="utf-8"))
