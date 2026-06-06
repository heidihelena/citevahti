/* CiteVahti inline review layer (ADR-0002).
 * The review happens INSIDE the manuscript: highlight a claim, type oo/o/r/d,
 * the agent proposes edits as diffs, the card shows the evidence. No dashboard.
 *   oo supported -> Add to Zotero (decision-gated, undoable transaction)
 *   o  partly    -> cite with caution / revise wording
 *   r  revise    -> agent proposes a claim rewrite as an inline diff (never silent)
 *   d  delete    -> remove the SOURCE candidate (claim + sentence stay) */

const FIT = {
  supported: { code: "oo", label: "Supported" },
  partial:   { code: "o ", label: "Partly supported" },
  revise:    { code: "r ", label: "Revise" },
  delete:    { code: "d ", label: "Unsupported" },
};
const MARK_EYE = { neutral: "#8B6FC9", supported: "#C98A00", partial: "#1E9E8A", revise: "#8B6FC9", delete: "#C24D7E" };

const CLAIMS = {
  c1: { code: "supported", text: "Low-dose CT screening reduces lung-cancer mortality in high-risk populations",
    src: "1", srcRemoved: false,
    paper: "National Lung Screening Trial — NEJM 2011 · PMID 21714641 · DOI 10.1056/NEJMoa1102873",
    excerpt: "Screening with low-dose CT reduced lung-cancer mortality vs chest radiography in high-risk participants.",
    checks: { Population: true, Intervention: true, Outcome: true, Direction: true, "Study type": true },
    ai: "Directly supports", human: "Directly supports", fit: 8 },
  c2: { code: "partial", text: "smoking-related comorbidities that can shape implementation",
    src: "2", srcRemoved: false,
    paper: "Smoking-related comorbidities on LDCT — Chest 2026 · PMID 42217822 · DOI 10.1016/j.chest.2026.05.028",
    excerpt: "LDCT frequently detects emphysema, coronary calcium and ILA — relevant to implementation, though a narrower claim than written.",
    checks: { Population: true, Intervention: true, Outcome: false, Direction: true, "Study type": false },
    ai: "Partially supports", human: "Partially supports", fit: 5 },
  c3: { code: "revise", text: "every incidental pulmonary nodule should be treated as cancer until proven otherwise",
    src: "3", srcRemoved: false,
    paper: "Management of incidental pulmonary nodules — Radiology Clinics 2024 · PMID 41199102",
    excerpt: "Most incidental nodules are benign; risk-stratified follow-up is recommended rather than assumed malignancy.",
    checks: { Population: true, Intervention: false, Outcome: false, Direction: false, "Study type": true },
    ai: "Contradicts as written", human: "—", fit: 2,
    revision: { from: "every incidental pulmonary nodule should be treated as cancer until proven otherwise",
                to: "most incidental pulmonary nodules are benign and warrant risk-stratified follow-up rather than assumed malignancy" },
    altPaper: { paper: "Fleischner Society guidelines: management of incidental pulmonary nodules — Radiology 2023 · PMID 40012345",
                excerpt: "Risk-stratified follow-up of incidental nodules — supports a revised, guideline-aligned version of the claim.",
                code: "partial" } },
  c4: { code: "delete", text: "prehabilitation improves surgical readiness for early-stage resections",
    src: "4", srcRemoved: false,
    paper: "Prehabilitation cohort — J Thorac Oncol 2025 · PMID 41900124 · DOI 10.5555/prehab-demo",
    excerpt: "Single-center, heterogeneous cohort; does not establish that prehabilitation improves readiness for this claim.",
    checks: { Population: true, Intervention: false, Outcome: false, Direction: false, "Study type": false },
    ai: "Does not support", human: "—", fit: 2 },
};

/* the manuscript; claim segments reference CLAIMS by id */
const DOC = [
  { h1: "Background" },
  { t: "Lung cancer remains the leading cause of cancer death worldwide. " },
  { claim: "c1" }, { t: ". Screening programs also detect " },
  { claim: "c2" }, { t: ". Some guidance overstates risk — for example, the assertion that " },
  { claim: "c3" }, { t: " — which the cited evidence does not support. Finally, " },
  { claim: "c4" }, { t: "." },
];

let activeId = "c1";
let lastO = 0;

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
    const c = CLAIMS[node.claim];
    const active = node.claim === activeId ? " active" : "";
    const src = `<sup class="src${c.srcRemoved ? " removed" : ""}">[${c.src}]</sup>`;
    const struck = c.claimDeleted ? " deleted-claim" : "";
    return `<span class="claim ${c.code}${active}${struck}" data-id="${node.claim}" tabindex="0" role="button"
        aria-label="${FIT[c.code].label} claim">${c.text}${src}<span class="code">[${FIT[c.code].code}]</span></span>`;
  }).join("");
  document.querySelector("#doc").innerHTML = "<p>" + html + "</p>";
}

function checkChips(checks) {
  return Object.entries(checks).map(([k, v]) =>
    `<span class="check ${v ? "ok" : "no"}">${k} ${v ? "✓" : "✗"}</span>`).join("");
}

function fitLabel(n) { return n >= 7 ? "Strong" : n >= 4 ? "Moderate" : n >= 1 ? "Weak" : "None"; }

function cardActions(id, code) {
  if (code === "supported") return `<button class="btn primary">Add to Zotero</button><button class="btn ghost">Open paper</button>`;
  if (code === "partial") return `<button class="btn primary">Add with caution</button><button class="btn ghost" data-act="revise" data-id="${id}">Revise wording</button>`;
  if (code === "revise") return `<button class="btn primary" data-act="accept-rev" data-id="${id}">Revise claim</button><button class="btn ghost" data-act="change-ref" data-id="${id}">Change reference</button>`;
  return `<button class="btn primary" data-act="remove-src" data-id="${id}">Remove candidate from claim</button><button class="btn danger" data-act="remove-all" data-id="${id}">Remove candidate + strike claim (diff)</button>`;
}

function renderCard() {
  const id = activeId, c = CLAIMS[id], code = c.code;
  const diff = code === "revise" && c.revision
    ? `<div class="lbl">Suggested revision (never applied silently)</div>
       <div class="diff"><div class="del">${c.revision.from}</div><div class="add">${c.revision.to}</div></div>` : "";
  // blinded validation: the AI rating is hidden until the human submits theirs
  const blinded = c.human === "—";
  const human = blinded
    ? `<span class="muted">awaiting blinded human rating</span>` : `<b>${c.human}</b>`;
  const aiCell = blinded
    ? `<span class="muted">hidden during blinded validation</span>` : `<b>${c.ai}</b>`;
  document.querySelector("#card").className = `card ${code}`;
  document.querySelector("#card").innerHTML = `
    <div class="card-code"><span class="code">[${FIT[code].code}]</span>${FIT[code].label}</div>
    <div class="lbl">Claim</div><div class="claimline">“${c.text}”</div>
    <div class="lbl">Candidate source</div><div class="paper">${c.paper}</div>
    <div class="excerpt">${c.excerpt}</div>
    <div class="lbl">Fit checks</div><div class="checks">${checkChips(c.checks)}</div>
    ${diff}
    <div class="lbl">Ratings (blinded)</div>
    <div class="rate"><span>AI</span>${aiCell}</div>
    <div class="rate"><span>Human</span>${human}</div>
    <div class="rate"><span>Citation fit</span><b>${fitLabel(c.fit)} (${c.fit}/8)</b></div>
    <div class="actions">${cardActions(id, code)}</div>`;
}

function renderAgent() {
  const c = CLAIMS[activeId], code = c.code;
  const lines = {
    supported: `<span class="pill">[oo] supported → ready for the decision-gated write — creates a transaction with an undo path. Nothing is written silently.</span>`,
    partial: `<span class="pill">[o ] partly supported → cite with caution, or ask me to revise the wording so the claim matches the evidence.</span>`,
    revise: `<span class="pill">[r ] revise → fix the wording (“Revise claim” applies the diff above) or “Change reference” to swap a better-fitting paper. I never edit your text without confirm.</span>`,
    delete: c.claimDeleted
      ? `<span class="pill">[d ] unsupported → removed the source candidate AND struck the claim (shown as a diff, undo to restore). Nothing in Zotero is deleted.</span>`
      : `<span class="pill">[d ] unsupported → “Remove candidate from claim” keeps your claim & sentence; “Remove candidate + strike claim” also strikes the claim text as a diff (never silent, undoable).</span>`,
  };
  document.querySelector("#agent").innerHTML = `<span class="who">CiteVahti ▸</span> ${lines[code]}`;
}

function render() { renderDoc(); renderCard(); renderAgent();
  document.querySelectorAll("[data-logo]").forEach((n) => n.innerHTML = markSvg(n.dataset.logo)); }

function setActive(id) { if (CLAIMS[id]) { activeId = id; render(); } }
function setCode(code) { CLAIMS[activeId].code = code; render(); }

/* claim navigation + the oo/o/r/d keyboard model */
const ORDER = ["c1", "c2", "c3", "c4"];
document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, textarea")) return;
  const i = ORDER.indexOf(activeId);
  if (e.key === "j" || e.key === "ArrowDown") { setActive(ORDER[Math.min(i + 1, ORDER.length - 1)]); e.preventDefault(); return; }
  if (e.key === "k" || e.key === "ArrowUp") { setActive(ORDER[Math.max(i - 1, 0)]); e.preventDefault(); return; }
  if (e.key === "o") {
    const now = Date.now();
    setCode(now - lastO < 450 ? "supported" : "partial");   // double-o within 450ms = oo
    lastO = now; e.preventDefault(); return;
  }
  if (e.key === "r") { setCode("revise"); e.preventDefault(); }
  if (e.key === "d") { setCode("delete"); e.preventDefault(); }
});

document.addEventListener("click", (e) => {
  const span = e.target.closest(".claim");
  if (span) { setActive(span.dataset.id); return; }
  const act = e.target.closest("[data-act]");
  if (!act) return;
  const id = act.dataset.id || activeId, c = CLAIMS[id];
  if (act.dataset.act === "remove-src") { c.srcRemoved = true; c.claimDeleted = false; render(); }
  if (act.dataset.act === "remove-all") { c.srcRemoved = true; c.claimDeleted = true; render(); }
  if (act.dataset.act === "accept-rev" && c.revision) { c.text = c.revision.to; c.code = "supported"; delete c.revision; render(); }
  if (act.dataset.act === "change-ref" && c.altPaper) {
    c.paper = c.altPaper.paper; c.excerpt = c.altPaper.excerpt; c.code = c.altPaper.code;
    c.refChanged = true; delete c.revision; render();
  }
  if (act.dataset.act === "revise") { c.code = "revise"; render(); }
});

document.querySelector("#theme").addEventListener("click", () => {
  document.documentElement.classList.toggle("zs-dark");
  document.querySelector("#theme").textContent =
    document.documentElement.classList.contains("zs-dark") ? "◐ Light" : "◑ Dark";
});

render();
