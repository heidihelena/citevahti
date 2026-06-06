"""Evidence-map validators: node/attachment kinds, scope rules, reverse index.

These operationalize the per-kind attachment scope rules and the citekey-centered
reverse index. They do not implement extraction/assessment/claim behavior; they
ensure the map can store those future outputs correctly.
"""

from __future__ import annotations

from typing import Optional

from ..schemas.evidence_map import Attachment, EvidenceMap, Node
from .errors import ValidationError

NODE_TYPES = {"item", "claim", "passage", "rating", "recommendation", "section",
              "outcome", "study"}
ATTACHMENT_KINDS = {"extracted_field", "verified_claim", "assessment",
                    "staleness_flag", "retraction_flag", "screening_decision"}
ROB_SCHEMES = {"RoB2", "ROBINS-I"}


class EvidenceMapError(ValidationError):
    code = "evidence_map_invalid"


def _nodes_by_id(emap: EvidenceMap) -> dict[str, Node]:
    return {n.node_id: n for n in emap.nodes}


def _is_type(nodes: dict[str, Node], node_id: Optional[str], node_type: str) -> bool:
    n = nodes.get(node_id) if node_id else None
    return n is not None and n.type == node_type


def validate_node(node: Node) -> None:
    if node.type not in NODE_TYPES:
        raise EvidenceMapError(f"unknown node type {node.type!r}")


def study_citekey(node: Optional[Node]) -> Optional[str]:
    if node is None or node.type != "study":
        return None
    return node.item.citekey if node.item else None


def validate_attachment(att: Attachment, emap: EvidenceMap) -> None:
    """Enforce the per-kind attachment scope rules."""
    if att.kind not in ATTACHMENT_KINDS:
        raise EvidenceMapError(f"unknown attachment kind {att.kind!r}")
    nodes = _nodes_by_id(emap)
    study_ref = att.study_node_id or (att.target_node_id
                                      if _is_type(nodes, att.target_node_id, "study") else None)
    has_study = att.citekey is not None or _is_type(nodes, study_ref, "study")

    if att.kind == "extracted_field":
        if not has_study:
            raise EvidenceMapError("extracted_field must reference a study node or citekey")
        if att.provenance is None:
            raise EvidenceMapError("extracted_field must carry provenance")

    elif att.kind == "verified_claim":
        if not has_study:
            raise EvidenceMapError("verified_claim must reference a study node or citekey")
        if not (att.claim_text or att.claim_id):
            raise EvidenceMapError("verified_claim must carry claim_text or claim_id")

    elif att.kind == "assessment":
        if att.scheme_kind is None:
            raise EvidenceMapError("assessment must declare scheme_kind")
        has_outcome = _is_type(nodes, att.outcome_node_id, "outcome")
        has_study_scope = _is_type(nodes, study_ref, "study")
        if not (has_outcome or has_study_scope):
            raise EvidenceMapError("assessment must be scoped to a study and/or an outcome")
        if att.scheme_kind == "GRADE":
            # GRADE certainty is outcome-level (body of evidence for an outcome).
            if not has_outcome or has_study_scope:
                raise EvidenceMapError("GRADE assessment must be scoped to an outcome only")
        elif att.scheme_kind in ROB_SCHEMES:
            # RoB is study-level or study x outcome -- never outcome-only.
            if not has_study_scope:
                raise EvidenceMapError("RoB assessment must be scoped to a study "
                                       "(or study x outcome), not outcome-only")
        if att.outcome_node_id and not has_outcome:
            raise EvidenceMapError(f"outcome_node_id {att.outcome_node_id!r} is not an outcome node")

    elif att.kind == "staleness_flag":
        if att.citekey is None and not _is_type(nodes, study_ref, "study"):
            raise EvidenceMapError("staleness_flag must reference a citekey-linked object")

    elif att.kind == "retraction_flag":
        if not has_study:
            raise EvidenceMapError("retraction_flag must reference a study or citekey")

    elif att.kind == "screening_decision":
        # Human decision only; AI votes are stored as rating references, not here.
        if not att.decided_by:
            raise EvidenceMapError("screening_decision is human-only and requires decided_by")
        if not att.decision:
            raise EvidenceMapError("screening_decision must carry a decision value")


def reverse_index_problems(emap: EvidenceMap,
                           rating_exists=None) -> list[str]:
    """Return a list of broken/dangling reverse-index references (empty == clean).

    ``rating_exists`` is an optional callable ``rating_id -> bool`` used to check
    that referenced rating records exist.
    """
    nodes = _nodes_by_id(emap)
    att_ids = {a.attachment_id for a in emap.attachments}
    stale_att_ids = {a.attachment_id for a in emap.attachments if a.kind == "staleness_flag"}
    link_ids = {l.link_id for l in emap.links if l.link_id}
    problems: list[str] = []

    for citekey, entry in emap.reverse_index.items():
        sid = entry.study_node_id
        if sid is not None:
            node = nodes.get(sid)
            if node is None or node.type != "study":
                problems.append(f"reverse_index[{citekey}]: study_node_id {sid!r} missing/not a study")
            elif study_citekey(node) is None:
                problems.append(f"reverse_index[{citekey}]: study node {sid!r} has no citekey")
            elif study_citekey(node) != citekey:
                problems.append(f"reverse_index[{citekey}]: study citekey != index key")
        for aid in entry.attachment_ids:
            if aid not in att_ids:
                problems.append(f"reverse_index[{citekey}]: attachment {aid!r} missing")
        for lid in entry.link_ids:
            if lid not in link_ids:
                problems.append(f"reverse_index[{citekey}]: link {lid!r} missing")
        for sf in entry.stale_flags:
            if sf not in stale_att_ids:
                problems.append(f"reverse_index[{citekey}]: stale_flag {sf!r} missing")
        for nid in entry.recommendation_node_ids:
            if not _is_type(nodes, nid, "recommendation"):
                problems.append(f"reverse_index[{citekey}]: recommendation {nid!r} missing/wrong type")
        for nid in entry.outcome_node_ids:
            if not _is_type(nodes, nid, "outcome"):
                problems.append(f"reverse_index[{citekey}]: outcome {nid!r} missing/wrong type")
        for rid in entry.rating_ids:
            if rating_exists is not None and not rating_exists(rid):
                problems.append(f"reverse_index[{citekey}]: rating {rid!r} not found")
    return problems


def validate_evidence_map(emap: EvidenceMap, rating_exists=None) -> None:
    """Full structural validation: nodes, attachments, links, reverse index."""
    nodes = _nodes_by_id(emap)
    if len(nodes) != len(emap.nodes):
        raise EvidenceMapError("duplicate node_id in evidence map")
    for node in emap.nodes:
        validate_node(node)
    for link in emap.links:
        if link.from_ not in nodes or link.to not in nodes:
            raise EvidenceMapError(f"link references missing node: {link.from_} -> {link.to}")
    for att in emap.attachments:
        validate_attachment(att, emap)
    problems = reverse_index_problems(emap, rating_exists=rating_exists)
    if problems:
        raise EvidenceMapError("; ".join(problems))
