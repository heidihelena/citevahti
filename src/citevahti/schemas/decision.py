"""Final decision per (claim, candidate) — ADR-0001 step 4.

One candidate may carry many ratings, but exactly one *final decision*: the
human-owned terminal judgment on whether the paper is accepted as evidence for
the claim. It records the final support status it rests on, the human/AI
agreement status, who decided, and why. This is the object the decision-gated
Zotero write (step 5) will require: no final decision, no validated write.

The mission invariant lives here (enforced in validators): you cannot **accept**
a citation whose final support judgment does not actually support the claim.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .. import SCHEMA_VERSION
from .claim_support import SUPPORT_VALUES
from .common import Provenance
from .rating import ComparisonStatus

# The terminal decision vocabulary (manifesto).
FINAL_DECISIONS = ("accept", "reject", "needs_second_review", "accepted_with_caution")

# Support values that actually support the claim (the only ones an 'accept' may rest on).
SUPPORTING_VALUES = ("directly_supports", "partially_supports", "indirectly_supports")


class FinalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    decision_id: str
    claim_id: str
    candidate_id: str
    rating_id: Optional[str] = None                    # the claim-support rating it rests on
    final_support_status: Optional[Literal[SUPPORT_VALUES]] = None  # type: ignore[valid-type]
    final_decision: Literal[FINAL_DECISIONS]           # type: ignore[valid-type]
    agreement_status: Optional[ComparisonStatus] = None
    decided_by: str = "human"
    decision_reason: Optional[str] = None
    created_at: Optional[str] = None
    provenance: Optional[Provenance] = None
    # The claim_text_hash this decision was made against, stamped once at first
    # write. After a claim revision, current hash != this → the decision is stale
    # (made on the previous wording). Optional/legacy-safe. See claims/bonds.py.
    claim_text_hash: Optional[str] = None
    audit_event_id: Optional[str] = None
