"""A truncated AI reply is a MISCONFIGURATION, not a judgement.

Regression guard for the 2026-07-26 finding: a reasoning ("thinking") model such as
qwen3:14b spends its reply budget on chain of thought, so on the old 300-token
ceiling it was cut off before answering. The rater then recorded an abstention —
indistinguishable from a genuine "cannot judge", so an operator saw abstentions where
the real event was a setup problem. Measured cost: 12 of 44 items (27%) on the
claim-support path.

These tests lock the distinction in both directions: a cut-off reply is recorded as a
typed ``failure`` (never an abstention), and a real abstention carries no failure.
Offline throughout (fake poster); no model is contacted.
"""

from __future__ import annotations

import json

from citevahti.claims import HttpClaimSupportRater
from citevahti.rating.ai import (
    API_MAX_REPLY_TOKENS,
    LOCAL_MAX_REPLY_TOKENS,
    TRUNCATED_REPLY_REASON,
    HttpAiRater,
    chat_reply,
    is_truncation_reason,
    resolve_ai_connection,
)
from citevahti.schemas.config import Config


class _Claim:
    def __init__(self, text):
        self.claim_text = text


class _Cand:
    def __init__(self, title, abstract):
        self.title = title
        self.abstract = abstract


CLAIM = _Claim("Drug X reduced mortality")
CAND = _Cand("A trial", "Drug X did not reduce mortality in the treatment arm.")


class FakePoster:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(self, url, headers, payload, timeout):
        self.calls.append({"headers": headers, "payload": payload})
        return self.response


# A thinking model's reply cut off mid-reasoning: prose, no JSON, finish_reason=length.
THINKING_TRUNCATED = {
    "choices": [{
        "message": {"content": "Okay, let me work through this. The claim says Drug X "
                               "reduced mortality. I need to check the population, the "
                               "intervention, and the outcome against the abstract. The "
                               "abstract reports a trial of Drug X, so the intervention "
                               "matches. Now for the outcome, the abstract states that"},
        "finish_reason": "length",
    }],
}
# A genuine abstention: the model answered, and its answer was "I cannot judge".
GENUINE_ABSTENTION = {
    "choices": [{
        "message": {"content": json.dumps({"value": None, "abstained": True,
                                           "confidence": None,
                                           "rationale": "abstract lacks the outcome"})},
        "finish_reason": "stop",
    }],
}


def _support_rater(poster, **kw):
    return HttpClaimSupportRater(shape="openai", model="qwen3:14b", poster=poster,
                                 endpoint="http://localhost:11434/v1/chat/completions", **kw)


# --- the distinction, on the claim-support path (the one that was measured) ----

def test_truncated_thinking_reply_is_reported_as_configuration_not_judgement():
    out = _support_rater(FakePoster(THINKING_TRUNCATED)).rate(
        claim=CLAIM, candidate=CAND, task_type="claim_support")
    assert out.value is None                            # still never fabricates a value
    assert out.failure == "truncated_reply" and not out.abstained
    assert is_truncation_reason(out.domain_reasoning)
    assert out.domain_reasoning == TRUNCATED_REPLY_REASON


def test_genuine_abstention_is_not_flagged_as_configuration():
    out = _support_rater(FakePoster(GENUINE_ABSTENTION)).rate(
        claim=CLAIM, candidate=CAND, task_type="claim_support")
    assert out.abstained and out.value is None and out.failure is None
    assert not is_truncation_reason(out.domain_reasoning)
    assert out.domain_reasoning == "abstract lacks the outcome"


def test_truncated_and_genuine_abstentions_are_distinguishable():
    """The point of the fix: the two events must not collapse into one signal."""
    trunc = _support_rater(FakePoster(THINKING_TRUNCATED)).rate(
        claim=CLAIM, candidate=CAND, task_type="claim_support")
    real = _support_rater(FakePoster(GENUINE_ABSTENTION)).rate(
        claim=CLAIM, candidate=CAND, task_type="claim_support")
    assert trunc.value is None and real.value is None              # neither has a value...
    assert trunc.failure == "truncated_reply" and not trunc.abstained
    assert real.abstained and real.failure is None                 # ...for opposite reasons
    assert is_truncation_reason(trunc.domain_reasoning)
    assert not is_truncation_reason(real.domain_reasoning)


def test_unparseable_but_complete_reply_is_its_own_failure_kind():
    """Garbage that was NOT cut off is still a failed call, but a different one: the token
    budget is fine, so the recorded kind must not send the operator to the wrong fix."""
    poster = FakePoster({"choices": [{"message": {"content": "I think maybe yes?"},
                                      "finish_reason": "stop"}]})
    out = _support_rater(poster).rate(claim=CLAIM, candidate=CAND, task_type="claim_support")
    assert out.failure == "unparseable_reply" and not out.abstained
    assert not is_truncation_reason(out.domain_reasoning)


# --- the same distinction on the GRADE path -----------------------------------

class _Scheme:
    kind = "grade"
    scheme_id = "grade-v1"
    unit = "outcome"

    def level_values(self):
        return {"high", "moderate", "low", "very_low"}


class _Subject:
    outcome_id = None
    study_id = None
    domain_id = None


class _Frame:
    pico = None
    outcomes: list = []


def test_grade_rater_reports_truncation_as_configuration():
    r = HttpAiRater(shape="openai", endpoint="https://x", model="qwen3:14b",
                    poster=FakePoster(THINKING_TRUNCATED))
    out = r.rate(frame=_Frame(), scheme=_Scheme(), subject=_Subject(), task_type="grade")
    assert out.value is None
    assert out.failure == "truncated_reply" and not out.abstained
    assert is_truncation_reason(out.domain_reasoning)


def test_grade_rater_genuine_abstention_not_flagged():
    r = HttpAiRater(shape="openai", endpoint="https://x", model="m",
                    poster=FakePoster(GENUINE_ABSTENTION))
    out = r.rate(frame=_Frame(), scheme=_Scheme(), subject=_Subject(), task_type="grade")
    assert out.abstained and out.failure is None
    assert not is_truncation_reason(out.domain_reasoning)


# --- the truncation signal comes from the provider, not a heuristic -----------

def test_anthropic_max_tokens_stop_reason_is_truncation():
    poster = FakePoster({"content": [{"type": "text", "text": "Let me reason about this"}],
                         "stop_reason": "max_tokens"})
    reply = chat_reply(shape="anthropic", endpoint="https://api.anthropic.com/v1/messages",
                       model="m", prompt="p", api_key="sk-1", poster=poster)
    assert reply.truncated and reply.text == "Let me reason about this"


def test_normal_stop_is_not_truncation():
    reply = chat_reply(shape="openai", endpoint="https://x", model="m", prompt="p",
                       poster=FakePoster(GENUINE_ABSTENTION))
    assert not reply.truncated


def test_unexpected_shape_is_a_provider_error_not_a_silent_empty_reply():
    """The endpoint answered with nothing the model said. Left as a bare empty reply this
    reaches the rater looking exactly like a model that wrote something unreadable — a
    transport fault wearing the model's behaviour."""
    reply = chat_reply(shape="openai", endpoint="https://x", model="m", prompt="p",
                       poster=FakePoster({"unexpected": True}))
    assert reply.text == "" and not reply.truncated
    assert reply.provider_error


def test_slow_but_complete_reply_is_never_called_truncated():
    """Latency is machine-dependent — a slow laptop is not a misconfiguration. Only the
    provider's own stop signal marks truncation."""
    reply = chat_reply(shape="openai", endpoint="https://x", model="m", prompt="p",
                       poster=FakePoster(GENUINE_ABSTENTION))
    assert not reply.truncated


# --- the reply budget --------------------------------------------------------

def test_local_mode_sends_headroom_for_a_reasoning_model():
    poster = FakePoster(GENUINE_ABSTENTION)
    _support_rater(poster, max_tokens=LOCAL_MAX_REPLY_TOKENS).rate(
        claim=CLAIM, candidate=CAND, task_type="claim_support")
    sent = poster.calls[0]["payload"]["max_tokens"]
    assert sent == LOCAL_MAX_REPLY_TOKENS
    # measured worst case for qwen3:14b on the prescreen corpus was 596 tokens
    assert sent > 596


def test_resolve_local_defaults_to_headroom_and_api_stays_frugal():
    local = Config.default()
    local.ai_connection.mode = "local"
    assert resolve_ai_connection(local)["max_tokens"] == LOCAL_MAX_REPLY_TOKENS

    api = Config.default()
    api.ai_connection.mode = "api"
    api.ai_provenance.provider = "openai"
    api.ai_connection.endpoint = "https://api.openai.com/v1/chat/completions"
    conn = resolve_ai_connection(api, resolve_secret=lambda n: "k")
    assert conn["max_tokens"] == API_MAX_REPLY_TOKENS


def test_operator_can_override_the_reply_budget():
    cfg = Config.default()
    cfg.ai_connection.mode = "local"
    cfg.ai_connection.max_reply_tokens = 4096
    assert resolve_ai_connection(cfg)["max_tokens"] == 4096


def test_built_local_support_rater_carries_the_budget():
    from citevahti.claims import build_support_ai_rater
    cfg = Config.default()
    cfg.ai_connection.mode = "local"
    cfg.ai_provenance.model_id = "qwen3:14b"
    assert build_support_ai_rater(cfg).max_tokens == LOCAL_MAX_REPLY_TOKENS


# --- invariants still hold ---------------------------------------------------

def test_truncation_never_produces_a_value():
    """Invariant: the rater must never fabricate a value — a cut-off reply included."""
    for shape, resp in (("openai", THINKING_TRUNCATED),
                        ("anthropic", {"content": [{"type": "text", "text": "reasoning"}],
                                       "stop_reason": "max_tokens"})):
        out = HttpClaimSupportRater(shape=shape, endpoint="https://x", model="m",
                                    poster=FakePoster(resp)).rate(
            claim=CLAIM, candidate=CAND, task_type="claim_support")
        assert out.value is None and out.failure == "truncated_reply"
