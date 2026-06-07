"""Resolve a manuscript's source text and map claims onto it (ADR-0002/0007).

The ledger stores each claim's ``claim_text`` plus a ``manuscript_id`` (a bare
filename) and ``manuscript_location`` (``<file>:L<line>``) — never the manuscript
body. To review claims *in place*, the panel binds a manuscripts folder, resolves
``manuscript_id`` to a file on disk, and maps each claim onto the prose by
whitespace-tolerant matching. When no file resolves, the document is reconstructed
from the ordered claim texts so the inliner is never blank.

This module is pure (no store, no sockets): the server gathers claims and a bound
folder and calls these helpers. Document edits (revise/strike) are computed here as
plain text transforms; the server gates them behind preview → commit → undo.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


# ---- location parsing -------------------------------------------------------
_LOC = re.compile(r"^(?P<file>.+?)(?::L(?P<line>\d+))?$")


def parse_location(manuscript_location: Optional[str]) -> tuple[Optional[str], Optional[int]]:
    """``"draft.md:L233"`` -> ``("draft.md", 233)``; tolerate a bare filename."""
    if not manuscript_location:
        return None, None
    m = _LOC.match(manuscript_location.strip())
    if not m:
        return None, None
    line = m.group("line")
    return m.group("file"), (int(line) if line else None)


def resolve_path(manuscripts_dir: Optional[str], manuscript_id: Optional[str]) -> Optional[Path]:
    """Find ``manuscript_id`` (a basename) under the bound folder, recursively.

    Returns ``None`` when no folder is bound or no matching file exists — the
    caller then reconstructs the document from claim text."""
    if not manuscripts_dir or not manuscript_id:
        return None
    base = Path(manuscripts_dir).expanduser()
    name = Path(manuscript_id).name
    direct = base / name
    if direct.is_file():
        return direct
    try:
        return next((p for p in base.rglob(name) if p.is_file()), None)
    except OSError:
        return None


# ---- whitespace-tolerant matching ------------------------------------------
def _normalize_with_map(s: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs to one space, keeping a map back to original
    offsets so a match in the normalized text yields original char positions."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = False
    for i, ch in enumerate(s):
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                idx.append(i)
            prev_space = True
        else:
            out.append(ch)
            idx.append(i)
            prev_space = False
    return "".join(out), idx


def _line_offset(source: str, line: Optional[int]) -> int:
    """Char offset of the start of 1-based ``line`` (0 when unknown)."""
    if not line or line < 2:
        return 0
    pos = 0
    for _ in range(line - 1):
        nl = source.find("\n", pos)
        if nl == -1:
            return pos
        pos = nl + 1
    return pos


@dataclass
class _Span:
    start: int
    end: int
    claim_id: str


def _locate(norm_src: str, src_map: list[int], source: str, claim_text: str,
            line: Optional[int]) -> Optional[tuple[int, int]]:
    """Original (start, end) offsets of ``claim_text`` in ``source``, or None.

    Matches on normalized whitespace and, when the same text repeats, prefers the
    occurrence nearest the ``:Lnnn`` hint."""
    norm_claim = _normalize_with_map(claim_text)[0].strip()
    if not norm_claim:
        return None
    # all normalized-space occurrences
    starts: list[int] = []
    at = norm_src.find(norm_claim)
    while at != -1:
        starts.append(at)
        at = norm_src.find(norm_claim, at + 1)
    if not starts:
        return None
    if len(starts) > 1 and line:
        # pick the occurrence whose original start is closest to the line hint
        hint = _line_offset(source, line)
        starts.sort(key=lambda n: abs(src_map[n] - hint))
    n0 = starts[0]
    n1 = n0 + len(norm_claim) - 1
    return src_map[n0], src_map[n1] + 1


# ---- document view ----------------------------------------------------------
def _segments(source: str, spans: list[_Span]) -> list[dict]:
    """Interleave plain-text and claim segments from non-overlapping spans."""
    spans = sorted(spans, key=lambda s: s.start)
    out: list[dict] = []
    cursor = 0
    for sp in spans:
        if sp.start < cursor:        # overlap — skip the later claim's span
            continue
        if sp.start > cursor:
            out.append({"kind": "text", "text": source[cursor:sp.start]})
        out.append({"kind": "claim", "text": source[sp.start:sp.end], "claim_id": sp.claim_id})
        cursor = sp.end
    if cursor < len(source):
        out.append({"kind": "text", "text": source[cursor:]})
    return out


def build_view(manuscript_id: str, claims: list[dict],
               manuscripts_dir: Optional[str]) -> dict:
    """Build the document model for one manuscript.

    ``claims`` items need ``claim_id``, ``claim_text`` and ``manuscript_location``.
    Returns ``mode`` ``"file"`` (real prose, spans mapped) or ``"reconstructed"``
    (claim sentences only), the ordered ``segments``, the ``resolved_path`` if any,
    and the ``unmatched`` claim ids (rendered by the UI as a side list)."""
    path = resolve_path(manuscripts_dir, manuscript_id)
    if path is None:
        return _reconstructed(manuscript_id, claims)
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _reconstructed(manuscript_id, claims)

    norm_src, src_map = _normalize_with_map(source)
    spans: list[_Span] = []
    unmatched: list[str] = []
    for c in claims:
        _, line = parse_location(c.get("manuscript_location"))
        hit = _locate(norm_src, src_map, source, c.get("claim_text", ""), line)
        if hit:
            spans.append(_Span(hit[0], hit[1], c["claim_id"]))
        else:
            unmatched.append(c["claim_id"])
    return {
        "manuscript_id": manuscript_id,
        "mode": "file",
        "resolved_path": str(path),
        "segments": _segments(source, spans),
        "matched": [s.claim_id for s in spans],
        "unmatched": unmatched,
    }


def _reconstructed(manuscript_id: str, claims: list[dict]) -> dict:
    """Fallback document: ordered claim sentences, no surrounding prose."""
    def key(c):
        _, line = parse_location(c.get("manuscript_location"))
        return (line if line is not None else 1_000_000, c.get("claim_id", ""))
    segs: list[dict] = []
    for c in sorted(claims, key=key):
        if segs:
            segs.append({"kind": "text", "text": " "})
        segs.append({"kind": "claim", "text": c.get("claim_text", ""), "claim_id": c["claim_id"]})
    return {
        "manuscript_id": manuscript_id,
        "mode": "reconstructed",
        "resolved_path": None,
        "segments": segs,
        "matched": [c["claim_id"] for c in claims],
        "unmatched": [],
    }


# ---- document edits (revise / strike), gated by the server ------------------
def compute_edit(source: str, claim: dict, kind: str,
                 replacement: Optional[str] = None) -> dict:
    """Return ``{ok, new_text, diff, reason}`` for a revise/strike of ``claim``.

    ``revise`` replaces the claim's text with ``replacement`` (the accepted
    revision); ``strike`` wraps it in Markdown strikethrough (``~~…~~``) so the
    content is preserved and the edit is trivially reversible. The match uses the
    same whitespace-tolerant locator as the document view; if the claim text is not
    found verbatim, the edit is refused rather than guessed."""
    norm_src, src_map = _normalize_with_map(source)
    _, line = parse_location(claim.get("manuscript_location"))
    hit = _locate(norm_src, src_map, source, claim.get("claim_text", ""), line)
    if not hit:
        return {"ok": False, "reason": "claim text not found in the manuscript source"}
    start, end = hit
    original = source[start:end]
    if kind == "revise":
        if not (replacement and replacement.strip()):
            return {"ok": False, "reason": "no replacement text for the revision"}
        new_fragment = replacement
    elif kind == "strike":
        new_fragment = f"~~{original}~~"
    else:
        return {"ok": False, "reason": f"unknown edit kind: {kind}"}
    new_text = source[:start] + new_fragment + source[end:]
    diff = "".join(difflib.unified_diff(
        source.splitlines(keepends=True), new_text.splitlines(keepends=True),
        fromfile="manuscript", tofile="manuscript (proposed)"))
    return {"ok": True, "new_text": new_text, "diff": diff, "reason": ""}
