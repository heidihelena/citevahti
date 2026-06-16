"""AtlasVahti contribution — the consented, de-identified warehouse → corpus path.

This is the one genuinely outward-facing capability, so it is built to never
surprise anyone (mirrors MatchVahti A16):

  * **De-identification is enforced, not assumed.** ``assert_poolable`` raises on
    any record that carries claim text without the sensitive opt-in, or any field
    outside the de-identified ``ValidationRecord`` shape. ``build_contribution_bundle``
    runs it over every record and refuses to build on any leak.
  * **Nothing is transmitted here.** This module only *builds* a bundle (records +
    a consent receipt + a content hash + a derived ``contribution_id``) and a
    revocation request. Actual upload is a separate, explicitly-confirmed action to
    an endpoint the operator configures — there is no hardcoded corpus URL.
  * **Revocable.** Every bundle carries an id; ``build_revocation`` emits a purge
    request referencing it.

Pseudonymization, not anonymization: the claim hash is one-way but a short claim
is re-identifiable. The real corpus re-hashes client hashes with a server-side
salted HMAC (the blind index) and enforces k >= 5 — that is where the privacy
guarantee lives. The consent receipt says so.
"""

from __future__ import annotations

from typing import Optional

from .schemas.validation_record import ValidationRecord
from .state.store import CiteVahtiStore
from .util import canonical_json, sha256_hex, utc_now_iso


class ContributionError(Exception):
    """A poolable-record invariant was violated — refuse to build/transmit."""

    code = "contribution_unsafe"


# The de-identified contract: exactly the fields a ValidationRecord may carry into
# the shared corpus. Anything outside this set is a leak; ``claim_text`` is allowed
# ONLY under the sensitive opt-in. Kept here (not derived) so a schema change can't
# silently widen what leaves the machine.
_POOLABLE_FIELDS = frozenset(ValidationRecord.model_fields)
_SENSITIVE_FIELDS = frozenset({"claim_text"})


def assert_poolable(record: dict, *, allow_claim_text: bool = False) -> None:
    """Raise ``ContributionError`` unless ``record`` is safe to pool.

    Enforces: no field outside the de-identified ``ValidationRecord`` shape; the
    one-way ``claim_text_hash`` is present; and ``claim_text`` is absent unless the
    caller passed the explicit sensitive opt-in.
    """
    extra = set(record) - _POOLABLE_FIELDS
    if extra:
        raise ContributionError(f"record carries non-poolable field(s): {sorted(extra)}")
    if not record.get("claim_text_hash"):
        raise ContributionError("record is missing claim_text_hash (the de-identified key)")
    if record.get("claim_text") is not None and not allow_claim_text:
        raise ContributionError(
            "record carries raw claim_text but the sensitive opt-in was not given")


def build_contribution_bundle(*, root: Optional[str] = None,
                              allow_claim_text: bool = False) -> dict:
    """Build a de-identified contribution bundle from the warehouse — no transmission.

    Reads every stored ValidationRecord, ``assert_poolable``-checks each (refusing to
    build on any leak), and returns the bundle with a content hash, a derived
    ``contribution_id``, and a plain consent receipt. The id is stable for the same
    content, so a revocation can reference it. Appends an ``atlas.bundle_preview``
    audit entry — building a bundle is itself a recorded action.
    """
    store = CiteVahtiStore(root or ".")
    records = [r.model_dump() for r in store.read_validation_records()]
    # strip claim_text up front when the opt-in is off, so an enabled-with-text
    # warehouse can still contribute the de-identified tier safely.
    if not allow_claim_text:
        for r in records:
            r["claim_text"] = None
    for r in records:
        assert_poolable(r, allow_claim_text=allow_claim_text)

    content_hash = sha256_hex(canonical_json(records))
    contribution_id = "contrib_" + content_hash[:16]
    sensitivity = "claim_text" if allow_claim_text else "de_identified"
    bundle = {
        "contribution_id": contribution_id,
        "created_at": utc_now_iso(),
        "count": len(records),
        "sensitivity": sensitivity,
        "content_hash": content_hash,
        "consent_receipt": {
            "scope": "de-identified claim-test ValidationRecords (claim-hash + public "
                     "paper id + ratings/fit); raw claim text "
                     + ("INCLUDED (sensitive opt-in)" if allow_claim_text else "excluded"),
            "egress": "nothing is transmitted by building this bundle; uploading is a "
                      "separate, explicitly-confirmed action to an endpoint you configure",
            "privacy_model": "pseudonymized (one-way hash), not anonymized; the corpus "
                             "re-hashes with a salted HMAC and publishes a cell only at "
                             ">= 5 distinct contributors",
            "revocable": True,
        },
        "records": records,
    }
    store.audit.append("atlas.bundle_preview",
                       {"contribution_id": contribution_id, "count": len(records),
                        "sensitivity": sensitivity, "content_hash": content_hash})
    return bundle


def build_revocation(contribution_id: str, *, reason: Optional[str] = None,
                     root: Optional[str] = None) -> dict:
    """Build a revocation (purge) request referencing a prior contribution.

    Like the bundle, this only *builds* the request (for download or a confirmed
    send); it appends an ``atlas.revoke`` audit entry.
    """
    if not contribution_id:
        raise ContributionError("a contribution_id is required to revoke")
    store = CiteVahtiStore(root or ".")
    req = {"kind": "revocation", "contribution_id": contribution_id,
           "created_at": utc_now_iso(), "reason": reason or None}
    store.audit.append("atlas.revoke", {"contribution_id": contribution_id})
    return req
