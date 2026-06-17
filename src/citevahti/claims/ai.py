"""A real, optional, BLIND ClaimSupportRater over a local or external chat model.

The live claim-support flow (panel / MCP) rates a (claim, candidate) pair against
the controlled support vocabulary. The agent path supplies the rating directly
(``submit_ai_support_rating``); this module lets CiteVahti make its OWN call when
there is no assistant — the standalone / high-volume screener's path. It reuses
the shared transport + connection rules from ``rating.ai``, so off/local/api,
key handling, and endpoint safety behave identically.

Blind by construction (``rate`` never receives the human value) and it ABSTAINS
rather than fabricate an out-of-vocabulary value.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from ..rating.ai import HttpPoster, chat_completion, resolve_ai_connection
from ..schemas.claim_support import SUPPORT_VALUES, FitScores
from .support import SupportAiOutput


class HttpClaimSupportRater:
    name = "http_support_rater"

    def __init__(self, *, shape: str, endpoint: str, model: str,
                 api_key: Optional[str] = None, poster: Optional[HttpPoster] = None,
                 timeout: float = 60.0) -> None:
        if shape not in ("openai", "anthropic"):
            raise ValueError(f"unknown AI shape: {shape!r}")
        self.shape = shape
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self.poster = poster
        self.timeout = timeout

    def rate(self, *, claim, candidate, task_type: str) -> SupportAiOutput:
        prompt = self._build_prompt(claim, candidate)
        text = chat_completion(shape=self.shape, endpoint=self.endpoint, model=self.model,
                               api_key=self.api_key, prompt=prompt, poster=self.poster,
                               timeout=self.timeout)
        return self._parse(text)

    # blinded: only the claim + the paper's own title/abstract are available here
    @staticmethod
    def _build_prompt(claim, candidate) -> str:
        values = sorted(SUPPORT_VALUES)
        title = getattr(candidate, "title", None) or ""
        abstract = getattr(candidate, "abstract", None) or "(no abstract available)"
        return "\n".join([
            "You are a BLINDED second rater for a citation-integrity tool.",
            "Judge how the cited PAPER relates to the CLAIM — its support or contrast, NOT mere",
            "topical relevance. 'overstated' = the paper supports a weaker claim than the one made.",
            f'CLAIM: """{claim.claim_text}"""',
            f'PAPER (title + abstract): """{title}\n\n{abstract}"""',
            f"Choose EXACTLY ONE support value from: {values}.",
            "If the abstract is insufficient to judge, abstain.",
            'Reply with ONLY JSON: {"value":"<one value or null>","abstained":<bool>,'
            '"confidence":<0..1 or null>,"rationale":"<=25 words"}',
        ])

    @staticmethod
    def _parse(text: str) -> SupportAiOutput:
        m = re.search(r"\{.*\}", text or "", re.DOTALL)
        if not m:
            return SupportAiOutput(abstained=True, fit=FitScores(),
                                   domain_reasoning="unparseable AI reply")
        try:
            pj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return SupportAiOutput(abstained=True, fit=FitScores(),
                                   domain_reasoning="unparseable AI reply")
        rationale = (str(pj.get("rationale") or "")[:200]) or None
        conf = pj.get("confidence")
        conf = float(conf) if isinstance(conf, (int, float)) else None
        if pj.get("abstained") or pj.get("value") in (None, "", "null"):
            return SupportAiOutput(abstained=True, confidence=conf, fit=FitScores(),
                                   domain_reasoning=rationale)
        value = str(pj["value"])
        if value not in SUPPORT_VALUES:
            # never fabricate an out-of-vocabulary value -> abstain honestly
            return SupportAiOutput(abstained=True, confidence=conf, fit=FitScores(),
                                   domain_reasoning=f"AI returned out-of-vocab value {value!r}")
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
                                 poster=poster, timeout=config.ai_connection.request_timeout_s)
