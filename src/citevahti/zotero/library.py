"""Library selector -> Zotero local-API base path.

The local API mirrors the Zotero Web API v3 path layout:
  - personal             -> ``users/0``
  - group {group_id}     -> ``groups/<id>``
  - all                  -> expanded to the user library + every group
A bare ``group`` (no id) is ambiguous for a read and is rejected.
"""

from __future__ import annotations

from typing import Any

from ..schemas.common import GroupLibrary, LibrarySelector


class LibrarySelectorError(Exception):
    code = "library_selector"


def coerce_library(library: Any) -> LibrarySelector:
    """Accept a string, a GroupLibrary, or a ``{"kind":"group","group_id":...}`` dict."""
    if isinstance(library, GroupLibrary):
        return library
    if isinstance(library, dict):
        return GroupLibrary(**library)
    if library in ("personal", "group", "all"):
        return library
    raise LibrarySelectorError(f"unknown library selector {library!r}")


def base_path(library: Any) -> str:
    """Return the single base path for ``library`` (not valid for ``all``)."""
    library = coerce_library(library)
    if library == "personal":
        return "users/0"
    if isinstance(library, GroupLibrary):
        return f"groups/{library.group_id}"
    if library == "group":
        raise LibrarySelectorError(
            "a 'group' library requires a group_id; pass "
            '{"kind": "group", "group_id": "<id>"}'
        )
    # library == "all"
    raise LibrarySelectorError("use bases_for() to expand the 'all' selector")


def bases_for(library: Any, group_ids: list[str] | None = None) -> list[str]:
    """Expand ``library`` to the list of base paths to query.

    For ``all`` the caller supplies the discovered ``group_ids`` (the personal
    library is always included).
    """
    library = coerce_library(library)
    if library == "all":
        bases = ["users/0"]
        bases += [f"groups/{gid}" for gid in (group_ids or [])]
        return bases
    return [base_path(library)]
