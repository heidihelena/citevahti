"""A transient AI-call failure is retried; a judgement is never re-asked.

Measured 2026-07-26 on the 44-pair prescreen corpus: qwen3:14b lost 15 of 44 ratings to
what the ledger called abstentions — 13 unreadable replies and 2 timeouts, none of them
the model declining. The failures were **flaky, not deterministic**: item D01 returned an
unreadable reply during the run and parsed cleanly on retry with identical input. So the
ratings were recoverable, and were being thrown away.

The policy has two halves and both are load-bearing:
  * a TRANSIENT no-answer (``provider_error`` / ``unparseable_reply``, including a raised
    transport error) is retried, because asking again can produce the answer that was lost;
  * everything the model actually SAID is returned on the first attempt — a rating, an
    abstention, an off-scale answer, or a reply cut off at a token ceiling. Re-asking a
    judgement until it changes would be selecting on the outcome, and re-asking a
    misconfiguration just reproduces it.

Offline throughout (scripted poster); no model is contacted and nothing sleeps.
"""

from __future__ import annotations

import json

import pytest

from citevahti.claims import HttpClaimSupportRater
from citevahti.rating.ai import RETRYABLE_FAILURE_KINDS, HttpAiRater

CLAIM = type("C", (), {"claim_text": "Drug X reduced mortality"})()
CAND = type("P", (), {"title": "A trial", "abstract": "Drug X did not reduce mortality."})()


def _reply(payload, finish="stop"):
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return {"choices": [{"message": {"content": body}, "finish_reason": finish}]}


GOOD = _reply({"value": "contradicts", "abstained": False, "rationale": "opposite result"})
ABSTAIN = _reply({"value": None, "abstained": True, "rationale": "no outcome reported"})
GARBLED = _reply("Hmm, let me think about this one.")          # no JSON -> unparseable
CUT_OFF = _reply("Okay, so the claim says", finish="length")   # -> truncated_reply
OFF_SCALE = _reply({"value": "super_supports", "abstained": False})
BAD_SHAPE = {"error": "model not loaded"}                      # -> provider_error


class ScriptedPoster:
    """Returns (or raises) one scripted item per call, so a test states the exact sequence
    of transport outcomes it is about. Records every prompt sent."""

    def __init__(self, *script):
        self.script = list(script)
        self.prompts = []

    def post_json(self, url, headers, payload, timeout):
        self.prompts.append(payload["messages"][0]["content"])
        item = self.script[min(len(self.prompts) - 1, len(self.script) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def calls(self):
        return len(self.prompts)


def _rater(poster, **kw):
    kw.setdefault("retry_backoff_s", 0.0)          # nothing sleeps in the suite
    return HttpClaimSupportRater(shape="openai", endpoint="http://localhost:11434/v1/x",
                                 model="qwen3:14b", poster=poster, **kw)


def _rate(poster, **kw):
    return _rater(poster, **kw).rate(claim=CLAIM, candidate=CAND, task_type="claim_support")


# --- what gets recovered -----------------------------------------------------

def test_a_flaky_unreadable_reply_is_retried_and_the_rating_recovered():
    """The measured D01 case: unreadable once, clean on the very next identical call."""
    poster = ScriptedPoster(GARBLED, GOOD)
    out = _rate(poster)
    assert out.value == "contradicts" and out.failure is None
    assert poster.calls == 2


def test_an_unreachable_endpoint_is_retried_and_recovered():
    poster = ScriptedPoster(BAD_SHAPE, GOOD)
    out = _rate(poster)
    assert out.value == "contradicts" and out.failure is None
    assert poster.calls == 2


def test_a_raised_transport_error_is_retried_and_recovered():
    """The 2 timeouts in the measured run raised out of the rater entirely, so nothing
    could recover them. They are now retried like any other transient no-answer."""
    poster = ScriptedPoster(TimeoutError("read timed out"), GOOD)
    out = _rate(poster)
    assert out.value == "contradicts" and out.failure is None
    assert poster.calls == 2


def test_retries_ask_the_same_question_every_time():
    """A retry must be the SAME call again, never a reworded or loosened one — otherwise
    'retry' becomes prompting until the model says something usable."""
    poster = ScriptedPoster(GARBLED, GARBLED, GOOD)
    _rate(poster)
    assert poster.calls == 3
    assert len(set(poster.prompts)) == 1


# --- what is never re-asked --------------------------------------------------

def test_a_genuine_abstention_is_never_re_asked():
    """The model read the pair and declined. That is its judgement; asking again until it
    changes its mind would manufacture a rating the model did not give."""
    poster = ScriptedPoster(ABSTAIN, GOOD)
    out = _rate(poster)
    assert out.abstained is True and out.value is None
    assert poster.calls == 1


def test_an_off_scale_answer_is_never_re_asked():
    """The model answered — off the vocabulary. Repeating the identical call until it
    lands in scale is selecting on the outcome, and it would hide a prompt-compliance
    defect that has to stay visible in the ledger."""
    poster = ScriptedPoster(OFF_SCALE, GOOD)
    out = _rate(poster)
    assert out.failure == "out_of_vocab_value"
    assert poster.calls == 1


def test_a_cut_off_reply_is_never_retried():
    """The token ceiling is a setting, not a glitch: the same call under the same ceiling
    is cut off again. Retrying would burn time reproducing a misconfiguration."""
    poster = ScriptedPoster(CUT_OFF, GOOD)
    out = _rate(poster)
    assert out.failure == "truncated_reply"
    assert poster.calls == 1


def test_a_successful_rating_costs_exactly_one_call():
    poster = ScriptedPoster(GOOD)
    assert _rate(poster).value == "contradicts"
    assert poster.calls == 1


def test_only_the_transient_kinds_are_retryable():
    """The policy itself, asserted rather than implied by the cases above."""
    assert set(RETRYABLE_FAILURE_KINDS) == {"provider_error", "unparseable_reply"}


# --- when retrying does not help ---------------------------------------------

def test_a_persistent_failure_is_recorded_and_says_it_persisted():
    """A consistently broken adapter must not read like one unlucky call — the recorded
    reason has to tell the operator which of the two they are looking at."""
    poster = ScriptedPoster(GARBLED)
    out = _rate(poster)
    assert out.failure == "unparseable_reply" and out.value is None
    assert poster.calls == 3                       # AI_RETRY_ATTEMPTS
    assert "retried 3x" in out.domain_reasoning
    assert "unlikely to be a transient glitch" in out.domain_reasoning


def test_an_endpoint_that_never_answers_still_raises():
    """Terminal behaviour is unchanged: if every attempt raises, the error propagates
    rather than being quietly written into the ledger as a rating attempt."""
    poster = ScriptedPoster(TimeoutError("read timed out"))
    with pytest.raises(TimeoutError):
        _rate(poster)
    assert poster.calls == 3


def test_retries_can_be_switched_off():
    poster = ScriptedPoster(GARBLED, GOOD)
    out = _rate(poster, retry_attempts=1)
    assert out.failure == "unparseable_reply"
    assert poster.calls == 1
    assert "retried" not in (out.domain_reasoning or "")   # a single attempt says nothing


# --- the same policy on the study-quality path -------------------------------

class _Scheme:
    kind, scheme_id, unit = "grade", "grade-v1", "outcome"

    def level_values(self):
        return {"High", "Moderate", "Low", "Very Low"}


class _Subject:
    outcome_id = study_id = domain_id = None


class _Frame:
    pico = None
    outcomes: list = []


def _grade_rate(poster, **kw):
    kw.setdefault("retry_backoff_s", 0.0)
    r = HttpAiRater(shape="openai", endpoint="https://x", model="qwen3:14b",
                    poster=poster, **kw)
    return r.rate(frame=_Frame(), scheme=_Scheme(), subject=_Subject(), task_type="grade")


def test_grade_rater_retries_a_transient_failure_too():
    poster = ScriptedPoster(GARBLED, _reply({"value": "Low", "abstained": False}))
    out = _grade_rate(poster)
    assert out.value == "Low" and out.failure is None
    assert poster.calls == 2


def test_grade_rater_never_re_asks_an_abstention():
    poster = ScriptedPoster(ABSTAIN, _reply({"value": "Low", "abstained": False}))
    out = _grade_rate(poster)
    assert out.abstained is True and poster.calls == 1


# --- the operator's knob -----------------------------------------------------

def test_retry_budget_comes_from_config(tmp_path):
    """The worst case for one item is retry_attempts x request_timeout_s, so the budget
    has to be the operator's to set — not a constant baked into the rater."""
    from citevahti.claims.ai import build_support_ai_rater
    from citevahti.rating.ai import build_ai_rater
    from citevahti.schemas.config import Config

    cfg = Config.default()
    cfg.ai_connection.mode = "local"
    cfg.ai_connection.retry_attempts = 1
    cfg.ai_provenance.model_id = "qwen3:14b"
    assert build_support_ai_rater(cfg).retry_attempts == 1
    assert build_ai_rater(cfg).retry_attempts == 1

    cfg.ai_connection.retry_attempts = 5
    assert build_support_ai_rater(cfg).retry_attempts == 5
