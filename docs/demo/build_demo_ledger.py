"""Build a small, fully synthetic CiteVahti ledger for screenshots and demos.

The content here is invented — no real manuscript, no real citations — so the
resulting screenshots are safe to commit to a public repo and can be regenerated
at any time. It drives the same engine the panel uses, so the demo shows real
claim states (accepted / caution / needs-review / rejected / pending) and real
claim-span highlighting, not a mock-up.

Usage:
    PYTHONPATH=src python3 docs/demo/build_demo_ledger.py [OUTPUT_ROOT]

Then point the panel at it:
    PYTHONPATH=src python3 -m citevahti.panel.server --root OUTPUT_ROOT --port 8775
"""

from __future__ import annotations

import sys
from pathlib import Path

from citevahti.claims import (
    CandidateService,
    ClaimService,
    ClaimSupportEngine,
    DecisionService,
)
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.panel import prefs
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore

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


def build(root: Path) -> None:
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

    for n, (text, ctype, decision, human, ai) in enumerate(CLAIMS, start=1):
        loc = f"{MANUSCRIPT_NAME}:L{_line_of(MANUSCRIPT, text)}"
        claim = claims.add_claim(text, ctype, manuscript_id=MANUSCRIPT_NAME,
                                 manuscript_location=loc)
        if decision is None:
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
        if decision == "await_rating":
            continue  # AI is in, human has not rated — the panel shows the blind Rate step
        support.support_commit_human(rec.rating_id, human)
        support.support_compare(rec.rating_id)
        reason = {"accept": "the cited source supports the claim",
                  "accepted_with_caution": "supported, but only partially",
                  "needs_second_review": "the two raters disagree — needs a look",
                  "reject": "the cited source does not support the claim"}[decision]
        decisions.decide(claim.claim_id, cand_id, decision, reason, rating_id=rec.rating_id)

    print(f"Demo ledger built at {root}")
    print(f"  manuscript: {msdir / MANUSCRIPT_NAME}")
    print(f"  claims:     {len(CLAIMS)} ({sum(c[2] is not None for c in CLAIMS)} decided, "
          f"{sum(c[2] is None for c in CLAIMS)} pending)")


if __name__ == "__main__":
    out = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path(".demo-ledger")
    build(out)
