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


def chat_completion(*, shape: str, endpoint: str, model: str, prompt: str,
                    api_key: Optional[str] = None, poster: Optional[HttpPoster] = None,
                    timeout: float = 60.0) -> str:
    """One blinded chat turn over an OpenAI-compatible or Anthropic endpoint → reply text.

    Shared by every CiteVahti rater. A key (when present) rides the provider's header;
    local servers (Ollama / LM Studio) need none. Returns "" on an unexpected shape.
    """
    poster = poster or HttpxPoster()
    if shape == "anthropic":
        headers = {"content-type": "application/json", "anthropic-version": "2023-06-01"}
        if api_key:
            headers["x-api-key"] = api_key
        payload = {"model": model, "max_tokens": 300,
                   "messages": [{"role": "user", "content": prompt}]}
    else:
        headers = {"content-type": "application/json"}
        if api_key:
            headers["authorization"] = "Bearer " + api_key
        payload = {"model": model, "max_tokens": 300, "temperature": 0,
                   "messages": [{"role": "user", "content": prompt}]}
    data = poster.post_json(endpoint, headers, payload, timeout)
    try:
        if isinstance(data.get("content"), list):          # anthropic
            return data["content"][0].get("text", "")
        return data["choices"][0]["message"]["content"]    # openai-compatible
    except (KeyError, IndexError, AttributeError, TypeError):
        return ""


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
        text = chat_completion(shape=self.shape, endpoint=self.endpoint, model=self.model,
                               api_key=self.api_key, prompt=prompt, poster=self.poster,
                               timeout=self.timeout)
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


def resolve_ai_connection(config, *, resolve_secret=None) -> Optional[dict]:
    """Resolve ``{shape, endpoint, api_key}`` for the configured AI connection, or
    **None when AI is off**. Shared by every rater factory so the connection rules
    live in one place.

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
        return {"shape": "openai", "endpoint": endpoint, "api_key": None}
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
    return {"shape": shape, "endpoint": endpoint, "api_key": api_key}


def build_ai_rater(config, *, poster: Optional[HttpPoster] = None, resolve_secret=None):
    """Construct the configured GRADE/scheme AI rater, or **None when AI is off**."""
    c = resolve_ai_connection(config, resolve_secret=resolve_secret)
    if c is None:
        return None
    return HttpAiRater(shape=c["shape"], endpoint=c["endpoint"],
                       model=config.ai_provenance.model_id, api_key=c["api_key"],
                       poster=poster, timeout=config.ai_connection.request_timeout_s)


# --- local model discovery (Ollama) ------------------------------------------
# Claim verification is term-extraction / word-mining work; Qwen tends to beat
# llama3.1 at it, so it leads the preference order. But the model actually on the
# machine wins: we offer what `ollama list` reports and only fall back to a name.
PREFERRED_LOCAL_MODELS = ("qwen2.5", "qwen2", "llama3.1")
DEFAULT_LOCAL_MODEL = PREFERRED_LOCAL_MODELS[0]


def _ollama_base(endpoint: str) -> str:
    """The Ollama root (…:11434) from a chat endpoint (…/v1/chat/completions)."""
    u = urlparse(endpoint or _OLLAMA_DEFAULT)
    return f"{u.scheme}://{u.netloc}"


def _httpx_get_json(url: str, timeout: float = 5.0) -> dict:
    import httpx
    resp = httpx.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def list_ollama_models(endpoint: str = _OLLAMA_DEFAULT, *, fetch=None) -> list[dict]:
    """Installed Ollama models as ``[{name, digest}]`` (empty list if unreachable).

    ``fetch(url) -> dict`` is injectable for tests; defaults to a short httpx GET.
    """
    fetch = fetch or _httpx_get_json
    try:
        data = fetch(_ollama_base(endpoint) + "/api/tags")
    except Exception:  # noqa: BLE001 (Ollama not running / no network) — degrade to empty
        return []
    out = []
    for m in (data.get("models") or []):
        name = m.get("name") or m.get("model")
        if name:
            out.append({"name": name, "digest": m.get("digest")})
    return out


def suggest_local_model(models: list[dict]) -> str:
    """Pick the model to offer: a preferred extraction model if installed, else the
    first installed one, else the default name (so the UI always has a suggestion)."""
    names = [m["name"] for m in models]
    for pref in PREFERRED_LOCAL_MODELS:
        for n in names:
            if n == pref or n.split(":")[0] == pref:
                return n
    return names[0] if names else DEFAULT_LOCAL_MODEL


def ollama_model_snapshot(endpoint: str, model: str, *, fetch=None) -> Optional[str]:
    """The installed model's digest — pinned into ``ai_provenance.model_snapshot`` so a
    local model is auditable just like a cloud one. None if it isn't installed."""
    for m in list_ollama_models(endpoint, fetch=fetch):
        if m["name"] == model or m["name"].split(":")[0] == model.split(":")[0]:
            return m.get("digest")
    return None
