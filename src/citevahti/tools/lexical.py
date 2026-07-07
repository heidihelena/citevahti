"""Deterministic extraction + lexical claim-check (ADR-0010 PR 1h — read-only group).

Deterministic text tools: assistive field extraction from a Zotero item, lexical
claim-support between a claim and its cited sources, and a standalone claim<->passage
overlap check. All read-only — they read item text (via the Zotero API text source) or
operate on a passage and return data. They NEVER assert truth, never invent citekeys,
never write to the evidence map or the ledger; ``claim_lexical_check`` is deliberately
shown only AFTER the human's blind rating so it cannot bias it.

Re-exported unchanged from ``citevahti.tools`` (frozen by tests/test_tools_public_api_stable.py).
"""

from __future__ import annotations

from typing import Optional

from ..probe.client import HttpxClient
from ..schemas.common import ItemRef, LibrarySelector
from ..schemas.config import Endpoints


def _text_source(endpoints: Optional[Endpoints]):
    from ..bbt.client import BbtClient
    from ..retrieval import ZoteroApiTextSource
    from ..zotero import ZoteroService

    http = HttpxClient()
    return ZoteroApiTextSource(ZoteroService(http, endpoints), BbtClient(http, endpoints))


def extract(subject: ItemRef, fields: Optional[list[str]] = None, mode: str = "assistive",
            require_passage: bool = False, library: LibrarySelector = "personal", *,
            source=None, endpoints: Optional[Endpoints] = None):
    """Assistive, deterministic field extraction. Returns an ExtractResult.
    Never guesses; never writes to the evidence map."""
    from ..extract import ExtractService

    src = source or _text_source(endpoints)
    return ExtractService(src).extract(subject, fields, mode=mode,
                                       require_passage=require_passage, library=library)


def claim_check(claim_text: str, citekeys: list[str], context: Optional[str] = None,
                require_page: bool = False, library: LibrarySelector = "personal", *,
                source=None, endpoints: Optional[Endpoints] = None):
    """Deterministic lexical claim support. Returns a ClaimCheckResult.
    Never asserts truth; never invents keys; exact citekey resolution only."""
    from ..claimcheck import ClaimCheckService

    src = source or _text_source(endpoints)
    return ClaimCheckService(src).check(claim_text, citekeys, context=context,
                                        require_page=require_page, library=library)


def claim_lexical_check(claim_text: str, text: str) -> dict:
    """Deterministic lexical overlap between a claim and a passage (the candidate's
    abstract/full text). Reuses the same content-token logic as ``claim_check``.

    NEVER asserts truth — only whether the claim's key terms appear in the text. The
    panel shows it AFTER the human's blind rating so it can't bias it."""
    from ..retrieval.text import (content_tokens, coverage_score,
                                 polarity_conflict, polarity_cue, segment_sentences)
    claim_terms = content_tokens(claim_text or "")
    if not claim_terms or not (text or "").strip():
        return {"available": False}
    text_terms = content_tokens(text)
    cov = coverage_score(claim_text, text)
    # Direction guard (same rule as claim_check): a sentence can overlap the claim's
    # terms yet assert the OPPOSITE polarity ("did not reduce" vs "reduced"). Surface
    # it as an inspectable "may contradict" cue — never a verdict, never hidden.
    opposing = next((s for _a, _b, s in segment_sentences(text)
                     if polarity_conflict(claim_text, s)), None)
    cue = polarity_cue(claim_text, opposing) if opposing else None
    return {
        "available": True,
        "coverage": round(cov, 2),
        "status": "terms_present" if cov >= 0.5 else "terms_missing",
        "present": sorted(t for t in claim_terms if t in text_terms),
        "missing": sorted(t for t in claim_terms if t not in text_terms),
        "contradiction": opposing is not None,
        "polarity_cue": cue,
        "opposing_quote": opposing,
    }
