/* Headless test for the inliner's claim-activation/navigation logic.
 *
 * Loads the REAL panel app.js in a stubbed sandbox (no browser, no deps) and
 * exercises the pure navigation functions. Guards the two bugs fixed in the
 * activation path:
 *   1. j/k + auto-advance must follow DOCUMENT order, not claim_states (ledger)
 *      order — claimOrder() derives order from the rendered segments.
 *   2. no claim may be stranded: unmatched + any orphan claim_states ids are
 *      still reachable (the catch-all in claimOrder()).
 *
 * Run directly (`node nav_test.js`) or via tests/test_panel_js.py.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

// The panel ships as classic scripts loaded in dependency order; concatenate them the
// same way so the sandbox sees the same global scope the browser does (see index.html).
const webDir = path.join(__dirname, "..", "..", "src", "citevahti", "panel", "web");
const src = ["state.js", "util.js", "api.js", "modal.js", "feedback.js", "events.js",
             "card.js", "card-phases.js", "card-edit.js", "review-actions.js",
             "connect.js", "search.js", "workspace.js", "manuscripts.js", "checks.js",
             "atlas.js", "output.js", "settings.js", "prompts.js", "app.js"]
  .map((f) => fs.readFileSync(path.join(webDir, f), "utf8"))
  .join("\n");

// minimal DOM/browser stubs — just enough for app.js to load without throwing
const fakeEl = () => new Proxy({ value: "", textContent: "", innerHTML: "", hidden: false, dataset: {} }, {
  get(t, p) {
    if (p === "addEventListener") return () => {};
    if (p === "setAttribute" || p === "removeAttribute" || p === "toggleAttribute") return () => {};
    if (p === "querySelector") return () => fakeEl();
    if (p === "querySelectorAll") return () => [];
    if (p === "classList") return { toggle() {}, contains() { return true; }, add() {}, remove() {} };
    if (p in t) return t[p];
    return undefined;
  },
  set() { return true; },
});
const documentStub = {
  querySelector: () => fakeEl(),
  querySelectorAll: () => [],
  addEventListener: () => {},
  documentElement: { classList: { toggle() {}, contains() { return true; } } },
};
const sandbox = {
  document: documentStub,
  location: { origin: "http://127.0.0.1:8765", reload() {} },
  fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
  console,
  setInterval: () => 0, clearInterval: () => {}, setTimeout: () => 0,
  alert: () => {}, prompt: () => "",
};
sandbox.window = sandbox;

// expose the otherwise-closure-scoped helpers + state for assertions
const exposed = src + "\n;globalThis.__cv = { claimOrder, nextPending, phaseOf, recoverableTxn, committedZoteroTxn, citeOf, get state(){ return state; } };";
vm.createContext(sandbox);
vm.runInContext(exposed, sandbox, { filename: "app.js" });
const cv = sandbox.__cv;

// a manuscript where DOCUMENT order (d1,d2,d3,d4) != claim_states/ledger order,
// plus one unmatched claim (u1) and one orphan present only in claim_states (o1)
cv.state.view = {
  segments: [
    { kind: "text", text: "intro " },
    { kind: "claim", claim_id: "d1" },
    { kind: "text", text: " mid " },
    { kind: "claim", claim_id: "d2" },
    { kind: "claim", claim_id: "d3" },
    { kind: "text", text: " end " },
    { kind: "claim", claim_id: "d4" },
  ],
  unmatched: ["u1"],
  claim_states: {
    // d1 is "verified" (an Accept) — decided is ANY non-pending state, not just
    // "decision_recorded" (the bug: Accept/Revise verdicts weren't treated as decided).
    d3: { state: "needs_support" }, d1: { state: "accepted" },
    d4: { state: "needs_support" }, d2: { state: "needs_support" },
    u1: { state: "needs_support" }, o1: { state: "needs_support" },
  },
};

let failures = 0;
const eq = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  console.log((ok ? "ok   " : "FAIL ") + name);
  if (!ok) { failures++; console.error("   got:", JSON.stringify(got), "want:", JSON.stringify(want)); }
};

// 1. document order, then unmatched, then orphan catch-all (never strand a claim)
eq("claimOrder follows document order + unmatched + catch-all",
   cv.claimOrder(), ["d1", "d2", "d3", "d4", "u1", "o1"]);

// 2. auto-advance skips decided claims in document order (d1 = verified/Accept -> d2)
cv.state.activeClaim = "d1";
eq("nextPending skips a verified (Accept) claim, document order", cv.nextPending(), "d2");

// 3. auto-advance wraps in document order (after d4 -> u1, not a ledger neighbour)
cv.state.activeClaim = "d4";
eq("nextPending wraps in document order", cv.nextPending(), "u1");

// 4. regression guard: order must NOT equal raw claim_states key order
const ledgerOrder = Object.keys(cv.state.view.claim_states);
eq("claimOrder differs from ledger order (the original bug)",
   JSON.stringify(cv.claimOrder()) !== JSON.stringify(ledgerOrder), true);

// 5. phase comes from the server (workflow.candidate_step) — phaseOf renders cand.step,
// it no longer re-derives the rate→decide→write rules client-side. The in-session done
// overlay still gives instant feedback right after a commit.
const decidedCand = { candidate_id: "c1", step: { phase: "write" } };
cv.state.activeClaim = "d2";
cv.state.candIdx = 0;
cv.state.claim = { claim: { claim_id: "d2" }, candidates: [decidedCand] };
cv.state.done = new Set();
eq("phaseOf renders the server-provided step.phase", cv.phaseOf(decidedCand), "write");
decidedCand.step = { phase: "done" };
eq("phaseOf follows the server to 'done' (e.g. a committed write)", cv.phaseOf(decidedCand), "done");
decidedCand.step = undefined;
eq("phaseOf defaults to 'rate' when the server sent no step", cv.phaseOf(decidedCand), "rate");
cv.state.done.add("d2:c1");
eq("phaseOf overlays in-session done for instant post-commit feedback",
   cv.phaseOf(decidedCand), "done");
cv.state.done = new Set();

// undo-after-return: a committed (not-undone) Zotero write for the active candidate is
// still recovered from the per-claim audit trail so the Undo button works after a return.
cv.state.lastTxn = null;
cv.state.history = { transactions: [
  { transaction_id: "txn-aaa", candidate_id: "c1", status: "committed", undone_at: null },
] };
eq("recoverableTxn returns the committed txn id after return (lastTxn cleared)",
   cv.recoverableTxn(), "txn-aaa");
cv.state.history = { transactions: [
  { transaction_id: "txn-aaa", candidate_id: "c1", status: "undone", undone_at: "2026-06-15T00:00" },
] };
eq("recoverableTxn is null once the write is undone", cv.recoverableTxn(), null);
cv.state.lastTxn = "txn-session";
eq("recoverableTxn prefers the in-session lastTxn", cv.recoverableTxn(), "txn-session");
cv.state.lastTxn = null;

// 6. citation-on-copy: citeOf() formats a one-line reference from whatever a candidate
// carries, preferring DOI over PMID and degrading honestly with partial metadata.
eq("citeOf prefers DOI and trims trailing period",
   cv.citeOf({ title: "Telephone follow-up after surgery.", journal: "BMJ", year: 2021, doi: "10.1/x" }),
   "Telephone follow-up after surgery. BMJ 2021. https://doi.org/10.1/x");
eq("citeOf falls back to PMID when no DOI",
   cv.citeOf({ title: "A trial", pmid: "30000004" }), "A trial. PMID 30000004");
eq("citeOf with only a title", cv.citeOf({ title: "Bare claim" }), "Bare claim");
eq("citeOf with nothing is empty", cv.citeOf(null), "");

console.log(failures ? `\n${failures} test(s) failed` : "\nall navigation tests passed");
process.exit(failures ? 1 : 0);
