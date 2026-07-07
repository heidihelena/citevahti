"""File-writing exports (ADR-0010 PR 1l — export group).

The artefacts a review hands off: neutral evidence tables, the human↔AI agreement
report, the self-contained review packet (.zip), the Word report, and the cite-stable
manuscript export (embedded ``[@citekey]`` + ``references.bib``). These write LOCAL
files (under ``exports/`` or beside the manuscript) and read the ledger — nothing is
transmitted anywhere, no judgment is computed, no Zotero library is touched (that is
``tools/writeback.py``).

Forward deps only (no cycle): ``claim_report`` from ``.reports`` renders the packet/docx.

Re-exported unchanged from ``citevahti.tools`` (frozen by tests/test_tools_public_api_stable.py).
"""

from __future__ import annotations

from typing import Optional

from ._common import _open_store
from .reports import claim_report


def evidence_export(selection: Optional[dict] = None, formats: Optional[list[str]] = None,
                    include_provenance: bool = False, include_ai_values: bool = False,
                    output_dir: Optional[str] = None, *, root: Optional[str] = None):
    """Neutral CSV/Markdown/CSL-JSON evidence tables. Read-only; no judgments."""
    from ..export import EvidenceExportService
    return EvidenceExportService(_open_store(root)).export(
        selection=selection, formats=formats, include_provenance=include_provenance,
        include_ai_values=include_ai_values, output_dir=output_dir)


def agreement_report(filters: Optional[dict] = None, metrics: Optional[list[str]] = None,
                     output_formats: Optional[list[str]] = None, output_dir: Optional[str] = None,
                     *, root: Optional[str] = None):
    """Human-AI agreement metrics + method-transparency section. Read-only."""
    from ..export import AgreementReportService
    return AgreementReportService(_open_store(root)).report(
        filters=filters, metrics=metrics, output_formats=output_formats, output_dir=output_dir)


_PACKET_README = (
    "CiteVahti review packet\n"
    "=======================\n\n"
    "A self-contained, local snapshot of a citation-integrity review — for a\n"
    "supervisor, co-author, or journal. Nothing here was transmitted anywhere.\n\n"
    "  citation-integrity-report.md    — the human-readable report (Markdown)\n"
    "  citation-integrity-report.html  — the same report, print-ready (open + Save as PDF)\n"
    "  claims.json                     — the structured claim-by-claim evidence trail,\n"
    "                                    ratings, decisions, and the audit-chain provenance\n"
    "  methods.md                      — a submission-ready methods paragraph, auto-filled\n"
    "                                    with this review's numbers (paste into your manuscript)\n\n"
    "The states record citation support from the blinded human -> AI -> adjudication\n"
    "workflow — not clinical or scientific truth. See the report's Scope & limitations.\n"
)


def export_review_packet(output_path: Optional[str] = None, *, root: Optional[str] = None) -> dict:
    """Bundle the report (Markdown + print-ready HTML) + the structured evidence/audit
    trail into one local ``.zip`` for handing off. Stdlib only; nothing is transmitted."""
    import json
    import os
    import zipfile

    from ..report import build_methods_markdown, render_html, render_markdown
    store = _open_store(root)
    rep = claim_report(root=root)
    stamp = (rep.generated_at or "report").replace(":", "-").replace(".", "-")[:19]
    out = output_path or str(store.dir / "exports" / f"review-packet-{stamp}.zip")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    members = ["citation-integrity-report.md", "citation-integrity-report.html",
               "claims.json", "methods.md", "README.txt"]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(members[0], render_markdown(rep))
        z.writestr(members[1], render_html(rep))
        z.writestr(members[2], json.dumps(rep.model_dump(mode="json"), indent=2, sort_keys=True))
        z.writestr(members[3], build_methods_markdown(store))   # submission-ready methods paragraph
        z.writestr(members[4], _PACKET_README)
    return {"output_file": out, "claim_count": rep.total, "members": members}


def export_report_docx(output_path: Optional[str] = None, *, root: Optional[str] = None) -> dict:
    """Export the report as a Word .docx (needs the optional 'docx' extra; raises a clear
    error otherwise). Local file under exports/; nothing is transmitted."""
    import os

    from ..report import render_docx
    store = _open_store(root)
    rep = claim_report(root=root)
    data = render_docx(rep)          # RuntimeError with install hint if python-docx is absent
    stamp = (rep.generated_at or "report").replace(":", "-").replace(".", "-")[:19]
    out = output_path or str(store.dir / "exports" / f"citation-integrity-report-{stamp}.docx")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(data)
    return {"output_file": out, "claim_count": rep.total}


def _bbt_citekey_source(store):
    """A BbtCitekeySource over the configured Better BibTeX endpoint, or None. The
    source itself degrades to None per-lookup when BBT is unreachable, so callers
    fall back to minted keys without erroring."""
    try:
        from ..bbt.client import BbtClient
        from ..probe.client import HttpxClient
        from ..report.citation_export import BbtCitekeySource
        endpoints = store.load_config().endpoints
        return BbtCitekeySource(BbtClient(HttpxClient(), endpoints))
    except Exception:  # noqa: BLE001 (BBT is best-effort; minted keys are the fallback)
        return None


def cite_export(manuscript_path: str, *, claim_ids: Optional[list[str]] = None,
                root: Optional[str] = None):
    """Cite-stable export: embed a durable ``[@citekey]`` after each ACCEPTED claim
    in the manuscript Markdown and build a matching ``references.bib``.

    Prefers the paper's OWN Better BibTeX citekey (so ``[@key]`` matches the user's
    Zotero), minting a PMID/DOI key only when BBT can't confirm one. The embedded key
    is the citation's portable form — plain text that survives copy-paste and a Pandoc
    Markdown→Word conversion. Read-only over the ledger; returns the annotated text +
    bibliography (the caller writes the files).
    """
    from pathlib import Path

    from ..report.citation_export import CitationExportService
    store = _open_store(root)
    md = Path(manuscript_path).read_text(encoding="utf-8")
    return CitationExportService(store).export(
        md, claim_ids=claim_ids, citekey_source=_bbt_citekey_source(store))


def cite_export_manuscript(manuscript_path: str, *, make_docx: bool = False,
                           root: Optional[str] = None):
    """Run cite-export over a manuscript FILE and write ``<name>.cited.md`` +
    ``references.bib`` beside it (and a ``.docx`` when Pandoc is available). Returns
    the written paths, counts, key sources, and any warnings — for the panel button."""
    from ..report.citation_export import write_outputs
    result = cite_export(manuscript_path, root=root)
    # user-initiated (button) → allow the one-time Pandoc fetch for the .docx
    info = write_outputs(result, manuscript_path, make_docx=make_docx,
                         allow_pandoc_download=make_docx)
    return {**info, "injected": result.injected, "skipped": result.skipped,
            "warnings": result.warnings,
            "bbt_keys": sum(1 for e in result.entries if e.key_source == "bbt"),
            "minted_keys": sum(1 for e in result.entries if e.key_source == "minted")}
