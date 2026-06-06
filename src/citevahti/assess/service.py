"""AssessmentService: human-chosen controlled-value recording + attachment."""

from __future__ import annotations

import re
from typing import Optional

from .. import __version__
from ..evidence import EvidenceMapService
from ..schemas.common import Provenance
from ..schemas.evidence_map import Attachment, Node
from ..schemas.rating import Subject
from ..schemas.results import AssessmentRecord
from ..util import config_hash, utc_now_iso
from ..validators.frame import validate_subject_for_scheme, validate_value_in_scheme

TAG_MIRROR_DEFERRED = "tag_mirror_deferred_to_step_9"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


class AssessmentService:
    def __init__(self, store, engine=None) -> None:
        self.store = store
        self.engine = engine  # RatingEngine, used only when dual_rating=True

    def assess(self, frame_id: str, scheme_id: str, subject: Subject, human_value: str,
               reasons: Optional[list[str]] = None, rationale: Optional[str] = None,
               dual_rating: bool = False, tag_mirror: bool = False,
               committed_by: str = "human") -> AssessmentRecord:
        frame = self.store.load_frame(frame_id)
        scheme = validate_subject_for_scheme(frame, scheme_id, subject)  # raises FrameError
        if human_value is None:
            from ..validators.errors import ValidationError
            raise ValidationError("assess requires a human-chosen value")
        validate_value_in_scheme(scheme, human_value)  # rejects out-of-vocabulary/computed values

        prov = Provenance(tool="assess", tool_version=__version__, ran_at=utc_now_iso(),
                          config_hash=config_hash({"frame": frame_id, "scheme": scheme_id,
                                                   "subject": subject.model_dump()}),
                          sources=[{"kind": "local_state", "detail": "human-chosen value"}])
        record = AssessmentRecord(frame_id=frame_id, scheme_id=scheme_id, scheme_kind=scheme.kind,
                                  subject=subject.model_dump(), human_value=human_value,
                                  reasons=reasons or [], rationale=rationale, provenance=prov)

        if tag_mirror:
            record.tag_mirror_status = TAG_MIRROR_DEFERRED
            record.warnings.append("tag mirroring to Zotero is out of scope until step 9")

        # ---- ensure nodes + create/replace the assessment attachment -----
        svc = EvidenceMapService(self.store)
        emap = svc.load()
        study_node_id = outcome_node_id = None
        if scheme.unit in ("study", "study_x_outcome"):
            study = next(s for s in frame.studies if s.study_id == subject.study_id)
            study_node_id = f"study:{frame_id}:{subject.study_id}"
            self._ensure_node(svc, emap, Node(node_id=study_node_id, type="study",
                                              item=study.item, label=subject.study_id))
        if scheme.unit in ("outcome", "study_x_outcome"):
            outcome = next(o for o in frame.outcomes if o.outcome_id == subject.outcome_id)
            outcome_node_id = f"outcome:{frame_id}:{subject.outcome_id}"
            self._ensure_node(svc, emap, Node(node_id=outcome_node_id, type="outcome",
                                              label=outcome.label))

        # surface (but never clear) existing stale flags affecting the subject
        if study_node_id is not None:
            ck = next((s.item.citekey for s in frame.studies if s.study_id == subject.study_id), None)
            if ck:
                record.stale_flags = [a.attachment_id for a in emap.attachments
                                      if a.kind == "staleness_flag" and a.citekey == ck]

        # dual-rating: start a blinded rating record + commit the human value.
        # The AI is NOT run here -- it remains advisory and blinded.
        rating_id = None
        if dual_rating and self.engine is not None:
            started = self.engine.rating_start(frame_id, scheme_id, subject)
            committed = self.engine.rating_commit_human(
                started.rating_id, human_value, rationale=rationale, reasons=reasons,
                committed_by=committed_by)
            rating_id = committed.rating_id
            record.status = "dual_rating_started"

        att_id = f"assess-{scheme_id}-{_slug(subject.study_id or '')}-{_slug(subject.outcome_id or '')}"
        emap.attachments = [a for a in emap.attachments if a.attachment_id != att_id]  # replace on re-rate
        svc.add_attachment(emap, Attachment(
            attachment_id=att_id, kind="assessment", scheme_kind=scheme.kind,
            study_node_id=study_node_id, outcome_node_id=outcome_node_id,
            target_node_id=study_node_id or outcome_node_id, rating_id=rating_id, provenance=prov,
            payload={"value": human_value, "reasons": reasons or [], "rationale": rationale}))
        svc.rebuild_reverse_index(emap)
        svc.save(emap)
        record.attachment_id = att_id
        record.rating_id = rating_id
        record.audit_event_id = self.store.audit.entries()[-1].hash
        return record

    @staticmethod
    def _ensure_node(svc, emap, node: Node) -> None:
        if not any(n.node_id == node.node_id for n in emap.nodes):
            svc.add_node(emap, node)
