"""Cite-stable export — durable, portable citations for the manuscript.

A citation survives copy-paste and a Markdown→Word conversion only when it lives
IN the text as a stable key resolvable from a sidecar bibliography. This service
turns the ledger's ACCEPTED decisions into exactly that:

  * it injects a stable ``[@citekey]`` (Pandoc form) right after each accepted
    claim in the manuscript Markdown — idempotent, so re-running never doubles a
    citation; and
  * it emits a matching ``references.bib`` built from the accepted papers'
    identifiers (PMID / DOI / title / journal / year).

It never cites a STALE bond (the claim was reworded after the citation was
accepted — see :mod:`citevahti.claims.bonds`) or an identifier-less paper; those
are reported as skipped, not silently cited. Strictly read-only over the ledger
and the supplied text — no Zotero, no network.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ..util import utc_now_iso
from .claim_report import _ACCEPTING, ClaimReportService


def mint_citekey(pmid: Optional[str], doi: Optional[str]) -> Optional[str]:
    """A stable, collision-free citekey from the paper's identifier. PMID first
    (short, globally unique), then DOI; ``None`` when the paper has neither — we
    never invent a key for an unidentifiable item (cf. ``cite.py``)."""
    if pmid:
        digits = re.sub(r"[^0-9]", "", str(pmid))
        if digits:
            return "pmid" + digits
    if doi:
        slug = re.sub(r"[^a-zA-Z0-9]", "", str(doi)).lower()
        if slug:
            return "doi" + slug
    return None


def _bib_field(name: str, value) -> Optional[str]:
    if value is None or value == "":
        return None
    text = str(value).replace("{", "(").replace("}", ")")   # keep BibTeX braces balanced
    return f"  {name} = {{{text}}}"


def bib_entry(citekey: str, *, title=None, journal=None, year=None,
              doi=None, pmid=None) -> str:
    """A minimal but valid ``@article`` entry. Authors aren't in the ledger's
    candidate snapshot, so the entry leans on the DOI/PMID as the strong
    identifier; CSL/Pandoc renders cleanly from title + journal + year."""
    fields = [f for f in (
        _bib_field("title", title),
        _bib_field("journal", journal),
        _bib_field("year", year),
        _bib_field("doi", doi),
        _bib_field("note", f"PMID: {pmid}" if pmid else None),
    ) if f]
    return f"@article{{{citekey},\n" + ",\n".join(fields) + "\n}"


class CitationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str
    candidate_id: Optional[str] = None
    citekey: Optional[str] = None
    # injected | already_present | not_located | stale | no_identifier
    status: str
    pmid: Optional[str] = None
    doi: Optional[str] = None


class CitationExport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generated_at: str
    annotated_markdown: str
    bibtex: str
    entries: list[CitationEntry] = Field(default_factory=list)
    injected: int = 0
    skipped: int = 0
    warnings: list[str] = Field(default_factory=list)


class CitationExportService:
    """Read-only: derives accepted citations from the ledger and embeds them."""

    def __init__(self, store) -> None:
        self.store = store

    def _candidate(self, claim_id: str, candidate_id: str):
        try:
            for c in self.store.load_candidates(claim_id).candidates:
                if c.candidate_id == candidate_id:
                    return c
        except Exception:  # noqa: BLE001 (a missing candidate just means thinner bib metadata)
            return None
        return None

    @staticmethod
    def _inject(md: str, claim_text: str, marker: str) -> tuple[str, str]:
        """Insert ``marker`` right after ``claim_text``. Idempotent: if the same
        marker already sits just after the claim, leave the text untouched."""
        idx = md.find(claim_text)
        if idx == -1:
            return md, "not_located"
        end = idx + len(claim_text)
        if marker in md[end:end + len(marker) + 60]:     # already cited here
            return md, "already_present"
        return md[:end] + " " + marker + md[end:], "injected"

    def export(self, markdown: str, claim_ids: Optional[list[str]] = None) -> CitationExport:
        report = ClaimReportService(self.store).report(claim_ids)
        md = markdown
        entries: list[CitationEntry] = []
        bib: dict[str, str] = {}        # citekey -> entry (dedup papers cited by >1 claim)
        warnings: list[str] = []
        for row in report.rows:
            if row.state != "accepted":
                continue
            accepting = [e for e in row.evidence if e.final_decision in _ACCEPTING]
            fresh = [e for e in accepting if not e.stale]
            if not accepting:
                continue
            if not fresh:                # accepted, but the claim was reworded since
                ev = accepting[0]
                entries.append(CitationEntry(claim_id=row.claim_id, candidate_id=ev.candidate_id,
                                             status="stale", pmid=ev.pmid, doi=ev.doi))
                warnings.append(f"{row.claim_id}: not cited — the claim was reworded after the "
                                "citation was accepted (stale bond); re-accept to refresh it.")
                continue
            ev = fresh[0]
            citekey = mint_citekey(ev.pmid, ev.doi)
            if not citekey:
                entries.append(CitationEntry(claim_id=row.claim_id, candidate_id=ev.candidate_id,
                                             status="no_identifier", pmid=ev.pmid, doi=ev.doi))
                warnings.append(f"{row.claim_id}: not cited — the accepted paper has no PMID or DOI "
                                "to key on.")
                continue
            md, status = self._inject(md, row.claim_text, f"[@{citekey}]")
            entries.append(CitationEntry(claim_id=row.claim_id, candidate_id=ev.candidate_id,
                                         citekey=citekey, status=status, pmid=ev.pmid, doi=ev.doi))
            if status == "not_located":
                warnings.append(f"{row.claim_id}: claim text not found in the manuscript (was the "
                                f".md edited?); [@{citekey}] not inserted.")
                continue
            cand = self._candidate(row.claim_id, ev.candidate_id)   # journal/year live here
            bib.setdefault(citekey, bib_entry(
                citekey, title=(cand.title if cand else ev.title),
                journal=getattr(cand, "journal", None), year=getattr(cand, "year", None),
                doi=ev.doi, pmid=ev.pmid))
        injected = sum(1 for e in entries if e.status in ("injected", "already_present"))
        return CitationExport(
            generated_at=utc_now_iso(), annotated_markdown=md,
            bibtex=("\n\n".join(bib.values()) + "\n") if bib else "",
            entries=entries, injected=injected, skipped=len(entries) - injected,
            warnings=warnings)
