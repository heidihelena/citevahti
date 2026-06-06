"""TransactionService (ADR-0001 step 5): decision-gated, undoable Zotero writes.

A *validated* write is the terminal step of the ledger: it exists only when a
final ACCEPT decision does, and it always produces a durable transaction with an
undo path. This enforces the §6 invariant — one claim, one paper, one decision,
one provenance, one transaction, one audit trail, one undo path — or no write.

It reuses the guarded WriteLayer (dry-run preview, one-use token, audit, honest
degradation, capability checks) for the actual apply; the transaction wraps it
with status + undo_snapshot + the claim/candidate/decision links.
"""

from __future__ import annotations

import uuid
from typing import Optional

from .. import __version__
from ..schemas.common import Provenance
from ..schemas.transaction import ZoteroTransaction
from ..schemas.writeback import WriteOperation
from ..util import config_hash, sha256_hex, utc_now_iso
from .backend import WriteUnavailable
from .layer import WriteLayer

# A validated reference may be written only for these final decisions.
_WRITABLE_DECISIONS = ("accept", "accepted_with_caution")


class TransactionError(Exception):
    code = "transaction_error"


class TransactionService:
    def __init__(self, store, backend) -> None:
        self.store = store
        self.backend = backend
        self.layer = WriteLayer(store, backend)

    def _prov(self, kind: str) -> Provenance:
        return Provenance(tool="zotero_transaction", tool_version=__version__,
                          ran_at=utc_now_iso(),
                          config_hash=config_hash({"kind": kind, "backend": self.backend.kind}),
                          sources=[{"kind": "writeback", "detail": self.backend.kind}])

    def _candidate(self, claim_id: str, candidate_id: str):
        cc = self.store.load_candidates(claim_id)        # raises StateError if none
        for c in cc.candidates:
            if c.candidate_id == candidate_id:
                return c
        raise TransactionError(f"candidate {candidate_id!r} not linked to claim {claim_id!r}")

    def _find_existing(self, pmid, doi):
        """Keys already in the write target, or `[]` (verified absent), or `None`
        (could-not-check — the write target was queryable but the search failed).

        A legacy/no-capability or unavailable backend returns `[]`: the write
        itself will fail (or is a non-target backend), so we don't double-flag.
        An available backend that genuinely can't verify returns `None`, which the
        caller treats as `dedupe_unverified` (refuse unless explicitly overridden).
        """
        fn = getattr(self.backend, "find_existing", None)
        if not callable(fn) or not getattr(self.backend, "available", False):
            return []
        try:
            return fn(pmid, doi)          # None | [] | [keys]
        except Exception:  # noqa: BLE001 (a dedupe-check failure must never crash the write path)
            return None

    def _failed_txn(self, op, decision, collection_key, library, code, remediation, result=None):
        txn = ZoteroTransaction(
            transaction_id=f"txn-{uuid.uuid4().hex[:10]}", kind=op.kind, validated=True,
            status="failed", library=str(library), collection_key=collection_key,
            claim_id=decision.claim_id, candidate_id=decision.candidate_id,
            decision_id=decision.decision_id, proposed_changes=op.proposed_changes,
            result=result or {}, error_code=code, remediation=remediation,
            provenance=self._prov(op.kind), created_at=utc_now_iso())
        return self.store.save_transaction(txn)

    @staticmethod
    def _metadata(candidate) -> dict:
        return {"record_id": candidate.candidate_id, "doi": candidate.doi, "pmid": candidate.pmid,
                "title": candidate.title, "authors": [], "journal": candidate.journal,
                "year": candidate.year, "publication_date": candidate.publication_date}

    # ---- validated, decision-gated write --------------------------------
    def commit_for_decision(self, decision_id: str, *, collection_key: Optional[str] = None,
                            library: str = "personal", dry_run: bool = True,
                            confirm_token: Optional[str] = None,
                            allow_unverified_dedupe: bool = False):
        decision = self.store.load_decision(decision_id)
        if decision.final_decision not in _WRITABLE_DECISIONS:
            raise TransactionError(
                f"decision {decision_id!r} is {decision.final_decision!r}; only "
                f"{_WRITABLE_DECISIONS} may be written to Zotero")
        candidate = self._candidate(decision.claim_id, decision.candidate_id)
        # anti-fabrication: never write a reference without a real identifier
        if not (candidate.pmid or candidate.doi):
            raise TransactionError(
                "candidate has neither PMID nor DOI; refusing to write an unverifiable citation")

        # cross-boundary dedupe: re-check the WRITE TARGET (Web API), not just the
        # local library, so a Web-API-created item not yet synced locally is caught.
        existing = self._find_existing(candidate.pmid, candidate.doi)

        metadata = self._metadata(candidate)
        op = WriteOperation(
            kind="item_add", library=str(library), targets=[],
            payload={"metadata_hash": sha256_hex(repr(sorted(metadata.items()))),
                     "collection_key": collection_key, "decision_id": decision_id},
            proposed_changes=[f"create verified item {metadata.get('title') or '(untitled)'!r} "
                              f"for claim {decision.claim_id} (decision: {decision.final_decision})"],
            structured={"create": [metadata], "skipped": [], "collection_key": collection_key})

        if dry_run:
            diff = self.layer.preview(op)            # ephemeral WriteDiff; no transaction yet
            if existing:
                diff.warnings.append(
                    f"already in the Zotero library as {existing}; a confirmed write "
                    "would be refused as a duplicate")
            elif existing is None:
                diff.warnings.append(
                    "dedupe_unverified: could not confirm the paper isn't already in the "
                    "library; a confirmed write would be refused unless explicitly overridden")
            return diff

        # ---- agent-write boundary: a confirmed write needs a prior preview's token.
        # This stops a one-call API write (tools.commit_decision(dry_run=False)) from
        # ever reaching Zotero without a user-visible preview/approval step.
        if not confirm_token:
            return self._failed_txn(
                op, decision, collection_key, library, "missing_confirm_token",
                "a confirmation token from a prior dry-run preview is required; preview "
                "first (the human/agent-visible approval step), then commit with that token")

        # ---- confirmed duplicate on the write target -> refuse (no dup across sync)
        if existing:
            return self._failed_txn(
                op, decision, collection_key, library, "duplicate_on_write_target",
                f"already in the Zotero library as {existing}; not written. Merge or cite "
                "the existing item instead.", result={"duplicate_keys": existing})

        # ---- dedupe could not be verified -> refuse unless explicitly overridden
        if existing is None and not allow_unverified_dedupe:
            return self._failed_txn(
                op, decision, collection_key, library, "dedupe_unverified",
                "could not verify the paper isn't already in the library (Zotero search "
                "unavailable); re-run when reachable, or pass allow_unverified_dedupe to override")

        res = self.layer.apply(op, confirm_token)
        created = (res.result or {}).get("created_keys") or []
        txn = ZoteroTransaction(
            transaction_id=f"txn-{uuid.uuid4().hex[:10]}", kind=op.kind, validated=True,
            status="committed" if res.applied else "failed", library=str(library),
            collection_key=collection_key, claim_id=decision.claim_id,
            candidate_id=decision.candidate_id, decision_id=decision_id,
            proposed_changes=op.proposed_changes, result=res.result,
            undo_snapshot=({"delete_keys": created, "library": str(library),
                            "collection_key": collection_key} if res.applied else {}),
            error_code=res.error_code, remediation=res.remediation, provenance=self._prov(op.kind),
            created_at=utc_now_iso(),
            committed_at=utc_now_iso() if res.applied else None)
        return self.store.save_transaction(txn)

    # ---- undo ------------------------------------------------------------
    def undo(self, transaction_id: str) -> ZoteroTransaction:
        txn = self.store.load_transaction(transaction_id)
        if txn.status != "committed":
            raise TransactionError(
                f"transaction {transaction_id!r} is {txn.status!r}; only a committed write can be undone")
        try:
            result = self.backend.undo(txn.undo_snapshot)
        except WriteUnavailable as exc:
            txn.error_code = "undo_unavailable"
            txn.remediation = str(exc)
            return self.store.save_transaction(txn, event="zotero.transaction.undo_failed")
        txn.status = "undone"
        txn.undone_at = utc_now_iso()
        txn.result = {**txn.result, "undo": result}
        txn.error_code = None
        txn.remediation = None
        return self.store.save_transaction(txn)

    def get(self, transaction_id: str) -> ZoteroTransaction:
        return self.store.load_transaction(transaction_id)

    def list(self) -> list[ZoteroTransaction]:
        return [self.store.load_transaction(t) for t in self.store.list_transactions()]
