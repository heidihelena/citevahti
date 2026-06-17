"""The real (optional) HttpClaimSupportRater + build_support_ai_rater.

Offline (fake poster). Locks the contract: blinded, returns a SUPPORT_VALUES value
or abstains (never an out-of-vocabulary value), local needs no key, api carries one.
"""

from __future__ import annotations

import json

from citevahti.claims import HttpClaimSupportRater, build_support_ai_rater
from citevahti.schemas.config import Config


class _Claim:
    def __init__(self, text):
        self.claim_text = text


class _Cand:
    def __init__(self, title, abstract):
        self.title = title
        self.abstract = abstract


class FakePoster:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(self, url, headers, payload, timeout):
        self.calls.append({"headers": headers, "payload": payload})
        return self.response


def _openai(obj):
    return {"choices": [{"message": {"content": json.dumps(obj)}}]}


def _anthropic(obj):
    return {"content": [{"type": "text", "text": json.dumps(obj)}]}


CLAIM = _Claim("Drug X reduced mortality")
CAND = _Cand("A trial", "Drug X did not reduce mortality in the treatment arm.")


def test_rater_returns_support_value_and_is_blinded():
    poster = FakePoster(_openai({"value": "contradicts", "abstained": False,
                                 "confidence": 0.6, "rationale": "opposite direction"}))
    r = HttpClaimSupportRater(shape="openai", endpoint="http://localhost:11434/v1/chat/completions",
                              model="qwen2.5", poster=poster)
    out = r.rate(claim=CLAIM, candidate=CAND, task_type="assess")
    assert out.value == "contradicts" and not out.abstained and out.confidence == 0.6
    sent = poster.calls[0]["payload"]["messages"][0]["content"]
    assert "Drug X reduced mortality" in sent and "human" not in sent.lower()  # blinded
    assert "authorization" not in poster.calls[0]["headers"]                   # local: no key


def test_rater_abstains_on_out_of_vocabulary():
    poster = FakePoster(_openai({"value": "super_supports", "abstained": False}))
    r = HttpClaimSupportRater(shape="openai", endpoint="https://x", model="m", poster=poster)
    out = r.rate(claim=CLAIM, candidate=CAND, task_type="assess")
    assert out.abstained and out.value is None


def test_rater_accepts_overstated_value():
    poster = FakePoster(_openai({"value": "overstated", "abstained": False}))
    r = HttpClaimSupportRater(shape="openai", endpoint="https://x", model="m", poster=poster)
    out = r.rate(claim=CLAIM, candidate=CAND, task_type="assess")
    assert out.value == "overstated"          # the cross-tool 'overstated' verdict is in vocab


def test_rater_anthropic_shape_sends_key():
    poster = FakePoster(_anthropic({"value": "directly_supports", "abstained": False}))
    r = HttpClaimSupportRater(shape="anthropic", endpoint="https://api.anthropic.com/v1/messages",
                              model="claude", api_key="sk-1", poster=poster)
    out = r.rate(claim=CLAIM, candidate=CAND, task_type="assess")
    assert out.value == "directly_supports" and poster.calls[0]["headers"]["x-api-key"] == "sk-1"


def _cfg(mode, *, provider="anthropic", model="claude-x", endpoint=None):
    c = Config.default()
    c.ai_connection.mode = mode
    if endpoint is not None:
        c.ai_connection.endpoint = endpoint
    c.ai_provenance.provider = provider
    c.ai_provenance.model_id = model
    return c


def test_build_off_returns_none():
    assert build_support_ai_rater(_cfg("off")) is None


def test_build_local_has_no_key():
    r = build_support_ai_rater(_cfg("local", model="qwen2.5"))
    assert isinstance(r, HttpClaimSupportRater) and r.shape == "openai" and r.api_key is None


def test_build_api_resolves_key():
    r = build_support_ai_rater(_cfg("api", provider="openai",
                                    endpoint="https://api.openai.com/v1/chat/completions"),
                               resolve_secret=lambda n: "test-key")
    assert r.shape == "openai" and r.api_key == "test-key"
