"""WritebackService: builds guarded write operations and runs them via WriteLayer.

Never mutates ``.citevahti/`` evidence state (only audit + pending-token
bookkeeping). dedupe by DOI/PMID where applicable. Honest degradation.
"""

from __future__ import annotations

from typing import Optional

from .. import __version__
from ..intake.dedupe import normalize_doi, normalize_pmid
from ..schemas.common import ItemRef, Provenance
from ..schemas.writeback import WriteDiff, WriteOperation, WriteResult
from ..util import sha256_hex, utc_now_iso
from .backend import WriteBackend
from .layer import WriteLayer

_SCHEME_PREFIX = {"GRADE": "GRADE:", "RoB2": "RoB2:", "ROBINS-I": "ROBINS-I:", "Generic": "Quality:"}


class WritebackService:
    def __init__(self, store, backend: WriteBackend, *, tag_reader=None, dedupe_index=None,
                 confirm_required: bool = True) -> None:
        self.store = store
        self.backend = backend
        self.layer = WriteLayer(store, backend, confirm_required=confirm_required)
        self.tag_reader = tag_reader        # callable: zotero_key -> list[str]
        self.dedupe_index = dedupe_index

    def _run(self, op: WriteOperation, dry_run: bool, token: Optional[str]):
        return self.layer.preview(op) if dry_run else self.layer.apply(op, token)

    # ---- simple writes ---------------------------------------------------
    def note_add(self, target: ItemRef, title: str, markdown: str, library="personal",
                 dry_run: bool = True, confirm_token: Optional[str] = None):
        op = WriteOperation(
            kind="note_add", library=str(library), targets=[target.zotero_key],
            payload={"title": title, "markdown_hash": sha256_hex(markdown),
                     "markdown_len": len(markdown)},
            proposed_changes=[f"add child note {title!r} to {target.zotero_key}"],
            structured={"create": [{"type": "note", "parent": target.zotero_key, "title": title}]})
        return self._run(op, dry_run, confirm_token)

    def annotation_add(self, target_attachment: ItemRef, page: str, text: str,
                       comment: Optional[str] = None, color: Optional[str] = None,
                       library="personal", dry_run: bool = True,
                       confirm_token: Optional[str] = None):
        op = WriteOperation(
            kind="annotation_add", library=str(library), targets=[target_attachment.zotero_key],
            payload={"page": page, "text_hash": sha256_hex(text),
                     "comment_hash": sha256_hex(comment or ""), "color": color},
            proposed_changes=[f"add annotation on page {page} to {target_attachment.zotero_key}"],
            structured={"create": [{"type": "annotation", "parent": target_attachment.zotero_key,
                                    "page": page}]})
        return self._run(op, dry_run, confirm_token)

    def item_add(self, metadata: dict, library="personal", collection_key: Optional[str] = None,
                 dedupe: bool = True, dry_run: bool = True, confirm_token: Optional[str] = None):
        doi = metadata.get("DOI") or metadata.get("doi")
        pmid = metadata.get("PMID") or metadata.get("pmid")
        dup = bool(dedupe and self.dedupe_index
                   and self.dedupe_index.contains(pmid, doi) is True)
        op = WriteOperation(
            kind="item_add", library=str(library), targets=[],
            payload={"metadata_hash": sha256_hex(repr(sorted(metadata.items()))),
                     "collection_key": collection_key, "dup": dup},
            proposed_changes=[("skip duplicate (DOI/PMID already in library)" if dup
                               else f"create item {metadata.get('title', '(untitled)')!r}")],
            structured={"create": [] if dup else [metadata], "skipped": [metadata] if dup else [],
                        "collection_key": collection_key})
        return self._run(op, dry_run, confirm_token)

    def tag_add(self, targets: list[ItemRef], tags: list[str], library="personal",
                dry_run: bool = True, confirm_token: Optional[str] = None):
        keys = [t.zotero_key for t in targets]
        op = WriteOperation(
            kind="tag_add", library=str(library), targets=keys,
            payload={"tags": sorted(tags)},
            proposed_changes=[f"add tags {sorted(tags)} to {len(keys)} item(s)"],
            structured={"add_tags": sorted(tags), "targets": keys})
        return self._run(op, dry_run, confirm_token)

    def tag_remove(self, targets: list[ItemRef], tags: list[str], library="personal",
                   dry_run: bool = True, confirm_token: Optional[str] = None):
        keys = [t.zotero_key for t in targets]
        op = WriteOperation(
            kind="tag_remove", library=str(library), targets=keys,
            payload={"tags": sorted(tags)},
            proposed_changes=[f"remove tags {sorted(tags)} from {len(keys)} item(s)"],
            structured={"remove_tags": sorted(tags), "targets": keys})
        return self._run(op, dry_run, confirm_token)

    def collection_add_item(self, collection_key: str, items: list[ItemRef], library="personal",
                            dry_run: bool = True, confirm_token: Optional[str] = None):
        keys = [i.zotero_key for i in items]
        op = WriteOperation(
            kind="collection_add_item", library=str(library), targets=keys,
            payload={"collection_key": collection_key},
            proposed_changes=[f"add {len(keys)} item(s) to collection {collection_key}"],
            structured={"collection_key": collection_key, "items": keys})
        return self._run(op, dry_run, confirm_token)

    # ---- intake push -----------------------------------------------------
    def intake_push(self, intake_batch_id: str, record_ids: Optional[list[str]] = None,
                    collection_key: Optional[str] = None, library="personal",
                    dry_run: bool = True, confirm_token: Optional[str] = None,
                    allow_review_required: bool = False,
                    allow_unverified_dedupe: bool = False):
        rec = self.store.load_intake(intake_batch_id)
        # hard block: never write from a batch whose query was flagged for review
        # (e.g. malformed/translated PubMed syntax) without an explicit override.
        if not dry_run and getattr(rec, "review_required", False) and not allow_review_required:
            return WriteResult(
                kind="intake_push", library=str(library), applied=False, status="failed",
                error_code="batch_review_required",
                remediation="this intake batch was flagged review_required (PubMed warned about / "
                            "re-translated the query); verify the staged results, then re-run with "
                            "allow_review_required to push")
        hits = rec.hits
        if record_ids:
            wanted = set(record_ids)
            hits = [h for h in hits if h.record_id in wanted]
        find_existing = getattr(self.backend, "find_existing", None)
        can_check = callable(find_existing) and getattr(self.backend, "available", False)
        create, skipped, unverified = [], [], []
        for h in hits:
            in_lib = (self.dedupe_index.contains(h.pmid, h.doi) is True) if self.dedupe_index else False
            # intake_push must enforce the same rules as the validated path: never
            # stage a within-run duplicate, an identifier-less record, or one that
            # already exists locally or on the Web-API write target.
            if h.dedupe_status == "duplicate_in_run":
                skipped.append({"record_id": h.record_id, "reason": "duplicate_in_run"})
            elif not (h.pmid or h.doi):
                skipped.append({"record_id": h.record_id, "reason": "no_identifier"})
            elif h.dedupe_status == "already_in_library" or in_lib:
                skipped.append({"record_id": h.record_id, "reason": "already_in_library"})
            else:
                # find_existing: a list of keys -> already present; [] -> verified absent;
                # None -> could-not-check. Treat None HONESTLY (not as "clean"), matching
                # commit_for_decision -- an unreachable search must not pass as no-duplicate.
                try:
                    hit = find_existing(h.pmid, h.doi, library=library) if can_check else []
                except Exception:  # noqa: BLE001 (a dedupe failure must never crash the write)
                    hit = None
                if hit:
                    skipped.append({"record_id": h.record_id, "reason": "already_on_write_target"})
                    continue
                if hit is None:
                    unverified.append(h.record_id)
                # full metadata in `structured` (hashed into the confirm token by
                # _payload_hash) so a live backend can build complete Zotero items.
                create.append({"record_id": h.record_id, "doi": h.doi, "pmid": h.pmid,
                               "title": h.title, "authors": h.authors, "journal": h.journal,
                               "year": h.year, "publication_date": h.publication_date})
        # Honest dedupe degrade: a CONFIRMED write refuses if any record's dedupe could
        # not be verified, unless explicitly overridden (parallels commit_for_decision).
        if unverified and not dry_run and not allow_unverified_dedupe:
            return WriteResult(
                kind="intake_push", library=str(library), applied=False, status="failed",
                error_code="dedupe_unverified",
                remediation=(f"could not confirm {len(unverified)} record(s) aren't already on the "
                             "write target (Zotero search unavailable); re-run when reachable, or "
                             "pass allow_unverified_dedupe to override"))
        op = WriteOperation(
            kind="intake_push", library=str(library), targets=[],
            payload={"batch_id": intake_batch_id, "collection_key": collection_key,
                     "create_ids": sorted(c["record_id"] for c in create)},
            proposed_changes=[f"create {len(create)} item(s); skip {len(skipped)} "
                              "(duplicate / no-identifier / already present)"],
            structured={"create": create, "skipped": skipped, "collection_key": collection_key})
        result = self._run(op, dry_run, confirm_token)
        if unverified and getattr(result, "warnings", None) is not None:
            result.warnings.append(
                f"dedupe unverified for {len(unverified)} record(s): the Zotero search was "
                "unavailable, so they could already exist on the write target. A confirmed "
                "write needs allow_unverified_dedupe to proceed.")
        # A committed staging write gets a transaction + undo path too (labelled
        # validated=False — it carries no claim/decision, unlike a validated write).
        if not dry_run and getattr(result, "applied", False):
            self._record_staging_transaction(op, result, intake_batch_id, collection_key, library)
        return result

    def _record_staging_transaction(self, op, result, batch_id, collection_key, library):
        import uuid

        from ..schemas.transaction import ZoteroTransaction
        created = (result.result or {}).get("created_keys") or []
        if not created:
            return                                  # nothing created -> nothing to undo
        txn = ZoteroTransaction(
            transaction_id=f"txn-{uuid.uuid4().hex[:10]}", kind="intake_push", validated=False,
            status="committed", library=str(library), collection_key=collection_key,
            proposed_changes=op.proposed_changes, result=result.result,
            undo_snapshot={"delete_keys": created, "library": str(library),
                           "collection_key": collection_key},
            provenance=Provenance(tool="intake_push", tool_version=__version__,
                                  ran_at=utc_now_iso(),
                                  config_hash=sha256_hex(batch_id),
                                  sources=[{"kind": "intake", "detail": batch_id}]),
            created_at=utc_now_iso(), committed_at=utc_now_iso())
        saved = self.store.save_transaction(txn)
        result.result = {**result.result, "transaction_id": saved.transaction_id}

    # ---- assessment tag-mirror ------------------------------------------
    def assessment_tag_mirror(self, rating_id: Optional[str] = None,
                              assessment_attachment_id: Optional[str] = None,
                              dry_run: bool = True, confirm_token: Optional[str] = None,
                              library="personal"):
        value, scheme_kind, targets, err = self._mirror_inputs(rating_id, assessment_attachment_id)
        if err:
            return self._refuse(dry_run, "not_mirrorable", err)
        if not targets:
            return self._refuse(dry_run, "no_item_target",
                                "No Zotero item/citekey target found for this assessment.")
        prefix = _SCHEME_PREFIX.get(scheme_kind, "Quality:")
        new_tag = f"{prefix}{value}"
        per_target = []
        target_keys = []
        for zk, ck in targets:
            current = list(self.tag_reader(zk)) if self.tag_reader else []
            remove = [t for t in current if t.startswith(prefix) and t != new_tag]
            add = [] if new_tag in current else [new_tag]
            per_target.append({"zotero_key": zk, "citekey": ck, "remove": remove, "add": add})
            target_keys.append(zk)
        op = WriteOperation(
            kind="tag_mirror", library=str(library), targets=target_keys,
            payload={"scheme_kind": scheme_kind, "value": value, "new_tag": new_tag,
                     "per_target": per_target},
            proposed_changes=[f"replace {prefix}* with {new_tag!r} on {len(target_keys)} item(s)"],
            structured={"per_target": per_target, "new_tag": new_tag})
        return self._run(op, dry_run, confirm_token)

    # ---- mirror helpers --------------------------------------------------
    def _mirror_inputs(self, rating_id, attachment_id):
        emap = self.store.load_evidence_map()
        att = None
        if attachment_id:
            att = next((a for a in emap.attachments if a.attachment_id == attachment_id), None)
            if att is None:
                return None, None, [], f"attachment {attachment_id!r} not found"
            if att.kind != "assessment":
                return None, None, [], f"attachment {attachment_id!r} is not an assessment"
        rec = None
        rid = rating_id or (att.rating_id if att else None)
        if rid:
            try:
                rec = self.store.load_rating(rid)
            except Exception:  # noqa: BLE001
                rec = None

        # value: prefer the assessment's recorded human value; if a rating is
        # linked, it must be human/panel-decided (never AI-only/unadjudicated).
        if att is not None:
            scheme_kind = att.scheme_kind
            value = (att.payload or {}).get("value")
            if rec is not None:
                v, err = mirrorable_value(rec)
                if err:
                    return None, None, [], err
                value = v
            targets = self._targets_from_attachment(emap, att)
            return value, scheme_kind, targets, None

        if rec is not None:
            v, err = mirrorable_value(rec)
            if err:
                return None, None, [], err
            frame = self.store.load_frame(rec.frame_id)
            scheme = frame.get_scheme(rec.scheme_id)
            scheme_kind = scheme.kind if scheme else "Generic"
            targets = self._targets_from_rating(frame, rec)
            return v, scheme_kind, targets, None
        return None, None, [], "provide rating_id or assessment_attachment_id"

    def _targets_from_attachment(self, emap, att):
        nodes = {n.node_id: n for n in emap.nodes}
        if att.study_node_id and att.study_node_id in nodes:
            return self._study_items([nodes[att.study_node_id]])
        if att.outcome_node_id:
            studies = []
            for l in emap.links:
                if l.to == att.outcome_node_id and nodes.get(l.from_) and nodes[l.from_].type == "study":
                    studies.append(nodes[l.from_])
                elif l.from_ == att.outcome_node_id and nodes.get(l.to) and nodes[l.to].type == "study":
                    studies.append(nodes[l.to])
            return self._study_items(studies)
        if att.citekey:
            studies = [n for n in emap.nodes if n.type == "study" and n.item
                       and n.item.citekey == att.citekey]
            return self._study_items(studies)
        return []

    def _targets_from_rating(self, frame, rec):
        if rec.subject.study_id:
            study = next((s for s in frame.studies if s.study_id == rec.subject.study_id), None)
            if study and study.item.zotero_key:
                return [(study.item.zotero_key, study.item.citekey)]
        return []

    @staticmethod
    def _study_items(study_nodes):
        out = []
        for n in study_nodes:
            if n.item and n.item.zotero_key:
                out.append((n.item.zotero_key, n.item.citekey))
        return out

    def _refuse(self, dry_run, code, remediation):
        prov = Provenance(tool="assessment_tag_mirror", tool_version=__version__,
                          ran_at=utc_now_iso(), config_hash="", sources=[])
        if dry_run:
            return WriteDiff(kind="tag_mirror", library="personal", confirm_token="",
                             dry_run=True, backend_kind=self.backend.kind,
                             backend_available=self.backend.available, status="not_mirrorable",
                             error_code=code, remediation=remediation, provenance=prov)
        return WriteResult(kind="tag_mirror", library="personal", applied=False,
                           status="failed", error_code=code, remediation=remediation,
                           backend_kind=self.backend.kind, provenance=prov)


def mirrorable_value(rec):
    """Return (value, error). Mirrors only human/panel-decided values."""
    adj = rec.adjudication
    comp = rec.comparison.status
    if adj.event == "adjudicated" and adj.final_value is not None:
        return adj.final_value, None
    if comp == "concordant" and adj.event == "accepted" and adj.final_value is not None:
        return adj.final_value, None
    if (comp == "human_only" or rec.ai_rating is None) and rec.human_rating \
            and rec.human_rating.value is not None:
        return rec.human_rating.value, None
    if comp == "discordant":
        return None, "discordant rating requires human/panel adjudication before mirroring"
    return None, "no human/panel-decided value to mirror (AI values are never mirrored)"
