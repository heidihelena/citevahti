/* CiteVahti panel — backend liveness watchdog (the page heals itself).
 *
 * The engine behind this page can be replaced underneath it: the desktop app's
 * supervisor restarts a wedged sidecar, and the already-loaded page then LOOKS alive
 * while every call hits a dead socket or a foreign session (fresh CSRF) — which reads
 * as "the panel ignores everything I do" (seen live 2026-07-02). This watchdog polls
 * the cheap /api/ping endpoint:
 *   - connection lost           → after 2 misses, a "reconnecting" overlay says so;
 *   - backend answers again
 *       with the SAME boot_id   → overlay clears (a blip, same process);
 *       with a NEW boot_id      → the page reloads itself (new process: new CSRF
 *                                 session, possibly new state — a stale page must not
 *                                 keep driving it).
 *
 * Classic script with no dependencies, loaded before the app modules on purpose: it
 * must keep working even if a later script fails. If the page itself is dead (frozen
 * webview), no JS runs — that layer is the app shell's reload-on-restart, not ours. */
(function () {
  var INTERVAL_MS = 5000, MISSES_BEFORE_OVERLAY = 2;
  var bootId = null, misses = 0, overlay = null;

  function showOverlay() {
    if (overlay) return;
    overlay = document.createElement("div");
    overlay.id = "reconnectOverlay";
    overlay.setAttribute("role", "alert");
    overlay.style.cssText =
      "position:fixed;inset:0;z-index:99999;display:flex;align-items:center;" +
      "justify-content:center;background:rgba(17,21,26,.78);color:#fff;" +
      "font:500 15px/1.5 system-ui,sans-serif;text-align:center;padding:24px;";
    overlay.innerHTML =
      '<div><div style="font-size:17px;margin-bottom:6px">Connection to CiteVahti lost — reconnecting…</div>' +
      '<div style="opacity:.85">Your claims and ratings are safe on disk. ' +
      "If this doesn't clear in a minute, quit and reopen the app.</div></div>";
    document.body.appendChild(overlay);
  }
  function hideOverlay() { if (overlay) { overlay.remove(); overlay = null; } }

  function beat() {
    return fetch("/api/ping", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (b) {
        misses = 0;
        if (!b || b.ok !== true || !b.boot_id) return;  // not a CiteVahti backend — not ours to judge
        if (bootId === null) { bootId = b.boot_id; hideOverlay(); return; }
        if (b.boot_id !== bootId) { __cvReconnect._reload(); return; }
        hideOverlay();
      })
      .catch(function () {
        misses += 1;
        if (misses >= MISSES_BEFORE_OVERLAY) showOverlay();
      });
  }

  // Exposed for the frontend tests (classic-script convention): beat() is driven
  // directly instead of waiting on the interval, and _reload is stubbed because
  // jsdom cannot navigate.
  window.__cvReconnect = { beat: beat, _reload: function () { location.reload(); } };

  beat();
  setInterval(beat, INTERVAL_MS);
})();
