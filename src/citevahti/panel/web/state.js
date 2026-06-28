/* CiteVahti panel — domain constants + app state (extracted from app.js).
 * A classic (non-module) script loaded BEFORE app.js, so these globals live in
 * the shared global scope the rest of the panel already relies on. No DOM access,
 * no top-level side effects — safe to load first and safe to concatenate in the
 * headless JS test sandbox. */

const SUPPORT = [
  ["directly_supports", "Directly supports", "the paper directly supports this claim"],
  ["partially_supports", "Partially supports", "the paper supports part of this claim"],
  ["indirectly_supports", "Indirectly supports", "the paper supports this claim only indirectly"],
  ["overstated", "Overstated", "the paper supports a weaker version of this claim"],
  ["does_not_support", "Does not support", "the paper does not support this claim"],
  ["contradicts", "Contradicts", "the paper contradicts this claim"],
  ["unclear", "Unclear", "the paper's support for this claim is genuinely unclear"],
];
const SUP_LABEL = Object.fromEntries(SUPPORT.map(([v, l]) => [v, l]));
const SUP_DEF = Object.fromEntries(SUPPORT.map(([v, , d]) => [v, d]));
// Human-readable claim-type labels; the enum is stored, only the label is shown.
const CLAIM_TYPE_LABEL = {
  effectiveness: "Treatment effect", diagnostic_accuracy: "Diagnostic accuracy",
  prognosis: "Prognosis", risk_factor: "Risk factor", mechanism: "Mechanism",
  background: "Background claim", guideline_recommendation: "Guideline recommendation",
  implementation: "Implementation", other: "Other",
};
const claimTypeLabel = (t) => CLAIM_TYPE_LABEL[t] || t || "";
const DECISIONS = [
  ["accept", "Accept", "oo"],
  ["accepted_with_caution", "Caution", "o"],
  ["needs_second_review", "Needs review", "r"],
  ["reject", "Reject", "d"],
];
const HEALTHY = ["connected", "configured", "available", "ok"];
const STATE_CLASS = { oo: "s-oo", o: "s-o", r: "s-r", d: "s-d" };
// a claim is "decided" once a verdict exists — every state except the pending one.
// (verified=accept, review_needed=revise, decision_recorded=reject; needs_support=pending)
const PENDING_STATE = "needs_support";
const isDecided = (state) => !!state && state !== PENDING_STATE;
// PICO fit dimensions: key, short label, and a plain explanation of what to judge.
const PICO = [
  ["population_fit", "P", "Population — does the paper study the same people/setting the claim is about?"],
  ["intervention_fit", "I", "Intervention / exposure — does the paper test the same thing the claim is about?"],
  ["outcome_fit", "O", "Outcome — does the paper measure the outcome the claim is about?"],
  ["claim_fit", "Claim", "Overall — does this paper actually address this specific claim?"],
];
// What each 0/1/2 fit score means (the scale was ambiguous as bare numbers).
const FIT_SCORES = [["0", "0 — no / off-topic"], ["1", "1 — partial / indirect"], ["2", "2 — strong / direct"]];
const fitWord = (n) => n >= 7 ? "Strong" : n >= 4 ? "Moderate" : n >= 1 ? "Weak" : "None";

const state = {
  ctx: null, health: null, manuscripts: [], activeMs: null, view: null,
  activeClaim: null, claim: null, candIdx: 0, done: new Set(),
  lastTxn: null, docTxn: null, pendingDocToken: null,
  // which top-level surface is showing — see renderSurface() in app.js. Defaults to
  // the review workspace; boot() routes to "manuscripts" when the ledger is empty.
  surface: "workspace",
};
let oTimer = null;   // double-tap "o" (decide phase): single = caution [o], double = accept [oo]
