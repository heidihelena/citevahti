"""AgreementReportService: human-AI agreement metrics + method transparency.

Read-only over rating records. Changes nothing, adjudicates nothing, infers no
final values. human_only and ai_abstained are excluded from the agreement
denominator and reported separately. Adjudicated records are counted by their
ORIGINAL human-AI comparison, not the final adjudicated value.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from .. import __version__
from ..schemas.common import Provenance
from ..schemas.export import AgreementCounts, AgreementGroup, AgreementReport
from ..state.store import _atomic_write
from ..util import config_hash, sha256_hex, utc_now_iso
from .kappa import cohen_kappa, raw_agreement, weighted_kappa

_COMPARABLE = {"concordant", "discordant"}


def _rating_date(rec) -> Optional[str]:
    if rec.human_rating and rec.human_rating.committed_at:
        return rec.human_rating.committed_at
    if rec.ai_rating:
        return rec.ai_rating.provenance.rated_at
    return rec.comparison.computed_at


class AgreementReportService:
    def __init__(self, store) -> None:
        self.store = store
        self._frames: dict[str, object] = {}

    # ---- frame/scheme lookup --------------------------------------------
    def _scheme(self, frame_id: str, scheme_id: str):
        frame = self._frames.get(frame_id)
        if frame is None:
            try:
                frame = self.store.load_frame(frame_id)
            except Exception:  # noqa: BLE001
                return None
            self._frames[frame_id] = frame
        return frame.get_scheme(scheme_id)

    # ---- main ------------------------------------------------------------
    def report(self, filters: Optional[dict] = None, metrics: Optional[list[str]] = None,
               output_formats: Optional[list[str]] = None,
               output_dir: Optional[str] = None, persist: bool = True) -> AgreementReport:
        """Compute the agreement report. With ``persist=False`` it is a pure read —
        no files written under ``exports/`` and no audit event — for callers that only
        need the numbers (e.g. the methods statement), never an exported artifact."""
        filters = filters or {}
        metrics = metrics or ["raw_agreement", "adjudication_rate"]
        output_formats = output_formats or ["json", "markdown"]
        run_id = self._run_id()
        report = AgreementReport(
            run_id=run_id, filters=filters, metrics=metrics,
            grouped_by=filters.get("group_by", []) or [],
            provenance=Provenance(tool="agreement_report", tool_version=__version__,
                                  ran_at=utc_now_iso(),
                                  config_hash=config_hash({"filters": filters, "metrics": metrics}),
                                  sources=[{"kind": "local_state", "detail": "rating records"}]))

        records = self._load_filtered(filters, report)
        report.ai_provenance_summary = self._ai_summary(records)

        groups = self._partition(records, report.grouped_by)
        for key, recs in groups:
            report.groups.append(self._group_metrics(key, recs, metrics, report))
        report.overall = self._counts(records)
        report.method_transparency_markdown = self._transparency(report)

        if persist:
            self._write(report, output_formats, output_dir, run_id)
        return report

    # ---- loading / filtering --------------------------------------------
    def _load_filtered(self, filters, report) -> list:
        out = []
        for rid in self.store.list_ratings():
            try:
                rec = self.store.load_rating(rid)
            except Exception:  # noqa: BLE001
                report.warnings.append(f"skipped invalid rating {rid!r}")
                continue
            if filters.get("scheme_id") and rec.scheme_id != filters["scheme_id"]:
                continue
            if filters.get("task_type"):
                tt = rec.ai_rating.task_type if rec.ai_rating else None
                if tt != filters["task_type"]:
                    continue
            dr = filters.get("date_range") or {}
            d = _rating_date(rec)
            if dr.get("from") and (d or "") < dr["from"]:
                continue
            if dr.get("to") and (d or "") > dr["to"]:
                continue
            out.append(rec)
        return out

    # ---- grouping --------------------------------------------------------
    def _partition(self, records, group_by):
        if not group_by:
            return [({}, records)]
        buckets: dict = {}
        for rec in records:
            key = {}
            for g in group_by:
                if g == "scheme_id":
                    key["scheme_id"] = rec.scheme_id
                elif g == "task_type":
                    key["task_type"] = rec.ai_rating.task_type if rec.ai_rating else None
                elif g == "frame_id":
                    key["frame_id"] = rec.frame_id
                elif g == "frame_version":
                    key["frame_version"] = rec.frame_version
            buckets.setdefault(json.dumps(key, sort_keys=True), (key, []))[1].append(rec)
        return list(buckets.values())

    # ---- per-group metrics ----------------------------------------------
    def _counts(self, records) -> AgreementCounts:
        c = AgreementCounts()
        finals = Counter()
        for rec in records:
            s = rec.comparison.status
            if s == "concordant":
                c.comparable_pairs += 1
                c.agreements += 1
            elif s == "discordant":
                c.comparable_pairs += 1
                c.disagreements += 1
            elif s == "ai_abstained":
                c.ai_abstained += 1
            elif s == "human_only":
                c.human_only += 1
            if rec.adjudication.event == "adjudicated":
                c.adjudicated += 1
            if rec.adjudication.final_value is not None:
                finals[rec.adjudication.final_value] += 1
            if s == "discordant" and rec.adjudication.event != "adjudicated":
                c.pending_adjudication += 1
        c.final_value_categories = dict(finals)
        return c

    def _group_metrics(self, key, recs, metrics, report) -> AgreementGroup:
        counts = self._counts(recs)
        scheme_ids = {r.scheme_id for r in recs}
        frame_versions = {r.frame_version for r in recs}
        single_scheme = next(iter(scheme_ids)) if len(scheme_ids) == 1 else None
        grp = AgreementGroup(key=key, scheme_id=single_scheme, counts=counts)

        # ORIGINAL comparison drives agreement (not the final adjudicated value)
        pairs = [(r.human_rating.value, r.ai_rating.value) for r in recs
                 if r.comparison.status in _COMPARABLE and r.human_rating and r.ai_rating
                 and r.human_rating.value is not None and r.ai_rating.value is not None]

        if "raw_agreement" in metrics:
            grp.metrics["raw_agreement"] = raw_agreement(pairs)

        kappa_requested = "cohen_kappa" in metrics or "weighted_kappa" in metrics
        if kappa_requested and single_scheme is None:
            grp.warnings.append("kappa refused across mixed schemes; group by scheme_id")
        if kappa_requested and len(frame_versions) > 1:
            grp.warnings.append("multiple frame_versions in group; report grouped by frame_version")

        if "cohen_kappa" in metrics and single_scheme is not None and len(frame_versions) == 1:
            val, err = cohen_kappa(pairs)
            grp.metrics["cohen_kappa"] = {**val, "error": err} if err else val

        if "weighted_kappa" in metrics and single_scheme is not None and len(frame_versions) == 1:
            scheme = self._scheme(recs[0].frame_id, single_scheme)
            if scheme is None:
                grp.metrics["weighted_kappa"] = {"value": None, "error": "scheme_not_found"}
            else:
                ordinals = {lvl.value: lvl.ordinal for lvl in scheme.levels if not lvl.missing_like}
                missing_like = {lvl.value for lvl in scheme.levels if lvl.missing_like}
                kept = [(a, b) for a, b in pairs if a in ordinals and b in ordinals]
                excluded = len(pairs) - len(kept)
                val, err = weighted_kappa(kept, ordinals, weights="quadratic")
                res = {**val, "error": err} if err else dict(val)
                res["excluded_missing_like"] = excluded
                if excluded:
                    res["excluded_values"] = sorted(missing_like)
                    grp.warnings.append(
                        f"excluded {excluded} pair(s) with missing-like values "
                        f"({sorted(missing_like)}) from ordinal weighted kappa")
                grp.metrics["weighted_kappa"] = res

        if "adjudication_rate" in metrics:
            cp = counts.comparable_pairs
            grp.metrics["adjudication_rate"] = {
                "rate": (counts.disagreements / cp) if cp else None,
                "adjudicated": counts.adjudicated,
                "pending_adjudication": counts.pending_adjudication,
                "final_value_categories": counts.final_value_categories}
        return grp

    # ---- AI provenance summary ------------------------------------------
    def _ai_summary(self, records) -> dict:
        ai = [r.ai_rating for r in records if r.ai_rating is not None]
        if not ai:
            return {"ratings_with_ai": 0}
        dates = [a.provenance.rated_at for a in ai if a.provenance.rated_at]
        return {
            "ratings_with_ai": len(ai),
            "model_ids": sorted({a.provenance.model_id for a in ai}),
            "model_snapshots": sorted({a.provenance.model_snapshot for a in ai}),
            "prompt_template_versions": sorted({a.provenance.prompt_template_version for a in ai}),
            "prompt_hash_count": len({a.provenance.prompt_hash for a in ai}),
            "config_hash_count": len({a.provenance.config_hash for a in ai}),
            "rating_dates": {"min": min(dates), "max": max(dates)} if dates else {},
            "blinding_modes": sorted({r.blinding.mode for r in records}),
            "abstention_count": sum(1 for a in ai if a.abstained),
            "task_types": sorted({a.task_type for a in ai if a.task_type}),
        }

    # ---- method transparency (PRISMA-trAIce / RAISE-style) --------------
    def _transparency(self, report) -> str:
        cfg = self.store.load_config()
        ai = cfg.ai_provenance
        s = report.ai_provenance_summary
        lines = [
            "## AI-in-evidence-synthesis method transparency", "",
            "_This section reports what was done. It is not a claim of compliance with, or "
            "endorsement by, any reporting guideline._", "",
            "- **AI role**: advisory, blinded independent second rater. The AI never decides, "
            "never sets the recorded value, and never silently propagates a rating.",
            f"- **Task types where AI was used**: {s.get('task_types', [])}",
            f"- **Blinding mode**: {cfg.rating.order} (modes observed: {s.get('blinding_modes', [])}); "
            "the AI never receives the human value.",
            f"- **Abstention handling**: AI may abstain; abstentions ({s.get('abstention_count', 0)}) "
            "are excluded from the human-AI agreement denominator and reported separately.",
            "- **Comparison rule**: concordant -> accepted (human value); discordant -> "
            "needs adjudication; human_only and ai_abstained are not human-AI agreement.",
            "- **Adjudication rule**: a discordance is resolved only by a human or panel, with a "
            "rationale; the AI value is never copied to the final value automatically.",
            "- **Human/panel final authority**: the recorded final value is always human/panel-sourced.",
            f"- **Model provenance**: provider={ai.provider}, model_ids={s.get('model_ids', [])}, "
            f"snapshots={s.get('model_snapshots', [])}, "
            f"prompt_template_versions={s.get('prompt_template_versions', [])}, "
            f"distinct prompt hashes={s.get('prompt_hash_count', 0)}, "
            f"distinct config hashes={s.get('config_hash_count', 0)}.",
            f"- **Agreement metrics**: overall comparable pairs={report.overall.comparable_pairs}, "
            f"agreements={report.overall.agreements}, disagreements={report.overall.disagreements}, "
            f"pending adjudication={report.overall.pending_adjudication}.",
            "- **Limitations**: agreement reflects only records where both a human and a "
            "non-abstaining AI rating exist; metrics are descriptive and do not validate the AI, "
            "establish ground truth, or substitute for human judgment.",
        ]
        return "\n".join(lines) + "\n"

    # ---- output ----------------------------------------------------------
    def _run_id(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"{stamp}-{sha256_hex(stamp)[:6]}"

    def _write(self, report, formats, output_dir, run_id) -> None:
        out_root = (self.store.dir / "exports" / "agreement" / run_id) if output_dir is None \
            else (__import__("pathlib").Path(output_dir) / run_id)
        files = []
        if "json" in formats:
            p = out_root / "agreement.json"
            _atomic_write(p, json.dumps(report.model_dump(exclude={"output_files", "audit_event_id"}),
                                        ensure_ascii=False, indent=2))
            files.append(p.as_posix())
            report.formats_written.append("json")
        if "csv" in formats:
            p = out_root / "agreement_groups.csv"
            _atomic_write(p, self._groups_csv(report))
            files.append(p.as_posix())
            report.formats_written.append("csv")
        if "markdown" in formats:
            p = out_root / "agreement.md"
            _atomic_write(p, self._markdown(report))
            files.append(p.as_posix())
            report.formats_written.append("markdown")
        report.output_files = files
        entry = self.store.audit.append(
            "export.agreement", {"run_id": run_id, "files": len(files),
                                 "formats": report.formats_written})
        report.audit_event_id = entry.hash

    def _groups_csv(self, report) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["group", "scheme_id", "comparable_pairs", "agreements", "disagreements",
                    "human_only", "ai_abstained", "raw_agreement", "cohen_kappa", "weighted_kappa"])
        for g in report.groups:
            ck = (g.metrics.get("cohen_kappa") or {}).get("value")
            wk = (g.metrics.get("weighted_kappa") or {}).get("value")
            w.writerow([json.dumps(g.key), g.scheme_id, g.counts.comparable_pairs,
                        g.counts.agreements, g.counts.disagreements, g.counts.human_only,
                        g.counts.ai_abstained, g.metrics.get("raw_agreement"), ck, wk])
        return buf.getvalue()

    def _markdown(self, report) -> str:
        lines = ["# Agreement report", "",
                 f"_Run {report.run_id}. Descriptive metrics over recorded ratings; nothing "
                 "is changed, adjudicated, or inferred._", "",
                 "## Overall counts", "",
                 f"- comparable human-AI pairs: {report.overall.comparable_pairs}",
                 f"- agreements: {report.overall.agreements}",
                 f"- disagreements: {report.overall.disagreements}",
                 f"- human_only (excluded from agreement): {report.overall.human_only}",
                 f"- ai_abstained (excluded from agreement): {report.overall.ai_abstained}",
                 f"- pending adjudication: {report.overall.pending_adjudication}", ""]
        for g in report.groups:
            lines += [f"## Group {g.key or '(all)'}", "",
                      f"- scheme: {g.scheme_id}", f"- metrics: {g.metrics}"]
            for w in g.warnings:
                lines.append(f"- warning: {w}")
            lines.append("")
        lines += [report.method_transparency_markdown]
        if report.warnings:
            lines += ["## Warnings", ""] + [f"- {w}" for w in report.warnings]
        return "\n".join(lines) + "\n"
