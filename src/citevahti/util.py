"""Deterministic serialization + hashing helpers.

``config_hash`` and the audit-log hash chain both depend on a single canonical
JSON encoding so that hashes are reproducible across runs and machines.
"""

from __future__ import annotations

import hashlib
import json
import re
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


def config_hash(value: Any) -> str:
    """SHA-256 over canonicalized JSON of the relevant config subset."""
    return sha256_hex(canonical_json(value))


def utc_now_iso() -> str:
    """ISO-8601 UTC timestamp with explicit offset."""
    return datetime.now(timezone.utc).isoformat()
