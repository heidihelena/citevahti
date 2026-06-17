"""ClaimSupportEngine (ADR-0001, step 3): blinded dual rating of claim support.

Same invariants as the study-quality engine, reused value blocks, but keyed to a
``(claim_id, candidate_id)`` pair with a controlled support vocabulary + PICO fit.
The AI rater is a blind, advisory seam (a fake is used in tests); it never sees
the human value and can never become final automatically.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from .. import __version__
from ..schemas.claim_support import (
    SUPPORT_VALUES,
    ClaimSupportRating,
    FitScores,
    SupportAIRating,
    SupportHumanRating,
)
from ..schemas.common import PassageRef, Provenance
from ..schemas.rating import AccessLogEntry, Adjudication, AIProvenance
from ..util import canonical_json, config_hash, sha256_hex, utc_now_iso
from ..validators.claim_support import ClaimSupportError
from ..validators.config import authorize_rating_task, require_model_pinned


def rating_preference_key(rating) -> tuple:
    """Order ratings for the same (claim, candidate) so the *most advanced and most recent*
    one represents the pair: an adjudicated value > a committed human rating > a
    started-but-unrated one; ties broken by recency, then id.

    ``support_start`` mints a fresh rating id each call, so a pair can have more than one
    rating on disk; reports and the panel must select deterministically rather than take an
    arbitrary (uuid-sorted) one. Higher key wins.
    """
    has_final = rating.adjudication.final_value is not None
    committed_at = (rating.human_rating.committed_at
                    if rating.human_rating and rating.human_rating.committed_at else "")
    last_activity = max((e.ts for e in rating.blinding.access_log), default="")
    return (has_final, bool(committed_at), committed_at, last_activity, rating.rating_id)


def select_support_rating(store, claim_id: str, candidate_id: str):
    """The representative rating for a (claim, candidate) pair: the most advanced and
    recent one by ``rating_preference_key``. A pair can have several ratings on disk
    (``support_start`` mints a new id each call); selecting deterministically HERE keeps
    the panel, the report, and agent provenance consistent — none picks an arbitrary one."""
    best = None
    for rid in store.list_support_ratings():
        rec = store.load_support_rating(rid)
        if rec.claim_id == claim_id and rec.candidate_id == candidate_id:
            if best is None or rating_preference_key(rec) > rating_preference_key(best):
                best = rec
    return best


@dataclass
class SupportAiOutput:
    value: Optional[str] = None
    abstained: bool = False
    confidence: Optional[float] = None
    fit: Optional[FitScores] = None
    domain_reasoning: Optional[str] = None
    supporting_passages: list = field(default_factory=list)


@runtime_checkable
class ClaimSupportRater(Protocol):
    name: str

    def rate(self, *, claim, candidate, task_type: str) -> SupportAiOutput: ...


class FakeClaimSupportRater:
    """Deterministic rater for tests/offline use. Blind by construction."""

    name = "fake_support_rater"

    def __init__(self, value: Optional[str] = None, abstained: bool = False,
                 confidence: Optional[float] = None, fit: Optional[FitScores] = None) -> None:
        self._out = SupportAiOutput(value=None if abstained else value, abstained=abstained,
                                    confidence=confidence, fit=fit or FitScores())

    def rate(self, *, claim, candidate, task_type: str) -> SupportAiOutput:
        return self._out


class ClaimSupportEngine:
    def __init__(self, store, rater: Optional[ClaimSupportRater] = None, config=None) -> None:
        self.store = store
        self.rater = rater
        self.config = config or store.load_config()

    # ---- helpers ---------------------------------------------------------
    def _get_candidate(self, claim_id: str, candidate_id: str):
        self.store.load_claim(claim_id)            # raises if the claim is unknown
        cc = self.store.load_candidates(claim_id)   # raises if no candidates linked
        for c in cc.candidates:
            if c.candidate_id == candidate_id:
                return c
        raise ClaimSupportError(
            f"candidate {candidate_id!r} is not linked to claim {claim_id!r}")

    @staticmethod
    def _check_value(value: str) -> None:
        if value not in SUPPORT_VALUES:
            raise ClaimSupportError(
                f"support value {value!r} not in {SUPPORT_VALUES}")

    # ---- start -----------------------------------------------------------
    def support_start(self, claim_id: str, candidate_id: str,
                      rating_set_id: Optional[str] = None) -> ClaimSupportRating:
        self._get_candidate(claim_id, candidate_id)
        record = ClaimSupportRating(
            rating_id=f"cs-{uuid.uuid4().hex[:10]}", rating_set_id=rating_set_id,
            claim_id=claim_id, candidate_id=candidate_id)
        record.blinding.access_log.append(
            AccessLogEntry(ts=utc_now_iso(), actor="system", event="seal"))
        return self.store.save_support_rating(record)

    # ---- human commit ----------------------------------------------------
    def support_commit_human(self, rating_id: str, value: str, *,
                             fit: Optional[FitScores] = None, rationale: Optional[str] = None,
                             reasons: Optional[list] = None,
                             source_passages: Optional[list[PassageRef]] = None,
                             committed_by: str = "human") -> ClaimSupportRating:
        self._check_value(value)
        record = self.store.load_support_rating(rating_id)
        if record.human_rating is not None and record.human_rating.locked:
            raise ClaimSupportError("human support value is locked and cannot be overwritten")
        record.human_rating = SupportHumanRating(
            value=value, fit=fit or FitScores(), committed_at=utc_now_iso(),
            committed_by=committed_by, rationale=rationale, reasons=reasons or [],
            source_passages=source_passages or [], locked=True)
        record.blinding.access_log.append(
            AccessLogEntry(ts=utc_now_iso(), actor=committed_by, event="commit", target="human"))
        return self.store.save_support_rating(record)

    # ---- AI run (blind, advisory) ---------------------------------------
    def support_run_ai(self, rating_id: str, task_type: str = "assess") -> ClaimSupportRating:
        record = self.store.load_support_rating(rating_id)
        ai_cfg = self.config.ai_provenance
        require_model_pinned(ai_cfg)               # no fake/placeholder model
        authorize_rating_task(ai_cfg, task_type)   # task must be allowed
        if self.rater is None:
            raise ClaimSupportError("no ClaimSupportRater configured")
        claim = self.store.load_claim(record.claim_id)
        candidate = self._get_candidate(record.claim_id, record.candidate_id)

        out = self.rater.rate(claim=claim, candidate=candidate, task_type=task_type)
        if not out.abstained and out.value is not None:
            self._check_value(out.value)
        prompt_hash = sha256_hex(canonical_json({
            "claim_id": record.claim_id, "candidate_id": record.candidate_id,
            "task_type": task_type, "prompt_template_version": ai_cfg.prompt_template_version}))
        provenance = AIProvenance(
            provider=ai_cfg.provider, model_id=ai_cfg.model_id,
            model_snapshot=ai_cfg.model_snapshot,
            prompt_template_version=ai_cfg.prompt_template_version, prompt_hash=prompt_hash,
            config_hash=config_hash(ai_cfg.model_dump()), rated_at=utc_now_iso())
        record.ai_rating = SupportAIRating(
            value=None if out.abstained else out.value, abstained=out.abstained,
            confidence=out.confidence, fit=out.fit or FitScores(),
            supporting_passages=out.supporting_passages, domain_reasoning=out.domain_reasoning,
            task_type=task_type, provenance=provenance)
        record.blinding.access_log.append(
            AccessLogEntry(ts=utc_now_iso(), actor=ai_cfg.model_id, event="commit", target="ai"))
        record.blinding.independent = True
        return self.store.save_support_rating(record)

    def submit_ai_rating(self, rating_id: str, value: Optional[str], *,
                         confidence: Optional[float] = None, fit=None,
                         reasoning: Optional[str] = None, abstained: bool = False,
                         task_type: str = "assess") -> ClaimSupportRating:
        """Record an AI support rating supplied directly (the agent IS the rater).

        Same invariants as ``support_run_ai``: model must be pinned, task allowed,
        value controlled; carries full provenance; never becomes final.
        """
        record = self.store.load_support_rating(rating_id)
        ai_cfg = self.config.ai_provenance
        require_model_pinned(ai_cfg)
        authorize_rating_task(ai_cfg, task_type)
        if not abstained and value is not None:
            self._check_value(value)
        if isinstance(fit, dict):
            fit = FitScores(**fit)
        prompt_hash = sha256_hex(canonical_json({
            "claim_id": record.claim_id, "candidate_id": record.candidate_id,
            "task_type": task_type, "prompt_template_version": ai_cfg.prompt_template_version}))
        provenance = AIProvenance(
            provider=ai_cfg.provider, model_id=ai_cfg.model_id,
            model_snapshot=ai_cfg.model_snapshot,
            prompt_template_version=ai_cfg.prompt_template_version, prompt_hash=prompt_hash,
            config_hash=config_hash(ai_cfg.model_dump()), rated_at=utc_now_iso())
        record.ai_rating = SupportAIRating(
            value=None if abstained else value, abstained=abstained, confidence=confidence,
            fit=fit or FitScores(), domain_reasoning=reasoning, task_type=task_type,
            provenance=provenance)
        record.blinding.access_log.append(
            AccessLogEntry(ts=utc_now_iso(), actor=ai_cfg.model_id, event="commit", target="ai"))
        record.blinding.independent = True
        return self.store.save_support_rating(record)

    # ---- compare ---------------------------------------------------------
    def support_compare(self, rating_id: str) -> ClaimSupportRating:
        record = self.store.load_support_rating(rating_id)
        hv = record.human_rating.value if record.human_rating else None
        av = record.ai_rating.value if record.ai_rating else None
        if record.ai_rating is None:
            status = "human_only"
        elif record.ai_rating.abstained:
            status = "ai_abstained"
        elif hv == av:
            status = "concordant"
        else:
            status = "discordant"
        record.comparison.status = status
        record.comparison.computed_at = utc_now_iso()
        # Concordance locks in the HUMAN value (never the AI value as the source).
        if status == "concordant":
            record.adjudication = Adjudication(final_value=hv, event="accepted",
                                               decided_at=utc_now_iso())
        return self.store.save_support_rating(record)

    # ---- adjudicate ------------------------------------------------------
    def support_adjudicate(self, rating_id: str, final_value: str, rationale: str,
                           decider: str = "human") -> ClaimSupportRating:
        if not rationale:
            raise ClaimSupportError("adjudication requires a rationale")
        if decider not in ("human", "panel"):
            raise ClaimSupportError("decider must be 'human' or 'panel'")
        self._check_value(final_value)
        record = self.store.load_support_rating(rating_id)
        # Adjudication is the ONLY path to a final value on a DISCORDANCE, and only
        # after a locked human rating AND an AI second rating exist and were COMPUTED
        # to disagree. NEVER fabricate the comparison: a missing / non-discordant
        # status means there is nothing to adjudicate. This is the human-first trust
        # boundary — without it, a manual override on an unrated pair could become an
        # accepted citation.
        if record.human_rating is None or not record.human_rating.locked:
            raise ClaimSupportError(
                "cannot adjudicate before a locked human support rating exists")
        if record.ai_rating is None:
            raise ClaimSupportError(
                "cannot adjudicate before an AI second rating exists")
        if record.comparison.status != "discordant":
            raise ClaimSupportError(
                "adjudication requires a computed discordance (comparison is "
                f"{record.comparison.status or 'uncomputed'}); run compare first")
        record.adjudication = Adjudication(
            final_value=final_value, event="adjudicated", decided_by=decider,
            decided_at=utc_now_iso(), rationale=rationale)
        return self.store.save_support_rating(record)

    def provenance(self) -> Provenance:
        return Provenance(tool="claim_support_engine", tool_version=__version__,
                          ran_at=utc_now_iso(), config_hash=config_hash({}), sources=[])
