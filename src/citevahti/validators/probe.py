"""Probe-layer validator: a probed version is dotted-version-shaped or null.

This prevents a placeholder (e.g. the integer schema version "42") from ever
being surfaced or persisted as the Zotero app version.
"""

from __future__ import annotations

from typing import Optional

from ..util import looks_like_version
from .errors import ValidationError


class ProbeValidationError(ValidationError):
    code = "probe_invalid"


def assert_valid_probed_version(version: Optional[str]) -> None:
    """Raise unless ``version`` is None or a dotted numeric version string."""
    if version is None:
        return
    if not looks_like_version(version):
        raise ProbeValidationError(
            f"probed_version {version!r} is not a valid version string; emit null "
            "with version_status='unknown' instead of a placeholder."
        )
