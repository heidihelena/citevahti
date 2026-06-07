/* CiteVahti inline review (ADR-0002/0007) — the default panel, wired to the
 * loopback API. The review happens inside the manuscript: claim spans are
 * highlighted in place; an action-first card walks one obvious next step at a time
 * (Rate → Reveal → Decide → Write). Blinding is enforced server-side — the API
 * never returns the AI rating until a human rating exists, so this UI cannot
 * reveal it early. Zotero writes and document edits are previewed then confirmed,
 * and undoable. Connect actions store secrets via the engine; keys never round-trip
 * back to the browser. */

const SUPPORT = [
  ["directly_supports", "Directly supports"],
  ["partially_supports", "Partially supports"],
  ["indirectly_supports", "Indirectly supports"],
  ["does_not_support", "Does not support"],
  ["contradicts", "Contradicts"],
  ["unclear", "Unclear"],
];
const SUP_LABEL = Object.fromEntries(SUPPORT.map(([v, l]) => [v, l]));
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
const PICO = [["population_fit", "P"], ["intervention_fit", "I"], ["outcome_fit", "O"], ["claim_fit", "Claim"]];
const fitWord = (n) => n >= 7 ? "Strong" : n >= 4 ? "Moderate" : n >= 1 ? "Weak" : "None";

const state = {
  ctx: null, health: null, manuscripts: [], activeMs: null, view: null,
  activeClaim: null, claim: null, candIdx: 0, done: new Set(),
  lastTxn: null, docTxn: null, pendingDocToken: null,
};

async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const base = data.message || data.error || `HTTP ${res.status}`;
    throw new Error(data.remediation ? `${base} — ${data.remediation}` : base);
  }
  return data;
}
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const $ = (sel) => document.querySelector(sel);

/* ---------- boot ---------- */
async function boot() {
  drawLogos();
  try { state.ctx = await api("GET", "/api/context"); }
  catch (e) { $("#card").innerHTML = `<div class="err">panel API unreachable: ${esc(e.message)}</div>`; return; }
  renderLedger();
  await loadHealth();
  loadAudit();
  if (!state.ctx.claim_total) return renderFirstRun();
  await loadManuscripts();
  applyDeepLink();
}

// Optional URL hooks so a specific review state can be linked or screenshotted:
//   ?focus=<claim_id>   open that claim's card   ?legend=1   open the legend
function applyDeepLink() {
  const q = new URLSearchParams(location.search);
  const focus = q.get("focus");
  if (focus && claimOrder().includes(focus)) selectClaim(focus);
  if (q.get("legend") === "1") {
    $("#legend").removeAttribute("hidden");
    $("#legendBtn").setAttribute("aria-expanded", "true");
  }
}

async function loadHealth() {
  try { state.health = await api("GET", "/api/health"); } catch { state.health = null; }
  renderConns();
}

async function loadAudit() {
  try { state.audit = await api("GET", "/api/audit/verify"); } catch { state.audit = null; }
  renderAuditBadge();
}
function renderAuditBadge() {
  const el = $("#auditBadge"); if (!el) return;
  const a = state.audit;
  if (!a) { el.className = "auditbadge"; el.textContent = ""; return; }
  el.className = "auditbadge " + (a.intact ? "ok" : "bad");
  el.textContent = a.intact ? `⛓ audit ✓ ${a.entries}` : "⛓ audit ⚠ tampered";
}

async function loadManuscripts() {
  const data = await api("GET", "/api/manuscripts");
  state.manuscripts = data.manuscripts || [];
  state.ctx.manuscripts_dir = data.manuscripts_dir;
  state.activeMs = state.activeMs || (state.manuscripts[0] && state.manuscripts[0].manuscript_id);
  if (state.activeMs) await loadManuscript(state.activeMs);
  renderMsBar();
}

async function loadManuscript(id) {
  state.activeMs = id;
  state.view = await api("GET", `/api/manuscript/${encodeURIComponent(id)}`);
  $("#msName").textContent = id;
  renderDoc(); renderProgress();
}

/* ---------- header ---------- */
function renderLedger() { $("#ledger").textContent = state.ctx ? state.ctx.root : ""; }

function renderConns() {
  const conns = (state.health && state.health.connections) || {};
  const zoteroOk = HEALTHY.includes(conns.zotero_local_api) || HEALTHY.includes(conns.zotero_write_key);
  const canWrite = (state.health && state.health.can_write || []).length > 0;
  const pubmedOk = HEALTHY.includes(conns.pubmed_ncbi) || HEALTHY.includes(conns.ncbi_api_key);
  const chip = (key, label, ok) =>
    `<span class="conn ${ok ? "ok" : "off"}" data-connect="${key}"><span class="led"></span>${label}${ok ? "" : " — connect"}</span>`;
  $("#conns").innerHTML = chip("zotero", "Zotero", canWrite) + chip("pubmed", "PubMed", pubmedOk);
}

function renderMsBar() {
  const picks = state.manuscripts.map((m) =>
    `<button class="mspick${m.manuscript_id === state.activeMs ? " active" : ""}" data-ms="${esc(m.manuscript_id)}">
      ${esc(m.manuscript_id)} · ${m.claim_count}${m.resolved ? "" : " · unbound"}</button>`).join("");
  const dir = state.ctx.manuscripts_dir || "";
  const bind = `<span class="bind"><button class="chip-btn" id="addClaim">＋ Claim</button>
    <input id="bindDir" type="text" placeholder="manuscripts folder…" value="${esc(dir)}" />
    <button class="chip-btn" id="bindBtn">Bind folder</button></span>`;
  $("#msbar").innerHTML = picks + bind;
}

const CLAIM_TYPES = ["effectiveness", "diagnostic_accuracy", "prognosis", "risk_factor",
  "mechanism", "background", "guideline_recommendation", "implementation", "other"];

/* add a claim from the panel — prefilled with any text selected in the manuscript,
 * so you can highlight a sentence and mark it as a claim without the chat/CLI. */
function toggleAddClaim() {
  const box = $("#addClaimBox");
  if (box.innerHTML) { box.innerHTML = ""; return; }
  const sel = (window.getSelection && String(window.getSelection())) || "";
  box.innerHTML = `<div class="addclaim">
    <div class="lbl">New claim ${state.activeMs ? "in " + esc(state.activeMs) : ""}</div>
    <textarea id="newClaimText" class="revbox" placeholder="claim text — or select a sentence in the manuscript first">${esc(sel)}</textarea>
    <div class="row">
      <select id="newClaimType">${CLAIM_TYPES.map((t) => `<option>${t}</option>`).join("")}</select>
      <button class="btn primary" data-act="save-claim">Add claim</button>
      <button class="btn ghost" data-act="cancel-claim">Cancel</button>
    </div></div>`;
  const ta = $("#newClaimText"); if (ta) ta.focus();
}
async function saveClaim() {
  const text = (($("#newClaimText") || {}).value || "").trim();
  const type = ($("#newClaimType") || {}).value || "other";
  if (!text) { alert("enter the claim text first"); return; }
  try {
    const r = await api("POST", "/api/claims", { claim_text: text, claim_type: type,
      manuscript_id: state.activeMs, manuscript_location: state.activeMs });
    $("#addClaimBox").innerHTML = "";
    await loadManuscripts();
    if (r.claim_id) await selectClaim(r.claim_id);
  } catch (e) { alert("Add claim failed: " + e.message); }
}

/* ---------- manuscript document ---------- */
function renderDoc() {
  const v = state.view, doc = $("#doc");
  if (!v) { doc.innerHTML = ""; return; }
  const states = v.claim_states || {};
  const html = (v.segments || []).map((seg) => {
    if (seg.kind === "text") return esc(seg.text);
    const st = states[seg.claim_id] || {};
    const decided = isDecided(st.state);                 // hue once a verdict exists (any non-pending state)
    const cls = decided ? (STATE_CLASS[st.code] || "pending") : "pending";
    const code = decided && st.code ? `[${st.code.padEnd(2)}]` : "[··]";
    const active = seg.claim_id === state.activeClaim ? " active" : "";
    const aria = decided ? ({ oo: "accepted", o: "accept with caution", r: "needs review", d: "rejected" }[st.code] || "decided") : "pending";
    return `<span class="claim ${cls}${active}" data-claim="${esc(seg.claim_id)}" tabindex="0" role="button" aria-label="${esc("claim " + aria + ": " + seg.text)}">${esc(seg.text)}<span class="code" aria-hidden="true">${esc(code)}</span></span>`;
  }).join("");
  doc.innerHTML = html;
  if (v.mode === "reconstructed") {
    doc.insertAdjacentHTML("beforebegin", "");
    $("#doc").innerHTML = `<div class="recon-note">Reconstructed from claim text — bind the manuscripts folder above to review claims inside the real prose.</div>` + html;
  }
  // unmatched claims (file mode): show as a side list so none are lost
  const un = (v.unmatched || []);
  $("#unmatched").innerHTML = un.length
    ? `<div class="uhead">Claims not located in the source (${un.length})</div>` +
      un.map((id) => `<div class="urow" data-claim="${esc(id)}">${esc((states[id] || {}).code ? "[" + states[id].code + "]" : "[··]")} ${esc(id)}</div>`).join("")
    : "";
}

function renderProgress() {
  const states = (state.view && state.view.claim_states) || {};
  const ids = claimOrder();                              // document order, same as j/k
  const decidedId = (id) => isDecided((states[id] || {}).state);
  const decided = ids.filter(decidedId).length;
  const segs = ids.map((id) => {
    const cls = decidedId(id) ? "done" : "";
    const cur = id === state.activeClaim ? " current" : "";
    return `<span class="seg ${cls}${cur}" data-claim="${esc(id)}"></span>`;
  }).join("");
  $("#progress").innerHTML = `<div class="bar">${segs}</div>
    <span class="tally"><b>${ids.length - decided}</b> pending · <b>${decided}</b> decided · <b>${ids.length}</b> claims</span>`;
}

/* Claim ids in DOCUMENT order (the order they appear in the manuscript), then any
 * unmatched claims. This — not claim_states' ledger order — drives j/k navigation
 * and auto-advance, so moving between claims follows what the eye sees. */
function claimOrder() {
  const v = state.view; if (!v) return [];
  const seen = new Set(), order = [];
  for (const seg of (v.segments || [])) {
    if (seg.kind === "claim" && !seen.has(seg.claim_id)) { seen.add(seg.claim_id); order.push(seg.claim_id); }
  }
  for (const id of (v.unmatched || [])) if (!seen.has(id)) { seen.add(id); order.push(id); }
  // catch-all: any claim in the group not placed above (e.g. a span dropped for
  // overlap) is still reachable rather than stranded.
  for (const id of Object.keys(v.claim_states || {})) if (!seen.has(id)) { seen.add(id); order.push(id); }
  return order;
}

/* ---------- claim card ---------- */
async function selectClaim(id) {
  const sameClaim = id === state.activeClaim;
  state.activeClaim = id;
  if (!sameClaim) { state.candIdx = 0; resetWrite(); }   // keep the candidate in view on a same-claim refresh
  renderDoc(); renderProgress();
  try { state.claim = await api("GET", `/api/claims/${encodeURIComponent(id)}`); }
  catch (e) { $("#card").innerHTML = `<div class="err">${esc(e.message)}</div>`; return; }
  try { state.history = await api("GET", `/api/claims/${encodeURIComponent(id)}/history`); }
  catch { state.history = null; }
  renderCard();
}
function activeCand() { return (state.claim && state.claim.candidates || [])[state.candIdx] || null; }
function phaseOf(cand) {
  const r = cand && cand.rating, ev = cand && cand.evidence;
  const key = state.activeClaim + ":" + (cand && cand.candidate_id);
  if (state.done.has(key)) return "done";
  if (!r || !r.human) return "rate";
  if (!ev || !ev.decision_id) return "decide";
  return "write";
}

function stepper(active) {
  const steps = [["rate", "Rate"], ["reveal", "Reveal"], ["decide", "Decide"], ["write", "Write"]];
  const idx = { rate: 0, reveal: 1, decide: 2, write: 3, done: 4 }[active];
  return `<div class="stepper">` + steps.map(([k, label], i) => {
    const cls = i < idx ? "done" : i === idx ? "current" : "";
    const arrow = i < steps.length - 1 ? `<span class="arrow"></span>` : "";
    return `<span class="step ${cls}"><span class="num">${i < idx ? "✓" : i + 1}</span>${label}</span>${arrow}`;
  }).join("") + `</div>`;
}

function renderCard() {
  const card = $("#card");
  if (!state.claim) return;
  const claim = state.claim.claim;
  const cands = state.claim.candidates || [];
  const cand = activeCand();
  const picker = cands.length > 1
    ? `<div class="lbl">Candidate (${cands.length})</div><div class="candpick">` +
      cands.map((c, i) => `<button class="pick${i === state.candIdx ? " active" : ""}" data-cand="${i}">${esc(c.pmid || c.title || ("#" + (i + 1)))}</button>`).join("") + `</div>` : "";
  if (!cand) {
    card.innerHTML = `<div class="lbl">Claim · ${esc(claim.claim_type || "")}</div>
      <div class="claimline">“${esc(claim.claim_text)}”</div>
      <div class="note">No candidate evidence linked yet — find and link one below.</div>
      ${searchBlock()}<div class="err" id="cardErr"></div>`;
    renderAgent("rate", claim, null);
    return;
  }
  const ph = phaseOf(cand);
  let block;
  if (ph === "rate") block = rateBlock(cand);
  else if (ph === "decide") block = decideBlock(cand);
  else if (ph === "write") block = writeBlock(claim, cand);
  else block = doneBlock(cand);
  card.innerHTML = stepper(ph) +
    `<div class="lbl">Claim · ${esc(claim.claim_type || "")}</div><div class="claimline">“${esc(claim.claim_text)}”</div>` +
    picker + candidateTags(cand) + block + contextBlock(cand) + lexCheckBlock(ph) + historyBlock() + finderMore() + `<div class="err" id="cardErr"></div>`;
  renderAgent(ph, claim, cand);
}

/* deterministic lexical sanity check — only AFTER the blind rating, so it can't
 * bias it. Reuses the engine's content-token overlap (same logic as claim_check). */
function lexCheckBlock(ph) {
  if (ph === "rate") return "";
  return `<details class="context"><summary>Lexical check (deterministic)</summary><div class="body">
    <div class="why">Whether the claim's key terms appear in the candidate's abstract. A deterministic sanity check shown only after your rating — it never asserts truth.</div>
    <div class="actions"><button class="btn ghost" data-act="lexcheck">Run lexical check</button></div>
    <div id="lexResult"></div></div></details>`;
}
async function runLexCheck() {
  const cand = activeCand(); if (!cand) return;
  const box = $("#lexResult"); if (box) box.innerHTML = `<div class="note">checking…</div>`;
  try {
    const r = await api("POST", "/api/claim-check", { claim_id: state.activeClaim, candidate_id: cand.candidate_id });
    if (!r.available) { box.innerHTML = `<div class="note">No abstract text to check against.</div>`; return; }
    const tag = r.status === "terms_present"
      ? `<span class="tag ok">terms present</span>` : `<span class="tag nodoi">key terms missing</span>`;
    box.innerHTML = `<div class="checks">${tag}<span class="fittag">coverage ${Math.round(r.coverage * 100)}%</span></div>`
      + (r.missing.length ? `<div class="lbl">Not in the abstract</div><div class="note">${esc(r.missing.join(", "))}</div>` : "")
      + (r.present.length ? `<div class="lbl">Present</div><div class="note">${esc(r.present.join(", "))}</div>` : "");
  } catch (e) { box.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
}

const timeShort = (t) => t ? String(t).replace("T", " ").slice(0, 16) : "";

/* the auditable trail: every decision and Zotero write for this claim, with
 * who/when and (for writes) whether it was undone. Read-only. */
function historyBlock() {
  const h = state.history;
  if (!h || (!(h.decisions || []).length && !(h.transactions || []).length)) return "";
  const rows = [];
  for (const d of h.decisions) rows.push({ at: d.at,
    text: `Decision: ${d.final_decision}${d.final_support_status ? " · " + d.final_support_status : ""}`
        + ` — ${d.decided_by}${d.agreement_status ? " · " + d.agreement_status : ""}`,
    sub: d.reason || "" });
  for (const t of h.transactions) rows.push({ at: t.at,
    text: `Zotero write: ${t.status}${t.keys ? " · " + (Array.isArray(t.keys) ? t.keys.join(", ") : t.keys) : ""}`,
    sub: t.undone_at ? "undone " + timeShort(t.undone_at) : "" });
  rows.sort((a, b) => String(a.at || "").localeCompare(String(b.at || "")));
  const chain = state.audit ? (state.audit.intact ? " · chain verified ✓" : " · ⚠ chain tampered") : "";
  return `<details class="context"><summary>Audit trail (${rows.length})${chain}</summary><div class="body">
    ${rows.map((r) => `<div class="auditrow"><span class="atime">${esc(timeShort(r.at))}</span>
      <div class="acell"><div>${esc(r.text)}</div>${r.sub ? `<div class="note">${esc(r.sub)}</div>` : ""}</div></div>`).join("")}
  </div></details>`;
}

/* at-a-glance status for the active candidate: whether it's already in the Zotero
 * library (the write would dedupe-skip) and whether it has a DOI. */
function candidateTags(cand) {
  if (!cand) return "";
  const t = [];
  if (cand.retracted) t.push(`<span class="tag retracted">⚠ RETRACTED</span>`);
  if (cand.already_in_zotero) t.push(`<span class="tag inzot">✓ in Zotero</span>`);
  t.push(cand.doi ? `<span class="tag ok">DOI ✓</span>` : `<span class="tag nodoi">no DOI</span>`);
  return `<div class="ctags">${t.join("")}
    <button class="chip-btn" data-act="open-zotero" title="Open this reference's PDF in Zotero">Open in Zotero ↗</button></div>`;
}
async function openInZotero(cand) {
  if (!cand) return;
  try {
    const r = await api("POST", "/api/zotero/locate", { doi: cand.doi, title: cand.title, pmid: cand.pmid });
    if (!r.found) { alert("This reference isn't in your Zotero library yet."); return; }
    // trigger the zotero:// handler without navigating the panel away
    const a = document.createElement("a");
    a.href = `zotero://open-pdf/library/items/${r.key}`;
    a.click();
  } catch (e) { alert("Open in Zotero failed: " + e.message); }
}

/* find evidence: search PubMed or the Zotero library, then link a result as a
 * candidate — so the panel no longer sends you to the chat to attach evidence. */
function searchBlock() {
  return `<div class="finder">
    <div class="row">
      <input type="text" id="searchQ" placeholder="search terms…" />
      <select id="searchSrc"><option value="pubmed">PubMed</option><option value="openalex">OpenAlex</option><option value="semanticscholar">Semantic Scholar</option><option value="zotero">Zotero library</option></select>
      <button class="btn primary" data-act="search">Search</button>
    </div>
    <div id="searchResults" class="results"></div>
  </div>`;
}
function finderMore() {
  return `<details class="context"><summary>＋ Find more evidence</summary><div class="body">${searchBlock()}</div></details>`;
}

function rateBlock(cand) {
  const r = cand.rating;
  const btns = SUPPORT.map(([v, l], i) => {
    const chosen = r && r.human === v ? " chosen" : "";
    return `<button class="rate-btn${chosen}" data-rate="${v}"><span class="hk">${i + 1}</span>${l}</button>`;
  }).join("");
  const fit = `<div class="fitrow"><span class="lbl" style="margin:0">Optional PICO fit</span>` +
    PICO.map(([k, lab]) => `<label class="fitlab">${lab}<select data-fit="${k}"><option value="">–</option><option>0</option><option>1</option><option>2</option></select></label>`).join("") + `</div>`;
  return `<div class="next"><div class="ask">Your blind support rating</div>
    <div class="why">Press <kbd>1</kbd>–<kbd>6</kbd> or click. The AI second rating stays hidden until yours is recorded.</div>
    <div class="rates">${btns}</div>${fit}</div>`;
}

function decideBlock(cand) {
  const r = cand.rating;
  const cmp = r.comparison_status || (r.ai ? "—" : "");
  const decBtns = DECISIONS.map(([v, l, g]) => `<button class="btn ghost" data-decide="${v}">${l} <span class="hk">[${g}]</span></button>`).join("");
  const adj = (cmp === "discordant" && !r.final_value)
    ? `<div class="note">You and the AI disagree — your decision adjudicates; the reason is audited.</div>` : "";
  return `<div class="next"><div class="ask">Reveal &amp; decide</div>
    <div class="why">Your blind rating is in. Here is the AI second rating.</div>
    <div class="compare">
      <div class="col you"><div class="who">You</div><div class="val">${esc(SUP_LABEL[r.human] || r.human)}</div></div>
      <div class="col"><div class="who">AI (2nd)</div><div class="val">${esc(SUP_LABEL[r.ai] || r.ai || "—")}</div></div>
    </div>
    ${cmp ? `<span class="verdict-tag ${cmp}">${esc(cmp)}</span>` : ""}
    <div class="lbl">Record the verdict</div>
    <div class="decrow"><input type="text" id="decReason" placeholder="reason (recorded in the audit trail)" /></div>
    <div class="actions">${decBtns}</div>${adj}</div>`;
}

// A plain line stating where a Zotero write will land + under what permission,
// shown before the user previews/commits. Library id is an identifier, not a secret.
function writeTargetLine() {
  const t = (state.health && state.health.write_target) || null;
  if (!t || !t.available) return "";
  const backend = { zotero_web_api: "Zotero Web API", better_bibtex: "Better BibTeX",
    zotero_local: "Zotero local" }[t.backend] || t.backend || "Zotero";
  const lib = t.zotero_library ? `library ${esc(String(t.zotero_library))}` : "your personal library";
  const perm = (t.permissions && t.permissions.personal_library) || "item creation only";
  return `<div class="target"><b>This write targets:</b> ${lib} via ${esc(backend)}.
    <span class="dim">Permission: ${esc(perm)}.</span></div>`;
}

function writeBlock(claim, cand) {
  const code = (cand.evidence && cand.evidence.final_decision) || "";
  const canWrite = (state.health && state.health.can_write || []).length > 0;
  const head = `<div class="ask">Decision: ${esc((cand.evidence && cand.evidence.final_decision) || "recorded")}</div>`;
  // Accept / caution → Zotero write gate (or connect prompt if no write backend)
  if (code === "accept" || code === "accepted_with_caution") {
    if (!canWrite) {
      return `<div class="next">${head}
        <div class="connect"><div class="ask">Connect Zotero to enable this write</div>
          <div class="actions"><button class="btn primary" data-act="connect-zotero-oauth">Connect with Zotero (OAuth)</button></div>
          <div class="note">Opens Zotero in a tab; authorize and you're connected — no key to copy.</div>
          <div class="lbl" style="margin-top:10px">— or paste a key —</div>
          <input id="zoteroKey" type="password" placeholder="Zotero API key (write access)" />
          <div class="actions"><button class="btn ghost" data-act="connect-zotero">Use this key</button>
            <a class="btn ghost" href="https://www.zotero.org/settings/keys/new" target="_blank" rel="noopener">Get a key</a></div>
          <div class="note">Either way the key is stored in your OS keychain — it never returns to this page.</div></div></div>`;
    }
    const target = writeTargetLine();
    let body, note = "";
    if (!state.pendingZtoken) {
      body = `<div class="actions"><button class="btn primary" data-act="zpreview">Preview write <span class="hk">↵</span></button></div>`;
      note = `${target}<div class="why">Nothing is written to Zotero yet. Preview the change first.</div>`;
    } else {
      body = `<div class="actions"><button class="btn primary" data-act="zcommit">Confirm &amp; add to Zotero <span class="hk">↵</span></button>
        <button class="btn ghost" data-act="zcancel">Cancel</button></div>`;
      note = `<div class="note ok" id="writeNote">${esc(state.previewNote || "")}</div>`;
    }
    return `<div class="next">${head}${note}${body}</div>`;
  }
  // revise → author the new wording + write it to the .md; reject → strike the claim
  if (code === "needs_second_review" || code === "reject") {
    const kind = code === "reject" ? "strike" : "revise";
    const verb = code === "reject" ? "Strike the claim in the document" : "Rewrite the claim and apply it to the document";
    // revise: an editable box pre-filled with the current wording (or a pending proposal)
    const editor = kind === "revise" && !state.pendingDocToken
      ? `<div class="lbl">New wording</div><textarea id="revText" class="revbox">${esc(claim.proposed_revision || claim.claim_text)}</textarea>` : "";
    let body;
    if (!state.pendingDocToken) {
      body = `<div class="actions"><button class="btn primary" data-act="docpreview" data-kind="${kind}">Preview ${kind} <span class="hk">↵</span></button></div>`;
    } else {
      body = `<div id="docDiff"></div><div class="actions">
        <button class="btn primary" data-act="doccommit">Confirm &amp; write to .md <span class="hk">↵</span></button>
        <button class="btn ghost" data-act="doccancel">Cancel</button></div>`;
    }
    return `<div class="next">${head}<div class="why">${verb}. CiteVahti backs up the file first and the edit is undoable.</div>${editor}${body}</div>`;
  }
  return `<div class="next">${head}<div class="note">Decision recorded.</div></div>`;
}

function doneBlock(cand) {
  const code = (cand.evidence && cand.evidence.final_decision) || "";
  const what = { accept: "Added to Zotero", accepted_with_caution: "Added with caution",
    needs_second_review: "Manuscript revised", reject: "Claim struck in document" }[code] || "Recorded";
  const undo = state.lastTxn ? `<button class="btn ghost" data-act="zundo">Undo Zotero write</button>`
    : state.docTxn ? `<button class="btn ghost" data-act="docundo">Undo document edit</button>` : "";
  return `<div class="next"><div class="done-banner">✓ ${what} — recorded with an undo path.</div>
    <div class="actions">${undo}<button class="btn primary" data-act="next">Next claim <span class="hk">↵</span></button></div></div>`;
}

function contextBlock(cand) {
  const ev = cand.evidence || {};
  const ident = [cand.pmid && `PMID ${cand.pmid}`, cand.doi && `DOI ${cand.doi}`, cand.year].filter(Boolean).join(" · ");
  const picks = ev.fit ? PICO.map(([k, lab]) => {
    const val = ev.fit[k]; const cls = val == null ? "" : (val >= 2 ? "ok" : val >= 1 ? "" : "no");
    return `<span class="check ${cls}">${lab} ${val == null ? "–" : val}</span>`;
  }).join("") : "";
  const cit = ev.fit_total == null ? "" : `<span class="fittag">Citation fit ${fitWord(ev.fit_total)} (${ev.fit_total}/8)</span>`;
  return `<details class="context" open><summary>Evidence &amp; fit checks</summary><div class="body">
    <div class="lbl">Candidate source</div><div class="paper">${esc(cand.title || "(untitled)")}</div>
    <div class="note">${esc(cand.journal || "")} ${ident ? "· " + esc(ident) : ""}</div>
    ${cand.abstract ? `<div class="lbl">Abstract</div><div class="excerpt">${esc(cand.abstract)}</div>` : ""}
    ${ev.excerpt ? `<div class="lbl">Supporting excerpt</div><div class="excerpt">${esc(ev.excerpt)}</div>` : ""}
    ${picks || cit ? `<div class="lbl">Fit checks</div><div class="checks">${picks}${cit}</div>` : ""}
    <div class="actions" style="margin-top:10px"><button class="btn ghost" data-act="zot-evidence">Show Zotero highlights &amp; full text</button></div>
    <div id="zotEvidence"></div>
  </div></details>`;
}

/* the paper's own highlights (PDF annotations) + an indexed full-text snippet,
 * read on demand from Zotero. Content to read while rating — not an AI opinion. */
async function openZotEvidence() {
  const cand = activeCand(); if (!cand) return;
  const box = $("#zotEvidence"); if (!box) return;
  box.innerHTML = `<div class="note">Loading from Zotero…</div>`;
  try {
    const r = await api("POST", "/api/zotero/evidence", { doi: cand.doi, title: cand.title, pmid: cand.pmid });
    if (!r.found) { box.innerHTML = `<div class="note">Not in your Zotero library.</div>`; return; }
    const anns = (r.annotations || []).filter((a) => a.text || a.comment);
    let html = "";
    if (anns.length) html += `<div class="lbl">Your highlights (${anns.length})</div>` + anns.map((a) =>
      `<div class="excerpt">${esc(a.text || "")}${a.comment ? ` <span class="note">— ${esc(a.comment)}</span>` : ""}${a.page ? ` <span class="note">p.${esc(a.page)}</span>` : ""}</div>`).join("");
    if (r.fulltext) html += `<div class="lbl">Full text (indexed)</div><div class="excerpt ftsnip">${esc(r.fulltext)}</div>`;
    box.innerHTML = html || `<div class="note">In your library, but no highlights or indexed full text.</div>`;
  } catch (e) { box.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
}

function renderAgent(ph, claim, cand) {
  const code = cand && cand.evidence && cand.evidence.final_decision;
  const lines = {
    rate: `Read the evidence, then record your blind rating. I will not show my rating until yours is in — that gate is enforced by the engine, not by me.`,
    decide: (cand && cand.rating && cand.rating.comparison_status === "discordant")
      ? `We disagree. You decide; I am advisory only. Your reason is audited.`
      : `Record the verdict to continue — every Zotero write and document edit is previewed and undoable.`,
    write: code === "reject" || code === "needs_second_review"
      ? `I propose the document edit as a diff. Confirm to write it to the .md — I back up the file and it stays undoable.`
      : `Decision-gated Zotero write. Preview first; nothing is written silently.`,
    done: `Done and logged with an undo path. Press ↵ for the next claim.`,
  };
  $("#agent").innerHTML = `<span class="who">CiteVahti ▸</span> <span class="pill">${esc(lines[ph] || "")}</span>`;
}

/* ---------- actions ---------- */
function resetWrite() { state.pendingZtoken = null; state.previewNote = ""; state.pendingDocToken = null; }
function showErr(m) { const e = $("#cardErr"); if (e) { e.textContent = m; e.scrollIntoView({ block: "nearest" }); } }

async function ensureRatingId(cand) {
  if (cand.rating && cand.rating.rating_id) return cand.rating.rating_id;
  const r = await api("POST", "/api/ratings/start", { claim_id: state.activeClaim, candidate_id: cand.candidate_id });
  return r.rating_id;
}
function gatherFit() {
  const fit = {};
  for (const [k] of PICO) { const el = $(`[data-fit="${k}"]`); if (el && el.value !== "") fit[k] = +el.value; }
  return Object.keys(fit).length ? fit : undefined;
}
async function rate(value) {
  const cand = activeCand(); if (!cand) return;
  try {
    const rid = await ensureRatingId(cand);
    await api("POST", `/api/ratings/${encodeURIComponent(rid)}/human`, { value, fit: gatherFit() });
    await selectClaim(state.activeClaim);
  } catch (e) { showErr(e.message); }
}
async function recordDecision(v) {
  const cand = activeCand(); if (!cand || !cand.rating) return;
  const field = $("#decReason");
  const reason = (field && field.value || "").trim();
  if (!reason) {                                  // flag the field IN PLACE — not a hidden error at the card foot
    if (field) { field.classList.add("need"); field.placeholder = "reason required — recorded in the audit trail"; field.focus(); }
    return;
  }
  if (field) field.classList.remove("need");
  try {
    await api("POST", "/api/decisions", { claim_id: state.activeClaim, candidate_id: cand.candidate_id,
      final_decision: v, decision_reason: reason.trim(), rating_id: cand.rating.rating_id });
    await loadManuscript(state.activeMs);   // refresh span colour
    await selectClaim(state.activeClaim);
    loadAudit();                            // a decision appended an audit entry
  } catch (e) { showErr(e.message); }
}
async function zpreview() {
  const cand = activeCand(); const decId = cand && cand.evidence && cand.evidence.decision_id;
  if (!decId) return showErr("no decision to write");
  try {
    const p = await api("POST", "/api/writes/preview", { decision_id: decId });
    state.pendingZtoken = p.approval_token;
    state.previewNote = `Preview: ${JSON.stringify(p.proposed_changes)} — dedupe ${p.dedupe_status}. Confirm to write.`;
    renderCard();
  } catch (e) { showErr(e.message); }
}
async function zcommit() {
  const cand = activeCand(); const decId = cand && cand.evidence && cand.evidence.decision_id;
  try {
    const r = await api("POST", "/api/writes/commit", { decision_id: decId, approval_token: state.pendingZtoken });
    if (r.status === "committed") { state.lastTxn = r.transaction_id; markDone(cand); }
    else showErr(`write not committed: ${r.error_code || r.status}`);
  } catch (e) { showErr(e.message); }
}
async function zundo() {
  if (!state.lastTxn) return;
  try { await api("POST", "/api/writes/undo", { transaction_id: state.lastTxn }); state.lastTxn = null; unmarkDone(); }
  catch (e) { showErr(e.message); }
}
async function docPreview(kind) {
  // for a revise, send the wording the human typed; strike needs no replacement
  const replacement = kind === "revise" ? (($("#revText") || {}).value || "").trim() : undefined;
  if (kind === "revise" && !replacement) { showErr("type the new wording first"); return; }
  try {
    const p = await api("POST", "/api/document/preview-edit", { claim_id: state.activeClaim, kind, replacement });
    state.pendingDocToken = p.token; renderCard(); renderDiff(p.diff);
  } catch (e) { showErr(e.message); }
}
function renderDiff(diff) {
  const box = $("#docDiff"); if (!box) return;
  box.className = "diff";
  box.innerHTML = (diff || "").split("\n").filter((l) => !l.startsWith("---") && !l.startsWith("+++") && !l.startsWith("@@"))
    .map((l) => { const cls = l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : "ctx"; return `<div class="dl ${cls}">${esc(l)}</div>`; }).join("");
}
async function docCommit() {
  try {
    const r = await api("POST", "/api/document/commit-edit", { token: state.pendingDocToken });
    state.docTxn = r.transaction_id; markDone(activeCand());
  } catch (e) { showErr(e.message); }
}
async function docUndo() {
  if (!state.docTxn) return;
  try { await api("POST", "/api/document/undo-edit", { transaction_id: state.docTxn }); state.docTxn = null; await loadManuscript(state.activeMs); unmarkDone(); }
  catch (e) { showErr(e.message); }
}
function markDone(cand) {
  state.done.add(state.activeClaim + ":" + (cand && cand.candidate_id));
  resetWrite(); state.pendingZtoken = null; renderCard();
  loadAudit();                              // a Zotero/document write appended an audit entry
}
function unmarkDone() {
  const cand = activeCand(); state.done.delete(state.activeClaim + ":" + (cand && cand.candidate_id)); renderCard();
}
function nextPending() {
  const states = (state.view && state.view.claim_states) || {};
  const ids = claimOrder(); const i = ids.indexOf(state.activeClaim);
  for (let k = 1; k <= ids.length; k++) {
    const id = ids[(i + k) % ids.length];
    if (!isDecided((states[id] || {}).state)) return id;   // next not-yet-decided claim
  }
  return null;
}

async function connect(which) {
  try {
    let health;
    if (which === "zotero") {
      // use the inline write-step field if present, else prompt (header chip / first-run)
      let key = ($("#zoteroKey") || {}).value || "";
      if (!key.trim()) key = (prompt("Paste your Zotero API key (needs write access):") || "");
      if (!key.trim()) return;
      const r = await api("POST", "/api/connect/zotero", { api_key: key.trim() });
      health = r.health;
    } else {
      const email = prompt("Your NCBI / PubMed contact email (required by NCBI):");
      if (!email) return;
      const apiKey = prompt("NCBI API key (optional — raises your rate limit):") || undefined;
      const r = await api("POST", "/api/connect/pubmed", { email, api_key: apiKey });
      health = r.health;
    }
    state.health = health || state.health;
    renderConns();
    const canWrite = (state.health && state.health.can_write || []).length > 0;
    if (which === "zotero" && !canWrite)
      alert("Zotero key accepted but no write access detected — check the key has write permission to your library.");
    if (state.activeClaim) renderCard();
  } catch (e) {
    // surface the real reason (bad key, no write scope, network) instead of failing silently
    alert("Connect " + which + " failed: " + e.message);
  }
}

async function connectOAuth() {
  try {
    const r = await api("POST", "/api/connect/zotero/oauth/start", { callback_base: location.origin });
    window.open(r.authorize_url, "_blank", "noopener");
    // the callback stores the key in the other tab; poll health until write turns on
    let tries = 0;
    const iv = setInterval(async () => {
      tries++;
      await loadHealth();
      const ok = (state.health && state.health.can_write || []).length > 0;
      if (ok || tries > 40) { clearInterval(iv); if (ok && state.activeClaim) renderCard(); }
    }, 2000);
  } catch (e) { alert("Zotero OAuth: " + e.message); }
}

async function doSearch() {
  const q = (($("#searchQ") || {}).value || "").trim();
  const src = ($("#searchSrc") || {}).value || "pubmed";
  if (!q) return;
  const box = $("#searchResults"); if (box) box.innerHTML = `<div class="note">Searching ${esc(src)}…</div>`;
  try {
    const r = await api("POST", "/api/search", { query: q, source: src });
    state.searchBatch = r.batch_id;
    if (!r.hits || !r.hits.length) { if (box) box.innerHTML = `<div class="note">No results.</div>`; return; }
    if (box) box.innerHTML = r.hits.map((h) => {
      const meta = [h.journal, h.year, h.pmid && ("PMID " + h.pmid), h.doi && ("DOI " + h.doi)].filter(Boolean).join(" · ");
      const inzot = h.dedupe_status === "already_in_library" ? `<span class="tag inzot">in Zotero</span>` : "";
      return `<div class="result"><div class="rmeta"><b>${esc(h.title || "(untitled)")}</b> ${inzot}
        <div class="note">${esc(meta)}</div></div>
        <button class="btn ghost" data-link="${esc(h.record_id)}">Link</button></div>`;
    }).join("");
  } catch (e) { if (box) box.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
}
async function linkRecord(recordId) {
  if (!state.searchBatch) return;
  try {
    await api("POST", "/api/link", { claim_id: state.activeClaim, batch_id: state.searchBatch, record_ids: [recordId] });
    state.searchBatch = null;
    await selectClaim(state.activeClaim);   // reload the card with the newly linked candidate
  } catch (e) { showErr(e.message); }
}

/* ---------- first-run / empty-state ---------- */
async function renderFirstRun() {
  let ledgers = [];
  try { ledgers = (await api("GET", "/api/ledgers")).ledgers || []; } catch {}
  const others = ledgers.filter((l) => l.claims > 0 && l.root !== state.ctx.root);
  const rows = ledgers.map((l) =>
    `<div class="ledrow"><span class="path">${esc(l.root)}</span><span class="n">${l.claims} claims</span>
      ${l.root !== state.ctx.root && l.claims > 0 ? `<button class="btn ghost" data-switch="${esc(l.root)}">Switch here</button>` : (l.root === state.ctx.root ? `<span class="note">active</span>` : "")}</div>`).join("");
  $("#split").innerHTML = `<div class="firstrun">
    <div class="beta-banner"><b>CiteVahti is in beta — free to use.</b> Free for testing, research
      feedback, and early development. Pricing for hosted and advanced features may be introduced
      later; a free local/community version is intended to remain available.</div>
    <h2>No claims in this ledger yet</h2>
    <p class="note">Active ledger: <b>${esc(state.ctx.root)}</b> — it has no claims. ${others.length ? "Another ledger does:" : ""}</p>
    <div class="panel-box">${rows || '<div class="note">No other ledgers found.</div>'}</div>
    <div class="panel-box">
      <div class="lbl">Start from a manuscript</div>
      <p class="note">Paste your manuscript Markdown — CiteVahti saves it and binds the
      folder. Claim extraction runs in your chat client (the panel never calls an AI),
      so you'll get the exact prompt to paste there next.</p>
      <input id="pasteName" type="text" placeholder="filename, e.g. my-draft.md" />
      <textarea id="pasteBody" class="revbox" placeholder="# Title&#10;&#10;Paste your Markdown here…"></textarea>
      <div class="actions"><button class="btn primary" id="pasteSave">Save &amp; bind</button></div>
      <div id="pasteResult"></div>
    </div>
    <div class="panel-box">
      <div class="lbl">…or add claims directly</div>
      <p class="note">From your chat client run the <b>run_claim_tests</b> prompt, or use the CLI:
      <br><code>citevahti claim-add --text "…" --type interpretation</code></p>
      <div class="lbl">Connect sources</div>
      <div class="actions">
        <button class="btn ghost" data-connect="zotero">Connect Zotero</button>
        <button class="btn ghost" data-connect="pubmed">Connect PubMed</button>
      </div>
    </div></div>`;
}

async function savePastedManuscript() {
  const filename = (($("#pasteName") || {}).value || "").trim();
  const content = ($("#pasteBody") || {}).value || "";
  const out = $("#pasteResult");
  if (!filename) { out.innerHTML = `<div class="note">Give the file a name first.</div>`; return; }
  if (!content.trim()) { out.innerHTML = `<div class="note">Paste some Markdown first.</div>`; return; }
  try {
    const r = await api("POST", "/api/manuscripts/paste", { filename, content });
    out.innerHTML = `<div class="note ok">Saved <b>${esc(r.filename)}</b> and bound
      <code>${esc(r.manuscripts_dir)}</code>.</div>
      <div class="lbl" style="margin-top:8px">Next: extract claims in your chat client</div>
      <p class="note">Paste this prompt to CiteVahti over MCP — the panel will fill in
      once claims are staged:</p>
      <textarea class="revbox" readonly onclick="this.select()">${esc(r.next_prompt)}</textarea>`;
  } catch (e) { out.innerHTML = `<div class="note">${esc(e.message)}</div>`; }
}

/* ---------- events ---------- */
document.addEventListener("click", (e) => {
  const sw = e.target.closest("[data-switch]"); if (sw) return switchRoot(sw.dataset.switch);
  const cn = e.target.closest("[data-connect]"); if (cn) return void connect(cn.dataset.connect);
  const ms = e.target.closest("[data-ms]"); if (ms) return void loadManuscript(ms.dataset.ms).then(renderMsBar);
  if (e.target.id === "bindBtn") return void bindFolder();
  if (e.target.id === "pasteSave") return void savePastedManuscript();
  if (e.target.id === "addClaim") return void toggleAddClaim();
  const sp = e.target.closest("[data-claim]"); if (sp) return void selectClaim(sp.dataset.claim);
  const cp = e.target.closest("[data-cand]"); if (cp) { state.candIdx = +cp.dataset.cand; resetWrite(); return renderCard(); }
  const rb = e.target.closest("[data-rate]"); if (rb) return void rate(rb.dataset.rate);
  const dc = e.target.closest("[data-decide]"); if (dc) return void recordDecision(dc.dataset.decide);
  const lk = e.target.closest("[data-link]"); if (lk) return void linkRecord(lk.dataset.link);
  const act = e.target.closest("[data-act]"); if (!act) return;
  ({ "connect-zotero": () => connect("zotero"), "connect-zotero-oauth": connectOAuth, search: doSearch,
     "open-zotero": () => openInZotero(activeCand()), "zot-evidence": openZotEvidence, lexcheck: runLexCheck,
     "save-claim": saveClaim, "cancel-claim": () => { $("#addClaimBox").innerHTML = ""; },
     zpreview, zcommit, zcancel: () => { resetWrite(); renderCard(); },
     zundo, docpreview: () => docPreview(act.dataset.kind), doccommit: docCommit, doccancel: () => { resetWrite(); renderCard(); },
     docundo: docUndo, next: () => { const n = nextPending(); if (n) selectClaim(n); } }[act.dataset.act] || (() => {}))();
});
$("#reload").addEventListener("click", () => { loadManuscripts(); loadAudit(); });
$("#auditBadge").addEventListener("click", () => loadAudit());
$("#legendBtn").addEventListener("click", () => {
  const el = $("#legend"), opening = el.hasAttribute("hidden");
  el.toggleAttribute("hidden");
  $("#legendBtn").setAttribute("aria-expanded", String(opening));
});
async function maintenance(path, label, fmt) {
  try {
    const r = await api("POST", path, {});
    alert(fmt(r));
    await loadManuscripts();
    if (state.activeClaim) await selectClaim(state.activeClaim);
  } catch (e) { alert(`${label} failed: ${e.message}`); }
}
$("#resolveDois").addEventListener("click", () =>
  maintenance("/api/candidates/resolve-dois", "Resolve DOIs",
              (r) => `Resolved ${r.resolved || 0} missing DOI(s) from PMIDs.`));
$("#recheckLib").addEventListener("click", () =>
  maintenance("/api/candidates/recheck-library", "Re-check library",
              (r) => `Checked ${r.checked || 0} candidate(s); ${r.flagged || 0} now flagged as already in Zotero.`));
$("#scanRetractions").addEventListener("click", () =>
  maintenance("/api/candidates/scan-retractions", "Scan retractions",
              (r) => `Checked ${r.checked || 0} candidate(s); ${r.flagged || 0} flagged as RETRACTED.`));
$("#theme").addEventListener("click", () => {
  document.documentElement.classList.toggle("zs-dark");
  $("#theme").textContent = document.documentElement.classList.contains("zs-dark") ? "◐ Light" : "◑ Dark";
});
document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, textarea, select")) return;
  const ids = claimOrder(); if (!ids.length) return;   // document order, matching the eye
  const i = ids.indexOf(state.activeClaim);
  if (e.key === "j" || e.key === "ArrowDown") { selectClaim(ids[Math.min(i + 1, ids.length - 1)]); return e.preventDefault(); }
  if (e.key === "k" || e.key === "ArrowUp") { selectClaim(ids[Math.max(i - 1, 0)]); return e.preventDefault(); }
  const cand = activeCand();
  if (cand && phaseOf(cand) === "rate" && /^[1-6]$/.test(e.key)) { rate(SUPPORT[+e.key - 1][0]); return e.preventDefault(); }
  if (e.key === "Enter") { const p = primary(); if (p) { p(); e.preventDefault(); } }
});
function primary() {
  const cand = activeCand(); if (!cand) return null;
  const ph = phaseOf(cand), code = cand.evidence && cand.evidence.final_decision;
  if (ph === "write") {
    if (code === "accept" || code === "accepted_with_caution") return state.pendingZtoken ? zcommit : zpreview;
    if (code === "needs_second_review") return state.pendingDocToken ? docCommit : () => docPreview("revise");
    if (code === "reject") return state.pendingDocToken ? docCommit : () => docPreview("strike");
  }
  if (ph === "done") { const n = nextPending(); return n ? () => selectClaim(n) : null; }
  return null;
}

async function bindFolder() {
  const dir = ($("#bindDir") || {}).value || "";
  if (!dir.trim()) return;
  try { await api("POST", "/api/manuscripts/bind", { dir: dir.trim() }); await loadManuscripts(); }
  catch (e) { alert(e.message); }
}
async function switchRoot(root) {
  try { await api("POST", "/api/root", { root }); location.reload(); } catch (e) { alert(e.message); }
}

function drawLogos() {
  document.querySelectorAll("[data-logo]").forEach((n) => {
    n.innerHTML = `<svg width="100%" height="100%" viewBox="0 0 64 64" fill="none" role="img" aria-label="CiteVahti">
      <g fill="currentColor"><rect x="12" y="14" width="6" height="36"/><rect x="12" y="14" width="15" height="6"/><rect x="12" y="44" width="15" height="6"/>
      <rect x="46" y="14" width="6" height="36"/><rect x="37" y="14" width="15" height="6"/><rect x="37" y="44" width="15" height="6"/></g>
      <g fill="#8B6FC9"><path d="M24 28 L29 24 L31 32 L26 35 Z"/><path d="M40 28 L35 24 L33 32 L38 35 Z"/></g></svg>`;
  });
}

boot();
