"""`cite`: render a citation for a citekey -- never inventing keys.

Contract (step 2):
  * a bare citekey or an ItemRef carrying a citekey is accepted;
  * the citekey MUST resolve against Better BibTeX or `cite` fails;
  * an ItemRef without a citekey fails -- `cite` never invents one;
  * if Better BibTeX is absent, `cite` degrades honestly with remediation.
"""

from __future__ import annotations

from typing import Optional, Union

from . import __version__
from .bbt.client import BbtClient, BbtError, BbtUnavailable
from .probe.client import HttpClient
from .probe.probe import CapabilityReport
from .schemas.common import ItemRef, Provenance, ToolResult
from .schemas.config import Endpoints
from .util import config_hash, utc_now_iso

BBT_UNAVAILABLE_REMEDIATION = (
    "Better BibTeX is unavailable; cannot resolve citekeys. Install/enable the "
    "Better BibTeX add-on in Zotero (JSON-RPC at /better-bibtex/json-rpc)."
)

CiteTarget = Union[str, ItemRef]


def _format_citation(citekey: str, fmt: str) -> str:
    if fmt == "pandoc":
        return f"[@{citekey}]"
    if fmt == "latex":
        return f"\\cite{{{citekey}}}"
    if fmt == "citekey":
        return citekey
    raise ValueError(f"unsupported cite format {fmt!r}")


class CiteService:
    def __init__(self, http: HttpClient, endpoints: Optional[Endpoints] = None,
                 capability: Optional[CapabilityReport] = None) -> None:
        self.bbt = BbtClient(http, endpoints)
        self.endpoints = endpoints or Endpoints()
        self.capability = capability

    def _provenance(self, citekey: str) -> Provenance:
        return Provenance(
            tool="cite", tool_version=__version__, ran_at=utc_now_iso(),
            config_hash=config_hash({"bbt": self.endpoints.bbt_jsonrpc, "citekey": citekey}),
            sources=[{"kind": "bbt", "detail": self.endpoints.bbt_jsonrpc}],
        )

    def cite(self, target: CiteTarget, format: str = "pandoc") -> ToolResult:
        # Extract a candidate citekey WITHOUT inventing one.
        if isinstance(target, ItemRef):
            citekey = target.citekey
            if not citekey:
                return ToolResult.failure(
                    "no_citekey",
                    "cite: ItemRef has no citekey and cite never invents one; "
                    "resolve the citekey first.",
                )
        else:
            citekey = str(target).strip()
            if not citekey:
                return ToolResult.failure("no_citekey", "cite: empty citekey")

        # Honest degradation when BBT is known-unavailable.
        if self.capability is not None and not self.capability.available("bbt_ready"):
            return ToolResult.failure("bbt_unavailable",
                                      "cite: Better BibTeX unavailable",
                                      BBT_UNAVAILABLE_REMEDIATION)
        try:
            resolved = self.bbt.resolve_citekey(citekey)
        except BbtUnavailable:
            return ToolResult.failure("bbt_unavailable",
                                      "cite: Better BibTeX unavailable",
                                      BBT_UNAVAILABLE_REMEDIATION)
        except BbtError as exc:
            return ToolResult.failure("bbt_error", f"cite: Better BibTeX error: {exc}")

        if not resolved:
            return ToolResult.failure(
                "unresolved_citekey",
                f"cite: citekey {citekey!r} does not resolve to any item; "
                "cite never invents keys.",
            )
        try:
            citation = _format_citation(citekey, format)
        except ValueError as exc:
            return ToolResult.failure("bad_format", str(exc))
        return ToolResult(ok=True, data={"citekey": citekey, "format": format,
                                         "citation": citation},
                          provenance=self._provenance(citekey))
