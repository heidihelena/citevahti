"""Explicit, user-initiated update check against PyPI.

This is the read-only core of CiteVahti's "automatic updates" story. It is **opt-in
and user-initiated** — nothing here runs on launch or on a timer, so it does not
weaken the local-first / no-telemetry promise: it makes a single outbound request to
the public PyPI JSON API **only when the user (or their agent) asks**, sends no user
data, and never installs anything. The honest disclosure (it contacts ``pypi.org``)
lives in the CLI help, the agent tool docstring, and ``docs/STATUS.md``.

It exists because the painful failure mode is silent staleness: a user installs a new
``.mcpb`` / desktop app but an old build keeps running, with no signal. ``status``
already reports the *running* version (0.34.3); this reports whether a *newer* one is
published, so the two together answer "am I up to date?".
"""

from __future__ import annotations

from typing import Any, Optional

PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"


def _parse(version: str) -> tuple[int, ...]:
    """Best-effort numeric version tuple for comparison.

    CiteVahti ships clean ``MAJOR.MINOR.PATCH`` releases, so a tuple-of-ints compare is
    exact. For anything unexpected (a pre-release suffix, say) we read the leading digits
    of each dotted part and stop at the first non-digit — so ``0.35.0rc1`` → ``(0, 35, 0)``.
    The caller treats an unparseable result conservatively (never claims an update it
    isn't sure about)."""
    parts: list[int] = []
    for part in version.strip().split("."):
        digits = ""
        for ch in part:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def check_update(*, http: Any = None, current: Optional[str] = None,
                 package: str = "citevahti", timeout: float = 4.0) -> dict:
    """Ask PyPI whether a newer ``package`` release exists. Read-only, never installs.

    Returns a dict with: ``checked`` (did we get an answer), ``current``, ``latest``,
    ``update_available``, and a plain-language ``message`` safe to show a non-technical
    user. Any network/parse problem is reported calmly via ``checked=False`` — this
    function never raises, because "couldn't check" must not look like "something broke".

    ``http`` is an injectable :class:`~citevahti.probe.client.HttpClient` so the test
    suite stays fully offline; production uses the default httpx-backed client.
    """
    from . import __version__

    cur = current or __version__
    if http is None:
        from .probe import HttpxClient
        http = HttpxClient(timeout=timeout)

    url = PYPI_JSON_URL.format(package=package)
    try:
        resp = http.get(url, headers={"Accept": "application/json"})
    except Exception as exc:  # ProbeTransportError, or anything the client raises
        return {"checked": False, "current": cur, "latest": None, "update_available": False,
                "message": f"Couldn't reach PyPI to check for updates ({exc}). "
                           f"You're running {package} {cur}."}

    if getattr(resp, "status_code", None) != 200:
        code = getattr(resp, "status_code", "?")
        return {"checked": False, "current": cur, "latest": None, "update_available": False,
                "message": f"PyPI returned HTTP {code} when checking for updates. "
                           f"You're running {package} {cur}."}

    try:
        latest = ((resp.json() or {}).get("info") or {}).get("version")
    except Exception:
        latest = None
    if not latest:
        return {"checked": False, "current": cur, "latest": None, "update_available": False,
                "message": f"PyPI didn't report a version. You're running {package} {cur}."}

    newer = _parse(str(latest)) > _parse(cur)
    if newer:
        message = (f"A newer version is available: {package} {latest} (you have {cur}). "
                   f"Update with:  pip install -U {package}   ·   or reinstall the desktop "
                   f"app / the .mcpb extension in Claude Desktop (remove the old one first, "
                   f"then add the newest — it caches the previous build).")
    else:
        message = f"You're up to date — {package} {cur} is the latest release on PyPI."

    return {"checked": True, "current": cur, "latest": str(latest),
            "update_available": bool(newer), "message": message}
