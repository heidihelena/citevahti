"""Deterministic passage retrieval over Zotero full text + annotations (step 4).

Read-only: reads from the Zotero local API only and never writes. No OCR, no
hosted embeddings -- lexical, rule-based, reproducible. Locators are preserved
for audit; an unknown location is reported as null, never fabricated.
"""

from .service import PassageRetrievalService
from .source import (
    AnnotationDoc,
    FullTextDoc,
    StaticTextSource,
    TextSource,
    ZoteroApiTextSource,
)

__all__ = [
    "PassageRetrievalService",
    "TextSource",
    "ZoteroApiTextSource",
    "StaticTextSource",
    "FullTextDoc",
    "AnnotationDoc",
]
