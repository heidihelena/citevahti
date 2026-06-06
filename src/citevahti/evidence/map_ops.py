"""Evidence-map state operations over the ``.citevahti/`` store.

All mutations persist atomically through the store, which appends to the
hash-chained audit log. Nothing here writes to Zotero.
"""

from __future__ import annotations

import uuid
from typing import Optional

from ..schemas.evidence_map import (
    Attachment,
    EvidenceMap,
    Link,
    Node,
    ReverseIndexEntry,
)
from ..state import CiteVahtiStore
from ..state.store import StateError
from ..validators.evidence_map import (
    EvidenceMapError,
    reverse_index_problems,
    study_citekey,
    validate_attachment,
    validate_evidence_map,
    validate_node,
)


class EvidenceMapService:
    """Load/validate/mutate/save the evidence map, with reverse-index upkeep."""

    def __init__(self, store: CiteVahtiStore) -> None:
        self.store = store

    # ---- lifecycle -------------------------------------------------------
    def load(self) -> EvidenceMap:
        return self.store.load_evidence_map()

    def init_empty(self) -> EvidenceMap:
        emap = EvidenceMap()
        self.store.save_evidence_map(emap)
        return emap

    def save(self, emap: EvidenceMap, *, validate: bool = True) -> None:
        if validate:
            self.validate(emap)
        self.store.save_evidence_map(emap)  # atomic write + audit event

    # ---- validation ------------------------------------------------------
    def _rating_exists(self, rating_id: str) -> bool:
        try:
            self.store.load_rating(rating_id)
            return True
        except StateError:
            return False

    def validate(self, emap: EvidenceMap) -> None:
        validate_evidence_map(emap, rating_exists=self._rating_exists)

    def validate_reverse_index(self, emap: EvidenceMap) -> None:
        problems = self.detect_broken_references(emap)
        if problems:
            raise EvidenceMapError("; ".join(problems))

    def detect_broken_references(self, emap: EvidenceMap) -> list[str]:
        return reverse_index_problems(emap, rating_exists=self._rating_exists)

    # ---- mutations -------------------------------------------------------
    def add_node(self, emap: EvidenceMap, node: Node) -> Node:
        validate_node(node)
        if any(n.node_id == node.node_id for n in emap.nodes):
            raise EvidenceMapError(f"duplicate node_id {node.node_id!r}")
        emap.nodes.append(node)
        return node

    def add_link(self, emap: EvidenceMap, link: Link) -> Link:
        if link.link_id is None:
            link.link_id = f"link_{uuid.uuid4().hex[:12]}"
        ids = {n.node_id for n in emap.nodes}
        if link.from_ not in ids or link.to not in ids:
            raise EvidenceMapError(f"link references missing node: {link.from_} -> {link.to}")
        emap.links.append(link)
        return link

    def add_attachment(self, emap: EvidenceMap, att: Attachment) -> Attachment:
        if any(a.attachment_id == att.attachment_id for a in emap.attachments):
            raise EvidenceMapError(f"duplicate attachment_id {att.attachment_id!r}")
        validate_attachment(att, emap)
        emap.attachments.append(att)
        return att

    # ---- typed attachment helpers (NOT auto-invoked by extract/claim_check) --
    @staticmethod
    def _passage_payload(passage) -> Optional[dict]:
        if passage is None:
            return None
        return passage.model_dump() if hasattr(passage, "model_dump") else dict(passage)

    def add_extracted_field_attachment(self, emap: EvidenceMap, attachment_id: str, *,
                                       provenance, study_node_id: Optional[str] = None,
                                       citekey: Optional[str] = None, field: Optional[str] = None,
                                       value: Optional[str] = None, passage=None,
                                       persist: bool = True) -> Attachment:
        """Store an assistive extraction result as a typed attachment.

        Enforces the step-3 extracted_field scope (study/citekey + provenance) and
        appends an audit event when persisted. Never called automatically.
        """
        att = Attachment(
            attachment_id=attachment_id, kind="extracted_field",
            study_node_id=study_node_id, citekey=citekey, provenance=provenance,
            target_node_id=study_node_id,
            payload={"field": field, "value": value,
                     "passage": self._passage_payload(passage)})
        self.add_attachment(emap, att)  # validates scope + provenance
        if persist:
            self.save(emap)
        return att

    def add_verified_claim_attachment(self, emap: EvidenceMap, attachment_id: str, *,
                                      study_node_id: Optional[str] = None,
                                      citekey: Optional[str] = None,
                                      claim_text: Optional[str] = None,
                                      claim_id: Optional[str] = None, passage=None,
                                      provenance=None, persist: bool = True) -> Attachment:
        """Store a claim-support result as a typed attachment (study + claim)."""
        att = Attachment(
            attachment_id=attachment_id, kind="verified_claim",
            study_node_id=study_node_id, citekey=citekey, claim_text=claim_text,
            claim_id=claim_id, provenance=provenance, target_node_id=study_node_id,
            payload={"passage": self._passage_payload(passage)})
        self.add_attachment(emap, att)  # validates study/citekey + claim presence
        if persist:
            self.save(emap)
        return att

    def add_staleness_flag_attachment(self, emap: EvidenceMap, attachment_id: str, *,
                                      citekey: Optional[str] = None,
                                      study_node_id: Optional[str] = None,
                                      reason: Optional[str] = None, persist: bool = True) -> Attachment:
        """Flag affected citekey-linked objects as stale (corpus_diff uses this)."""
        att = Attachment(attachment_id=attachment_id, kind="staleness_flag",
                         citekey=citekey, study_node_id=study_node_id,
                         target_node_id=study_node_id, payload={"reason": reason})
        self.add_attachment(emap, att)  # validates: requires citekey or study ref
        if persist:
            self.save(emap)
        return att

    def add_retraction_flag_attachment(self, emap: EvidenceMap, attachment_id: str, *,
                                       citekey: Optional[str] = None,
                                       study_node_id: Optional[str] = None,
                                       notice: Optional[str] = None, persist: bool = True) -> Attachment:
        """Flag a study/citekey as retracted (retraction_scan uses this)."""
        att = Attachment(attachment_id=attachment_id, kind="retraction_flag",
                         citekey=citekey, study_node_id=study_node_id,
                         target_node_id=study_node_id, payload={"notice": notice})
        self.add_attachment(emap, att)  # validates: requires study or citekey
        if persist:
            self.save(emap)
        return att

    # ---- reverse index ---------------------------------------------------
    def _attachment_citekey(self, att: Attachment, nodes: dict[str, Node]) -> Optional[str]:
        if att.citekey:
            return att.citekey
        sid = att.study_node_id or att.target_node_id
        return study_citekey(nodes.get(sid)) if sid else None

    def rebuild_reverse_index(self, emap: EvidenceMap) -> None:
        """Recompute the citekey-centered reverse index from nodes/links/attachments."""
        nodes = {n.node_id: n for n in emap.nodes}
        index: dict[str, ReverseIndexEntry] = {}

        # one entry per study node that carries a citekey
        study_by_citekey: dict[str, str] = {}
        for n in emap.nodes:
            ck = study_citekey(n)
            if ck:
                study_by_citekey[ck] = n.node_id
                index[ck] = ReverseIndexEntry(study_node_id=n.node_id)

        # attachments
        for a in emap.attachments:
            ck = self._attachment_citekey(a, nodes)
            if ck is None:
                continue
            entry = index.setdefault(ck, ReverseIndexEntry(study_node_id=study_by_citekey.get(ck)))
            entry.attachment_ids.append(a.attachment_id)
            if a.kind == "staleness_flag":
                entry.stale_flags.append(a.attachment_id)
            if a.rating_id and a.rating_id not in entry.rating_ids:
                entry.rating_ids.append(a.rating_id)
            if a.outcome_node_id and a.outcome_node_id not in entry.outcome_node_ids:
                entry.outcome_node_ids.append(a.outcome_node_id)

        # links touching a study node
        for l in emap.links:
            for this_id, other_id in ((l.from_, l.to), (l.to, l.from_)):
                node = nodes.get(this_id)
                ck = study_citekey(node)
                if not ck:
                    continue
                entry = index.setdefault(ck, ReverseIndexEntry(study_node_id=this_id))
                if l.link_id and l.link_id not in entry.link_ids:
                    entry.link_ids.append(l.link_id)
                other = nodes.get(other_id)
                if other is None:
                    continue
                if other.type == "outcome" and other_id not in entry.outcome_node_ids:
                    entry.outcome_node_ids.append(other_id)
                elif other.type == "recommendation" and other_id not in entry.recommendation_node_ids:
                    entry.recommendation_node_ids.append(other_id)

        emap.reverse_index = index
