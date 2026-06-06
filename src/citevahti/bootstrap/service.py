"""MapBootstrapService: parse a guideline into proposed evidence-map seeds."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .. import __version__
from ..bibsync.extract import extract_keys_for_ext
from ..schemas.bootstrap import MapBootstrapReport, ProposedLink, ProposedNode
from ..schemas.common import ItemRef, Provenance
from ..schemas.evidence_map import Link, Node
from ..util import config_hash, sha256_hex, utc_now_iso

_MD_HEAD = re.compile(r"^(#{1,6})\s+(.*\S)\s*$", re.MULTILINE)
_TEX_HEAD = re.compile(r"\\(?:sub)*section\*?\{([^}]*)\}")
_OUT_COMMENT = re.compile(r"<!--\s*outcome:\s*(.+?)\s*-->", re.IGNORECASE)
_OUT_LINE = re.compile(r"^Outcome:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-") or "x"


def _sections(text: str, ext: str) -> list[tuple[str, int, int]]:
    heads: list[tuple[int, str]] = []
    if ext == ".tex":
        heads = [(m.start(), m.group(1).strip()) for m in _TEX_HEAD.finditer(text)]
    else:
        heads = [(m.start(), m.group(2).strip()) for m in _MD_HEAD.finditer(text)]
    if not heads:
        return [("document", 0, len(text))]
    out = []
    for i, (start, label) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        out.append((label, start, end))
    return out


def _outcomes(span: str) -> list[str]:
    found: list[str] = []
    for m in _OUT_COMMENT.finditer(span):
        found.append(m.group(1).strip())
    for m in _OUT_LINE.finditer(span):
        found.append(m.group(1).strip())
    # de-dup preserving order
    seen = set()
    return [o for o in found if not (o in seen or seen.add(o))]


class MapBootstrapService:
    def __init__(self, store, resolver) -> None:
        self.store = store
        self.resolver = resolver  # object with resolve_citekey(citekey, library) -> ItemRef|None

    def bootstrap(self, guideline_path: str, bibliography_path: Optional[str] = None,
                  library="personal", dry_run: bool = True) -> MapBootstrapReport:
        prov = Provenance(tool="map_bootstrap", tool_version=__version__, ran_at=utc_now_iso(),
                          config_hash=config_hash({"guideline": guideline_path, "dry_run": dry_run}),
                          sources=[{"kind": "local_state", "detail": "guideline parse"},
                                   {"kind": "bbt", "detail": "exact citekey resolution"}])
        path = Path(guideline_path)
        report = MapBootstrapReport(guideline_path=guideline_path, dry_run=dry_run, provenance=prov)
        if not path.is_file():
            report.status = "degraded"
            report.error_code = "file_not_found"
            report.remediation = f"Guideline file not found: {guideline_path}"
            return report
        text = path.read_text(encoding="utf-8", errors="replace")
        ext = path.suffix.lower()

        nodes: dict[str, ProposedNode] = {}
        links: list[ProposedLink] = []
        resolved_refs: dict[str, ItemRef] = {}
        orphans: list[str] = []
        outcomes_seen: list[str] = []

        for label, start, end in _sections(text, ext):
            span = text[start:end]
            sec_id = f"section:{_slug(label)}"
            nodes.setdefault(sec_id, ProposedNode(node_id=sec_id, type="section", label=label))
            report.sections.append(label)

            for ck in extract_keys_for_ext(span, ext):
                if ck not in resolved_refs and ck not in orphans:
                    ref = self.resolver.resolve_citekey(ck, library)
                    if ref is None:
                        orphans.append(ck)          # never invented
                        continue
                    resolved_refs[ck] = ref
                    sid = f"study:{ck}"
                    nodes.setdefault(sid, ProposedNode(node_id=sid, type="study", label=ck, citekey=ck))
                if ck in resolved_refs:
                    links.append(ProposedLink(**{"from": sec_id, "to": f"study:{ck}", "type": "cites"}))

            for outcome in _outcomes(span):   # EXPLICIT markers only
                oid = f"outcome:{_slug(outcome)}"
                nodes.setdefault(oid, ProposedNode(node_id=oid, type="outcome", label=outcome))
                if outcome not in outcomes_seen:
                    outcomes_seen.append(outcome)
                links.append(ProposedLink(**{"from": sec_id, "to": oid, "type": "about_outcome"}))

        report.resolved_citekeys = list(resolved_refs.keys())
        report.orphan_citekeys = orphans
        report.outcomes = outcomes_seen
        report.proposed_nodes = list(nodes.values())
        report.proposed_links = links

        if not dry_run:
            self._apply(report, resolved_refs)
        return report

    def _apply(self, report: MapBootstrapReport, resolved_refs: dict[str, ItemRef]) -> None:
        from ..evidence import EvidenceMapService
        svc = EvidenceMapService(self.store)
        emap = svc.load()
        existing_nodes = {n.node_id for n in emap.nodes}
        for pn in report.proposed_nodes:
            if pn.node_id in existing_nodes:
                continue
            item = resolved_refs.get(pn.citekey) if pn.type == "study" and pn.citekey else None
            svc.add_node(emap, Node(node_id=pn.node_id, type=pn.type, label=pn.label, item=item))
            existing_nodes.add(pn.node_id)
        existing_links = {(l.from_, l.to, l.type) for l in emap.links}
        for pl in report.proposed_links:
            sig = (pl.from_, pl.to, pl.type)
            if sig in existing_links:
                continue
            svc.add_link(emap, Link.model_validate({"from": pl.from_, "to": pl.to, "type": pl.type}))
            existing_links.add(sig)
        svc.rebuild_reverse_index(emap)
        svc.save(emap)
        report.written = True
        report.audit_event_id = self.store.audit.entries()[-1].hash
