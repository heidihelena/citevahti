"""Read-only manuscript-side helpers (ADR-0010 PR 1d — read-only group).

The in-the-writing surface: check a drafted paragraph against vetted claims, one advisory
chat turn with the configured model, convert an uploaded .docx to Markdown for the paste
flow, and the two ready-to-paste prompt choreographies. All read-only — none records a
rating, decides anything, or writes to the ledger or a library. ``chat`` explicitly RECORDS
nothing and is never the blinded rating path; ``import_manuscript_docx`` returns text the
human reviews and saves themselves.

The manuscript "unit test" suite — ``run_manuscript_tests`` / ``_evaluate_claim_tests`` —
stays in the facade for the write-aware PR: its ``online=True`` path orchestrates the
stateful ``scan_retractions`` / ``backfill_candidate_dois`` (ADR-0010 §3, read-only first).

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
