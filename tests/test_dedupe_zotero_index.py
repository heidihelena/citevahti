"""ZoteroLibraryIndex (the live, zot_search-backed dedupe index).

Regression guard: library dedupe must search Zotero with the NORMALIZED DOI, so
the same DOI written with a `https://doi.org/` / `doi:` prefix or in upper case
still finds an item stored in its canonical form. Searching the raw string was a
silent dedupe miss (a duplicate would be reported absent).
"""

from citevahti.intake.dedupe import ZoteroLibraryIndex


class _Res:
    def __init__(self, ok, data):
        self.ok = ok
        self.data = data


class _RecordingZotero:
    """Fake zot_search that records the query it was asked to run."""

    def __init__(self, items):
        self._items = items
        self.queries = []

    def zot_search(self, query, library="personal"):
        self.queries.append(query)
        return _Res(True, list(self._items))


def test_contains_searches_zotero_with_normalized_doi():
    # Library stores the canonical (normalized) DOI.
    zot = _RecordingZotero([{"DOI": "10.1234/abc"}])
    idx = ZoteroLibraryIndex(zot)

    # Manuscript DOI arrives prefixed + upper-case (a different raw string).
    assert idx.contains(pmid=None, doi="https://doi.org/10.1234/ABC") is True

    # The contract: the Zotero search used the normalized form, not the raw URL.
    assert zot.queries == ["10.1234/abc"]


def test_contains_false_when_doi_absent_from_library():
    zot = _RecordingZotero([{"DOI": "10.9999/other"}])
    idx = ZoteroLibraryIndex(zot)
    assert idx.contains(pmid=None, doi="10.1234/abc") is False
    assert zot.queries == ["10.1234/abc"]


def test_contains_degrades_to_none_when_zotero_read_fails():
    class _Failing:
        def zot_search(self, query, library="personal"):
            return _Res(False, None)

    idx = ZoteroLibraryIndex(_Failing())
    assert idx.contains(pmid=None, doi="10.1234/abc") is None
