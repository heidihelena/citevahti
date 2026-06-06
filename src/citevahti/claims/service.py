"""ClaimService: create and list manuscript claims (ADR-0001, step 1).

Creating a claim records *what is asserted, where, and who/what extracted it*.
It mutates nothing in Zotero, retrieves no papers, and decides nothing -- those
are downstream steps. Every claim is stamped with provenance and audited.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .. import __version__
from ..schemas.claim import Claim
from ..schemas.common import Provenance
from ..util import config_hash, sha256_hex, utc_now_iso


class ClaimService:
    def __init__(self, store) -> None:
        self.store = store

    def _claim_id(self, claim_text: str, manuscript_location: Optional[str]) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        digest = sha256_hex(f"{claim_text}|{manuscript_location or ''}")[:8]
        return f"claim-{stamp}-{digest}"

    def add_claim(self, claim_text: str, claim_type: str = "other", *,
                  manuscript_location: Optional[str] = None,
                  manuscript_id: Optional[str] = None,
                  project_id: Optional[str] = None,
                  extracted_by: str = "human",
                  extraction_model: Optional[str] = None,
                  claim_id: Optional[str] = None) -> Claim:
        prov = Provenance(
            tool="claim_add", tool_version=__version__, ran_at=utc_now_iso(),
            config_hash=config_hash({"claim_type": claim_type, "extracted_by": extracted_by}),
            sources=[{"kind": "manuscript", "detail": manuscript_location or "unspecified"}])
        claim = Claim(
            claim_id=claim_id or self._claim_id(claim_text, manuscript_location),
            project_id=project_id, manuscript_id=manuscript_id,
            claim_text=claim_text, claim_type=claim_type,
            manuscript_location=manuscript_location,
            extracted_by=extracted_by, extraction_model=extraction_model,
            created_at=utc_now_iso(), provenance=prov)
        return self.store.save_claim(claim)

    def list_claims(self) -> list[Claim]:
        return [self.store.load_claim(cid) for cid in self.store.list_claims()]

    # ---- revision-diff: propose -> human reviews diff -> accept/reject -------
    def propose_revision(self, claim_id: str, new_text: str, *,
                         extracted_by: str = "human",
                         extraction_model: Optional[str] = None) -> Claim:
        """Attach a pending rewrite to a claim. The agent may propose (ai, model
        required); nothing is applied -- the human reviews the diff and accepts."""
        new_text = (new_text or "").strip()
        if not new_text:
            raise ValueError("proposed revision is empty")
        claim = self.store.load_claim(claim_id)
        if new_text == claim.claim_text:
            raise ValueError("proposed revision is identical to the current claim")
        if extracted_by == "ai" and not extraction_model:
            raise ValueError("an AI-proposed revision requires extraction_model (provenance)")
        claim.proposed_revision = new_text
        claim.proposed_revision_by = extracted_by
        claim.proposed_revision_model = extraction_model if extracted_by == "ai" else None
        self.store.audit.append("claim.revision_proposed",
                                {"claim_id": claim_id, "by": extracted_by})
        return self.store.save_claim(claim)

    def accept_revision(self, claim_id: str, *, expected_text: Optional[str] = None) -> Claim:
        """Apply the pending rewrite to the claim text. Human action; audited with
        the before/after so the change is never silent."""
        claim = self.store.load_claim(claim_id)
        if not claim.proposed_revision:
            raise ValueError(f"claim {claim_id!r} has no proposed revision to accept")
        if expected_text is not None and claim.proposed_revision != expected_text.strip():
            raise ValueError(
                "proposed revision changed since it was previewed; refresh and review the latest diff")
        old, new = claim.claim_text, claim.proposed_revision
        self.store.audit.append("claim.revised",
                                {"claim_id": claim_id, "from_len": len(old),
                                 "to_len": len(new), "by": claim.proposed_revision_by})
        claim.claim_text = new
        claim.proposed_revision = None
        claim.proposed_revision_by = None
        claim.proposed_revision_model = None
        return self.store.save_claim(claim)

    def reject_revision(self, claim_id: str) -> Claim:
        """Discard the pending rewrite; the claim text is unchanged. Audited."""
        claim = self.store.load_claim(claim_id)
        if not claim.proposed_revision:
            raise ValueError(f"claim {claim_id!r} has no proposed revision to reject")
        self.store.audit.append("claim.revision_rejected",
                                {"claim_id": claim_id, "by": claim.proposed_revision_by})
        claim.proposed_revision = None
        claim.proposed_revision_by = None
        claim.proposed_revision_model = None
        return self.store.save_claim(claim)
