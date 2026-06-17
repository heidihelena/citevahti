"""The AiRater seam, plus a real OpenAI-compatible / Anthropic rater.

The rater is BLIND: it never receives the human value. Unit tests use
``FakeAiRater``; ``HttpAiRater`` is the real, optional rater that talks to a
local (Ollama / LM Studio) or external (OpenAI / Anthropic / compatible) chat
endpoint. ``build_ai_rater`` constructs it from config, or returns None when AI
is off — the engine's ``ai_rater`` seam is unchanged.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable
from urllib.parse import urlparse

from ..schemas.common import PassageRef


@dataclass
class AiRatingOutput:
    value: Optional[str] = None
    abstained: bool = False
    confidence: Optional[float] = None
    supporting_passages: list[PassageRef] = field(default_factory=list)
    domain_reasoning: Optional[str] = None


@runtime_checkable
class AiRater(Protocol):
    # NOTE: the signature intentionally excludes any human value.
    def rate(self, *, frame, scheme, subject, task_type: str) -> AiRatingOutput: ...


class FakeAiRater:
    """Deterministic offline rater for tests."""

    def __init__(self, value: Optional[str] = None, abstained: bool = False,
                 confidence: Optional[float] = None,
                 supporting_passages: Optional[list[PassageRef]] = None,
                 domain_reasoning: Optional[str] = None) -> None:
        self._out = AiRatingOutput(value=None if abstained else value, abstained=abstained,
                                   confidence=confidence,
                                   supporting_passages=supporting_passages or [],
                                   domain_reasoning=domain_reasoning)

    def rate(self, *, frame, scheme, subject, task_type: str) -> AiRatingOutput:
        return self._out


# --- real rater (optional) ---------------------------------------------------

_OPENAI_DEFAULT = "https://api.openai.com/v1/chat/completions"
_ANTHROPIC_DEFAULT = "https://api.anthropic.com/v1/messages"
_OLLAMA_DEFAULT = "http://localhost:11434/v1/chat/completions"


def _safe_endpoint(url: str, *, allow_local: bool) -> bool:
    """https everywhere; plain http only for localhost (and only when allowed)."""
    try:
        u = urlparse(url)
    except Exception:  # noqa: BLE001
        return False
    if u.scheme == "https":
        return True
    if allow_local and u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1"):
        return True
    return False


@runtime_checkable
class HttpPoster(Protocol):
    def post_json(self, url: str, headers: dict, payload: dict, timeout: float) -> dict: ...


class HttpxPoster:
    """Default poster over httpx (already a dependency)."""

    def post_json(self, url: str, headers: dict, payload: dict, timeout: float) -> dict:
        import httpx
        resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()


class HttpAiRater:
    """A real, BLIND AI rater over an OpenAI-compatible or Anthropic chat endpoint.

    It never receives the human value (the ``rate`` signature forbids it). It asks
    the model for exactly one controlled-vocabulary level and **abstains on anything
    it cannot map** — it never fabricates an out-of-scheme value.
    """

    def __init__(self, *, shape: str, endpoint: str, model: str,
                 api_key: Optional[str] = None, poster: Optional[HttpPoster] = None,
                 timeout: float = 60.0) -> None:
        if shape not in ("openai", "anthropic"):
            raise ValueError(f"unknown AI shape: {shape!r}")
        self.shape = shape
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self.poster = poster or HttpxPoster()
        self.timeout = timeout

    def rate(self, *, frame, scheme, subject, task_type: str) -> AiRatingOutput:
        prompt = self._build_prompt(frame, scheme, subject, task_type)
        text = self._extract_text(self._call(prompt))
        return self._parse(text, scheme)

    # blinded: only the frame/scheme/subject context is available here
    @staticmethod
    def _build_prompt(frame, scheme, subject, task_type: str) -> str:
        levels = sorted(scheme.level_values())
        lines = [
            "You are a BLINDED second rater for a citation-integrity tool.",
            f"Apply the {scheme.kind} scheme ({scheme.scheme_id}, unit={scheme.unit}).",
        ]
        pico = getattr(frame, "pico", None)
        if pico:
            bits = [f"{k.upper()}={getattr(pico, k)}" for k in ("p", "i", "c") if getattr(pico, k, None)]
            if getattr(pico, "o", None):
                bits.append("O=" + "; ".join(pico.o))
            if bits:
                lines.append("PICO: " + " | ".join(bits))
        if subject.outcome_id:
            o = next((x for x in frame.outcomes if x.outcome_id == subject.outcome_id), None)
            lines.append(f"Outcome: {o.label if o else subject.outcome_id}")
        if subject.study_id:
            lines.append(f"Study: {subject.study_id}")
        if subject.domain_id:
            lines.append(f"Domain: {subject.domain_id}")
        lines.append(f"Choose EXACTLY ONE level from: {levels}.")
        lines.append("If the evidence is insufficient to judge, abstain.")
        lines.append('Reply with ONLY JSON: {"value":"<one level or null>",'
                     '"abstained":<bool>,"confidence":<0..1 or null>,"rationale":"<=25 words"}')
        return "\n".join(lines)

    def _call(self, prompt: str) -> dict:
        if self.shape == "anthropic":
            headers = {"content-type": "application/json", "anthropic-version": "2023-06-01"}
            if self.api_key:
                headers["x-api-key"] = self.api_key
            payload = {"model": self.model, "max_tokens": 300,
                       "messages": [{"role": "user", "content": prompt}]}
        else:
            headers = {"content-type": "application/json"}
            if self.api_key:  # local servers (Ollama/LM Studio) need no key
                headers["authorization"] = "Bearer " + self.api_key
            payload = {"model": self.model, "max_tokens": 300, "temperature": 0,
                       "messages": [{"role": "user", "content": prompt}]}
        return self.poster.post_json(self.endpoint, headers, payload, self.timeout)

    @staticmethod
    def _extract_text(data: dict) -> str:
        try:
            if isinstance(data.get("content"), list):          # anthropic
                return data["content"][0].get("text", "")
            return data["choices"][0]["message"]["content"]    # openai-compatible
        except (KeyError, IndexError, AttributeError, TypeError):
            return ""

    def _parse(self, text: str, scheme) -> AiRatingOutput:
        m = re.search(r"\{.*\}", text or "", re.DOTALL)
        if not m:
            return AiRatingOutput(abstained=True, domain_reasoning="unparseable AI reply")
        try:
            pj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return AiRatingOutput(abstained=True, domain_reasoning="unparseable AI reply")
        rationale = (str(pj.get("rationale") or "")[:200]) or None
        conf = pj.get("confidence")
        conf = float(conf) if isinstance(conf, (int, float)) else None
        if pj.get("abstained") or pj.get("value") in (None, "", "null"):
            return AiRatingOutput(abstained=True, confidence=conf, domain_reasoning=rationale)
        value = str(pj["value"])
        if value not in scheme.level_values():
            # never fabricate an out-of-scheme value -> abstain honestly
            return AiRatingOutput(abstained=True, confidence=conf,
                                  domain_reasoning=f"AI returned out-of-scheme value {value!r}")
        return AiRatingOutput(value=value, abstained=False, confidence=conf,
                              domain_reasoning=rationale)


def build_ai_rater(config, *, poster: Optional[HttpPoster] = None, resolve_secret=None):
    """Construct the configured AI rater, or **None when AI is off**.

    ``local`` -> OpenAI-compatible, no key, localhost/https only. ``api`` -> provider
    shape + key from the credential store (env escape hatch honored), https only —
    a key is never sent over plaintext. ``resolve_secret(name)`` is injectable for tests.
    """
    conn = config.ai_connection
    if not conn.is_enabled():
        return None
    prov = config.ai_provenance
    if conn.mode == "local":
        endpoint = conn.endpoint or _OLLAMA_DEFAULT
        if not _safe_endpoint(endpoint, allow_local=True):
            raise ValueError("local AI endpoint must be http://localhost or an https URL")
        return HttpAiRater(shape="openai", endpoint=endpoint, model=prov.model_id,
                           api_key=None, poster=poster, timeout=conn.request_timeout_s)
    # api mode
    shape = "anthropic" if prov.provider == "anthropic" else "openai"
    endpoint = conn.endpoint or (_ANTHROPIC_DEFAULT if shape == "anthropic" else _OPENAI_DEFAULT)
    if not _safe_endpoint(endpoint, allow_local=False):
        raise ValueError("external AI endpoint must be https (never send a key in plaintext)")
    from ..credentials import AI_API_KEY
    if resolve_secret is not None:
        api_key = resolve_secret(AI_API_KEY)
    else:
        from ..credentials import CredentialError, get_credential_store
        from ..credentials import resolve_secret as cred_resolve
        try:
            store = get_credential_store(getattr(config, "secrets_backend", "system_keyring"))
        except CredentialError:
            store = None          # keyring extra absent — env escape hatch still works
        api_key = cred_resolve(AI_API_KEY, store)
    if not api_key:
        raise ValueError("api mode needs an AI key (set CITEVAHTI_AI_API_KEY or store it)")
    return HttpAiRater(shape=shape, endpoint=endpoint, model=prov.model_id,
                       api_key=api_key, poster=poster, timeout=conn.request_timeout_s)
