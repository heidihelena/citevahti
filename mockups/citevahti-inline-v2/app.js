/* CiteVahti inline review — v2 (ADR-0002, redesigned workflow).
 *
 * The clunk this rewrite targets: in v1 the card was read-first (you scrolled
 * past context to reach the action), the blinded human-first protocol was
 * implicit (typing oo/o/r/d on the manuscript), and the Zotero write gate was a
 * single "Add to Zotero" click. v2 makes the protocol a visible state machine
 * with one obvious next action per claim:
 *
 *   RATE   you record a blind support rating (1–6). The AI rating stays hidden.
 *   REVEAL the AI second rating appears; concordance is shown. (automatic)
 *   DECIDE you set the verdict (Accept / Caution / Review / Reject) + a reason.
 *   WRITE  the verdict's action runs behind a preview → confirm → undo gate.
 *
 * Still a static mockup — no real PubMed/Zotero calls; the live behaviour and the
 * actual blinding enforcement live in the CLI/engine + panel server. */

/* the six blind support ratings (engine: claim_support values), with hotkeys */
const SUPPORT = [
  { v: "directly_supports",   label: "Directly supports",   pol: "+" },
  { v: "partially_supports",  label: "Partially supports",  pol: "+" },
  { v: "indirectly_supports", label: "Indirectly supports", pol: "+" },
  { v: "does_not_support",    label: "Does not support",    pol: "-" },
  { v: "contradicts",         label: "Contradicts",         pol: "-" },
  { v: "unclear",             label: "Unclear",             pol: "?" },
];
const POL = Object.fromEntries(SUPPORT.map((s) => [s.v, s.pol]));
const LABEL = Object.fromEntries(SUPPORT.map((s) => [s.v, s.label]));

/* the four decisions → the four verdict hues (oo/o/r/d) shown on the manuscript */
const DECISIONS = [
  { v: "accept",              label: "Accept",        code: "supported", glyph: "oo" },
  { v: "accept_with_caution", label: "Caution",       code: "partial",   glyph: "o " },
  { v: "needs_second_review", label: "Needs review",  code: "revise",    glyph: "r " },
  { v: "reject",              label: "Reject",        code: "delete",    glyph: "d " },
];
const DEC = Object.fromEntries(DECISIONS.map((d) => [d.v, d]));
const FIT_LABEL = { supported: "Supported", partial: "Partly supported", revise: "Revise", delete: "Unsupported" };
const PICO = [["Population", "P"], ["Intervention", "I"], ["Outcome", "O"], ["Direction", "Dir"], ["Study type", "Type"]];
const MARK_EYE = { neutral: "#8B6FC9", supported: "#C98A00", partial: "#1E9E8A", revise: "#8B6FC9", delete: "#C24D7E" };

const CLAIMS = {
  c1: { text: "Low-dose CT screening reduces lung-cancer mortality in high-risk populations",
    src: "1", paper: "National Lung Screening Trial — NEJM 2011 · PMID 21714641 · DOI 10.1056/NEJMoa1102873",
    excerpt: "Screening with low-dose CT reduced lung-cancer mortality vs chest radiography in high-risk participants.",
    checks: { Population: true, Intervention: true, Outcome: true, Direction: true, "Study type": true },
    ai: "directly_supports", fit: 8 },
  c2: { text: "smoking-related comorbidities that can shape implementation",
    src: "2", paper: "Smoking-related comorbidities on LDCT — Chest 2026 · PMID 42217822 · DOI 10.1016/j.chest.2026.05.028",
    excerpt: "LDCT frequently detects emphysema, coronary calcium and ILA — relevant to implementation, though a narrower claim than written.",
    checks: { Population: true, Intervention: true, Outcome: false, Direction: true, "Study type": false },
    ai: "partially_supports", fit: 5 },
  c3: { text: "every incidental pulmonary nodule should be treated as cancer until proven otherwise",
    src: "3", paper: "Management of incidental pulmonary nodules — Radiology Clinics 2024 · PMID 41199102",
    excerpt: "Most incidental nodules are benign; risk-stratified follow-up is recommended rather than assumed malignancy.",
    checks: { Population: true, Intervention: false, Outcome: false, Direction: false, "Study type": true },
    ai: "contradicts", fit: 2,
    revision: { from: "every incidental pulmonary nodule should be treated as cancer until proven otherwise",
                to: "most incidental pulmonary nodules are benign and warrant risk-stratified follow-up rather than assumed malignancy" },
    altPaper: { paper: "Fleischner Society guidelines: management of incidental pulmonary nodules — Radiology 2023 · PMID 40012345",
                excerpt: "Risk-stratified follow-up of incidental nodules — supports a revised, guideline-aligned version of the claim." } },
  c4: { text: "prehabilitation improves surgical readiness for early-stage resections",
    src: "4", paper: "Prehabilitation cohort — J Thorac Oncol 2025 · PMID 41900124 · DOI 10.5555/prehab-demo",
    excerpt: "Single-center, heterogeneous cohort; does not establish that prehabilitation improves readiness for this claim.",
    checks: { Population: true, Intervention: false, Outcome: false, Direction: false, "Study type": false },
    ai: "does_not_support", fit: 2 },
};
const ORDER = ["c1", "c2", "c3", "c4"];

/* per-claim review state (the state machine). Starts empty = phase "rate". */
for (const id of ORDER) CLAIMS[id].st = { human: null, decision: null, write: null, srcRemoved: false, claimDeleted: false };

const DOC = [
  { h1: "Background" },
  { t: "Lung cancer remains the leading cause of cancer death worldwide. " },
  { claim: "c1" }, { t: ". Screening programs also detect " },
  { claim: "c2" }, { t: ". Some guidance overstates risk — for example, the assertion that " },
  { claim: "c3" }, { t: " — which the cited evidence does not support. Finally, " },
  { claim: "c4" }, { t: "." },
];

let activeId = "c1";

/* ---- derived helpers ---- */
function phaseOf(c) {                          // which step the claim is on
  const s = c.st;
  if (s.write === "committed") return "done";
  if (!s.human) return "rate";
  if (!s.decision) return "decide";
  return "write";
}
function verdictCode(c) {                       // hue shown on the manuscript span
  return c.st.decision ? DEC[c.st.decision].code : "pending";
}
function concordance(c) {                        // human vs AI, bucketed by polarity
  if (!c.st.human) return null;
  return POL[c.st.human] === POL[c.ai] ? "concordant" : "discordant";
}
function fitWord(n) { return n >= 7 ? "Strong" : n >= 4 ? "Moderate" : n >= 1 ? "Weak" : "None"; }
function nextPendingId(from) {
  const i = ORDER.indexOf(from);
  for (let k = 1; k <= ORDER.length; k++) {
    const id = ORDER[(i + k) % ORDER.length];
    if (phaseOf(CLAIMS[id]) !== "done") return id;
  }
  return null;
}

/* ---- manuscript ---- */
function markSvg(state = "neutral") {
  const eye = MARK_EYE[state] || MARK_EYE.neutral;
  return `<svg width="100%" height="100%" viewBox="0 0 64 64" fill="none" role="img" aria-label="CiteVahti ${state}">
    <g fill="currentColor">
      <rect x="12" y="14" width="6" height="36"/><rect x="12" y="14" width="15" height="6"/><rect x="12" y="44" width="15" height="6"/>
      <rect x="46" y="14" width="6" height="36"/><rect x="37" y="14" width="15" height="6"/><rect x="37" y="44" width="15" height="6"/>
    </g>
    <g fill="${eye}"><path d="M24 28 L29 24 L31 32 L26 35 Z"/><path d="M40 28 L35 24 L33 32 L38 35 Z"/></g>
  </svg>`;
}

function renderDoc() {
  const html = DOC.map((node) => {
    if (node.h1) return `<h1>${node.h1}</h1><p>`;
    if (node.t) return node.t;
    const c = CLAIMS[node.claim], s = c.st;
    const code = verdictCode(c);
    const active = node.claim === activeId ? " active" : "";
    const written = s.write === "committed" && code !== "delete" ? " written" : "";
    const struck = s.claimDeleted ? " deleted-claim" : "";
    const src = `<sup class="src${s.srcRemoved ? " removed" : ""}">[${c.src}]</sup>`;
    const glyph = code === "pending" ? "··" : DECISIONS.find((d) => d.code === code).glyph;
    return `<span class="claim ${code}${active}${written}${struck}" data-id="${node.claim}" tabindex="0" role="button"
        aria-label="claim">${c.text}${src}<span class="code">[${glyph}]</span></span>`;
  }).join("");
  document.querySelector("#doc").innerHTML = "<p>" + html + "</p>";
}

function renderProgress() {
  const rated = ORDER.filter((id) => CLAIMS[id].st.human).length;
  const done = ORDER.filter((id) => phaseOf(CLAIMS[id]) === "done").length;
  const pending = ORDER.length - rated;
  const segs = ORDER.map((id) => {
    const ph = phaseOf(CLAIMS[id]);
    const cls = ph === "done" ? "done" : CLAIMS[id].st.human ? "rated" : "";
    const cur = id === activeId ? " current" : "";
    return `<span class="seg ${cls}${cur}" data-id="${id}" title="${id}"></span>`;
  }).join("");
  document.querySelector("#progress").innerHTML =
    `<div class="bar">${segs}</div>
     <span class="tally"><b>${pending}</b> pending · <b>${rated}</b> rated · <b>${done}</b> cited</span>`;
}

/* ---- the card: action-first, driven by phase ---- */
function stepper(active) {
  const steps = [["rate", "Rate"], ["reveal", "Reveal"], ["decide", "Decide"], ["write", "Write"]];
  const idx = { rate: 0, reveal: 1, decide: 2, write: 3, done: 4 }[active];
  return `<div class="stepper">` + steps.map(([k, label], i) => {
    const cls = i < idx ? "done" : i === idx ? "current" : "";
    const arrow = i < steps.length - 1 ? `<span class="arrow"></span>` : "";
    return `<span class="step ${cls}"><span class="num">${i < idx ? "✓" : i + 1}</span>${label}</span>${arrow}`;
  }).join("") + `</div>`;
}

function contextBlock(c, open) {
  const chips = PICO.map(([k, lab]) => {
    const v = c.checks[k];
    return `<span class="check ${v ? "ok" : "no"}">${lab} ${v ? "✓" : "✗"}</span>`;
  }).join("");
  return `<details class="context"${open ? " open" : ""}>
    <summary>Evidence &amp; fit checks</summary>
    <div class="body">
      <div class="lbl">Candidate source</div><div class="paper">${c.paper}</div>
      <div class="excerpt">${c.excerpt}</div>
      <div class="lbl">PICO fit checks</div>
      <div class="checks">${chips}<span class="fittag">Citation fit ${fitWord(c.fit)} (${c.fit}/8)</span></div>
    </div></details>`;
}

function rateBlock(c) {
  const btns = SUPPORT.map((s, i) => {
    const chosen = c.st.human === s.v ? " chosen" : "";
    return `<button class="rate-btn${chosen}" data-rate="${s.v}"><span class="hk">${i + 1}</span>${s.label}</button>`;
  }).join("");
  const fit = `<div class="fitrow"><span class="lbl">Optional PICO fit</span>` +
    PICO.map(([k, lab]) =>
      `<label class="fitlab">${lab}<select data-fit="${k}"><option value="">–</option><option>0</option><option>1</option><option>2</option></select></label>`
    ).join("") + `</div>`;
  return `<div class="next">
    <div class="ask">Your blind support rating</div>
    <div class="why">Press <kbd>1</kbd>–<kbd>6</kbd> or click. The AI second rating stays hidden until you record yours.</div>
    <div class="rates">${btns}</div>
    ${fit}
  </div>`;
}

function decideBlock(c) {
  const cmp = concordance(c);
  const decBtns = DECISIONS.map((d) =>
    `<button class="btn ghost" data-decide="${d.v}">${d.label} <span class="hk">[${d.glyph.trim()}]</span></button>`).join("");
  const disagree = cmp === "discordant"
    ? `<div class="note">You and the AI disagree — your decision adjudicates. The reason is recorded in the audit trail.</div>` : "";
  return `<div class="next">
    <div class="ask">Reveal &amp; decide</div>
    <div class="why">Your blind rating is in. Here is the AI second rating.</div>
    <div class="reveal">
      <div class="compare">
        <div class="col you"><div class="who">You</div><div class="val">${LABEL[c.st.human]}</div></div>
        <div class="col"><div class="who">AI (2nd)</div><div class="val">${LABEL[c.ai]}</div></div>
      </div>
      <span class="verdict-tag ${cmp}">${cmp}</span>
    </div>
    <div class="lbl">Record the verdict</div>
    <div class="decrow"><input type="text" id="decReason" placeholder="reason (recorded in the audit trail)" /></div>
    <div class="actions">${decBtns}</div>
    ${disagree}
  </div>`;
}

function writeBlock(c) {
  const code = verdictCode(c), s = c.st;
  const head = `<div class="ask">${FIT_LABEL[code]} — ${({ supported: "cite it", partial: "cite with caution", revise: "fix the claim", delete: "remove the candidate" })[code]}</div>`;
  // supported / partial → the Zotero write gate (preview → confirm → undo)
  if (code === "supported" || code === "partial") {
    let body, note = "";
    if (!s.write) {
      body = `<div class="actions"><button class="btn primary" data-act="preview">Preview write <span class="hk">↵</span></button></div>`;
      note = `<div class="why">Nothing is written to Zotero yet. Preview the change first.</div>`;
    } else if (s.write === "previewed") {
      body = `<div class="actions">
        <button class="btn primary" data-act="commit">Confirm &amp; add to Zotero <span class="hk">↵</span></button>
        <button class="btn ghost" data-act="cancel">Cancel</button></div>`;
      note = `<div class="note ok">Preview: add “${c.paper.split(" — ")[0]}” to library · dedupe clean. Confirm to write — it stays undoable.</div>`;
    }
    return `<div class="next">${head}${note}${body}</div>`;
  }
  // revise → apply the suggested diff, or change reference (manuscript edit, confirmed)
  if (code === "revise") {
    const diff = c.revision
      ? `<div class="diff"><div class="del">${c.revision.from}</div><div class="add">${c.revision.to}</div></div>` : "";
    return `<div class="next">${head}
      <div class="why">CiteVahti never edits your text without confirm.</div>${diff}
      <div class="actions">
        <button class="btn primary" data-act="apply-rev">Apply revision <span class="hk">↵</span></button>
        ${c.altPaper ? `<button class="btn ghost" data-act="change-ref">Change reference</button>` : ""}
      </div></div>`;
  }
  // delete → remove candidate (claim stays) or also strike the claim text as a diff
  return `<div class="next">${head}
    <div class="why">Removes the source candidate only — your claim and sentence stay unless you also strike them.</div>
    <div class="actions">
      <button class="btn primary" data-act="remove-src">Remove candidate <span class="hk">↵</span></button>
      <button class="btn danger" data-act="remove-all">Remove + strike claim (diff)</button>
    </div></div>`;
}

function doneBlock(c) {
  const code = verdictCode(c);
  const what = { supported: "Added to Zotero", partial: "Added with caution", revise: "Claim revised", delete: "Candidate removed" }[code];
  const nxt = nextPendingId(activeId);
  return `<div class="next">
    <div class="done-banner">✓ ${what} — recorded with an undo path.</div>
    <div class="actions">
      <button class="btn ghost" data-act="undo">Undo</button>
      ${nxt ? `<button class="btn primary" data-act="next">Next claim <span class="hk">↵</span></button>`
            : `<div class="note ok">All claims reviewed. 🎉</div>`}
    </div></div>`;
}

function renderCard() {
  const c = CLAIMS[activeId], ph = phaseOf(c);
  const card = document.querySelector("#card");
  card.className = `card ${verdictCode(c)}`;
  const claimHead = `<div class="lbl">Claim ${c.st.human ? "" : "· awaiting your blind rating"}</div>
    <div class="claimline">“${c.text}”</div>`;
  let block, openCtx;
  if (ph === "rate") { block = rateBlock(c); openCtx = true; }       // context open: you read before rating
  else if (ph === "decide") { block = decideBlock(c); openCtx = false; }
  else if (ph === "write") { block = writeBlock(c); openCtx = false; }
  else { block = doneBlock(c); openCtx = false; }
  card.innerHTML = stepper(ph) + claimHead + block + contextBlock(c, openCtx);
}

function renderAgent() {
  const c = CLAIMS[activeId], ph = phaseOf(c);
  const lines = {
    rate: `Read the evidence, then record your blind rating. I will not show my rating until yours is in — that gate is enforced by the engine, not by me.`,
    decide: concordance(c) === "discordant"
      ? `We disagree. You decide; I am advisory only. Your reason goes in the audit trail.`
      : `We agree. Record the verdict to continue — every Zotero write is still previewed and undoable.`,
    write: ({ supported: `Verdict Accept → I will stage a decision-gated Zotero write. Preview first; nothing is silent.`,
              partial: `Verdict Caution → same gated write, flagged for caution.`,
              revise: `Verdict Revise → I propose a wording fix as a diff. Apply it or swap the reference — never silent.`,
              delete: `Verdict Reject → I remove the source candidate. Your claim text stays unless you strike it.` })[verdictCode(c)],
    done: `Done and logged with an undo path. Press ↵ for the next claim.`,
  };
  document.querySelector("#agent").innerHTML = `<span class="who">CiteVahti ▸</span> <span class="pill">${lines[ph]}</span>`;
}

function render() {
  renderDoc(); renderProgress(); renderCard(); renderAgent();
  document.querySelectorAll("[data-logo]").forEach((n) => n.innerHTML = markSvg(n.dataset.logo));
}

/* ---- actions ---- */
function setActive(id) { if (CLAIMS[id]) { activeId = id; render(); } }

function recordRating(v) {
  const c = CLAIMS[activeId];
  if (phaseOf(c) !== "rate") return;
  c.st.human = v;
  render();
}
function recordDecision(v) {
  const c = CLAIMS[activeId];
  const reason = (document.querySelector("#decReason") || {}).value || "";
  if (!reason.trim()) { flashReason(); return; }
  c.st.decision = v; c.st.write = null;
  render();
}
function flashReason() {
  const el = document.querySelector("#decReason");
  if (el) { el.placeholder = "a reason is required — it is recorded in the audit trail"; el.focus(); el.style.borderColor = "var(--zs-delete-border)"; }
}

function primary() {                            // what Enter triggers, per phase
  const c = CLAIMS[activeId], ph = phaseOf(c), code = verdictCode(c);
  if (ph === "write") {
    if (code === "supported" || code === "partial")
      return c.st.write === "previewed" ? () => commit() : () => preview();
    if (code === "revise") return () => applyRevision();
    if (code === "delete") return () => removeSrc(false);
  }
  if (ph === "done") { const n = nextPendingId(activeId); return n ? () => setActive(n) : null; }
  return null;
}
function preview() { CLAIMS[activeId].st.write = "previewed"; render(); }
function commit() { CLAIMS[activeId].st.write = "committed"; render(); autoAdvance(); }
function applyRevision() {
  const c = CLAIMS[activeId];
  if (c.revision) { c.text = c.revision.to; delete c.revision; }
  c.st.write = "committed"; render(); autoAdvance();
}
function changeRef() {
  const c = CLAIMS[activeId];
  if (c.altPaper) { c.paper = c.altPaper.paper; c.excerpt = c.altPaper.excerpt; delete c.revision; }
  // changing the reference re-opens the loop: a new candidate needs a fresh rating
  c.st = { human: null, decision: null, write: null, srcRemoved: false, claimDeleted: false };
  render();
}
function removeSrc(strike) {
  const c = CLAIMS[activeId];
  c.st.srcRemoved = true; c.st.claimDeleted = strike; c.st.write = "committed"; render(); autoAdvance();
}
function undo() {
  const c = CLAIMS[activeId];
  c.st = { human: c.st.human, decision: null, write: null, srcRemoved: false, claimDeleted: false };
  render();
}
function autoAdvance() {
  const n = nextPendingId(activeId);
  if (n) setTimeout(() => setActive(n), 650);   // brief pause so the ✓ is visible
}

/* ---- events ---- */
document.addEventListener("click", (e) => {
  const seg = e.target.closest(".seg"); if (seg) return setActive(seg.dataset.id);
  const span = e.target.closest(".claim"); if (span) return setActive(span.dataset.id);
  const rate = e.target.closest("[data-rate]"); if (rate) return recordRating(rate.dataset.rate);
  const dec = e.target.closest("[data-decide]"); if (dec) return recordDecision(dec.dataset.decide);
  const act = e.target.closest("[data-act]"); if (!act) return;
  ({ preview, commit, cancel: () => { CLAIMS[activeId].st.write = null; render(); },
     "apply-rev": applyRevision, "change-ref": changeRef,
     "remove-src": () => removeSrc(false), "remove-all": () => removeSrc(true),
     undo, next: () => { const n = nextPendingId(activeId); if (n) setActive(n); } }[act.dataset.act] || (() => {}))();
});

document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, textarea, select")) return;
  const i = ORDER.indexOf(activeId);
  if (e.key === "j" || e.key === "ArrowDown") { setActive(ORDER[Math.min(i + 1, ORDER.length - 1)]); return e.preventDefault(); }
  if (e.key === "k" || e.key === "ArrowUp") { setActive(ORDER[Math.max(i - 1, 0)]); return e.preventDefault(); }
  if (phaseOf(CLAIMS[activeId]) === "rate" && /^[1-6]$/.test(e.key)) { recordRating(SUPPORT[+e.key - 1].v); return e.preventDefault(); }
  if (e.key === "Enter") { const p = primary(); if (p) { p(); e.preventDefault(); } }
});

document.querySelector("#theme").addEventListener("click", () => {
  document.documentElement.classList.toggle("zs-dark");
  document.querySelector("#theme").textContent =
    document.documentElement.classList.contains("zs-dark") ? "◐ Light" : "◑ Dark";
});

render();
