"""EvidenceExportService: neutral CSV / Markdown / CSL-JSON evidence tables.

Read-only. Computes no judgments, resolves no flags, mutates nothing. AI values
are excluded by default and clearly labelled + separated when requested.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Optional

from .. import __version__
from ..schemas.common import Provenance
from ..schemas.export import EvidenceExportReport
from ..state.store import _atomic_write
from ..util import config_hash, sha256_hex, utc_now_iso


def _csv(rows: list[dict], columns: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


class EvidenceExportService:
    def __init__(self, store) -> None:
        self.store = store

    def _run_id(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"{stamp}-{sha256_hex(stamp)[:6]}"

    def export(self, selection: Optional[dict] = None,
               formats: Optional[list[str]] = None, include_provenance: bool = False,
               include_ai_values: bool = False,
               output_dir: Optional[str] = None) -> EvidenceExportReport:
        formats = formats or ["csv", "markdown"]
        emap = self.store.load_evidence_map()
        ratings = self._load_ratings()
        run_id = self._run_id()
        report = EvidenceExportReport(
            run_id=run_id, selection=selection or {}, include_provenance=include_provenance,
            include_ai_values=include_ai_values,
            provenance=Provenance(tool="evidence_export", tool_version=__version__,
                                  ran_at=utc_now_iso(),
                                  config_hash=config_hash({"selection": selection or {},
                                                           "formats": formats}),
                                  sources=[{"kind": "local_state", "detail": "evidence map + ratings"}]))

        sel_nodes, sel_citekeys, full = self._resolve_selection(emap, selection, report)
        report.full_map = full
        report.selected_node_count = len(sel_nodes)
        report.selected_citekeys = sorted(sel_citekeys)
        report.selected_citekey_count = len(sel_citekeys)

        nodes_by_id = {n.node_id: n for n in emap.nodes}
        sel_atts = [a for a in emap.attachments if self._att_selected(a, sel_nodes, sel_citekeys)]

        tables = self._build_tables(emap, nodes_by_id, sel_nodes, sel_citekeys, sel_atts,
                                    ratings, include_provenance, include_ai_values, report)

        # ---- write outputs (timestamped run dir; never clobbers prior) ---
        out_root = (self.store.dir / "exports" / "evidence" / run_id) if output_dir is None \
            else (__import__("pathlib").Path(output_dir) / run_id)
        files: list[str] = []
        if "csv" in formats:
            for name, (cols, rows) in tables.items():
                path = out_root / f"{name}.csv"
                _atomic_write(path, _csv(rows, cols))
                files.append(path.as_posix())
            report.formats_written.append("csv")
        if "markdown" in formats:
            path = out_root / "evidence.md"
            _atomic_write(path, self._markdown(tables, report))
            files.append(path.as_posix())
            report.formats_written.append("markdown")
        if "csl-json" in formats:
            path = out_root / "studies.csl.json"
            _atomic_write(path, self._csl_json(emap, nodes_by_id, sel_nodes, report))
            files.append(path.as_posix())
            report.formats_written.append("csl-json")

        report.output_files = files
        entry = self.store.audit.append(
            "export.evidence", {"run_id": run_id, "files": len(files), "formats": report.formats_written})
        report.audit_event_id = entry.hash
        return report

    # ---- helpers ---------------------------------------------------------
    def _load_ratings(self) -> dict:
        out = {}
        for rid in self.store.list_ratings():
            try:
                out[rid] = self.store.load_rating(rid)
            except Exception:  # noqa: BLE001
                continue
        return out

    def _resolve_selection(self, emap, selection, report):
        nodes_by_id = {n.node_id: n for n in emap.nodes}
        if not selection or not any(selection.values()):
            sel_nodes = {n.node_id for n in emap.nodes}
            sel_ck = set(emap.reverse_index.keys())
            for n in emap.nodes:
                if n.type == "study" and n.item and n.item.citekey:
                    sel_ck.add(n.item.citekey)
            return sel_nodes, sel_ck, True

        sel_nodes: set = set()
        sel_ck: set = set()
        for nid in selection.get("node_ids", []) or []:
            (sel_nodes.add(nid) if nid in nodes_by_id
             else report.warnings.append(f"unknown node_id {nid!r}"))
        for ck in selection.get("citekeys", []) or []:
            entry = emap.reverse_index.get(ck)
            if entry is None:
                report.warnings.append(f"unknown citekey {ck!r}")
                continue
            sel_ck.add(ck)
            if entry.study_node_id:
                sel_nodes.add(entry.study_node_id)
            sel_nodes.update(entry.outcome_node_ids)
            sel_nodes.update(entry.recommendation_node_ids)
        for rid in selection.get("recommendation_ids", []) or []:
            if rid not in nodes_by_id:
                report.warnings.append(f"unknown recommendation_id {rid!r}")
                continue
            sel_nodes.add(rid)
            for l in emap.links:
                if l.from_ == rid:
                    sel_nodes.add(l.to)
        for oid in selection.get("outcome_ids", []) or []:
            if oid not in nodes_by_id:
                report.warnings.append(f"unknown outcome_id {oid!r}")
                continue
            sel_nodes.add(oid)
            for ck, entry in emap.reverse_index.items():
                if oid in entry.outcome_node_ids:
                    sel_ck.add(ck)
                    if entry.study_node_id:
                        sel_nodes.add(entry.study_node_id)
            for l in emap.links:
                if l.to == oid:
                    sel_nodes.add(l.from_)
        for n in emap.nodes:
            if n.node_id in sel_nodes and n.type == "study" and n.item and n.item.citekey:
                sel_ck.add(n.item.citekey)
        return sel_nodes, sel_ck, False

    @staticmethod
    def _att_selected(a, sel_nodes, sel_ck) -> bool:
        return (a.citekey in sel_ck or a.study_node_id in sel_nodes
                or a.outcome_node_id in sel_nodes or a.target_node_id in sel_nodes)

    def _build_tables(self, emap, nodes_by_id, sel_nodes, sel_ck, sel_atts, ratings,
                      inc_prov, inc_ai, report):
        retraction_by_ck: dict[str, list[str]] = {}
        for a in emap.attachments:
            if a.kind == "retraction_flag" and a.citekey:
                retraction_by_ck.setdefault(a.citekey, []).append(a.attachment_id)

        studies = []
        for n in emap.nodes:
            if n.node_id not in sel_nodes or n.type != "study":
                continue
            ck = n.item.citekey if n.item else None
            entry = emap.reverse_index.get(ck) if ck else None
            studies.append({"node_id": n.node_id, "citekey": ck,
                            "zotero_key": n.item.zotero_key if n.item else None,
                            "label": n.label,
                            "stale_flags": ";".join(entry.stale_flags) if entry else "",
                            "retraction_flags": ";".join(retraction_by_ck.get(ck, []))})
        studies_cols = ["node_id", "citekey", "zotero_key", "label", "stale_flags", "retraction_flags"]

        extracted, claims, assessments = [], [], []
        prov_cols = ["prov_tool", "prov_ran_at", "prov_config_hash"] if inc_prov else []
        ai_cols = ["ai_value", "ai_abstained", "ai_confidence", "ai_model_id",
                   "ai_model_snapshot"] if inc_ai else []
        for a in sel_atts:
            prov = {}
            if inc_prov and a.provenance:
                prov = {"prov_tool": a.provenance.tool, "prov_ran_at": a.provenance.ran_at,
                        "prov_config_hash": a.provenance.config_hash}
            if a.kind == "extracted_field":
                loc = (a.payload.get("passage") or {}).get("location") if a.payload else None
                extracted.append({"attachment_id": a.attachment_id, "citekey": a.citekey,
                                  "study_node_id": a.study_node_id,
                                  "field": (a.payload or {}).get("field"),
                                  "value": (a.payload or {}).get("value"),
                                  "passage_locator": loc, **prov})
            elif a.kind == "verified_claim":
                loc = (a.payload.get("passage") or {}).get("location") if a.payload else None
                claims.append({"attachment_id": a.attachment_id, "citekey": a.citekey,
                               "claim_id": a.claim_id, "claim_text": a.claim_text,
                               "passage_locator": loc, **prov})
            elif a.kind == "assessment":
                row = {"attachment_id": a.attachment_id, "scheme_kind": a.scheme_kind,
                       "study_node_id": a.study_node_id, "outcome_node_id": a.outcome_node_id,
                       "value": (a.payload or {}).get("value"), "rating_id": a.rating_id,
                       "human_value": None, "final_value": None, "comparison_status": None, **prov}
                rec = ratings.get(a.rating_id) if a.rating_id else None
                if rec is not None:
                    row["human_value"] = rec.human_rating.value if rec.human_rating else None
                    row["final_value"] = rec.adjudication.final_value
                    row["comparison_status"] = rec.comparison.status
                    if inc_ai and rec.ai_rating is not None:
                        row.update({"ai_value": rec.ai_rating.value,
                                    "ai_abstained": rec.ai_rating.abstained,
                                    "ai_confidence": rec.ai_rating.confidence,
                                    "ai_model_id": rec.ai_rating.provenance.model_id,
                                    "ai_model_snapshot": rec.ai_rating.provenance.model_snapshot})
                assessments.append(row)
        extracted_cols = ["attachment_id", "citekey", "study_node_id", "field", "value",
                          "passage_locator"] + prov_cols
        claims_cols = ["attachment_id", "citekey", "claim_id", "claim_text",
                       "passage_locator"] + prov_cols
        assess_cols = ["attachment_id", "scheme_kind", "study_node_id", "outcome_node_id",
                       "value", "rating_id", "human_value", "final_value",
                       "comparison_status"] + ai_cols + prov_cols

        links = [{"from": l.from_, "to": l.to, "type": l.type, "link_id": l.link_id}
                 for l in emap.links if l.from_ in sel_nodes and l.to in sel_nodes]
        links_cols = ["from", "to", "type", "link_id"]

        return {"studies": (studies_cols, studies),
                "extracted_fields": (extracted_cols, extracted),
                "verified_claims": (claims_cols, claims),
                "assessments": (assess_cols, assessments),
                "links": (links_cols, links)}

    def _markdown(self, tables, report) -> str:
        lines = ["# Evidence export (neutral table)", "",
                 f"_Run {report.run_id}. This is a record of what was captured; it makes no "
                 "judgments and resolves no flags._", "",
                 f"- Selected nodes: {report.selected_node_count}",
                 f"- Selected citekeys: {report.selected_citekey_count}",
                 f"- AI values included: {report.include_ai_values}", ""]
        sc, srows = tables["studies"]
        lines += ["## Studies", "", "| citekey | label | stale_flags | retraction_flags |",
                  "| --- | --- | --- | --- |"]
        for r in srows:
            lines.append(f"| {r.get('citekey') or ''} | {r.get('label') or ''} | "
                         f"{r.get('stale_flags') or ''} | {r.get('retraction_flags') or ''} |")
        ac, arows = tables["assessments"]
        lines += ["", "## Assessments", "",
                  "| scheme | value | human_value | final_value | comparison |",
                  "| --- | --- | --- | --- | --- |"]
        for r in arows:
            lines.append(f"| {r.get('scheme_kind') or ''} | {r.get('value') or ''} | "
                         f"{r.get('human_value') or ''} | {r.get('final_value') or ''} | "
                         f"{r.get('comparison_status') or ''} |")
        if report.warnings:
            lines += ["", "## Warnings", ""] + [f"- {w}" for w in report.warnings]
        lines += ["", "## Provenance", "",
                  f"- tool: {report.provenance.tool} {report.provenance.tool_version}",
                  f"- generated: {report.provenance.ran_at}"]
        return "\n".join(lines) + "\n"

    def _csl_json(self, emap, nodes_by_id, sel_nodes, report) -> str:
        snap = None
        snaps = self.store.list_snapshots()
        if snaps:
            snap = self.store.load_snapshot(snaps[-1])
        items = []
        for n in emap.nodes:
            if n.node_id not in sel_nodes or n.type != "study":
                continue
            ck = n.item.citekey if n.item else None
            if not ck:
                report.warnings.append(f"study {n.node_id!r} has no citekey; omitted from CSL-JSON")
                continue
            meta = snap.items.get(ck) if snap else None
            item = {"id": ck, "type": "article-journal"}
            if meta is not None:
                if meta.title:
                    item["title"] = meta.title
                if meta.doi:
                    item["DOI"] = meta.doi
                if meta.year:
                    item["issued"] = {"date-parts": [[meta.year]]}
            if "title" not in item:
                report.warnings.append(f"insufficient CSL metadata for {ck!r} (no title)")
            items.append(item)        # never invents missing fields
        return json.dumps(items, ensure_ascii=False, indent=2)
