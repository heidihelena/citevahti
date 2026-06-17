"""Deterministic serialization + hashing helpers.

``config_hash`` and the audit-log hash chain both depend on a single canonical
JSON encoding so that hashes are reproducible across runs and machines.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

# A dotted version like "9.0.4". A bare integer (e.g. the Zotero *schema*
# version "42") is deliberately NOT a valid app version.
_VERSION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)*$")


def looks_like_version(value: Any) -> bool:
    """True only for a dotted numeric version string (>= major.minor)."""
    return isinstance(value, str) and bool(_VERSION_RE.match(value.strip()))


def canonical_json(value: Any) -> str:
    """Canonical JSON: sorted keys, no insignificant whitespace, UTF-8 safe.

    This is the ``sha256_canonical_json`` basis referenced by the config and the
    AI provenance ``config_hash``.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Claim-text normalization v1 — the SHARED spec across the -vahti house.
# claim_text_hash = sha256_hex(normalize_claim_text(text)). It MUST stay
# byte-identical to the JavaScript implementation in MatchVahti and to anything
# that computes the corpus blind index, or the same claim hashes differently and
# never pools into one AtlasVahti cell. The canonical definition + test vectors
# live in docs/CLAIM_NORMALIZATION.md. Order is fixed: NFC → lowercase → collapse
# Unicode whitespace runs to one space → trim. Do not reorder or add steps on one
# side only.
_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_claim_text(text: str) -> str:
    """Canonical claim-text normalization (spec v1) used for ``claim_text_hash``.

    NFC-normalize, lowercase, collapse any run of Unicode whitespace to a single
    U+0020, and strip the ends. Mirrors ``normalizeClaimText`` in MatchVahti's
    index.html exactly — see docs/CLAIM_NORMALIZATION.md.
    """
    s = unicodedata.normalize("NFC", text or "")
    s = s.lower()
    s = _WHITESPACE_RUN.sub(" ", s).strip()
    return s


def claim_text_hash(text: str) -> str:
    """The shared cross-tool ``claim_text_hash`` = sha256 over the normalized text.

    One definition so CiteVahti, MatchVahti and the corpus blind index agree
    byte-for-byte (see ``normalize_claim_text`` and docs/CLAIM_NORMALIZATION.md).
    """
    return sha256_hex(normalize_claim_text(text))


def config_hash(value: Any) -> str:
    """SHA-256 over canonicalized JSON of the relevant config subset."""
    return sha256_hex(canonical_json(value))


def utc_now_iso() -> str:
    """ISO-8601 UTC timestamp with explicit offset."""
    return datetime.now(timezone.utc).isoformat()
