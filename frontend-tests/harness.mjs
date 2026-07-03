/* Test harness for the CiteVahti loopback panel.
 *
 * Boots the REAL served app (the production index.html skeleton + the concatenated panel
 * scripts) inside a jsdom window, with a routable fetch mock. Because the app wires its own
 * event listeners, tests interact through the DOM the way a user does (click a button, read
 * what appears) — not by poking internals. A small exposed set of PURE functions is provided
 * for unit tests; everything else is exercised via the DOM. */
import { JSDOM } from "jsdom";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WEB = path.resolve(HERE, "..", "src", "citevahti", "panel", "web");

// the exact load order index.html uses
const FILES = ["reconnect.js", "state.js", "util.js", "api.js", "modal.js", "feedback.js", "events.js", "card.js",
  "card-phases.js", "card-edit.js", "review-actions.js", "connect.js", "search.js", "workspace.js",
  "manuscripts.js", "checks.js", "evidence-map.js", "atlas.js", "output.js", "settings.js", "prompts.js", "app.js"];

// pure / output functions exposed for unit tests (their string output is user-facing)
const EXPOSE = ["relTime", "projectName", "humanEvent", "citeOf", "claimTypeLabel",
  "savedToFolderCard", "isDecided", "fitWord"];

function bundle() {
  const src = FILES.map((f) => fs.readFileSync(path.join(WEB, f), "utf8")).join("\n");
  return src + `\n;window.__t = { ${EXPOSE.join(", ")} };`;
}

/* Routable fetch mock. `routes` maps "METHOD /path" (or just "/path") to a payload, a function
 * (opts)=>payload, or {__status, __body}. Unmatched calls return {} with 200 so boot() never
 * trips on a call a test didn't set up. Every call is recorded in `log`. */
export function makeFetch(routes, log) {
  return async (url, opts = {}) => {
    const method = (opts.method || "GET").toUpperCase();
    const p = String(url).split("?")[0];
    log.push(`${method} ${p}`);
    let r = `${method} ${p}` in routes ? routes[`${method} ${p}`] : (p in routes ? routes[p] : {});
    if (typeof r === "function") r = r(opts);
    const status = (r && r.__status) || 200;
    const body = (r && r.__body !== undefined) ? r.__body : (r || {});
    return { ok: status < 400, status, json: async () => body };
  };
}

const DEFAULTS = () => ({
  "GET /api/ping": { ok: true, boot_id: "test-boot" },
  "GET /api/session": { csrf_token: "test-token" },
  "GET /api/context": { root: "/x/demo", claim_total: 0, manuscripts_dir: "/x/demo/manuscripts" },
  "GET /api/health": { connections: {}, can_write: [], version: "9.9.9" },
  "GET /api/audit/verify": { intact: true, entries: 5 },
  "GET /api/ledgers": { active: "/x/demo", ledgers: [] },
  "GET /api/next": { next: null },
  "GET /api/manuscripts": { manuscripts: [], manuscripts_dir: "/x/demo/manuscripts" },
  "GET /api/triage": { needs_attention: 0, total: 0, items: [] },
});

// jsdom windows keep live timers (toast auto-dismiss, the claims poll). node --test runs
// each file in its own process; closeAll() in a file-level after() lets that process exit
// (Node 20 has no --test-force-exit).
const _windows = [];
export function closeAll() {
  for (const w of _windows.splice(0)) { try { w.stop && w.stop(); w.close(); } catch { /* closed */ } }
}

export async function mount(routes = {}) {
  const html = fs.readFileSync(path.join(WEB, "index.html"), "utf8");
  const dom = new JSDOM(html, { runScripts: "dangerously", url: "http://localhost/", pretendToBeVisual: true });
  const { window } = dom;
  _windows.push(window);
  // Drop the per-file <script src> tags (jsdom doesn't fetch them anyway) and inject the
  // concatenated bundle below — done via the DOM, not string-munging, so it's exact.
  window.document.querySelectorAll("script[src]").forEach((s) => s.remove());
  const log = [];
  window.fetch = makeFetch({ ...DEFAULTS(), ...routes }, log);
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  window.print = () => {};
  window.Element.prototype.scrollIntoView = function () {};   // jsdom has no layout
  window.getSelection = () => ({ rangeCount: 0, isCollapsed: true, toString: () => "" });
  window.open = () => ({ document: { write() {}, close() {} }, focus() {}, print() {} });
  const s = window.document.createElement("script");
  s.textContent = bundle();
  window.document.body.appendChild(s);            // executes → app boots + wires listeners

  const h = {
    dom, window, doc: window.document, log,
    t: () => window.__t,                                       // exposed pure functions
    run: (code) => window.eval(code),
    text: () => window.document.body.textContent.replace(/\s+/g, " ").trim(),
    $: (sel) => window.document.querySelector(sel),
    $$: (sel) => [...window.document.querySelectorAll(sel)],
    click: (el) => el && el.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true })),
    press: (key, opts = {}) => window.document.dispatchEvent(
      new window.KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...opts })),
    byText: (re) => [...window.document.querySelectorAll("button, a, summary")]
      .find((b) => re.test((b.textContent || "").trim())),
    byAct: (act) => window.document.querySelector(`[data-act="${act}"]`),
    surface: () => window.eval("state.surface"),
    async waitFor(predicate, ms = 1500) {
      const t0 = Date.now();
      for (;;) {
        try { if (predicate()) return true; } catch { /* keep waiting */ }
        if (Date.now() - t0 > ms) throw new Error("waitFor: timed out");
        await new Promise((r) => window.setTimeout(r, 10));
      }
    },
  };
  await h.waitFor(() => { const n = h.$("#surfnav"); return n && !n.hidden; }).catch(() => {});
  return h;
}
