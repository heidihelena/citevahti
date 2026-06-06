"""Minimal deterministic evidence-map seeding from a guideline file (step 6).

Parses section headings, citation keys, and EXPLICIT outcome markers only.
Never infers recommendations or outcomes from prose, never decides inclusion,
never writes to Zotero. dry_run defaults to true.
"""

from .service import MapBootstrapService

__all__ = ["MapBootstrapService"]
