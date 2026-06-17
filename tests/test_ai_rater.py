"""The real (optional) HttpAiRater + build_ai_rater factory.

Offline: a FakePoster stands in for the HTTP call. Locks the contract — blinded,
returns a scheme level or abstains (never an out-of-scheme value), local needs no
key, api needs https + a key, and the key never rides a plaintext endpoint.
"""

from __future__ import annotations

import json

import pytest

from citevahti.credentials import AI_API_KEY
from citevahti.rating import HttpAiRater, build_ai_rater
from citevahti.schemas.config import Config
from citevahti.schemas.rating import Subject

SUBJECT = Subject(outcome_id="o_mortality")


class FakePoster:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(self, url, headers, payload, timeout):
        self.calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout})
        return self.response


def _openai(obj):
    return {"choices": [{"message": {"content": json.dumps(obj)}}]}


def _anthropic(obj):
    return {"content": [{"type": "text", "text": json.dumps(obj)}]}


# ---- rater ------------------------------------------------------------------
def test_rater_returns_scheme_value_and_is_blinded(frame):
    scheme = frame.get_scheme("grade_certainty")
    poster = FakePoster(_openai({"value": "Moderate", "abstained": False,
                                 "confidence": 0.7, "rationale": "ok"}))
    r = HttpAiRater(shape="openai", endpoint="http://localhost:11434/v1/chat/completions",
                    model="llama3.1", poster=poster)
    out = r.rate(frame=frame, scheme=scheme, subject=SUBJECT, task_type="assess")
    assert out.value == "Moderate" and not out.abstained and out.confidence == 0.7
    sent = poster.calls[0]["payload"]["messages"][0]["content"]
    assert "GRADE" in sent and "Moderate" in sent          # scheme levels are in the prompt…
    assert "human" not in sent.lower()                     # …but no human value (blinded)
    assert "authorization" not in poster.calls[0]["headers"]  # local => no key sent


def test_rater_abstains_on_out_of_scheme_value(frame):
    scheme = frame.get_scheme("grade_certainty")
    poster = FakePoster(_openai({"value": "Excellent", "abstained": False}))
    r = HttpAiRater(shape="openai", endpoint="https://x/v1/chat/completions",
                    model="m", poster=poster)
    out = r.rate(frame=frame, scheme=scheme, subject=SUBJECT, task_type="assess")
    assert out.abstained and out.value is None             # never fabricate out-of-scheme


def test_rater_honors_explicit_abstain(frame):
    scheme = frame.get_scheme("grade_certainty")
    poster = FakePoster(_openai({"value": None, "abstained": True}))
    r = HttpAiRater(shape="openai", endpoint="https://x", model="m", poster=poster)
    out = r.rate(frame=frame, scheme=scheme, subject=SUBJECT, task_type="assess")
    assert out.abstained and out.value is None


def test_rater_unparseable_reply_abstains(frame):
    scheme = frame.get_scheme("grade_certainty")
    poster = FakePoster(_openai("sorry, I cannot help with that"))
    r = HttpAiRater(shape="openai", endpoint="https://x", model="m", poster=poster)
    out = r.rate(frame=frame, scheme=scheme, subject=SUBJECT, task_type="assess")
    assert out.abstained


def test_rater_anthropic_shape_sends_key_header(frame):
    scheme = frame.get_scheme("grade_certainty")
    poster = FakePoster(_anthropic({"value": "Low", "abstained": False}))
    r = HttpAiRater(shape="anthropic", endpoint="https://api.anthropic.com/v1/messages",
                    model="claude", api_key="sk-1", poster=poster)
    out = r.rate(frame=frame, scheme=scheme, subject=SUBJECT, task_type="assess")
    assert out.value == "Low"
    assert poster.calls[0]["headers"]["x-api-key"] == "sk-1"


# ---- factory ----------------------------------------------------------------
def _cfg(mode, *, provider="anthropic", model="claude-x", endpoint=None):
    c = Config.default()
    c.ai_connection.mode = mode
    if endpoint is not None:
        c.ai_connection.endpoint = endpoint
    c.ai_provenance.provider = provider
    c.ai_provenance.model_id = model
    return c


def test_build_off_returns_none():
    assert build_ai_rater(_cfg("off")) is None


def test_build_local_has_no_key():
    r = build_ai_rater(_cfg("local", model="llama3.1"))
    assert isinstance(r, HttpAiRater) and r.shape == "openai" and r.api_key is None
    assert "localhost" in r.endpoint


def test_build_api_resolves_key_and_shape():
    r = build_ai_rater(_cfg("api", provider="openai",
                            endpoint="https://api.openai.com/v1/chat/completions"),
                       resolve_secret=lambda name: "test-key" if name == AI_API_KEY else None)
    assert r.shape == "openai" and r.api_key == "test-key"


def test_build_api_rejects_plaintext_endpoint():
    with pytest.raises(ValueError):
        build_ai_rater(_cfg("api", endpoint="http://evil.example/v1"),
                       resolve_secret=lambda n: "k")


def test_build_api_requires_a_key():
    with pytest.raises(ValueError):
        build_ai_rater(_cfg("api", provider="openai",
                            endpoint="https://api.openai.com/v1/chat/completions"),
                       resolve_secret=lambda n: None)


def test_build_local_rejects_remote_http():
    with pytest.raises(ValueError):
        build_ai_rater(_cfg("local", endpoint="http://192.168.1.5:11434/v1/chat/completions"))
