"""The Better BibTeX seam for `bib_sync`: resolve + export.

`BibProvider` is the interface the service depends on so tests can run fully
offline. `BbtBibProvider` is the live implementation; `StaticBibProvider` is a
deterministic in-memory double.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from ..bbt.client import BbtClient, BbtError, BbtUnavailable
from ..probe.client import HttpClient
from ..schemas.config import Endpoints

# BBT translator names per export format (used by the live provider only).
_TRANSLATORS = {
    "bibtex": "Better BibTeX",
    "biblatex": "Better BibLaTeX",
    "csl-json": "Better CSL JSON",
}


class BibProviderUnavailable(Exception):
    code = "bbt_unavailable"


@runtime_checkable
class BibProvider(Protocol):
    def resolve_many(self, citekeys: list[str]) -> dict[str, bool]: ...

    def export(self, citekeys: list[str], export_format: str) -> str: ...


class BbtBibProvider:
    """Live provider backed by the Better BibTeX JSON-RPC endpoint."""

    def __init__(self, http: HttpClient, endpoints: Optional[Endpoints] = None) -> None:
        self.bbt = BbtClient(http, endpoints)

    def resolve_many(self, citekeys: list[str]) -> dict[str, bool]:
        out: dict[str, bool] = {}
        for key in citekeys:
            try:
                out[key] = self.bbt.resolve_citekey(key)
            except BbtUnavailable as exc:
                raise BibProviderUnavailable(str(exc)) from exc
        return out

    def export(self, citekeys: list[str], export_format: str) -> str:
        translator = _TRANSLATORS.get(export_format, _TRANSLATORS["bibtex"])
        try:
            result = self.bbt.jsonrpc("item.export", [citekeys, translator])
        except BbtUnavailable as exc:
            raise BibProviderUnavailable(str(exc)) from exc
        except BbtError as exc:
            raise BibProviderUnavailable(f"BBT export error: {exc}") from exc
        if isinstance(result, list):  # some BBT versions return [body, ...]
            result = result[0] if result else ""
        return str(result)


class StaticBibProvider:
    """In-memory provider for tests/offline use.

    ``known`` maps citekey -> a bibliography fragment. Unknown keys do not
    resolve. If ``available`` is False, every call raises
    ``BibProviderUnavailable`` to simulate BBT being absent.
    """

    def __init__(self, known: dict[str, str], available: bool = True) -> None:
        self.known = dict(known)
        self.available = available

    def resolve_many(self, citekeys: list[str]) -> dict[str, bool]:
        if not self.available:
            raise BibProviderUnavailable("Better BibTeX is not available")
        return {k: (k in self.known) for k in citekeys}

    def export(self, citekeys: list[str], export_format: str) -> str:
        if not self.available:
            raise BibProviderUnavailable("Better BibTeX is not available")
        if export_format == "csl-json":
            import json
            items = [{"id": k} for k in citekeys if k in self.known]
            return json.dumps(items, indent=2)
        return "\n".join(self.known[k] for k in citekeys if k in self.known)
