"""The panel's static assets must be complete and self-consistent.

Two ways the panel ships blank or half-broken:
  * an asset named in the ``_STATIC`` allow-list doesn't exist in ``WEB_DIR``
    (the server would 404 a file it promises to serve), or
  * ``index.html`` references a local script/stylesheet that is NOT on the
    allow-list (the page loads but that file 404s — the sibling bug of the
    frozen-binary blank panel fixed in desktop-extension/build-binary.sh).

Fully offline: reads package files only, no server is started.
"""

from __future__ import annotations

import re

from citevahti.panel.server import _STATIC, WEB_DIR

_LOCAL_REF = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']""")


def _local_refs(html: str) -> set[str]:
    """Local src/href targets in the page, as server paths ("/styles.css")."""
    refs = set()
    for target in _LOCAL_REF.findall(html):
        if target.startswith(("http://", "https://", "//", "#", "mailto:", "data:")):
            continue
        refs.add("/" + target.lstrip("/"))
    return refs


def test_every_allowlisted_asset_exists_on_disk():
    missing = sorted(name for name in set(_STATIC.values())
                     if not (WEB_DIR / name).is_file())
    assert not missing, f"_STATIC promises files absent from {WEB_DIR}: {missing}"


def test_every_local_ref_in_index_html_is_allowlisted():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    refs = _local_refs(html)
    assert refs, "expected index.html to reference local scripts/styles"
    unserved = sorted(refs - set(_STATIC))
    assert not unserved, f"index.html references assets the server won't serve: {unserved}"
