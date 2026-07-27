"""A real, optional, BLIND ClaimSupportRater over a local or external chat model.

The live claim-support flow (panel / MCP) rates a (claim, candidate) pair against
the controlled support vocabulary. The agent path supplies the rating directly
(``submit_ai_support_rating``); this module lets CiteVahti make its OWN call when
there is no assistant — the standalone / high-volume screener's path. It reuses
the shared transport + connection rules from ``rating.ai``, so off/local/api,
key handling, and endpoint safety behave identically.

Blind by construction (``rate`` never receives the human value) and it never fabricates
an out-of-vocabulary value. When no usable verdict comes back it records a typed
**failure** (see schemas/rating.py::AI_FAILURE_KINDS) — never an abstention, which is
reserved for the model reading the pair and declining to rate it.
"""

from __future__ import annotations

from typing import Optional

from ..rating.ai import (
    LOCAL_MAX_REPLY_TOKENS,
    ChatReply,
    HttpPoster,
    chat_reply,
    failure_reason,
    failure_reason_for,
    parse_verdict_json,
    resolve_ai_connection,
)
from ..schemas.claim_support import SUPPORT_VALUES, FitScores
from .support import SupportAiOutput


class HttpClaimSupportRater:
    name = "http_support_rater"

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
        self.poster = poster
        self.timeout = timeout
        self.max_tokens = max_tokens

    def rate(self, *, claim, candidate, task_type: str) -> SupportAiOutput:
        prompt = self._build_prompt(claim, candidate)
        reply = chat_reply(shape=self.shape, endpoint=self.endpoint, model=self.model,
                           api_key=self.api_key, prompt=prompt, poster=self.poster,
                           timeout=self.timeout, max_tokens=self.max_tokens)
        return self._parse(reply)

    # blinded: only the claim + the paper's own title/abstract are available here
    @staticmethod
    def _build_prompt(claim, candidate) -> str:
        from ..schemas.claim_support import SUPPORT_DEFINITIONS
        title = getattr(candidate, "title", None) or ""
        abstract = getattr(candidate, "abstract", None) or "(no abstract available)"
        defs = "\n".join(f"  - {v}: {d}" for v, d in SUPPORT_DEFINITIONS.items())
        return "\n".join([
            "You are a BLINDED second rater for a citation-integrity tool.",
            "Decide whether the cited PAPER supports the CLAIM, using ONLY the paper's title and",
            "abstract below. Judge SUPPORT (does this evidence back this specific claim?), not mere",
            "topical relevance. Check the claim's population, intervention/exposure, and outcome are",
            "actually addressed by the paper — a mismatch on any of them means it is not full support.",
            "",
            f'CLAIM: """{claim.claim_text}"""',
            f'PAPER (title + abstract): """{title}\n\n{abstract}"""',
            "",
            "Choose EXACTLY ONE support value. Definitions:",
            defs,
            "",
            "Use 'overstated' when the paper supports a weaker version of the claim.",
            "Use 'unclear' when the text IS on-topic but does not settle THIS claim. Wording such as",
            "'not established', 'inconclusive', 'uncertain', 'mixed', 'limited evidence', 'debated',",
            "or 'an open question' means 'unclear' — NOT 'contradicts': text saying the evidence does",
            "not establish X leaves X undecided, it does not assert X is false. Choose 'unclear' too",
            "when the text addresses only a related but different point and leaves this specific",
            "claim unresolved. 'unclear' IS a rating — prefer it over abstaining whenever there is",
            "text to read.",
            "Set abstained=true ONLY when there is NO text to rate (title and abstract missing or",
            "unreadable) or you cannot form a reply. Abstention is a non-rating, not a verdict.",
            'Reply with ONLY JSON: {"value":"<one value or null>","abstained":<bool>,'
            '"confidence":<0..1 or null>,"rationale":"<=25 words"}',
        ])

    @staticmethod
    def _parse(reply) -> SupportAiOutput:
        if isinstance(reply, str):                 # tolerate a bare string (older callers)
            reply = ChatReply(text=reply)
        pj = parse_verdict_json(reply)
        if isinstance(pj, str):                    # a failure kind, not a verdict
            # No verdict came back. This is a FAILURE, not an abstention: the model never
            # judged the pair, so the ledger must not record it as the model declining.
            return SupportAiOutput(failure=pj, fit=FitScores(),
                                   domain_reasoning=failure_reason_for(pj, reply))
        rationale = (str(pj.get("rationale") or "")[:200]) or None
        conf = pj.get("confidence")
        conf = float(conf) if isinstance(conf, (int, float)) else None
        if pj.get("abstained") or pj.get("value") in (None, "", "null"):
            # The model read the pair and declined. THIS is an abstention.
            return SupportAiOutput(abstained=True, confidence=conf, fit=FitScores(),
                                   domain_reasoning=rationale)
        value = str(pj["value"])
        if value not in SUPPORT_VALUES:
            # Never fabricate an out-of-vocabulary value — and never file it as an
            # abstention either. The model DID answer; the answer is off-vocabulary, which
            # is a prompt-compliance defect that has to stay visible as one in the ledger.
            return SupportAiOutput(failure="out_of_vocab_value", confidence=conf,
                                   fit=FitScores(),
                                   domain_reasoning=failure_reason("out_of_vocab_value",
                                                                   repr(value)))
        return SupportAiOutput(value=value, abstained=False, confidence=conf,
                               fit=FitScores(), domain_reasoning=rationale)


def build_support_ai_rater(config, *, poster: Optional[HttpPoster] = None, resolve_secret=None):
    """The configured claim-support rater, or **None when AI is off**. Connection rules
    (off/local/api, key, endpoint safety) are shared with the GRADE rater."""
    c = resolve_ai_connection(config, resolve_secret=resolve_secret)
    if c is None:
        return None
    return HttpClaimSupportRater(shape=c["shape"], endpoint=c["endpoint"],
                                 model=config.ai_provenance.model_id, api_key=c["api_key"],
                                 poster=poster, timeout=config.ai_connection.request_timeout_s,
                                 max_tokens=c["max_tokens"])
