"""Stable claim-test finding labels (the "manuscript as code" frame).

A claim is a test case; a *finding* is what the test turned up. These labels are
the shared vocabulary the agent (via the `run_claim_tests` MCP prompt), the report
formatter, the docs, and the UI copy all use, so a finding means the same thing
everywhere. The set is **stable** — asserted by tests; add, don't repurpose.

The labels split into four groups:
  - support: how well the paper supports THIS claim;
  - reference integrity: is the cited reference real, and is it the right paper;
  - PICO / meaning mismatch: topic match is not support;
  - workflow: where the claim is in the guarded write loop.

Most reference-integrity and mismatch findings are the agent's reasoning over the
evidence (a paper existing is not the same as it supporting the claim); the
``support_to_finding`` map derives the coarse support finding from the recorded,
human-sourced support value so the structured report can show a label too.
"""

from __future__ import annotations

# --- support -----------------------------------------------------------------
SUPPORT_FINDINGS = (
    "support_direct",            # the paper directly supports the claim
    "support_partial",          # supports part of the claim, or with caveats
    "related_but_insufficient",  # on-topic / indirect, but does not establish the claim
    "missing_support",          # no candidate supports the claim
)

# --- reference integrity -----------------------------------------------------
REFERENCE_FINDINGS = (
    "reference_broken",          # the citation does not resolve (bad DOI/PMID/link)
    "reference_hallucinated",    # the cited reference appears not to exist
    "reference_real_but_wrong",  # the reference exists but does not support the claim
)

# --- PICO / meaning mismatch (topic match is not support) --------------------
MISMATCH_FINDINGS = (
    "population_mismatch",
    "intervention_mismatch",
    "comparator_mismatch",
    "outcome_mismatch",
    "study_design_mismatch",
    "overclaim",                 # the claim says more than the evidence supports
    "needs_full_text",           # abstract is insufficient; full text required to decide
)

# --- workflow ----------------------------------------------------------------
WORKFLOW_FINDINGS = (
    "candidate_found",           # a candidate paper was located for the claim
    "zotero_action_ready",       # a guarded write is staged and previewed
    "zotero_write_committed",    # a previewed, confirmed write was committed
    "zotero_write_undone",       # a committed write was undone
)

# The complete, stable vocabulary (order-insensitive; membership is the contract).
FINDING_LABELS = SUPPORT_FINDINGS + REFERENCE_FINDINGS + MISMATCH_FINDINGS + WORKFLOW_FINDINGS

# Map the recorded human support value (schemas.claim_support.SUPPORT_VALUES) to a
# coarse support finding, so the structured report can carry a label without the
# agent. Blinding-safe: it reads the human value, never the blinded AI value.
_SUPPORT_VALUE_TO_FINDING = {
    "directly_supports": "support_direct",
    "partially_supports": "support_partial",
    "indirectly_supports": "related_but_insufficient",
    "overstated": "overclaim",
    "does_not_support": "missing_support",
    "contradicts": "reference_real_but_wrong",
    "unclear": "needs_full_text",
}


def support_to_finding(support_value):
    """Coarse finding label for a recorded support value, or ``None`` if unset."""
    return _SUPPORT_VALUE_TO_FINDING.get(support_value)


def is_finding(label: str) -> bool:
    return label in FINDING_LABELS
