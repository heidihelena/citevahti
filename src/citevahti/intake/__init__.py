"""PubMed intake staging + manual import (step 5).

Stages pre-decision candidate records into ``.citevahti/intake/``. Never imports
into Zotero, never decides inclusion, never touches the evidence map.
"""

from .dedupe import (
    LibraryDedupeIndex,
    StaticLibraryIndex,
    ZoteroLibraryIndex,
    make_record_id,
    normalize_doi,
    normalize_pmid,
)
from .service import IntakeService

__all__ = [
    "IntakeService",
    "LibraryDedupeIndex",
    "StaticLibraryIndex",
    "ZoteroLibraryIndex",
    "normalize_doi",
    "normalize_pmid",
    "make_record_id",
]
