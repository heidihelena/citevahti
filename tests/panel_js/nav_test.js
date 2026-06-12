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

const appPath = path.join(__dirname, "..", "..", "src", "citevahti", "panel", "web", "app.js");
const src = fs.readFileSync(appPath, "utf8");

// minimal DOM/browser stubs — just enough for app.js to load without throwing
const fakeEl = () => new Proxy({ value: "", textContent: "", innerHTML: "" }, {
  get(t, p) {
    if (p === "addEventListener") return () => {};
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
const exposed = src + "\n;globalThis.__cv = { claimOrder, nextPending, get state(){ return state; } };";
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

console.log(failures ? `\n${failures} test(s) failed` : "\nall navigation tests passed");
process.exit(failures ? 1 : 0);
