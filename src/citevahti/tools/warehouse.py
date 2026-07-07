"""Validation warehouse, Atlas contribution, PRISMA ledger (ADR-0010 PR 1k).

The consent-governed validation-data surface: the de-identified warehouse (default-OFF;
``warehouse_configure`` is the explicit consent toggle, ``warehouse_purge`` the withdrawal),
the AtlasVahti contribution bundle/revocation builders (which BUILD locally and transmit
nothing), and the human-only PRISMA flow ledger. ``aggregate_ratings`` remains a pinned
signature awaiting its build-order step (the ``_todo`` marker moves with it, its last
caller). Ledger/config writes only; nothing leaves the machine from here.

Re-exported unchanged from ``citevahti.tools`` (frozen by tests/test_tools_public_api_stable.py).
"""

from __future__ import annotations

from typing import Optional

from ._common import _open_store


def _todo(step: int, tool: str):
    raise NotImplementedError(f"{tool}: scheduled for build order step {step}; not yet approved")


def prisma_ledger(question_id: str, action: str, payload: Optional[dict] = None, *,
                  root: Optional[str] = None):
    """Human-only PRISMA flow accounting. AI votes are rating_id references only."""
    from ..prisma import PrismaLedgerService
    return PrismaLedgerService(_open_store(root)).prisma_ledger(question_id, action, payload)


def aggregate_ratings(frame_id: str, actor_ids: Optional[list[str]] = None):
    """Refuses to aggregate across mismatched frame_version or scheme_id."""
    _todo(8, "aggregate_ratings")


def warehouse_status(*, root: Optional[str] = None):
    """De-identified validation warehouse status (read-only)."""
    from ..warehouse import ValidationWarehouseService
    return ValidationWarehouseService(_open_store(root)).status()


def warehouse_emit(claim_id: str, candidate_id: str, *, root: Optional[str] = None):
    """Emit one de-identified validation record for a (claim, candidate). No-op if disabled."""
    from ..warehouse import ValidationWarehouseService
    return ValidationWarehouseService(_open_store(root)).emit_for_decision(claim_id, candidate_id)


def warehouse_export(output_path: Optional[str] = None, *, root: Optional[str] = None):
    """Export the de-identified validation records."""
    from ..warehouse import ValidationWarehouseService
    return ValidationWarehouseService(_open_store(root)).export(output_path)


def warehouse_purge(*, root: Optional[str] = None):
    """Erase the validation warehouse (consent withdrawal)."""
    from ..warehouse import ValidationWarehouseService
    return ValidationWarehouseService(_open_store(root)).purge()


def warehouse_configure(*, enabled: Optional[bool] = None,
                        include_claim_text: Optional[bool] = None,
                        auto_emit: Optional[bool] = None, domain: Optional[str] = None,
                        root: Optional[str] = None):
    """Set the warehouse opt-ins (enable / include-claim-text / auto-emit / domain).

    The warehouse is default-off; this is the explicit consent toggle. Only the
    fields passed are changed. Returns the resulting status.
    """
    from ..warehouse import ValidationWarehouseService

    store = _open_store(root)
    cfg = store.load_config()
    wh = cfg.validation_warehouse
    if enabled is not None:
        wh.enabled = bool(enabled)
    if include_claim_text is not None:
        wh.include_claim_text = bool(include_claim_text)
    if auto_emit is not None:
        wh.auto_emit = bool(auto_emit)
    if domain is not None:
        wh.domain = domain or None
    store.save_config(cfg)
    return ValidationWarehouseService(store).status()


# ---- AtlasVahti contribution (consented, de-identified, revocable) ----------
def atlas_contribution_preview(*, allow_claim_text: bool = False,
                               root: Optional[str] = None) -> dict:
    """Build a de-identified contribution bundle from the warehouse. No transmission."""
    from ..atlas import build_contribution_bundle
    return build_contribution_bundle(root=root, allow_claim_text=allow_claim_text)


def atlas_revoke(contribution_id: str, *, reason: Optional[str] = None,
                 root: Optional[str] = None) -> dict:
    """Build a revocation (purge) request referencing a prior contribution."""
    from ..atlas import build_revocation
    return build_revocation(contribution_id, reason=reason, root=root)
