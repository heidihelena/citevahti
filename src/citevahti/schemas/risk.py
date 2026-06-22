"""Epistemic Risk Score report schema (read-only, advisory).

A *derived, advisory* summary of a manuscript's citation-integrity risk, computed
purely from the existing ``ClaimReport`` (and, optionally, agreement metrics). It
introduces **no new judgments** and mutates nothing — exactly like ``report.py``.

Design stance (matches the CiteVahti manifesto):
  - The score is **advisory triage**, never a pass/fail gate. The per-claim
    sub-contributions are the truth; the headline number is derived and shown
    *with* them, never alone.
  - **Non-compensatory:** a single fatal item (an accepted claim resting on a
    retracted source; a high-salience claim that the evidence *contradicts*)
    sets a floor that good citation completeness cannot average away.
  - **Coverage-aware:** a manuscript cannot earn a low score by leaving most of
    its claims untested — low coverage widens the reported band and flags it.
  - **Rule-based v0, uncalibrated.** Severity/salience are transparent, documented
    defaults, not weights fit to outcomes. Calibration against panel-adjudicated
    labels is a separate, future step (and a publication pathway).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .. import SCHEMA_VERSION

# Higher score = more epistemic risk. Bands are advisory cut-points, not gates.
RISK_BANDS = ("low", "moderate", "high", "insufficient_coverage")


class ClaimRiskContribution(BaseModel):
    """One claim's transparent contribution to the manuscript risk."""

    model_config = ConfigDict(extra="forbid")
    claim_id: str
    claim_text: Optional[str] = None
    state: str
    support_status: Optional[str] = None
    salience: float = 0.0          # 0..1, how central the claim is to the argument
    severity: float = 0.0          # 0..1, how badly the citation fails to support it
    retracted: bool = False        # a retracted source sits behind this claim
    fatal: bool = False            # triggers the non-compensatory floor
    risk: float = 0.0              # 0..1 per-claim contribution (severity x salience x exposure)


class RiskSubscores(BaseModel):
    """The component risks (each 0..1). These are the audited truth; the headline
    score is derived from the per-claim contributions, not from these directly."""

    model_config = ConfigDict(extra="forbid")
    unsupported_share: float = 0.0       # testable claims with no accepted support
    contradiction_risk: float = 0.0      # claims the evidence does_not_support / contradicts
    retraction_exposure: float = 0.0     # claims resting on a retracted source
    disagreement_risk: float = 0.0       # unresolved human/AI discordance (review_needed)
    fit_risk: float = 0.0                # weak PICO/claim fit behind 'supported' claims


class EpistemicRiskReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    generated_at: str

    score: int = 0                       # 0..100, higher = more risk (ADVISORY)
    band: Literal[RISK_BANDS] = "low"    # type: ignore[valid-type]
    score_low: int = 0                   # coverage-derived uncertainty band
    score_high: int = 100

    subscores: RiskSubscores = Field(default_factory=RiskSubscores)

    n_claims: int = 0
    n_testable: int = 0                  # excludes 'untestable' (out-of-scope) claims
    n_tested: int = 0                    # testable claims with a recorded decision/rating
    coverage: float = 0.0                # n_tested / n_testable

    top_contributors: list[ClaimRiskContribution] = Field(default_factory=list)

    method: str = (
        "rule-based v0 (uncalibrated): per-claim severity x salience x retraction "
        "exposure, aggregated by a non-compensatory power-mean (p=3) with a fatal "
        "floor; coverage-banded. Advisory triage only, not a pass/fail gate."
    )
    caveats: list[str] = Field(default_factory=list)


class TriageItem(BaseModel):
    """One claim that needs the researcher's attention, with the reason + next action."""

    model_config = ConfigDict(extra="forbid")
    claim_id: str
    claim_text: Optional[str] = None
    state: str
    reason: str                          # plain-language WHY it needs attention
    action: str                          # the concrete next step
    risk: float = 0.0                    # 0..1 per-claim risk contribution (for ordering)
    fatal: bool = False                  # a non-compensatory issue (e.g. retracted source)


class TriageReport(BaseModel):
    """Risk-first triage: the few claims worth attention, worst-first, + a clean count."""

    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    generated_at: str
    total: int = 0                       # all claims in scope
    needs_attention: int = 0             # claims surfaced below
    clean: int = 0                       # testable claims with nothing to do
    score: int = 0                       # the advisory Epistemic Risk Score (0..100)
    band: str = "low"
    items: list[TriageItem] = Field(default_factory=list)
