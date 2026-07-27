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
from typing import Optional, Protocol, Union, runtime_checkable
from urllib.parse import urlparse

from ..schemas.common import PassageRef


@dataclass
class AiRatingOutput:
    value: Optional[str] = None
    abstained: bool = False              # the model read the subject and DECLINED
    failure: Optional[str] = None        # one of AI_FAILURE_KINDS — it never judged
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

# Reply budget. A rating reply is ~50 tokens, so 300 is ample for a model that
# answers directly — but a reasoning ("thinking") model such as the qwen3 family
# spends reply tokens on its chain of thought, and the OpenAI-compatible endpoint
# gives us no way to turn that off (Ollama's native /api/chat takes ``think:
# false``; the /v1 shape does not). On a 300-token ceiling such a model is cut off
# before it answers, so the rater abstains — see ``TRUNCATED_REPLY_REASON``.
#
# Measured 2026-07-27, qwen3:14b over all 44 pairs of the prescreen corpus with the
# ceiling set deliberately non-binding (8192), reading the provider's own
# usage.completion_tokens rather than inferring the need: median 269, p90 393, and
# then a long tail — one item at 2396, and ONE ITEM THAT NEVER STOPPED. That item
# (C09: a claim about sleep against a paper about machine intelligence — a pair with
# no honest reconciliation) spent all 8192 tokens over 489s and returned zero
# characters, exactly as it had spent all 2048 at the shipped ceiling.
#
# So the ceiling is sized for the tail that ends, and NOT as a fix for the tail that
# doesn't: 4096 clears the largest reply that actually answered, with room over it.
# No ceiling clears a model that will not stop, and every token of headroom is also
# time a stuck item burns before failing — at the ~17 tok/s this model ran, 4096 is
# ~4 minutes. (It is usually the clock that stops such an item first: at that rate
# the default 60s request_timeout_s runs out around 1000 tokens, so raising this
# without also allowing the time changes nothing.) Local models are free and private,
# so local mode gets the headroom; api mode stays frugal because it is billed.
LOCAL_MAX_REPLY_TOKENS = 4096
API_MAX_REPLY_TOKENS = 300
# The advisory chat turn writes prose, not a one-line verdict, so 300 tokens cut
# real answers off mid-sentence. It is a different task shape, hence its own budget.
CHAT_MAX_REPLY_TOKENS = 1024
# Default policy: the raters default to the generous local budget, because a rater
# constructed directly (a script, a bench harness) must not silently truncate — that
# is the bug being fixed here. The low-level transport keeps the frugal default,
# because a bare call has no way to know it is talking to a free local model. Every
# production path passes an explicit budget from ``resolve_ai_connection``.

# A reply that never delivered a verdict is NOT a judgement. The rater still refuses
# to invent a value, but it records a **failure**, not an abstention: an abstention is
# the model declining, and a failure is the model never speaking. Collapsing the two
# writes a broken adapter into the audit trail — and into a published methods section —
# as the model exercising epistemic humility. The kinds live in schemas/rating.py
# (AI_FAILURE_KINDS); the operator-facing prose for each lives here.
TRUNCATED_REPLY_PREFIX = "configuration: "
TRUNCATED_REPLY_REASON = (
    TRUNCATED_REPLY_PREFIX
    + "the model hit its reply-token ceiling before returning an answer, so it "
      "never judged this item. This is a setup problem, not a rating. A reasoning "
      "('thinking') model needs a larger ai_connection.max_reply_tokens, or a "
      "model that answers directly."
)

_FAILURE_REASONS = {
    "provider_error":
        "the model endpoint returned no readable reply, so it never judged this item. "
        "This is a connection/endpoint problem, not a rating — check that the model is "
        "running and that ai_connection.endpoint and the model id are correct.",
    "truncated_reply": TRUNCATED_REPLY_REASON,
    "unparseable_reply":
        "the model replied but the reply contained no readable JSON verdict, so nothing "
        "was judged. This is an adapter/prompt-compliance problem, not a rating. Such "
        "replies are often transient — re-running the item usually recovers it.",
    "out_of_vocab_value":
        "the model answered with a value outside the controlled vocabulary, so there is "
        "no rating to record. This is a prompt-compliance problem, not a judgement about "
        "the evidence, and it is never mapped onto a nearby in-vocabulary value.",
}


def failure_reason(kind: str, detail: Optional[str] = None) -> str:
    """The recorded, operator-readable reason for an AI-rating ``failure`` kind.

    One place, so the panel, the ledger and the report describe the same event the same
    way. ``detail`` appends what the model actually returned (e.g. the out-of-vocabulary
    value) — evidence for the reader, never a value the system acts on.
    """
    base = _FAILURE_REASONS.get(kind, f"the AI call failed ({kind}), so nothing was judged.")
    return f"{base} Model returned: {detail}" if detail else base


def reply_budget_note(reply: "ChatReply") -> Optional[str]:
    """What a cut-off reply spent, in the operator's own units, or None if the provider
    said nothing about it.

    Deliberately worded for what these two numbers can and cannot show. A reply cut off
    at the ceiling spent EXACTLY the ceiling, so "used vs allowed" is never a measured
    shortfall — the reply stopped before the model was done, and the budget it actually
    needed is unknowable from that call. What the note IS good for is naming the number
    in force, which is the one the operator has to raise, without making them go and find
    it. Any wording implying a measured "how far short" would be inventing evidence.
    """
    used, allowed = reply.completion_tokens, reply.max_tokens
    if allowed is None:
        return None
    if used is None:
        return f"The ceiling in force was {allowed} reply tokens."
    return (f"It spent {used} of the {allowed} reply tokens allowed and still had not "
            f"answered, so it needs more than {allowed} on this item — a cut-off reply "
            "cannot show how much more.")


def failure_reason_for(kind: str, reply: "ChatReply") -> str:
    """``failure_reason`` plus what the reply itself reveals about the failure.

    Shared by both raters so a truncation reads the same in the claim-support ledger and
    in the GRADE one.
    """
    base = failure_reason(kind)
    note = reply_budget_note(reply) if kind == "truncated_reply" else None
    return f"{base} {note}" if note else base


def parse_verdict_json(reply: "ChatReply") -> Union[dict, str]:
    """The model's JSON verdict (a ``dict``), or the **failure kind** (a ``str``) when no
    verdict came back — callers branch on ``isinstance(result, str)``.

    Shared by both raters so the claim-support and GRADE paths classify a missing answer
    identically. Note what is deliberately NOT here: the three no-answer routes below are
    kept apart, because each is a different real event (the endpoint failed / the reply was
    cut off / the model wrote something unreadable) and only the last is about the model's
    behaviour at all. None of them is the model declining to rate.
    """
    if reply.provider_error:
        return "provider_error"
    cut_off_or_garbled = "truncated_reply" if reply.truncated else "unparseable_reply"
    m = re.search(r"\{.*\}", reply.text or "", re.DOTALL)
    if not m:
        return cut_off_or_garbled
    try:
        verdict = json.loads(m.group(0))
    except json.JSONDecodeError:
        return cut_off_or_garbled
    if not isinstance(verdict, dict):
        return "unparseable_reply"
    return verdict


def is_truncation_reason(reason: Optional[str]) -> bool:
    """True when a recorded reason marks a truncated reply (a misconfiguration) rather
    than a genuine 'cannot judge'.

    Superseded for new records by the typed ``ai_rating.failure`` field: this remains the
    classifier for records written **before** that field existed, where the prefixed
    reason string is the only evidence of what happened. New code should read ``failure``.
    """
    return bool(reason) and str(reason).startswith(TRUNCATED_REPLY_PREFIX)


@dataclass
class ChatReply:
    """One model reply, plus why it may not contain an answer.

    ``truncated`` comes from the provider's own stop signal (OpenAI-compatible
    ``finish_reason == "length"``, Anthropic ``stop_reason == "max_tokens"``) —
    not from a latency or length heuristic, which would misfire on a slow machine.

    ``provider_error`` is set when the response carried no readable model content at
    all (an error payload, or an unexpected shape). That is a transport-level event,
    not something the model said, and it must not reach the ledger looking like one.

    ``completion_tokens`` is what the provider says this reply spent (OpenAI-compatible
    ``usage.completion_tokens``, Anthropic ``usage.output_tokens``; None when the
    provider reports no usage) and ``max_tokens`` is the ceiling that was in force. They
    are carried so a truncation can name the budget the operator has to raise instead of
    only saying that some ceiling was hit — see ``reply_budget_note``.
    """

    text: str = ""
    truncated: bool = False
    provider_error: Optional[str] = None
    completion_tokens: Optional[int] = None
    max_tokens: Optional[int] = None


def _int_or_none(v) -> Optional[int]:
    """A provider's usage count when it really is a number — never a coerced guess."""
    return int(v) if isinstance(v, int) and not isinstance(v, bool) else None


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


def chat_reply(*, shape: str, endpoint: str, model: str, prompt: str,
               api_key: Optional[str] = None, poster: Optional[HttpPoster] = None,
               timeout: float = 60.0,
               max_tokens: int = API_MAX_REPLY_TOKENS) -> ChatReply:
    """One blinded chat turn over an OpenAI-compatible or Anthropic endpoint.

    Shared by every CiteVahti rater. A key (when present) rides the provider's header;
    local servers (Ollama / LM Studio) need none. Returns an empty reply on an
    unexpected shape, and flags a reply the provider says it cut off at ``max_tokens``
    so a caller can tell "never answered" from "answered, but abstained".
    """
    poster = poster or HttpxPoster()
    if shape == "anthropic":
        headers = {"content-type": "application/json", "anthropic-version": "2023-06-01"}
        if api_key:
            headers["x-api-key"] = api_key
        payload = {"model": model, "max_tokens": max_tokens,
                   "messages": [{"role": "user", "content": prompt}]}
    else:
        headers = {"content-type": "application/json"}
        if api_key:
            headers["authorization"] = "Bearer " + api_key
        payload = {"model": model, "max_tokens": max_tokens, "temperature": 0,
                   "messages": [{"role": "user", "content": prompt}]}
    data = poster.post_json(endpoint, headers, payload, timeout)
    raw_usage = data.get("usage")
    usage: dict = raw_usage if isinstance(raw_usage, dict) else {}
    try:
        if isinstance(data.get("content"), list):          # anthropic
            return ChatReply(text=data["content"][0].get("text", ""),
                             truncated=data.get("stop_reason") == "max_tokens",
                             completion_tokens=_int_or_none(usage.get("output_tokens")),
                             max_tokens=max_tokens)
        choice = data["choices"][0]                        # openai-compatible
        return ChatReply(text=choice["message"]["content"],
                         truncated=choice.get("finish_reason") == "length",
                         completion_tokens=_int_or_none(usage.get("completion_tokens")),
                         max_tokens=max_tokens)
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        # The endpoint answered, but with nothing the model said — an error payload or
        # an unexpected shape. Flag it as a TRANSPORT event: an empty reply would
        # otherwise reach the rater indistinguishable from a model that replied with
        # unreadable text, and end up recorded as if the model had spoken.
        return ChatReply(provider_error=f"{type(exc).__name__}: {str(exc)[:120]}",
                         max_tokens=max_tokens)


def chat_completion(*, shape: str, endpoint: str, model: str, prompt: str,
                    api_key: Optional[str] = None, poster: Optional[HttpPoster] = None,
                    timeout: float = 60.0,
                    max_tokens: int = API_MAX_REPLY_TOKENS) -> str:
    """``chat_reply`` reduced to just the text, for callers that cannot act on
    truncation (the advisory chat turn). Raters use ``chat_reply`` instead."""
    return chat_reply(shape=shape, endpoint=endpoint, model=model, prompt=prompt,
                      api_key=api_key, poster=poster, timeout=timeout,
                      max_tokens=max_tokens).text


class HttpAiRater:
    """A real, BLIND AI rater over an OpenAI-compatible or Anthropic chat endpoint.

    It never receives the human value (the ``rate`` signature forbids it). It asks
    the model for exactly one controlled-vocabulary level and **abstains on anything
    it cannot map** — it never fabricates an out-of-scheme value.
    """

    def __init__(self, *, shape: str, endpoint: str, model: str,
                 api_key: Optional[str] = None, poster: Optional[HttpPoster] = None,
                 timeout: float = 60.0,
                 max_tokens: int = LOCAL_MAX_REPLY_TOKENS) -> None:
        if shape not in ("openai", "anthropic"):
            raise ValueError(f"unknown AI shape: {shape!r}")
        self.shape = shape
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self.poster = poster or HttpxPoster()
        self.timeout = timeout
        self.max_tokens = max_tokens

    def rate(self, *, frame, scheme, subject, task_type: str) -> AiRatingOutput:
        prompt = self._build_prompt(frame, scheme, subject, task_type)
        reply = chat_reply(shape=self.shape, endpoint=self.endpoint, model=self.model,
                           api_key=self.api_key, prompt=prompt, poster=self.poster,
                           timeout=self.timeout, max_tokens=self.max_tokens)
        return self._parse(reply, scheme)

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

    def _parse(self, reply, scheme) -> AiRatingOutput:
        if isinstance(reply, str):                 # tolerate a bare string (older callers)
            reply = ChatReply(text=reply)
        pj = parse_verdict_json(reply)
        if isinstance(pj, str):                    # a failure kind, not a verdict
            return AiRatingOutput(failure=pj, domain_reasoning=failure_reason_for(pj, reply))
        rationale = (str(pj.get("rationale") or "")[:200]) or None
        conf = pj.get("confidence")
        conf = float(conf) if isinstance(conf, (int, float)) else None
        if pj.get("abstained") or pj.get("value") in (None, "", "null"):
            # The model read the subject and declined. THIS is an abstention.
            return AiRatingOutput(abstained=True, confidence=conf, domain_reasoning=rationale)
        value = str(pj["value"])
        if value not in scheme.level_values():
            # Never fabricate an out-of-scheme value, and never file it as an abstention
            # either: the model did answer, its answer just is not in the scheme. That is a
            # prompt-compliance defect, and it has to stay visible as one in the ledger.
            return AiRatingOutput(failure="out_of_vocab_value", confidence=conf,
                                  domain_reasoning=failure_reason("out_of_vocab_value",
                                                                  repr(value)))
        return AiRatingOutput(value=value, abstained=False, confidence=conf,
                              domain_reasoning=rationale)


def resolve_ai_connection(config, *, resolve_secret=None) -> Optional[dict]:
    """Resolve ``{shape, endpoint, api_key, max_tokens}`` for the configured AI
    connection, or **None when AI is off**. Shared by every rater factory so the
    connection rules live in one place.

    ``local`` -> OpenAI-compatible, no key, localhost/https only. ``api`` -> provider
    shape + key from the credential store (env escape hatch honored), https only —
    a key is never sent over plaintext. ``resolve_secret(name)`` is injectable for tests.

    ``max_tokens`` is the operator's ``max_reply_tokens`` when set, else the per-mode
    default (local gets headroom for a reasoning model; api stays frugal).
    """
    conn = config.ai_connection
    if not conn.is_enabled():
        return None
    prov = config.ai_provenance
    if conn.mode == "local":
        endpoint = conn.endpoint or _OLLAMA_DEFAULT
        if not _safe_endpoint(endpoint, allow_local=True):
            raise ValueError("local AI endpoint must be http://localhost or an https URL")
        return {"shape": "openai", "endpoint": endpoint, "api_key": None,
                "max_tokens": conn.max_reply_tokens or LOCAL_MAX_REPLY_TOKENS}
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
    return {"shape": shape, "endpoint": endpoint, "api_key": api_key,
            "max_tokens": conn.max_reply_tokens or API_MAX_REPLY_TOKENS}


def build_ai_rater(config, *, poster: Optional[HttpPoster] = None, resolve_secret=None):
    """Construct the configured GRADE/scheme AI rater, or **None when AI is off**."""
    c = resolve_ai_connection(config, resolve_secret=resolve_secret)
    if c is None:
        return None
    return HttpAiRater(shape=c["shape"], endpoint=c["endpoint"],
                       model=config.ai_provenance.model_id, api_key=c["api_key"],
                       poster=poster, timeout=config.ai_connection.request_timeout_s,
                       max_tokens=c["max_tokens"])


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
