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
    key_source: Optional[str] = None          # "bbt" (the user's own key) | "minted"
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

    def export(self, markdown: str, claim_ids: Optional[list[str]] = None,
               citekey_source=None) -> CitationExport:
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
            # Prefer the paper's OWN Better BibTeX citekey (so [@key] matches the user's
            # Zotero library); fall back to a minted PMID/DOI key — never guessing.
            bbt_key = citekey_source.citekey_for(ev.pmid, ev.doi) if citekey_source else None
            citekey = bbt_key or mint_citekey(ev.pmid, ev.doi)
            key_source = "bbt" if bbt_key else "minted"
            if not citekey:
                entries.append(CitationEntry(claim_id=row.claim_id, candidate_id=ev.candidate_id,
                                             status="no_identifier", pmid=ev.pmid, doi=ev.doi))
                warnings.append(f"{row.claim_id}: not cited — the accepted paper has no PMID or DOI "
                                "to key on.")
                continue
            md, status = self._inject(md, row.claim_text, f"[@{citekey}]")
            entries.append(CitationEntry(claim_id=row.claim_id, candidate_id=ev.candidate_id,
                                         citekey=citekey, status=status, key_source=key_source,
                                         pmid=ev.pmid, doi=ev.doi))
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


class BbtCitekeySource:
    """Resolve a paper's OWN Better BibTeX citekey, so the embedded ``[@key]`` matches
    the user's Zotero library (and their normal BBT auto-export ``.bib``).

    Returns ``None`` when BBT is unreachable or can't confirm a single matching item —
    the caller then mints a key, never guessing. Talks to the Better BibTeX plugin's
    JSON-RPC; it does NOT require the FullVahti add-on.
    """

    def __init__(self, bbt) -> None:
        self.bbt = bbt

    def citekey_for(self, pmid, doi) -> Optional[str]:
        from ..bbt.client import BbtError, BbtUnavailable, _extract_citekey
        from ..intake.dedupe import normalize_doi, normalize_pmid
        np, nd = normalize_pmid(pmid), normalize_doi(doi)
        for term in filter(None, [doi, pmid]):
            try:
                items = self.bbt.jsonrpc("item.search", [term])
            except (BbtUnavailable, BbtError):
                return None
            matches = []
            for it in (items if isinstance(items, list) else []):
                if not isinstance(it, dict):
                    continue
                ck = _extract_citekey(it)
                if not ck:
                    continue
                it_doi = normalize_doi(it.get("DOI") or it.get("doi"))
                extra = str(it.get("extra") or "")
                pmid_hit = np and bool(re.search(rf"PMID:\s*{re.escape(np)}\b", extra))
                if (nd and it_doi == nd) or pmid_hit:
                    matches.append(ck)
            uniq = list(dict.fromkeys(matches))
            if len(uniq) == 1:          # exactly one confirmed item -> safe to use its key
                return uniq[0]
        return None


def _resolve_pandoc(allow_download: bool):
    """``(pandoc_path, error)``. System PATH first; else, when ``allow_download`` is
    set, fetch the Pandoc binary ONCE via pypandoc into the user data dir — the
    no-terminal "first-run fetch". Never downloads unless explicitly allowed (keeps
    offline tests/CI offline)."""
    import shutil

    sys_pandoc = shutil.which("pandoc")
    if sys_pandoc:
        return sys_pandoc, None
    try:
        import pypandoc
    except ImportError:
        return None, "pandoc_unavailable"          # pypandoc not installed at all
    try:
        return pypandoc.get_pandoc_path(), None     # a previously-fetched copy
    except OSError:
        pass
    if not allow_download:
        return None, "pandoc_not_found"
    try:
        pypandoc.download_pandoc()                   # one-time ~100MB into the user dir
        return pypandoc.get_pandoc_path(), None
    except Exception as exc:  # noqa: BLE001 (offline / disk / mirror — degrade honestly)
        return None, "pandoc_fetch_failed: " + str(exc)[:160]


def write_outputs(result: CitationExport, manuscript_path, *, out=None, bib=None,
                  in_place: bool = False, make_docx: bool = False,
                  allow_pandoc_download: bool = False) -> dict:
    """Write the annotated markdown + ``references.bib`` beside the manuscript, and —
    when Pandoc is available — a ``.docx`` with live citations + a bibliography.

    Pandoc is resolved from PATH, else fetched once via pypandoc when
    ``allow_pandoc_download`` is set. Without it you still get the portable
    ``.md`` + ``.bib`` pair; the ``.docx`` is best-effort."""
    import subprocess
    from pathlib import Path

    src = Path(manuscript_path)
    md_path = Path(out) if out else (src if in_place else src.with_suffix(".cited.md"))
    bib_path = Path(bib) if bib else src.with_name("references.bib")
    md_path.write_text(result.annotated_markdown, encoding="utf-8")
    info = {"markdown_path": str(md_path), "bib_path": None,
            "docx_path": None, "docx_status": None}
    if result.bibtex:
        bib_path.write_text(result.bibtex, encoding="utf-8")
        info["bib_path"] = str(bib_path)
    if make_docx:
        if not result.bibtex:
            info["docx_status"] = "no_citations"
        else:
            pandoc, err = _resolve_pandoc(allow_pandoc_download)
            if err:
                info["docx_status"] = err
            else:
                docx_path = md_path.with_suffix(".docx")
                try:
                    subprocess.run([pandoc, str(md_path), "--citeproc",
                                    f"--bibliography={bib_path}", "-o", str(docx_path)],
                                   check=True, capture_output=True)
                    info["docx_path"] = str(docx_path)
                    info["docx_status"] = "ok"
                except subprocess.CalledProcessError as exc:
                    info["docx_status"] = "pandoc_failed: " + (exc.stderr or b"").decode()[:160]
    return info
