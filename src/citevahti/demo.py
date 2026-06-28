"""A bundled, zero-setup demo ledger — the 3-minute "try it" path.

`citevahti demo` builds this and opens the panel, so a first-time user sees the
real Rate → Reveal → Decide loop and the integrity report WITHOUT Zotero, MCP, an
AI model, or a terminal dance. Everything here is fully synthetic — an invented
manuscript and invented sources — so it is safe to ship and shows real claim
states (accepted / caution / needs-review / pending / rejected), not a mock-up.

It drives the same engine the panel uses; the offline provider stands in for
PubMed so nothing leaves the machine.
"""

from __future__ import annotations

from pathlib import Path

from .claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
    DecisionService,
)
from .intake import IntakeService, StaticLibraryIndex
from .panel import prefs
from .pubmed import ProviderHit, ProviderSearchResult
from .state import CiteVahtiStore

MANUSCRIPT_NAME = "sample-review.md"
MANUSCRIPT = """\
# Telehealth follow-up after day surgery

## Background

Day-surgery volumes have grown steadily over the past decade.
Structured telephone follow-up reduces avoidable readmissions after day surgery.
Patient-reported outcome measures improve when collected within 48 hours of discharge.

## Findings

Nurse-led virtual clinics shorten the time to wound-complication detection.
A single patient leaflet lowers thirty-day anxiety scores after day-case surgery.
Routine in-person review adds no measurable benefit for low-risk procedures.
"""

# (claim text, claim type, final decision or None=leave pending, human value, ai value)
CLAIMS = [
    ("Structured telephone follow-up reduces avoidable readmissions after day surgery.",
     "effectiveness", "accept", "directly_supports", "directly_supports"),
    ("Patient-reported outcome measures improve when collected within 48 hours of discharge.",
     "effectiveness", "accepted_with_caution", "partially_supports", "partially_supports"),
    ("Nurse-led virtual clinics shorten the time to wound-complication detection.",
     "effectiveness", "needs_second_review", "directly_supports", "contradicts"),
    ("A single patient leaflet lowers thirty-day anxiety scores after day-case surgery.",
     "effectiveness", "await_rating", None, "indirectly_supports"),  # evidence staged, awaits YOUR rating
    ("Routine in-person review adds no measurable benefit for low-risk procedures.",
     "background", "reject", "does_not_support", "does_not_support"),
]


class _DemoProvider:
    """A deterministic offline 'PubMed' so the demo needs no network."""

    name = "pubmed"

    def __init__(self, hit):
        self._hit = hit

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=[self._hit], count=1,
                                    email_present=True, rate_tier="3rps")


def _pin(cfg):
    cfg.ai_provenance.model_id = "claude-opus-4-8"
    cfg.ai_provenance.model_snapshot = "2026-05-01"
    cfg.ai_provenance.prompt_template_version = "v1"
    return cfg


def _line_of(text: str, needle: str) -> int:
    for i, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return i
    return 1


def build(root: Path) -> dict:
    """Build the synthetic demo ledger + manuscript at ``root``. Returns a summary."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    msdir = root / "manuscripts"
    msdir.mkdir(exist_ok=True)
    (msdir / MANUSCRIPT_NAME).write_text(MANUSCRIPT, encoding="utf-8")

    store = CiteVahtiStore(root)
    store.init()
    store.save_config(_pin(store.load_config()))
    prefs.set_manuscripts_dir(str(root), str(msdir))

    claims = ClaimService(store)
    candidates = CandidateService(store)
    support = ClaimSupportEngine(store)
    decisions = DecisionService(store)

    decided = pending = 0
    for n, (text, ctype, decision, human, ai) in enumerate(CLAIMS, start=1):
        loc = f"{MANUSCRIPT_NAME}:L{_line_of(MANUSCRIPT, text)}"
        claim = claims.add_claim(text, ctype, manuscript_id=MANUSCRIPT_NAME,
                                 manuscript_location=loc)
        if decision is None:
            pending += 1
            continue  # leave it pending — shows the Rate step in the card

        hit = ProviderHit(pmid=f"3000000{n}", doi=f"10.9999/demo.{n}",
                          title=f"Demo source {n} for review")
        batch = IntakeService(store, provider=_DemoProvider(hit),
                              library_index=StaticLibraryIndex()).literature_search(
            text[:40], question_id=f"q{n}")
        candidates.link_from_intake(claim.claim_id, batch.batch_id)
        cand_id = store.load_candidates(claim.claim_id).candidates[0].candidate_id

        rec = support.support_start(claim.claim_id, cand_id)
        support.submit_ai_rating(rec.rating_id, ai)
        if decision == "await_rating" or human is None:
            # await_rating rows carry human=None by construction (the human hasn't rated);
            # the `or human is None` makes that link explicit (and narrows the type below).
            pending += 1
            continue  # AI is in, human has not rated — the panel shows the blind Rate step
        support.support_commit_human(rec.rating_id, human)
        support.support_compare(rec.rating_id)
        reason = {"accept": "the cited source supports the claim",
                  "accepted_with_caution": "supported, but only partially",
                  "needs_second_review": "the two raters disagree — needs a look",
                  "reject": "the cited source does not support the claim"}[decision]
        decisions.decide(claim.claim_id, cand_id, decision, reason, rating_id=rec.rating_id)
        decided += 1

    return {"root": str(root), "manuscript": str(msdir / MANUSCRIPT_NAME),
            "claims": len(CLAIMS), "decided": decided, "pending": pending}
