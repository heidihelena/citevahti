"""Native desktop window for the CiteVahti review panel — a real app, not a browser.

``citevahti-app`` brings the loopback rating panel up and shows it in the operating
system's own webview (WKWebView on macOS, WebView2 on Windows, WebKitGTK on Linux): a
real application window with an icon, no browser tab, no Chrome. It reuses the exact same
panel HTML/JS — only the shell changes — and keeps every guarantee: loopback-only,
single-user, human-first, the panel server is unchanged.

pywebview is an OPTIONAL dependency (the ``app`` extra). The core install never needs it;
the browser panel (``citevahti start``) and the chat/MCP surface are unaffected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .rootcfg import default_root
from .start import launch_panel

_TITLE = "CiteVahti — manuscript citation review"


def _import_webview():
    """Import pywebview, or raise a clear, actionable error (no terminal jargon)."""
    try:
        import webview  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only when the extra is absent
        raise RuntimeError(
            "the desktop window needs pywebview — install it with: "
            "pip install 'citevahti[app]'") from exc
    return webview


def _icon_path() -> Optional[str]:
    """The packaged window/app icon if it ships alongside the install, else None."""
    p = Path(__file__).resolve().parent / "panel" / "web" / "apple-touch-icon.png"
    return str(p) if p.is_file() else None


def run_app(root: Optional[str] = None, *, host: str = "127.0.0.1", port: int = 0,
            webview=None) -> int:
    """Open the panel in a native OS webview window; blocks until it closes.

    Starts the panel server on an ephemeral loopback port (``port=0``) with NO browser,
    then hands the URL to the native webview. ``webview`` is injectable for tests; in
    production it is the pywebview module. Returns a process exit code.
    """
    root = root or default_root()
    res = launch_panel(root, port=port, host=host, open_browser=False)
    if res["status"] == "refused_non_loopback":
        print("refusing a non-loopback host: the panel is loopback-only by design.")
        return 2
    if res["status"] == "port_conflict":
        print(f"a non-CiteVahti service already owns {res['url']}; close it and retry.")
        return 2

    wv = webview or _import_webview()
    wv.create_window(_TITLE, res["url"], width=1180, height=820, min_size=(900, 600))
    icon = _icon_path()
    try:
        wv.start(icon=icon) if icon else wv.start()   # icon honoured where the backend supports it
    except TypeError:
        wv.start()                                    # older pywebview: no icon kwarg
    return 0


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="citevahti-app",
        description="Open the CiteVahti review panel in a native desktop window (no browser).")
    parser.add_argument("--root", default=None,
                        help="project root holding .citevahti/ (default: $CITEVAHTI_ROOT, "
                             "the cwd ledger, the last-used root, or your home folder)")
    args = parser.parse_args(argv)
    return run_app(args.root)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
