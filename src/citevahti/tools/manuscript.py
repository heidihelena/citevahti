"""Read-only manuscript-side helpers (ADR-0010 PR 1d — read-only group).

The in-the-writing surface: check a drafted paragraph against vetted claims, one advisory
chat turn with the configured model, convert an uploaded .docx to Markdown for the paste
flow, and the two ready-to-paste prompt choreographies. All read-only — none records a
rating, decides anything, or writes to the ledger or a library. ``chat`` explicitly RECORDS
nothing and is never the blinded rating path; ``import_manuscript_docx`` returns text the
human reviews and saves themselves.

The manuscript "unit test" suite — ``run_manuscript_tests`` / ``_evaluate_claim_tests`` —
also lives here (PR 1m): offline it is deterministic and read-only; its ``online=True``
path drives the stateful ``scan_retractions`` / ``backfill_candidate_dois`` from
``.intake`` (forward deps, no cycle).

Re-exported unchanged from ``citevahti.tools`` (frozen by tests/test_tools_public_api_stable.py).
"""

from __future__ import annotations

from typing import Optional

from ._common import _open_store


def check_paragraph(text: str, *, root: Optional[str] = None):
    """Check-a-paragraph: for a snippet you just wrote, which sentences map to claims
    you've already vetted, which need attention, and which are new/untracked. Read-only,
    no AI — the everyday in-the-writing loop. Returns a per-sentence status + tally."""
    from ..report.paragraph import check_paragraph as _check
    return _check(_open_store(root), text or "")


_CHAT_FRAMING = (
    "You are CiteVahti's assistant, helping a researcher check that their manuscript's "
    "claims are supported by the sources cited for them. Help them find candidate claims, "
    "screen a topic, and refine wording. The researcher records every support rating and "
    "decision themselves in the panel — do NOT declare whether a source supports a claim "
    "before they have rated it; present evidence neutrally so you don't anchor them. Never "
    "assert that a paper proves a claim, or that a manuscript is correct or "
    "publication-ready: CiteVahti checks citation support, not truth."
)


def chat(message: str, *, root: Optional[str] = None, poster=None) -> dict:
    """One advisory chat turn with the CONFIGURED model — a local Ollama / LM Studio model
    (nothing leaves your machine) or your own API key — reusing the same connection plumbing
    as the AI rater. It RECORDS nothing, calls no tools, and writes nothing: a conversational
    helper, never the blinded rating path. Returns ``ai_off`` when no model is configured.
    ``poster`` is injectable for tests."""
    from ..rating.ai import chat_completion, resolve_ai_connection

    config = _open_store(root).load_config()
    conn = resolve_ai_connection(config)
    if conn is None:
        return {"status": "ai_off", "reply": None,
                "message": "No model is configured. Set one in AI settings — a local Ollama "
                           "model keeps everything on your machine."}
    prompt = f"{_CHAT_FRAMING}\n\nResearcher: {message or ''}\n\nAssistant:"
    reply = chat_completion(shape=conn["shape"], endpoint=conn["endpoint"],
                            model=config.ai_provenance.model_id, prompt=prompt,
                            api_key=conn["api_key"], poster=poster,
                            timeout=config.ai_connection.request_timeout_s)
    return {"status": "ok", "model": config.ai_provenance.model_id, "reply": reply}


def import_manuscript_docx(docx_base64: str, *, root: Optional[str] = None) -> dict:
    """Convert an uploaded .docx manuscript to Markdown for the paste → review flow
    (needs the 'docx' extra). Returns the text only — the human reviews and saves it."""
    import base64
    import binascii

    from ..report import docx_to_markdown
    try:
        data = base64.b64decode(docx_base64 or "", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("import payload is not valid base64") from exc
    if not data:
        raise ValueError("no .docx data provided")
    md = docx_to_markdown(data)      # RuntimeError with install hint if python-docx is absent
    return {"markdown": md, "lines": md.count("\n")}


def claim_tests_prompt(manuscript: str = "") -> dict:
    """The ready-to-paste ``run_claim_tests`` choreography, optionally pre-filled with
    a manuscript. This is the bridge that closes the Word/Markdown → claims loop: after
    importing a .docx, the panel hands the reviewer the exact prompt to paste into their
    chat client, with the imported text already embedded. Single source of truth — the
    choreography text lives in ``agent.prompts``, never duplicated in the UI."""
    from ..agent.prompts import CLAIM_TEST_PROMPT_NAME, run_claim_tests_prompt
    return {"name": CLAIM_TEST_PROMPT_NAME, "prompt": run_claim_tests_prompt(manuscript or "")}


def topic_screen_prompt(topic: str = "") -> dict:
    """The ready-to-paste ``screen_topic`` choreography (ADR-0008, Layer 0), optionally
    pre-filled with a topic. The panel's "Screen a topic" button hands the reviewer this
    prompt to paste into their chat client; the assistant then proposes candidate claims +
    nearby evidence (leads, not verdicts) and hands off to ``run_claim_tests``. The panel
    never calls an AI itself (ADR-0007); the choreography text lives in ``agent.prompts``."""
    from ..agent.prompts import SCREEN_TOPIC_PROMPT_NAME, screen_topic_prompt
    return {"name": SCREEN_TOPIC_PROMPT_NAME, "prompt": screen_topic_prompt(topic or "")}


# ---- the manuscript "unit test" suite (ADR-0010 PR 1m) ----------------------
# CiteVahti's core metaphor: each claim is a test case. A claim PASSES when it is
# backed by accepted, supporting evidence whose citation is identifiable (and,
# online, real + not retracted); FAILS when the citation does not support it, is
# retracted, or can't be identified; SKIPS when not yet reviewed or out of scope.
# Forward deps only: the online path drives the stateful scans in .intake, and the
# rows come from .reports' claim_report.
_ACCEPTED_DECISIONS = ("accept", "accepted_with_caution")


def _evaluate_claim_tests(row, online: bool) -> dict:
    checks: list[dict] = []

    def add(name, status, detail=""):
        checks.append({"name": name, "status": status, "detail": detail})

    def result(status):
        return {"claim_id": row.claim_id, "claim_text": row.claim_text,
                "state": row.state, "code": row.code.strip(),
                "manuscript_location": row.manuscript_location,
                "status": status, "checks": checks}

    # FAIL (loudly): a decision was edited outside CiteVahti — the ledger state can't be
    # trusted. Never a silent skip; the citation integrity of this claim is unknown.
    if getattr(row, "inconsistent", False):
        add("ledger_integrity", "fail",
            "ledger state is inconsistent with the audit trail (edited outside CiteVahti): "
            + (row.inconsistency or "decision disagrees with its rating"))
        return result("fail")
    # SKIP: explicitly out of indexed scope (book/grey lit) — not a failure.
    if row.state == "untestable":
        add("in_scope", "skip", row.untestable_reason or "cited source is out of indexed-literature scope")
        return result("skip")
    # SKIP: not yet reviewed (no evidence linked, or linked but not rated/decided).
    if row.state == "needs_support":
        detail = "no reference linked yet" if row.candidate_count == 0 else "evidence linked but not yet rated/decided"
        add("reviewed", "skip", detail)
        return result("skip")

    # decided states: accepted / review_needed / decision_recorded
    add("has_reference", "pass" if row.candidate_count >= 1 else "fail",
        "" if row.candidate_count >= 1 else "no reference linked")
    add("reviewed", "pass")

    if row.state == "review_needed":
        add("supported", "fail", "rater discordance or a needs-second-review verdict is unresolved")
        return result("fail")
    if row.state == "decision_recorded":
        add("supported", "fail", "no candidate was accepted as supporting this claim")
        return result("fail")

    # state == "accepted": the claim is supported — now test the citation itself.
    add("supported", "pass")
    accepted = [e for e in row.evidence if e.final_decision in _ACCEPTED_DECISIONS]
    operative = accepted or row.evidence
    identified = [e for e in operative if (e.doi or e.pmid)]
    add("citation_identified", "pass" if identified else "fail",
        "" if identified else "the supporting reference has no DOI or PMID")
    if online:
        retracted = [e for e in operative if e.retracted]
        add("not_retracted", "fail" if retracted else "pass",
            f"{len(retracted)} supporting reference(s) flagged retracted" if retracted else "")
        add("citation_real", "pass" if identified else "fail",
            "" if identified else "could not resolve a real DOI/PMID for the reference")

    return result("fail" if any(c["status"] == "fail" for c in checks) else "pass")


def run_manuscript_tests(*, root: Optional[str] = None, online: bool = False,
                         claim_ids: Optional[list] = None, http=None) -> dict:
    """Run the manuscript 'unit test' suite over the ledger's claims.

    Offline checks (instant, deterministic): the claim has a linked reference, was
    reviewed, the verdict supports it, and the supporting citation carries a DOI/PMID.
    With ``online=True`` it first refreshes retraction flags and backfills/validates
    identifiers (network), then also tests that the citation is real and not retracted.

    Returns a JSON-serialisable suite result so the CLI and the panel share one engine.
    """
    from .intake import backfill_candidate_dois, scan_retractions
    from .reports import claim_report

    online_actions: dict = {}
    if online:
        try:
            online_actions["retractions"] = scan_retractions(root=root, http=http)
        except Exception as e:  # noqa: BLE001 — a flaky network check must not crash the suite
            online_actions["retractions_error"] = str(e)
        try:
            online_actions["dois"] = backfill_candidate_dois(root=root, http=http)
        except Exception as e:  # noqa: BLE001
            online_actions["dois_error"] = str(e)

    rep = claim_report(claim_ids=claim_ids, root=root)
    claims = [_evaluate_claim_tests(r, online) for r in rep.rows]
    counts = {s: sum(1 for c in claims if c["status"] == s) for s in ("pass", "fail", "skip")}
    # Surface online-check failures explicitly: a swallowed retraction-scan / DOI
    # backfill error means the citation_real / not_retracted checks ran against stale
    # data, so a "pass" there is NOT trustworthy. Callers MUST show online_errors.
    online_errors = [v for k, v in online_actions.items() if k.endswith("_error")]
    return {"total": len(claims), "passed": counts["pass"], "failed": counts["fail"],
            "skipped": counts["skip"], "online": online, "claims": claims,
            "online_actions": online_actions or None, "online_errors": online_errors,
            "generated_at": rep.generated_at}
