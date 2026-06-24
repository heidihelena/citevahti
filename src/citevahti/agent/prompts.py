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
        "7. PRE-SCREEN — record YOUR OWN blind support rating now with "
        "`submit_ai_support_rating`. It is recorded BLIND: the engine SEALS it, never "
        "echoes it back, and keeps it hidden until the human rates. Rating first here is "
        "what builds the LLM rating corpus, and it does NOT anchor the human — your rating "
        "is never shown to them before they rate.\n"
        "8. SUGGEST the staged candidate(s) to the human NEUTRALLY: say what each paper is "
        "and what it reports, never whether you think it supports the claim — your sealed "
        "rating must not leak into your wording. Then direct the human to rate this claim "
        "against its candidate IN THE LOCALHOST SIDE PANEL (call `open_review_panel` if it "
        "may not be open, and give the URL). Do NOT state, hint at, or imply your support "
        "rating; if asked for it before they rate, decline and explain that withholding it "
        "keeps their rating unanchored.\n"
        "9. Reveal agreement or disagreement only AFTER the human has rated: call "
        "`get_provenance`, which keeps your value sealed until then. Report what it returns; "
        "never infer the hidden value.\n"
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
        "and provenance.\n"
        "16. Lead the human to what matters: call `triage` and present the few claims "
        "worth their attention right now, worst-first, each with the reason and the next "
        "action — so they fix the handful that matter rather than re-reading every claim. "
        "Offer to walk those through one at a time.\n\n"
        f"Use these stable finding labels: {labels}.\n\n"
        "Invariants you must never violate: your AI rating is recorded BLIND and stays "
        "SEALED until the human rates — you present candidates neutrally and never state, "
        "hint at, or imply it, so the human is never anchored; the human owns the final "
        "decision; you preview every write before committing and never commit without "
        "explicit confirmation."
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
        "nearby candidate evidence, and the human rates every claim unanchored in the "
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
        "5. HAND OFF to `run_claim_tests`: from here the normal blinded review applies — your "
        "own blind support rating is recorded and SEALED (never shown until the human rates), "
        "the human rates each claim unanchored IN THE SIDE PANEL (call `open_review_panel` if "
        "it may not be open), and every Zotero write is previewed, confirmed, and undoable. Do "
        "NOT state, hint at, or imply a support rating during screening.\n\n"
        "Invariant: screening only proposes leads and stages candidates. It records no rating "
        "and makes no decision; the human rates unanchored, exactly as in run_claim_tests.\n\n"
        "For a systematic review: because an LLM was in the discovery loop here, this step "
        "must be disclosed. Offer `methods` — it returns a paste-ready PRISMA 'how the "
        "literature was found' paragraph stating the model proposed leads only and humans "
        "made every screening and inclusion decision."
    )
    if topic.strip():
        body += "\n\n--- Topic to screen ---\n" + topic.strip()
    return body


CHECK_PARAGRAPH_PROMPT_NAME = "check_paragraph"
CHECK_PARAGRAPH_PROMPT_DESCRIPTION = (
    "Everyday in-writing check: paste a paragraph you're drafting and see, per claim-like "
    "sentence, which claims are already vetted, which need attention, and which are new — "
    "then hand off to run_claim_tests for anything that needs work. Read-only: it records "
    "no rating, decision, or write, and judges no claim's truth."
)


def check_paragraph_prompt(paragraph: str = "") -> str:
    """The everyday in-writing companion loop (read-only). Surfaces where a pasted
    paragraph's claims stand against the ledger, then routes real work into the blinded
    human-first claim-test flow. Adds no capability and rates/decides nothing."""
    body = (
        "You are running CiteVahti's EVERYDAY CHECK from this chat — the in-writing "
        "companion, not the full review. The researcher pastes a paragraph they are "
        "drafting; you tell them where each claim-like sentence stands against the claims "
        "ALREADY in their ledger, then hand off anything that needs work. This step is "
        "READ-ONLY: it records no rating, no decision, no write, and it judges no claim's "
        "truth and no manuscript's quality.\n\n"
        "1. Take the pasted paragraph (ask for it if none is given). Keep their wording.\n"
        "2. Call `check_paragraph` with the text. It matches each sentence to claims already "
        "in the ledger — exact normalized hash, then substring / token overlap — with NO AI "
        "and NO network, returning each as: `reviewed` (already vetted), `attention` (a "
        "tracked claim that needs the human, with a reason + next action), or `new` (not "
        "tracked yet).\n"
        "3. Report it plainly, grouped — vetted / needs attention / new. State honestly that "
        "`reviewed` means the citation SUPPORT was reviewed in the ledger, NOT that the claim "
        "is true, the source is sound, or the paragraph is publication-ready.\n"
        "4. Do NOT rate, decide, or assert support here. `check_paragraph` is a lookup, not a "
        "verdict; never infer support for the `new` sentences.\n"
        "5. Offer the next step: for `attention` items and for `new` sentences worth citing, "
        "hand off to the `run_claim_tests` choreography — the blinded, human-first flow where "
        "the human rates each claim FIRST, you rate second and blind, and every decision and "
        "Zotero write stays previewed, confirmed, and undoable. Do not shortcut that flow "
        "from here.\n\n"
        "Invariant: this is a read-only convenience view over the existing ledger. It never "
        "records a rating, a decision, or a write; it never reveals an AI rating; and it "
        "never claims a citation is correct or a manuscript is sound."
    )
    if paragraph.strip():
        body += "\n\n--- Paragraph to check ---\n" + paragraph.strip()
    return body


METHODS_PROMPT_NAME = "methods_statement"
METHODS_PROMPT_DESCRIPTION = (
    "Produce the paste-ready methods text for a manuscript or systematic review from this "
    "ledger: the blinded human→AI→adjudication workflow paragraph, the PRISMA 'how the "
    "literature was found' AI-disclosure, and the flow-of-evidence counts. Read-only; it "
    "reports what was done and discloses any AI use — it does not judge the manuscript."
)


def methods_prompt() -> str:
    """Guide the assistant to surface the auto-filled methods statement (read-only). It
    documents the workflow and discloses AI use for a methods section / PRISMA report; it
    records nothing and judges nothing."""
    return (
        "You are producing CiteVahti's METHODS TEXT from this chat — the paste-ready "
        "paragraph a researcher puts in their manuscript's methods section (or a systematic "
        "review's PRISMA reporting). This is READ-ONLY: it reports what was already done in "
        "the ledger and discloses any AI use. It records nothing, and it does NOT assert "
        "that the manuscript is true, correct, complete, of good quality, or ready to "
        "publish.\n\n"
        "1. Call `methods` (read-only; no AI, no network). It returns Markdown with three "
        "parts, auto-filled from this ledger's real numbers:\n"
        "   - the **methods paragraph** — the blinded dual-rating workflow (human rates "
        "first; the AI second opinion is withheld until then; every discordance is resolved "
        "by human adjudication; AI values are advisory and never set the final value), with "
        "the model provenance, agreement, and Cohen's κ;\n"
        "   - **'How the literature was found'** — the PRISMA *identification* disclosure of "
        "whether a large language model was in the discovery loop (it proposed leads only "
        "and made no eligibility or inclusion decision), naming the model + snapshot;\n"
        "   - **'Flow of evidence'** — the PRISMA-style identification→screening→included "
        "counts table.\n"
        "2. Present it verbatim for pasting, then point out anything marked `(unset — …)` or "
        "`n/a` and what the researcher must fill or pin before submission (e.g. the AI "
        "provenance model) — never invent those values.\n"
        "3. Be honest about scope: this text DOCUMENTS the human→AI→adjudication process and "
        "discloses AI use. It is NOT a claim that the citations are correct, that the "
        "evidence is sufficient, or that the paper is publication-ready. CiteVahti checks "
        "citation support, not the truth of the underlying claims.\n"
        "4. Do not rate, decide, write to Zotero, or reveal any AI rating here. If claims "
        "still need review, hand off to `run_claim_tests` (the blinded, human-first flow).\n\n"
        "Invariant: read-only reporting + AI-use disclosure. It records no rating, decision, "
        "or write, reveals no blinded AI value, and makes no truth/quality/publication "
        "claim."
    )
