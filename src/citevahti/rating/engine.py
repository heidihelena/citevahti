"""RatingEngine: start -> commit human -> run AI (blind) -> compare -> adjudicate.

Enforces the hardening invariants: human/ai/comparison/adjudication are distinct
fields; AI never becomes final automatically; discordant never accepted without
adjudication; human value never overwritten; every mutation is audited.
"""

from __future__ import annotations

import uuid
from typing import Optional

from .. import __version__
from ..schemas.common import PassageRef, Provenance
from ..schemas.rating import (
    AccessLogEntry,
    AIProvenance,
    AIRating,
    Adjudication,
    HumanRating,
    RatingRecord,
    Subject,
)
from ..schemas.results import RatingComparison
from ..util import canonical_json, config_hash, sha256_hex, utc_now_iso
from ..validators import (
    authorize_rating_task,
    require_model_pinned,
    validate_subject_for_scheme,
    validate_value_in_scheme,
)
from ..validators.errors import RatingValidityError
from ..validators.rating import is_agreement_countable
from .ai import AiRater


class RatingEngine:
    def __init__(self, store, ai_rater: Optional[AiRater] = None, config=None) -> None:
        self.store = store
        self.ai_rater = ai_rater
        self.config = config or store.load_config()

    # ---- start -----------------------------------------------------------
    def rating_start(self, frame_id: str, scheme_id: str, subject: Subject,
                     domain_id: Optional[str] = None) -> RatingRecord:
        frame = self.store.load_frame(frame_id)
        if domain_id is not None:
            subject = subject.model_copy(update={"domain_id": domain_id})
        validate_subject_for_scheme(frame, scheme_id, subject)  # raises FrameError if bad
        record = RatingRecord(rating_id=f"rt-{uuid.uuid4().hex[:10]}", frame_id=frame_id,
                              frame_version=frame.frame_version, scheme_id=scheme_id,
                              subject=subject)
        record.blinding.access_log.append(
            AccessLogEntry(ts=utc_now_iso(), actor="system", event="seal"))
        self.store.save_rating(record, frame=frame)
        return record

    # ---- human commit ----------------------------------------------------
    def rating_commit_human(self, rating_id: str, value: str, rationale: Optional[str] = None,
                            reasons: Optional[list[str]] = None,
                            source_passages: Optional[list[PassageRef]] = None,
                            committed_by: str = "human") -> RatingRecord:
        record = self.store.load_rating(rating_id)
        frame = self.store.load_frame(record.frame_id)
        scheme = validate_subject_for_scheme(frame, record.scheme_id, record.subject)
        validate_value_in_scheme(scheme, value)
        if record.human_rating is not None and record.human_rating.locked:
            # the store also guards this, but fail early with a clear error
            raise RatingValidityError("human value is locked and cannot be overwritten")
        record.human_rating = HumanRating(
            value=value, committed_at=utc_now_iso(), committed_by=committed_by,
            rationale=rationale, reasons=reasons or [], source_passages=source_passages or [],
            locked=True)
        record.blinding.access_log.append(
            AccessLogEntry(ts=utc_now_iso(), actor=committed_by, event="commit", target="human"))
        self.store.save_rating(record, frame=frame)
        return record

    # ---- AI run (blind, advisory) ---------------------------------------
    def rating_run_ai(self, rating_id: str, task_type: str) -> RatingRecord:
        record = self.store.load_rating(rating_id)
        frame = self.store.load_frame(record.frame_id)
        scheme = validate_subject_for_scheme(frame, record.scheme_id, record.subject)
        ai_cfg = self.config.ai_provenance
        require_model_pinned(ai_cfg)              # raises ModelNotPinnedError (no fake value)
        authorize_rating_task(ai_cfg, task_type)  # raises TaskNotAllowedError (e.g. claim_check)
        if self.ai_rater is None:
            raise RatingValidityError("no AiRater configured")

        # The rater is blind: it never receives the human value.
        out = self.ai_rater.rate(frame=frame, scheme=scheme, subject=record.subject,
                                 task_type=task_type)
        if not out.abstained and out.value is not None:
            validate_value_in_scheme(scheme, out.value)

        prompt_hash = sha256_hex(canonical_json({
            "scheme_id": record.scheme_id, "subject": record.subject.model_dump(),
            "task_type": task_type, "prompt_template_version": ai_cfg.prompt_template_version}))
        provenance = AIProvenance(
            provider=ai_cfg.provider, model_id=ai_cfg.model_id,
            model_snapshot=ai_cfg.model_snapshot,
            prompt_template_version=ai_cfg.prompt_template_version, prompt_hash=prompt_hash,
            config_hash=config_hash(ai_cfg.model_dump()), rated_at=utc_now_iso())
        record.ai_rating = AIRating(
            value=None if out.abstained else out.value, abstained=out.abstained,
            confidence=out.confidence, supporting_passages=out.supporting_passages,
            domain_reasoning=out.domain_reasoning, task_type=task_type, provenance=provenance)
        record.blinding.access_log.append(
            AccessLogEntry(ts=utc_now_iso(), actor=ai_cfg.model_id, event="commit", target="ai"))
        record.blinding.independent = True        # AI never saw the human value
        self.store.save_rating(record, frame=frame)
        return record

    # ---- compare ---------------------------------------------------------
    def rating_compare(self, rating_id: str) -> RatingComparison:
        record = self.store.load_rating(rating_id)
        frame = self.store.load_frame(record.frame_id)
        hv = record.human_rating.value if record.human_rating else None
        av = record.ai_rating.value if record.ai_rating else None

        if record.ai_rating is None:
            status, outcome = "human_only", "human_only"
        elif record.ai_rating.abstained:
            status, outcome = "ai_abstained", "ai_abstained"
        elif hv == av:
            status, outcome = "concordant", "accepted"
        else:
            status, outcome = "discordant", "needs_adjudication"

        record.comparison.status = status
        record.comparison.computed_at = utc_now_iso()
        # Concordance locks in the HUMAN value via an 'accepted' event. The AI
        # value is never the source -- even though it equals the human value here.
        if status == "concordant":
            record.adjudication = Adjudication(final_value=hv, event="accepted",
                                               decided_at=utc_now_iso())
        self.store.save_rating(record, frame=frame)
        return RatingComparison(
            rating_id=rating_id, status=status, outcome=outcome,
            needs_adjudication=(status == "discordant"), human_value=hv, ai_value=av,
            final_value=record.adjudication.final_value,
            agreement_countable=is_agreement_countable(record))

    # ---- adjudicate ------------------------------------------------------
    def rating_adjudicate(self, rating_id: str, final_value: str, rationale: str,
                          decider: str = "human") -> RatingRecord:
        if not rationale:
            raise RatingValidityError("adjudication requires a rationale")
        if decider not in ("human", "panel"):
            raise RatingValidityError("decider must be 'human' or 'panel'")
        record = self.store.load_rating(rating_id)
        frame = self.store.load_frame(record.frame_id)
        scheme = validate_subject_for_scheme(frame, record.scheme_id, record.subject)
        validate_value_in_scheme(scheme, final_value)
        record.adjudication = Adjudication(
            final_value=final_value, event="adjudicated", decided_by=decider,
            decided_at=utc_now_iso(), rationale=rationale)
        if record.comparison.status is None:
            record.comparison.status = "discordant"
        self.store.save_rating(record, frame=frame)
        return record

    def provenance(self) -> Provenance:
        return Provenance(tool="rating_engine", tool_version=__version__, ran_at=utc_now_iso(),
                          config_hash=config_hash({}), sources=[])
