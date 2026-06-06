"""Corpus snapshots + diffs (step 6). Read-only; never writes to Zotero."""

from .diff import CorpusDiffService
from .snapshot import SnapshotService
from .source import (
    CorpusItem,
    CorpusSource,
    StaticCorpusSource,
    ZoteroCorpusSource,
    metadata_hash,
)

__all__ = [
    "SnapshotService",
    "CorpusDiffService",
    "CorpusSource",
    "CorpusItem",
    "StaticCorpusSource",
    "ZoteroCorpusSource",
    "metadata_hash",
]
