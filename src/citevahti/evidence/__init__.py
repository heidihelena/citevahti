"""Operational evidence-map state model (step 3).

Makes the existing evidence-map schema capable of correctly storing future
outputs (extracted fields, verified claims, assessments, flags, screening
decisions) with a citekey-centered reverse index. It does NOT implement
extraction, assessment, or claim-checking behavior.
"""

from .map_ops import EvidenceMapService

__all__ = ["EvidenceMapService"]
