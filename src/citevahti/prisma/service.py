"""PrismaLedgerService: init / record_decision / update_counts / export."""

from __future__ import annotations

import json
from collections import Counter
from typing import Optional

from .. import __version__
from ..schemas.common import Provenance
from ..schemas.prisma import PrismaDecision, PrismaLedgerRecord
from ..state.store import _atomic_write
from ..util import config_hash, utc_now_iso
from ..validators.prisma import PrismaError, validate_decision

_DERIVED_KEYS = {"screened", "assessed", "included", "excluded"}


class PrismaLedgerService:
    def __init__(self, store) -> None:
        self.store = store

    def _prov(self, question_id, action) -> Provenance:
        return Provenance(tool="prisma_ledger", tool_version=__version__, ran_at=utc_now_iso(),
                          config_hash=config_hash({"question_id": question_id, "action": action}),
                          sources=[{"kind": "local_state", "detail": "human screening decisions"}])

    def prisma_ledger(self, question_id: str, action: str,
                      payload: Optional[dict] = None) -> PrismaLedgerRecord:
        payload = payload or {}
        if action == "init":
            return self._init(question_id)
        rec = self.store.load_prisma(question_id)
        rec.provenance = self._prov(question_id, action)
        if action == "record_decision":
            self._record_decision(rec, payload)
        elif action == "update_counts":
            self._update_counts(rec, payload)
        elif action == "export":
            return self._export(rec)
        else:
            raise PrismaError(f"unknown action {action!r}")
        rec.updated_at = utc_now_iso()
        self._recompute(rec)
        return self.store.save_prisma(rec)

    # ---- actions ---------------------------------------------------------
    def _init(self, question_id: str) -> PrismaLedgerRecord:
        if self.store.prisma_exists(question_id):
            raise PrismaError(f"PRISMA ledger {question_id!r} already initialized")
        now = utc_now_iso()
        rec = PrismaLedgerRecord(question_id=question_id, created_at=now, updated_at=now,
                                 counts={}, provenance=self._prov(question_id, "init"))
        return self.store.save_prisma(rec)

    def _record_decision(self, rec: PrismaLedgerRecord, payload: dict) -> None:
        # AI screening votes are referenced by rating_id ONLY -- never a decision.
        if payload.get("ai_vote_rating_id"):
            rid = str(payload["ai_vote_rating_id"])
            if rid not in rec.ai_vote_refs:
                rec.ai_vote_refs.append(rid)
            return
        if payload.get("decider") == "ai":
            raise PrismaError("AI cannot be a decider; reference AI votes by rating_id instead")
        decision = PrismaDecision(
            record_id=payload["record_id"], stage=payload["stage"],
            decision=payload["decision"], reason=payload.get("reason"),
            decider=payload.get("decider", "human"),
            decided_at=payload.get("decided_at") or utc_now_iso(), notes=payload.get("notes"))
        validate_decision(decision)   # rejects AI decider, bad stage/decision, missing reason
        rec.decisions.append(decision)

    def _update_counts(self, rec: PrismaLedgerRecord, payload: dict) -> None:
        # Accept externally-known counts (e.g. identified), but never let the
        # caller silently override decision-derived counts.
        for k, v in payload.items():
            if k in _DERIVED_KEYS:
                rec.warnings.append(f"ignoring '{k}': derived from decisions, not set manually")
                continue
            rec.counts[k] = v

    def _recompute(self, rec: PrismaLedgerRecord) -> None:
        ta = {d.record_id for d in rec.decisions if d.stage == "title_abstract"}
        ft = [d for d in rec.decisions if d.stage == "full_text"]
        rec.counts["screened"] = len(ta)
        rec.counts["assessed"] = len({d.record_id for d in ft})
        rec.counts["included"] = len([d for d in ft if d.decision == "include"])
        rec.counts["excluded"] = len([d for d in rec.decisions if d.decision == "exclude"])
        rec.excluded_reasons = dict(Counter(
            d.reason for d in rec.decisions if d.decision == "exclude" and d.reason))

    def _export(self, rec: PrismaLedgerRecord) -> PrismaLedgerRecord:
        self._recompute(rec)
        rec.updated_at = utc_now_iso()
        base = self.store.prisma_dir()
        base.mkdir(parents=True, exist_ok=True)
        json_path = base / f"{rec.question_id}-export.json"
        md_path = base / f"{rec.question_id}-summary.md"
        _atomic_write(json_path, json.dumps(rec.model_dump(), ensure_ascii=False, indent=2))
        _atomic_write(md_path, self._markdown(rec))
        rec.generated_files = [json_path.as_posix(), md_path.as_posix()]
        return self.store.save_prisma(rec)

    @staticmethod
    def _markdown(rec: PrismaLedgerRecord) -> str:
        lines = [f"# PRISMA flow — {rec.question_id}", "",
                 "## Counts", ""]
        for k, v in rec.counts.items():
            lines.append(f"- **{k}**: {v}")
        if rec.excluded_reasons:
            lines += ["", "## Exclusion reasons", ""]
            for reason, n in rec.excluded_reasons.items():
                lines.append(f"- {reason}: {n}")
        lines += ["", f"_Human decisions: {len(rec.decisions)}; "
                  f"AI vote references (metrics only): {len(rec.ai_vote_refs)}_"]
        return "\n".join(lines) + "\n"
