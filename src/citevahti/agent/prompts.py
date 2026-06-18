"""User-controlled MCP prompt(s) for CiteVahti (ADR-0007).

The frame: **the manuscript is the code, each claim is a test, CiteVahti runs the
evidence tests before you cite.** The canonical prompt is ``run_claim_tests``; it
choreographs a blinded, claim-by-claim review so the conversation cannot silently
break ADR-0001's method — the **human rates first** (in the localhost side panel),
the **AI second opinion stays hidden until the human rating exists**, and **Zotero
writes are previewed, confirmed, and undoable.**

``review_manuscript`` is kept as a **deprecated alias** (it shipped in 0.9.0) that
serves the same text.

The text lives here (not inline in the server) so it can be asserted offline,
without importing the optional ``mcp`` package.
"""

from __future__ import annotations

from ..findings import FINDING_LABELS

CLAIM_TEST_PROMPT_NAME = "run_claim_tests"
CLAIM_TEST_PROMPT_DESCRIPTION = (
    "Run unit tests on a manuscript: treat each scientific claim as a test case, "
    "check it against cited or candidate evidence (PubMed + Zotero), keep the AI "
    "rating blinded until the human rates, and prepare guarded, undoable citation "
    "updates."
)

# Deprecated alias (shipped in 0.9.0). Same workflow, old name.
REVIEW_PROMPT_NAME = "review_manuscript"
REVIEW_PROMPT_DESCRIPTION = CLAIM_TEST_PROMPT_DESCRIPTION


def run_claim_tests_prompt(manuscript: str = "") -> str:
    """Return the choreography the chat LLM must follow to run claim-tests.

    ``manuscript`` is the pasted/attached paragraph or section (may be empty — the
    user can paste it into the conversation instead).

    The ORDER of the steps is a safety contract asserted by tests: the human rating
    is requested before any AI rating is stated, the AI rating is submitted only
    after the human's is recorded, and a write is previewed before it is committed.
    """
    labels = ", ".join(f"`{x}`" for x in FINDING_LABELS)
    body = (
        "You are running CiteVahti's claim-tests from this chat. THE MANUSCRIPT IS "
        "THE CODE; EACH CLAIM IS A TEST CASE. The human is the decider; you are a "
        "blinded, advisory second rater only. Two surfaces are in play: THIS "
        "conversation (you orchestrate) and a separate localhost side panel (where "
        "the human records their blind rating). Never collapse them.\n\n"
        "Run the test suite one claim at a time, and do not skip or reorder steps:\n\n"
        "1. Take the manuscript paragraph, section, or attached text. If none is "
        "attached yet, ask for it. Walk it paragraph by paragraph.\n"
        "2. Identify exactly ONE candidate scientific claim to test next. Treat it "
        "as a test case.\n"
        "3. Record or verify the claim with the existing tools: `propose_claim` for "
        "a new claim (flagged ai-extracted; the human confirms), or `verify_claims` "
        "for the current 4-state report. You never confirm a claim for the human.\n"
        "4. Resolve the claim's CURRENT citation if it has one: use `pubmed_search` "
        "to confirm the cited paper actually exists and matches. A reference whose "
        "PMID/DOI does not resolve is `reference_broken`; one that appears not to "
        "exist at all is `reference_hallucinated`. **A paper existing is NOT the "
        "same as it supporting the claim** — a real paper that does not support the "
        "claim is `reference_real_but_wrong`.\n"
        "5. Find candidate evidence where needed: `pubmed_search` stages hits (the "
        "exact query is preserved; each hit reports whether it is already in the "
        "Zotero library via its dedupe status), then `link_candidates` attaches the "
        "chosen hits. Staged hits are candidates, not citations (`candidate_found`).\n"
        "6. Weigh MEANING, not topic: check Population / Intervention / Comparator / "
        "Outcome / study-design fit. Topic match is not support. Flag mismatches "
        "(`population_mismatch`, `outcome_mismatch`, …, `overclaim`, "
        "`needs_full_text`) where they apply.\n"
        "7. STOP and direct the human to rate this claim against its candidate IN "
        "THE LOCALHOST SIDE PANEL first. If the panel may not be open yet, call "
        "`open_review_panel` (it is idempotent and opens their browser) and give "
        "the human its URL. Do NOT state, hint at, or imply your own "
        "support rating yet. If asked for your opinion before they have rated, "
        "decline and explain that rating first keeps the review blinded.\n"
        "8. Only AFTER the human's rating is recorded, submit YOUR rating with "
        "`submit_ai_support_rating` (recorded blind, not echoed back).\n"
        "9. Reveal agreement or disagreement only AFTER the engine permits it: call "
        "`get_provenance`, which hides the AI value until the human has rated. "
        "Report what it returns; never infer the hidden value.\n"
        "10. Ask the human to adjudicate ONLY once BOTH ratings exist and they "
        "disagree. The human (or panel) owns the final decision; you never set it.\n"
        "11. Classify the claim's state: `[oo]` accepted · `[o]` needs support · "
        "`[r]` review needed · `[d]` decided · `[u]` untestable (out of indexed scope).\n"
        "12. When the human accepts a candidate, PREVIEW the Zotero write first with "
        "`preview_write` (this is `zotero_action_ready`) and show the proposed "
        "change and the approval token.\n"
        "13. NEVER commit without the human's explicit confirmation. Only after they "
        "confirm, call `commit_write` with the token (`zotero_write_committed`).\n"
        "14. After a commit, tell the human UNDO is available (`undo`, "
        "`zotero_write_undone`). Nothing is ever written to Zotero silently.\n"
        "15. Produce a final CLAIM TEST REPORT: a summary line of the state counts "
        "(`[oo]`/`[o]`/`[r]`/`[d]`), then per claim: id, claim text, current "
        "citation, evidence candidate, finding label, the human rating, the AI "
        "rating ONLY if the human has rated, the final decision, the Zotero action, "
        "and provenance.\n\n"
        f"Use these stable finding labels: {labels}.\n\n"
        "Invariants you must never violate: the human rates before you reveal any AI "
        "rating; you submit the AI rating only after the human's is recorded; you "
        "preview every write before committing; you never commit without explicit "
        "confirmation."
    )
    if manuscript.strip():
        body += "\n\n--- Manuscript to test ---\n" + manuscript.strip()
    return body


# Backwards-compatible alias for the 0.9.0 name.
def review_manuscript_prompt(manuscript: str = "") -> str:
    return run_claim_tests_prompt(manuscript)


# ---- Layer-0 topic screening (ADR-0008) -------------------------------------
SCREEN_TOPIC_PROMPT_NAME = "screen_topic"
SCREEN_TOPIC_PROMPT_DESCRIPTION = (
    "Layer-0 screening: turn a research topic into candidate claims worth testing plus "
    "nearby candidate evidence — leads, never verdicts. The human still rates each claim "
    "first; screening only proposes and stages, it decides nothing."
)


def screen_topic_prompt(topic: str = "") -> str:
    """Return the Layer-0 screening choreography (ADR-0008).

    Screening produces LEADS, not verdicts: the assistant proposes candidate claims and
    nearby candidate evidence on a topic, then hands off to ``run_claim_tests`` where the
    blinded, human-first review takes over. It records no rating and decides nothing — the
    same safety contract as the claim-tests flow, asserted by tests.
    """
    body = (
        "You are running CiteVahti's LAYER-0 TOPIC SCREENING from this chat. Screening "
        "produces LEADS, NOT VERDICTS: you propose candidate claims worth testing and "
        "nearby candidate evidence, and the human still rates every claim first in the "
        "localhost side panel. You are a blinded, advisory second rater only; you decide "
        "nothing here.\n\n"
        "Screen the topic, then hand off to the claim-tests flow — do not skip or reorder:\n\n"
        "1. Take the research topic below. If none is given, ask for it. Keep it tight — "
        "one topic, the kind a manuscript section or a guideline statement would cover.\n"
        "2. Propose a SHORT list of candidate scientific claims a careful author might make "
        "on this topic — the assertions worth checking. Present them explicitly as leads to "
        "assess, NOT as established facts, and let the human choose which to keep.\n"
        "3. For each kept claim, find candidate (nearby) evidence with `pubmed_search` (the "
        "exact query is preserved; each hit reports its Zotero dedupe status). These are "
        "candidates, never citations yet.\n"
        "4. Register the claims the human keeps with `propose_claim` (flagged ai-extracted; "
        "the human confirms — you never confirm a claim for them), then attach the chosen "
        "hits with `link_candidates`.\n"
        "5. HAND OFF to `run_claim_tests`: from here the normal blinded review applies — the "
        "human rates each claim IN THE SIDE PANEL first (call `open_review_panel` if it may "
        "not be open), you submit your rating only AFTER theirs is recorded, and every Zotero "
        "write is previewed, confirmed, and undoable. Do NOT state, hint at, or imply a "
        "support rating during screening.\n\n"
        "Invariant: screening only proposes leads and stages candidates. It records no rating "
        "and makes no decision; the human rates first, exactly as in run_claim_tests."
    )
    if topic.strip():
        body += "\n\n--- Topic to screen ---\n" + topic.strip()
    return body
