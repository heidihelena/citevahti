"""CiteVahti: citation-integrity and provenance system for research synthesis.

CiteVahti is the first product of Vahtian (see docs/adr/0004). The Python package
is imported as ``citevahti`` and the OS keychain service is ``CiteVahti`` — both
kept as stable identifiers across the rename so existing installs and stored
secrets keep working; the product, CLI, and UI are branded CiteVahti.

Design intent: a documented human -> AI -> adjudication workflow. The AI is a
blinded, independent second rater whose disagreements route to human
adjudication. The human or panel is always the sole decider. AI values are
advisory, never decisive, never silently propagated.

The ``.citevahti/`` state layer holds config, frames, the evidence map with reverse
index, ratings, snapshots, intake, and prisma records, plus a hash-chained audit
log and the binding validators, behind read/discover, cite, extraction,
claim-check, PubMed, dual-rating, and guarded write-back.
"""

__version__ = "0.21.3"

PRODUCT_NAME = "CiteVahti"
COMPANY = "Vahtian"

SCHEMA_VERSION = "7"

# Sentinels for the AI provenance pin. The model MUST be explicitly supplied by
# the user before any AI rating task runs (Patch 1).
PENDING_MODEL_ID = "PENDING_USER_APPROVAL"
PENDING_MODEL_SNAPSHOT = "PENDING_RUNTIME_PIN"
