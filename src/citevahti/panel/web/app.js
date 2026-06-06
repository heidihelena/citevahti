/* CiteVahti decision panel (ADR-0007) — wires the inline card to the loopback API.
 *
 * This panel is the BLIND human decision surface. It renders only what the API
 * returns; the API never returns the AI rating until a human rating exists, so the
 * panel cannot reveal it early. The human rates here first; the chat reveals the
 * AI second rating afterwards. Writes are previewed before commit, and undoable. */

const SUPPORT = [
  ["directly_supports", "Directly supports"],
  ["partially_supports", "Partially"],
  ["indirectly_supports", "Indirectly"],
  ["does_not_support", "Does not support"],
  ["contradicts", "Contradicts"],
  ["unclear", "Unclear"],
];
const DECISIONS = [
  ["", "— record decision —"],
  ["accept", "Accept as supporting reference"],
  ["accepted_with_caution", "Accept with caution"],
  ["needs_second_review", "Needs second review"],
  ["reject", "Reject candidate"],
];
// engine connection statuses that count as healthy (capabilities.ConnectionState)
const HEALTHY = ["connected", "configured", "available", "ok"];
const STATE_CLASS = { oo: "s-oo", o: "s-o", r: "s-r", d: "s-d" };
const PICO = [["population_fit", "P"], ["intervention_fit", "I"], ["outcome_fit", "O"], ["claim_fit", "Claim"]];
const fitLabel = (n) => n >= 7 ? "Strong" : n >= 4 ? "Moderate" : n >= 1 ? "Weak" : "None";

const state = { claims: [], activeClaim: null, claim: null, candIdx: 0, lastTxn: null };

async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.message || data.error || `HTTP ${res.status}`);
  return data;
}

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ---- health + claim list ---- */
async function loadHealth() {
  const dot = document.querySelector("#health");
  try {
    const h = await api("GET", "/api/health");
    const conns = h.connections || {};
    const ok = Object.values(conns).some((s) => HEALTHY.includes(s));
    dot.className = "dot " + (ok ? "ok" : "off");
    dot.title = "engine: " + Object.entries(conns).map(([k, v]) => `${k}=${v}`).join(", ");
  } catch (e) { dot.className = "dot off"; dot.title = "panel API unreachable"; }
}

async function loadClaims() {
  const box = document.querySelector("#claimlist");
  try {
    const data = await api("GET", "/api/claims");
    state.claims = data.claims || [];
  } catch (e) { box.innerHTML = `<div class="err">${esc(e.message)}</div>`; return; }
  if (!state.claims.length) { box.innerHTML = `<div class="empty">No claims yet. Add them from the chat (propose_claim) or the CLI.</div>`; return; }
  box.innerHTML = state.claims.map((c) => {
    const active = c.claim_id === state.activeClaim ? " active" : "";
    const sc = STATE_CLASS[c.code] || "";
    return `<div class="claimrow ${sc}${active}" data-id="${esc(c.claim_id)}">
      <span class="code">[${esc(c.code || "  ")}]</span>
      <span class="ctext" title="${esc(c.claim_text)}">${esc(c.claim_text)}</span></div>`;
  }).join("");
}

/* ---- claim card ---- */
async function selectClaim(id) {
  const sameClaim = id === state.activeClaim;
  state.activeClaim = id;
  if (!sameClaim) { state.candIdx = 0; resetWriteState(); }   // keep the candidate in view when refreshing the same claim
  await loadClaims();
  try { state.claim = await api("GET", `/api/claims/${encodeURIComponent(id)}`); }
  catch (e) { document.querySelector("#card").innerHTML = `<div class="err">${esc(e.message)}</div>`; return; }
  renderCard();
}

function activeCandidate() {
  const cands = (state.claim && state.claim.candidates) || [];
  return cands[state.candIdx] || null;
}

function renderCard() {
  const card = document.querySelector("#card");
  if (!state.claim) return;
  const claim = state.claim.claim;
  const cands = state.claim.candidates || [];
  const cand = activeCandidate();
  if (!cand) {
    card.innerHTML = `<div class="lbl">Claim</div><div class="claimline">“${esc(claim.claim_text)}”</div>
      <div class="empty">No candidate evidence linked yet. Search and link candidates from the chat (pubmed_search → link_candidates).</div>`;
    return;
  }
  const picker = cands.length > 1
    ? `<div class="lbl">Candidate (${cands.length})</div><div class="candpick">` +
      cands.map((c, i) => `<button class="pick${i === state.candIdx ? " active" : ""}" data-cand="${i}">${esc(c.pmid || c.title || ("#" + (i + 1)))}</button>`).join("") + `</div>` : "";
  const ident = [cand.pmid && `PMID ${cand.pmid}`, cand.doi && `DOI ${cand.doi}`, cand.year].filter(Boolean).join(" · ");
  const rating = cand.rating;
  const ev = cand.evidence || {};
  const rated = !!(rating && rating.human);

  card.innerHTML = `
    <div class="lbl">Claim · ${esc(claim.claim_type)}</div>
    <div class="claimline">“${esc(claim.claim_text)}”</div>
    ${picker}
    <div class="lbl">Candidate paper</div>
    <div class="paper">${esc(cand.title || "(untitled)")}</div>
    <div class="meta">${esc(cand.journal || "")} ${ident ? "· " + esc(ident) : ""}</div>
    ${cand.abstract
      ? `<div class="lbl">Abstract — read this before you rate</div><div class="excerpt">${esc(cand.abstract)}</div>`
      : `<div class="note">No abstract stored for this paper. Read it in the chat or open the source before rating.</div>`}
    ${cand.why_found ? `<div class="meta">${esc(cand.why_found)}</div>` : ""}

    <div class="lbl">Your rating (blind — record before the chat reveals the AI)</div>
    <div class="rating-btns" id="ratebtns">
      ${SUPPORT.map(([v, label]) => {
        const chosen = rating && rating.human === v ? " chosen" : "";
        const disabled = rated ? " disabled" : "";
        return `<button class="rate-btn${chosen}" data-rate="${v}"${disabled}>${label}</button>`;
      }).join("")}
    </div>
    ${rated ? "" : fitInputs()}
    ${rated ? "" : `<div class="note">The AI rating stays hidden until you record yours.</div>`}
    ${picoChips(ev)}

    ${renderStatus(rating)}
    ${renderDecisionAndWrite(rating)}
    <div class="err" id="cardErr"></div>`;
}

function fitInputs() {
  // optional PICO + claim fit (0 poor / 1 partial / 2 good), recorded WITH your rating
  const opt = (id) => `<select id="${id}"><option value="">–</option><option value="0">0</option><option value="1">1</option><option value="2">2</option></select>`;
  return `<div class="row"><span class="lbl" style="margin:0">PICO fit (optional)</span>
    ${PICO.map(([k, lab]) => `<label class="fitlab">${lab} ${opt("fit_" + k)}</label>`).join("")}</div>`;
}

function picoChips(ev) {
  if (!ev || !ev.fit) return "";   // only after the human records fit (blinding-safe)
  const chips = PICO.map(([k, lab]) => {
    const v = ev.fit[k];
    const cls = v == null ? "" : (v >= 2 ? "ok" : (v >= 1 ? "" : "no"));
    return `<span class="check ${cls}">${lab} ${v == null ? "–" : v}</span>`;
  }).join("");
  const tot = ev.fit_total;
  const cit = tot == null ? "" : `<span class="tag">Citation fit ${fitLabel(tot)} (${tot}/8)</span>`;
  const exc = ev.excerpt ? `<div class="excerpt">${esc(ev.excerpt)}</div>` : "";
  return `<div class="lbl">Fit checks</div><div class="checks">${chips} ${cit}</div>${exc}`;
}

function renderStatus(rating) {
  if (!rating) return "";
  const aiCell = rating.human
    ? `<b>${esc(rating.ai ?? "—")}</b>`
    : `<span class="blinded">hidden until you rate</span>`;
  const cmp = rating.comparison_status;
  const cmpTag = cmp
    ? `<span class="tag ${cmp === "concordant" ? "concordant" : (cmp === "discordant" ? "discordant" : "")}">${esc(cmp)}</span>`
    : "—";
  const adj = (cmp === "discordant" && !rating.final_value && rating.human)
    ? `<div class="row"><input type="text" id="adjReason" placeholder="adjudication rationale" />
        <select id="adjValue">${SUPPORT.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select>
        <button class="btn ghost" id="adjBtn">Adjudicate</button></div>` : "";
  return `<div class="statusbox">
    <div class="statusrow"><span>Your rating</span><b>${esc(rating.human ?? "—")}</b></div>
    <div class="statusrow"><span>AI rating</span>${aiCell}</div>
    <div class="statusrow"><span>Agreement</span>${cmpTag}</div>
    <div class="statusrow"><span>Final</span><b>${esc(rating.final_value ?? "—")}</b></div>
    ${adj}</div>`;
}

function renderDecisionAndWrite(rating) {
  if (!rating || !rating.human) return "";
  return `<div class="section">
    <div class="lbl">Decision &amp; Zotero write</div>
    <div class="row">
      <select id="decSel">${DECISIONS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select>
      <input type="text" id="decReason" placeholder="reason (audited)" />
      <button class="btn ghost" id="decBtn">Record</button>
    </div>
    <div class="row">
      <button class="btn ghost" id="previewBtn">Preview write</button>
      <button class="btn primary" id="commitBtn" disabled>Confirm &amp; add to Zotero</button>
      <button class="btn ghost" id="undoBtn"${state.lastTxn ? "" : " disabled"}>Undo last</button>
    </div>
    <div class="note" id="writeNote"></div>
  </div>`;
}

/* ---- actions ---- */
async function ensureRatingId(cand) {
  if (cand.rating && cand.rating.rating_id) return cand.rating.rating_id;
  const r = await api("POST", "/api/ratings/start",
    { claim_id: state.activeClaim, candidate_id: cand.candidate_id });
  return r.rating_id;
}

function gatherFit() {
  const fit = {};
  for (const [k] of PICO) {
    const el = document.querySelector("#fit_" + k);
    if (el && el.value !== "") fit[k] = +el.value;
  }
  return Object.keys(fit).length ? fit : undefined;
}

async function rate(value) {
  const cand = activeCandidate(); if (!cand) return;
  try {
    const rid = await ensureRatingId(cand);
    await api("POST", `/api/ratings/${encodeURIComponent(rid)}/human`, { value, fit: gatherFit() });
    // re-fetch so the report-derived PICO fit + citation-fit appear (same claim → candIdx kept)
    await selectClaim(state.activeClaim);
  } catch (e) { showErr(e.message); }
}

async function adjudicate() {
  const cand = activeCandidate(); if (!cand || !cand.rating) return;
  const final_value = document.querySelector("#adjValue").value;
  const rationale = document.querySelector("#adjReason").value.trim();
  try {
    cand.rating = await api("POST", `/api/ratings/${encodeURIComponent(cand.rating.rating_id)}/adjudicate`,
      { final_value, rationale });
    renderCard();
  } catch (e) { showErr(e.message); }
}

// Write state is per (claim, candidate). Switching either MUST clear the pending
// decision + approval token so a preview/commit can never run against a stale one.
let pendingDecisionId = null;
let approvalToken = null;
function resetWriteState() {
  pendingDecisionId = null;
  approvalToken = null;
  const c = document.querySelector("#commitBtn");
  if (c) c.disabled = true;
}

async function recordDecision() {
  const cand = activeCandidate(); if (!cand || !cand.rating) return;
  const final_decision = document.querySelector("#decSel").value;
  const decision_reason = document.querySelector("#decReason").value.trim();
  if (!final_decision) { showErr("pick a decision"); return; }
  if (!decision_reason) { showErr("a decision reason is required — it is recorded in the audit trail"); return; }
  try {
    const d = await api("POST", "/api/decisions", {
      claim_id: state.activeClaim, candidate_id: cand.candidate_id,
      final_decision, decision_reason, rating_id: cand.rating.rating_id,
    });
    pendingDecisionId = d.decision_id;
    note(`decision recorded: ${d.final_decision}. Preview the write next.`);
    await selectClaim(state.activeClaim);
  } catch (e) { showErr(e.message); }
}

async function previewWrite() {
  if (!pendingDecisionId) { showErr("record a decision first"); return; }
  try {
    const p = await api("POST", "/api/writes/preview", { decision_id: pendingDecisionId });
    approvalToken = p.approval_token;
    document.querySelector("#commitBtn").disabled = !approvalToken;
    note(`preview: ${JSON.stringify(p.proposed_changes)} — dedupe ${p.dedupe_status}. Confirm to write.`);
  } catch (e) { showErr(e.message); }
}

async function commitWrite() {
  if (!pendingDecisionId || !approvalToken) { showErr("preview first"); return; }
  try {
    const r = await api("POST", "/api/writes/commit",
      { decision_id: pendingDecisionId, approval_token: approvalToken });
    if (r.status === "committed") {
      state.lastTxn = r.transaction_id; approvalToken = null;
      note(`written. transaction ${r.transaction_id}. Undo available.`);
      await selectClaim(state.activeClaim);
    } else { showErr(`write not committed: ${r.error_code || r.status}`); }
  } catch (e) { showErr(e.message); }
}

async function undoWrite() {
  if (!state.lastTxn) return;
  try {
    const r = await api("POST", "/api/writes/undo", { transaction_id: state.lastTxn });
    note(`undone: removed ${(r.deleted_keys || []).join(", ") || "0 items"}.`);
    state.lastTxn = null; await selectClaim(state.activeClaim);
  } catch (e) { showErr(e.message); }
}

function showErr(msg) { const el = document.querySelector("#cardErr"); if (el) el.textContent = msg; }
function note(msg) { const el = document.querySelector("#writeNote"); if (el) el.textContent = msg; }

/* ---- events ---- */
document.addEventListener("click", (e) => {
  const row = e.target.closest(".claimrow");
  if (row) return void selectClaim(row.dataset.id);
  const pick = e.target.closest("[data-cand]");
  if (pick) { state.candIdx = +pick.dataset.cand; resetWriteState(); return renderCard(); }
  const rb = e.target.closest("[data-rate]");
  if (rb && !rb.disabled) return void rate(rb.dataset.rate);
  if (e.target.id === "adjBtn") return void adjudicate();
  if (e.target.id === "decBtn") return void recordDecision();
  if (e.target.id === "previewBtn") return void previewWrite();
  if (e.target.id === "commitBtn") return void commitWrite();
  if (e.target.id === "undoBtn") return void undoWrite();
  if (e.target.id === "reload") return void loadClaims();
});

const ORDER = () => state.claims.map((c) => c.claim_id);
document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, textarea, select")) return;
  const ids = ORDER(); if (!ids.length) return;
  const i = ids.indexOf(state.activeClaim);
  if (e.key === "j" || e.key === "ArrowDown") { selectClaim(ids[Math.min(i + 1, ids.length - 1)]); e.preventDefault(); }
  if (e.key === "k" || e.key === "ArrowUp") { selectClaim(ids[Math.max(i - 1, 0)]); e.preventDefault(); }
});

document.querySelector("#theme").addEventListener("click", () => {
  document.documentElement.classList.toggle("zs-dark");
  document.querySelector("#theme").textContent =
    document.documentElement.classList.contains("zs-dark") ? "◐ Light" : "◑ Dark";
});

/* ---- boot ---- */
loadHealth();
loadClaims();
