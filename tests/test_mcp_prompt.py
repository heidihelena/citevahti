"""The canonical claim-test MCP prompt (ADR-0007; "manuscript as code" frame).

The prompt is the user-controlled MCP primitive. Its text is a safety contract:
the human rates first, the AI rating is submitted after, and a write is previewed
before it is committed. These tests assert the prompt exists under its canonical
name, that ordering holds, that it carries the claim-test vocabulary, and that it
is actually registered on the server (with the deprecated 0.9.0 alias kept).
"""

import os
import sys

import pytest

from citevahti.agent import prompts
from citevahti.findings import FINDING_LABELS
from citevahti.state import CiteVahtiStore


def test_canonical_name_and_deprecated_alias():
    assert prompts.CLAIM_TEST_PROMPT_NAME == "run_claim_tests"
    assert prompts.REVIEW_PROMPT_NAME == "review_manuscript"   # deprecated alias (0.9.0)
    assert prompts.CLAIM_TEST_PROMPT_DESCRIPTION
    # the alias serves the same text
    assert prompts.review_manuscript_prompt() == prompts.run_claim_tests_prompt()


def test_screen_topic_prompt_screens_into_claim_tests_without_deciding():
    # Layer-0 screening (ADR-0008) proposes leads and hands off to run_claim_tests; it
    # must NOT rate or decide, and the human still rates first (the same safety contract)
    assert prompts.SCREEN_TOPIC_PROMPT_NAME == "screen_topic"
    assert prompts.SCREEN_TOPIC_PROMPT_DESCRIPTION
    t = prompts.screen_topic_prompt()
    low = t.lower()
    assert "leads, not verdicts" in low
    assert "run_claim_tests" in t                       # hands off to the blinded review
    assert "propose_claim" in t and "pubmed_search" in t  # proposes claims + nearby evidence
    assert "records no rating and makes no decision" in low
    # screening never submits an AI rating or writes — that is run_claim_tests' job
    assert "submit_ai_support_rating" not in t and "commit_write" not in t


def test_check_paragraph_prompt_is_read_only_and_hands_off_to_the_blinded_flow():
    # The everyday in-writing companion: a read-only lookup against the ledger that routes
    # real work into run_claim_tests. It must rate/decide/write nothing, reveal no AI value,
    # and make no truth/quality claim.
    assert prompts.CHECK_PARAGRAPH_PROMPT_NAME == "check_paragraph"
    assert prompts.CHECK_PARAGRAPH_PROMPT_DESCRIPTION
    t = prompts.check_paragraph_prompt()
    low = t.lower()
    assert "check_paragraph" in t                         # calls the read-only tool
    assert "run_claim_tests" in t                         # hands off real work to the blinded flow
    assert "read-only" in low and "no ai" in low
    assert "not that the claim" in low                    # honest: reviewed != true
    # it never rates, decides, writes, or reveals an AI value itself
    for forbidden in ("submit_ai_support_rating", "preview_write", "commit_write"):
        assert forbidden not in t
    # paragraph is appended when supplied
    t2 = prompts.check_paragraph_prompt("Nurse-led clinics shorten time to detection.")
    assert "Nurse-led clinics shorten time to detection." in t2 and "Paragraph to check" in t2


def test_methods_prompt_is_read_only_disclosure_not_a_quality_claim():
    # The methods skill produces paste-ready methods text + AI-use disclosure from the
    # ledger. Read-only: it reports/discloses, never rates/decides/writes, and must NOT
    # claim the manuscript is true, correct, or publication-ready.
    assert prompts.METHODS_PROMPT_NAME == "methods_statement"
    assert prompts.METHODS_PROMPT_DESCRIPTION
    t = prompts.methods_prompt()
    low = t.lower()
    assert "`methods`" in t                               # calls the read-only methods tool
    assert "read-only" in low
    assert "prisma" in low and "how the literature was found" in low  # the AI-discovery disclosure
    assert "not" in low and ("publication-ready" in low or "publish" in low)  # honest scope
    # never rates/decides/writes or reveals an AI value from this skill
    for forbidden in ("submit_ai_support_rating", "preview_write", "commit_write"):
        assert forbidden not in t


def test_prompt_seals_the_ai_rating_until_human_rates_then_previews_before_commit():
    # Sealed-envelope blinding: the agent may record its OWN support rating first (the LLM
    # corpus), but it is recorded blind and stays sealed/hidden until the human rates, and
    # candidates are presented neutrally so the human is never anchored. Writes are still
    # previewed before commit. (This replaced a chronological human-before-AI assertion:
    # blinding = the human is not anchored, NOT that the AI must rate last.)
    t = prompts.run_claim_tests_prompt()
    low = t.lower()
    assert "seals it" in low or "sealed" in low          # the AI rating is sealed
    assert "hidden until the human rates" in low          # withheld until the human rates
    assert "neutrally" in low                             # candidates presented without anchoring
    assert "do not state, hint at, or imply your support rating" in low
    i_preview = t.index("preview_write")
    i_commit = t.index("commit_write")
    assert i_preview < i_commit, "the write is previewed before it is committed"


def test_prompt_instructs_withholding_the_ai_opinion_until_human_rates():
    t = prompts.run_claim_tests_prompt().lower()
    assert "do not state" in t and "side panel" in t
    assert "decline" in t


def test_prompt_carries_the_claim_test_frame():
    t = prompts.run_claim_tests_prompt()
    # the manuscript-as-code framing and the reference-integrity distinctions
    assert "THE MANUSCRIPT IS THE CODE" in t and "test case" in t
    for phrase in ("reference_broken", "reference_hallucinated", "reference_real_but_wrong",
                   "is NOT the same as it supporting", "CLAIM TEST REPORT"):
        assert phrase in t
    # the four states appear paired with the codes
    for code in ("[oo]", "[o]", "[r]", "[d]"):
        assert code in t


def test_prompt_lists_the_stable_finding_labels():
    t = prompts.run_claim_tests_prompt()
    for label in FINDING_LABELS:
        assert f"`{label}`" in t


def test_prompt_mentions_the_existing_tools_only():
    t = prompts.run_claim_tests_prompt()
    for tool in ("propose_claim", "verify_claims", "pubmed_search", "link_candidates",
                 "submit_ai_support_rating", "get_provenance", "preview_write",
                 "commit_write", "undo"):
        assert tool in t


def test_manuscript_text_is_appended_when_supplied():
    t = prompts.run_claim_tests_prompt("Vitamin D prevents fractures.")
    assert "Vitamin D prevents fractures." in t
    assert "Manuscript to test" in t


def test_both_prompts_registered_over_stdio(tmp_path):
    pytest.importorskip("mcp")
    import anyio
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    CiteVahtiStore(tmp_path).init()

    async def run():
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "citevahti.agent.mcp_server", "--root", str(tmp_path)],
            cwd=os.getcwd(), env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_prompts()
                names = {p.name for p in listed.prompts}
                assert prompts.CLAIM_TEST_PROMPT_NAME in names
                assert prompts.REVIEW_PROMPT_NAME in names      # deprecated alias still works
                assert prompts.SCREEN_TOPIC_PROMPT_NAME in names  # Layer-0 screening (ADR-0008)
                assert prompts.CHECK_PARAGRAPH_PROMPT_NAME in names  # everyday in-writing check
                assert prompts.METHODS_PROMPT_NAME in names          # read-only methods + AI disclosure
                got = await session.get_prompt(prompts.CLAIM_TEST_PROMPT_NAME, {})
                text = " ".join(
                    m.content.text for m in got.messages if hasattr(m.content, "text"))
                assert "side panel" in text and "submit_ai_support_rating" in text

    anyio.run(run)


def test_desktop_manifests_list_the_same_prompts_as_the_server():
    # the .mcpb manifests must advertise every CANONICAL prompt the server registers, or a
    # Claude Desktop user can't discover it (check_paragraph + methods_statement were the gap
    # — and this test's old hardcoded set didn't catch the drift). The deprecated 0.9.0 alias
    # `review_manuscript` is intentionally NOT advertised.
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "desktop-extension"
    expected = {prompts.CLAIM_TEST_PROMPT_NAME, prompts.SCREEN_TOPIC_PROMPT_NAME,
                prompts.CHECK_PARAGRAPH_PROMPT_NAME, prompts.METHODS_PROMPT_NAME}
    for name in ("manifest.json", "manifest.binary.json"):
        m = json.loads((root / name).read_text())
        listed = {p["name"] for p in m.get("prompts", [])}
        assert expected <= listed, f"{name} is missing prompts: {expected - listed}"
        assert prompts.REVIEW_PROMPT_NAME not in listed, "the deprecated alias should not be advertised"
