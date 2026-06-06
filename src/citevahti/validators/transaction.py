"""Transaction validators (ADR-0001 step 5) — enforce the §6 chain."""

from __future__ import annotations

from ..schemas.transaction import TRANSACTION_STATUS, ZoteroTransaction
from .errors import ValidationError


class TransactionError(ValidationError):
    code = "transaction_invalid"


def validate_transaction(txn: ZoteroTransaction, *, require_audit: bool = False) -> None:
    if txn.status not in TRANSACTION_STATUS:
        raise TransactionError(f"unsupported transaction status {txn.status!r}")
    if txn.provenance is None:
        raise TransactionError("transaction is missing provenance")
    # The §6 invariant: a VALIDATED write must carry its full chain.
    if txn.validated:
        missing = [f for f in ("claim_id", "candidate_id", "decision_id")
                   if not getattr(txn, f)]
        if missing:
            raise TransactionError(
                f"a validated write transaction is missing its chain: {missing}")
    # A committed write must have a result and an undo path (or an explicit reason none exists).
    if txn.status == "committed":
        if not txn.result:
            raise TransactionError("a committed transaction must record a result")
        if not txn.undo_snapshot:
            raise TransactionError("a committed transaction must record an undo path")
    if txn.status == "undone" and not txn.undone_at:
        raise TransactionError("an undone transaction must record undone_at")
    if require_audit and not txn.audit_event_id:
        raise TransactionError("transaction missing audit_event_id after write")
