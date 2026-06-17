"""Stale-bond detection: has the claim text drifted out from under its evidence?

A *bond* is a claim-support rating or a final decision — an assessment formed
against a particular claim wording. Each is stamped (once, at first write) with
the ``claim_text_hash`` it was formed against. When the claim is later revised,
the claim's current hash no longer matches and the bond is **stale**: the
assessment predates the wording and should be re-checked.

This is advisory and non-destructive — exactly the "checkable advisory" model
the -vahti house shares. Nothing is invalidated automatically; the human is
simply warned that the evidence assessment may no longer fit the claim.

Status per bond:
  - ``current``  — stamped hash equals the claim's current hash;
  - ``stale``    — stamped hash differs (claim was revised since);
  - ``unknown``  — no stamp (a legacy record written before this feature). We
                   never silently call an unstamped bond ``current``.
"""

from __future__ import annotations

from typing import Optional

from ..util import claim_text_hash


def _status(rated_hash: Optional[str], current_hash: str) -> str:
    if not rated_hash:
        return "unknown"
    return "current" if rated_hash == current_hash else "stale"


def claim_bond_status(store, claim_id: str) -> dict:
    """Return the bond freshness for one claim.

    ``{claim_id, current_hash, has_stale_bonds, stale_count, unknown_count,
       bonds: [{kind, id, status, rated_hash}]}``
    where ``kind`` is ``"support_rating"`` or ``"decision"``.
    """
    claim = store.load_claim(claim_id)
    current_hash = claim_text_hash(claim.claim_text)
    bonds: list[dict] = []

    for rid in store.list_support_ratings():
        rec = store.load_support_rating(rid)
        if rec.claim_id != claim_id:
            continue
        bonds.append({"kind": "support_rating", "id": rec.rating_id,
                      "status": _status(rec.claim_text_hash, current_hash),
                      "rated_hash": rec.claim_text_hash})

    for did in store.list_decisions():
        rec = store.load_decision(did)
        if rec.claim_id != claim_id:
            continue
        bonds.append({"kind": "decision", "id": rec.decision_id,
                      "status": _status(rec.claim_text_hash, current_hash),
                      "rated_hash": rec.claim_text_hash})

    stale = sum(1 for b in bonds if b["status"] == "stale")
    unknown = sum(1 for b in bonds if b["status"] == "unknown")
    return {"claim_id": claim_id, "current_hash": current_hash,
            "has_stale_bonds": stale > 0, "stale_count": stale,
            "unknown_count": unknown, "bonds": bonds}
