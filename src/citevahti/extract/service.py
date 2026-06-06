"""ExtractService: assistive, deterministic field extraction with passages."""

from __future__ import annotations

from typing import Optional

from .. import __version__
from ..retrieval.source import TextSource
from ..retrieval.text import sentence_containing
from ..schemas.common import ItemRef, Provenance
from ..schemas.extract import EXTRACT_FIELDS, ExtractResult, FieldCandidate
from ..schemas.passage import RetrievedPassage
from ..util import config_hash, sha256_hex, utc_now_iso
from .fields import extract_field

FULLTEXT_UNAVAILABLE_REMEDIATION = (
    "No indexed full text was available for this item; extraction is assistive and "
    "reads only what Zotero has indexed (read-only)."
)


class ExtractService:
    def __init__(self, source: TextSource) -> None:
        self.source = source

    def _provenance(self, ref: ItemRef, fields) -> Provenance:
        return Provenance(
            tool="extract", tool_version=__version__, ran_at=utc_now_iso(),
            config_hash=config_hash({"zotero_key": ref.zotero_key, "citekey": ref.citekey,
                                     "fields": list(fields)}),
            sources=[{"kind": "zotero_api", "detail": "indexed full text (read-only)"}],
        )

    def _resolve_subject(self, subject: ItemRef) -> Optional[ItemRef]:
        if subject.zotero_key:
            return subject
        if subject.citekey:
            return self.source.resolve_citekey(subject.citekey, subject.library)
        return None

    def extract(self, subject: ItemRef, fields: Optional[list[str]] = None,
                mode: str = "assistive", require_passage: bool = False,
                library="personal") -> ExtractResult:
        fields = fields or list(EXTRACT_FIELDS)
        prov = self._provenance(subject, fields)
        result = ExtractResult(subject=subject.model_dump(), fields=fields, provenance=prov)
        if mode != "assistive":
            result.warnings.append(f"mode {mode!r} ignored; extract is assistive-only")

        ref = self._resolve_subject(subject)
        if ref is None:
            result.status = "degraded"
            result.error_code = "citekey_unresolved"
            result.remediation = ("Subject has no zotero_key and its citekey did not resolve; "
                                  "extract never invents keys.")
            result.unverifiable_fields = list(fields)
            return result

        doc = self.source.fulltext(ref, None)
        if doc is None or not doc.text.strip():
            result.status = "degraded"
            result.error_code = "full_text_unavailable"
            result.remediation = FULLTEXT_UNAVAILABLE_REMEDIATION
            result.unverifiable_fields = list(fields)
            return result

        text = doc.text
        for field in fields:
            hit = extract_field(field, text)
            if hit is None:
                result.unverifiable_fields.append(field)
                continue
            value, pos = hit
            start, end, quote = sentence_containing(text, pos)
            passage = RetrievedPassage(
                citekey=ref.citekey, zotero_key=ref.zotero_key,
                attachment_key=doc.attachment_key, page=None,
                location=f"char:{start}-{end}", char_start=start, char_end=end,
                quote=quote, text_hash=sha256_hex(quote), retrieval_method="fulltext",
                provenance=prov)
            # A value must be anchored to a passage; require_passage enforces it.
            if require_passage and (passage is None or not passage.quote.strip()):
                result.unverifiable_fields.append(field)
                continue
            result.candidates_by_field[field] = [
                FieldCandidate(field=field, value=value, passage=passage)
            ]
        return result
