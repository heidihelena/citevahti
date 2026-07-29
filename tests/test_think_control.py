"""ai_connection.think — the operator's chain-of-thought switch (local Ollama only).

Offline (fake poster). Locks four things:

1. The DEFAULT stays thinking-on: think is None out of the box and the /v1 payload
   carries no think field — the 2026-07-27 measurement showed think=false trades
   away 'unclear' discrimination, so it must never switch itself on.
2. think=false rides Ollama's NATIVE /api/chat (the /v1 shape has no such switch),
   with the ceiling carried as options.num_predict.
3. The ChatReply contract survives the native shape: done_reason=length is a
   truncation, a shapeless answer is a transport failure — never a rating.
4. api mode rejects the option at resolve time instead of silently ignoring it.
"""

from __future__ import annotations

import json

import pytest

from citevahti.claims import HttpClaimSupportRater, build_support_ai_rater
from citevahti.rating.ai import chat_reply, resolve_ai_connection
from citevahti.schemas.config import Config


class FakePoster:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(self, url, headers, payload, timeout):
        self.calls.append({"url": url, "headers": headers, "payload": payload})
        return self.response


class _Claim:
    claim_text = "Drug X reduced mortality"


class _Cand:
    title = "A trial"
    abstract = "Drug X did not reduce mortality in the treatment arm."


def _native(obj, *, done_reason="stop", eval_count=48):
    return {"message": {"role": "assistant", "content": json.dumps(obj)},
            "done": True, "done_reason": done_reason, "eval_count": eval_count}


def _v1(obj):
    return {"choices": [{"message": {"content": json.dumps(obj)}}]}


def _cfg(mode, **conn):
    c = Config.default()
    c.ai_connection.mode = mode
    for k, v in conn.items():
        setattr(c.ai_connection, k, v)
    c.ai_provenance.provider = "openai"
    c.ai_provenance.model_id = "qwen3:14b"
    return c


# --- 1. the default stays thinking-on ----------------------------------------

def test_config_default_is_none_thinking_stays_on():
    assert Config.default().ai_connection.think is None


def test_default_v1_payload_carries_no_think_field():
    poster = FakePoster(_v1({"value": "directly_supports", "abstained": False}))
    chat_reply(shape="openai", endpoint="http://localhost:11434/v1/chat/completions",
               model="qwen3:14b", prompt="p", poster=poster)
    call = poster.calls[0]
    assert call["url"].endswith("/v1/chat/completions")
    assert "think" not in call["payload"]


def test_resolve_local_passes_think_through_default_none():
    c = resolve_ai_connection(_cfg("local"))
    assert c["think"] is None


# --- 2. think=false rides the native /api/chat --------------------------------

def test_think_false_posts_to_native_api_chat_with_the_switch_and_ceiling():
    poster = FakePoster(_native({"value": "unclear", "abstained": False}))
    reply = chat_reply(shape="openai",
                       endpoint="http://localhost:11434/v1/chat/completions",
                       model="qwen3:14b", prompt="p", poster=poster,
                       max_tokens=4096, think=False)
    call = poster.calls[0]
    assert call["url"] == "http://localhost:11434/api/chat"
    assert call["payload"]["think"] is False
    assert call["payload"]["stream"] is False
    assert call["payload"]["options"]["num_predict"] == 4096
    assert reply.text and not reply.truncated
    assert reply.completion_tokens == 48 and reply.max_tokens == 4096


def test_support_rater_end_to_end_over_native_shape():
    poster = FakePoster(_native({"value": "unclear", "abstained": False,
                                 "confidence": 0.6, "rationale": "on-topic, unsettled"}))
    r = HttpClaimSupportRater(shape="openai",
                              endpoint="http://localhost:11434/v1/chat/completions",
                              model="qwen3:14b", poster=poster, think=False)
    out = r.rate(claim=_Claim(), candidate=_Cand(), task_type="assess")
    assert out.value == "unclear" and not out.abstained and out.failure is None


def test_built_local_rater_carries_the_operator_switch():
    r = build_support_ai_rater(_cfg("local", think=False))
    assert isinstance(r, HttpClaimSupportRater) and r.think is False


# --- 3. the ChatReply contract survives the native shape ----------------------

def test_native_done_reason_length_is_a_truncation():
    poster = FakePoster(_native({"value": "unclear"}, done_reason="length"))
    reply = chat_reply(shape="openai",
                       endpoint="http://localhost:11434/v1/chat/completions",
                       model="qwen3:14b", prompt="p", poster=poster, think=False)
    assert reply.truncated


def test_native_shapeless_answer_is_a_transport_failure_not_a_rating():
    # An LM Studio-style server has no /api/chat; its error payload has no message.
    poster = FakePoster({"error": "unknown path"})
    reply = chat_reply(shape="openai",
                       endpoint="http://localhost:11434/v1/chat/completions",
                       model="qwen3:14b", prompt="p", poster=poster, think=False)
    assert reply.provider_error and reply.text == ""


# --- 4. no silent ignoring ----------------------------------------------------

def test_api_mode_rejects_think_at_resolve_time():
    cfg = _cfg("api", think=False,
               endpoint="https://api.openai.com/v1/chat/completions")
    with pytest.raises(ValueError, match="think"):
        resolve_ai_connection(cfg, resolve_secret=lambda n: "test-key")


def test_anthropic_shape_rejects_think_at_construction():
    with pytest.raises(ValueError, match="think"):
        HttpClaimSupportRater(shape="anthropic",
                              endpoint="https://api.anthropic.com/v1/messages",
                              model="claude", think=False)
