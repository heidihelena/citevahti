"""PassageRetrievalService: deterministic candidate-passage retrieval."""

from __future__ import annotations

from typing import Optional

from .. import __version__
from ..schemas.common import ItemRef, Provenance
from ..schemas.passage import PassageRetrievalResult, RetrievedPassage
from ..util import config_hash, sha256_hex, utc_now_iso
from .source import AnnotationDoc, FullTextDoc, TextSource
from .text import coverage_score, segment_sentences

FULLTEXT_UNAVAILABLE_REMEDIATION = (
    "No indexed full text or annotations were available for this item. Ensure the "
    "PDF is attached and indexed in Zotero (read-only; CiteVahti never writes)."
)
CITEKEY_UNRESOLVED_REMEDIATION = (
    "The citekey did not resolve to a Zotero item via Better BibTeX. cite/extract "
    "never invent keys; check the key or that Better BibTeX is running."
)

_DEFAULT_MAX = 5


class PassageRetrievalService:
    def __init__(self, source: TextSource) -> None:
        self.source = source

    def _provenance(self, ref: ItemRef, query: Optional[str], method_note: str) -> Provenance:
        return Provenance(
            tool="passage_retrieval", tool_version=__version__, ran_at=utc_now_iso(),
            config_hash=config_hash({"zotero_key": ref.zotero_key, "citekey": ref.citekey,
                                     "query": query, "method": method_note}),
            sources=[{"kind": "zotero_api", "detail": "fulltext + annotations (read-only)"}],
        )

    def _resolve(self, citekey, zotero_key, item, library) -> tuple[Optional[ItemRef], Optional[str]]:
        if item is not None:
            return item, None
        if zotero_key:
            return ItemRef(zotero_key=zotero_key, library=library, citekey=citekey), None
        if citekey:
            ref = self.source.resolve_citekey(citekey, library)
            if ref is None:
                return None, "citekey_unresolved"
            return ref, None
        return None, "no_subject"

    def retrieve(self, *, citekey: Optional[str] = None, zotero_key: Optional[str] = None,
                 item: Optional[ItemRef] = None, attachment_key: Optional[str] = None,
                 query: Optional[str] = None, max_passages: int = _DEFAULT_MAX,
                 library="personal") -> PassageRetrievalResult:
        ref, err = self._resolve(citekey, zotero_key, item, library)
        prov = self._provenance(ref or ItemRef(zotero_key=zotero_key or "", citekey=citekey),
                                query, "retrieve")
        if err == "citekey_unresolved":
            return PassageRetrievalResult(status="degraded", error_code="citekey_unresolved",
                                          remediation=CITEKEY_UNRESOLVED_REMEDIATION,
                                          citekey=citekey, provenance=prov)
        if ref is None:
            return PassageRetrievalResult(status="degraded", error_code="no_subject",
                                          remediation="Provide an item, zotero_key, or citekey.",
                                          provenance=prov)

        doc = self.source.fulltext(ref, attachment_key)
        annots = self.source.annotations(ref, attachment_key)
        if (doc is None or not doc.text.strip()) and not annots:
            return PassageRetrievalResult(status="degraded", error_code="full_text_unavailable",
                                          remediation=FULLTEXT_UNAVAILABLE_REMEDIATION,
                                          citekey=ref.citekey or citekey, zotero_key=ref.zotero_key,
                                          provenance=prov)

        passages: list[RetrievedPassage] = []
        if doc is not None and doc.text.strip():
            passages += self._fulltext_passages(ref, doc, query, prov)
        passages += self._annotation_passages(ref, annots, query, prov)

        if query:
            passages = [p for p in passages if (p.score or 0) > 0]
        passages.sort(key=lambda p: (-(p.score or 0.0), p.char_start if p.char_start is not None else 1 << 30))
        passages = passages[:max_passages]

        return PassageRetrievalResult(status="ok", citekey=ref.citekey or citekey,
                                      zotero_key=ref.zotero_key, passages=passages,
                                      provenance=prov)

    # ---- builders --------------------------------------------------------
    def _fulltext_passages(self, ref, doc: FullTextDoc, query, prov) -> list[RetrievedPassage]:
        out: list[RetrievedPassage] = []
        for start, end, quote in segment_sentences(doc.text):
            score = coverage_score(query, quote) if query else None
            out.append(RetrievedPassage(
                citekey=ref.citekey, zotero_key=ref.zotero_key,
                attachment_key=doc.attachment_key,
                page=None, location=f"char:{start}-{end}",
                char_start=start, char_end=end, quote=quote,
                text_hash=sha256_hex(quote), retrieval_method="fulltext",
                score=score, provenance=prov))
        return out

    def _annotation_passages(self, ref, annots: list[AnnotationDoc], query, prov) -> list[RetrievedPassage]:
        out: list[RetrievedPassage] = []
        for a in annots:
            text = a.text or (a.comment or "")
            if not text.strip():
                continue
            location = f"pageIndex:{a.page_index}" if a.page_index is not None else None
            score = coverage_score(query, text) if query else None
            out.append(RetrievedPassage(
                citekey=ref.citekey, zotero_key=ref.zotero_key,
                attachment_key=a.attachment_key,
                page=a.page_label, location=location,
                quote=text.strip(), text_hash=sha256_hex(text.strip()),
                retrieval_method="annotation", score=score, provenance=prov))
        return out
