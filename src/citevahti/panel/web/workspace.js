/* CiteVahti panel — the workspace left pane: the manuscript document with inline claim
 * marks (renderDoc/renderProgress/claimOrder) and the persistent claims queue
 * (loadTriage/renderQueue). Classic script; loads before app.js. */

// Persistent claims queue. Fetches the risk-first triage, then renders a queue that is
// always present while a manuscript with claims is open — a "Needs attention" shortlist
// (worst-first) and an "All claims" view in document order. Rows carry data-claim, so the
// global click delegation selects them. Read-only; never mutates.
async function loadTriage() {
  try { state.triage = await api("GET", "/api/triage"); } catch { state.triage = null; }
  renderQueue();
}
function renderQueue() {
  const bar = $("#triagebar"); if (!bar) return;
  const ids = claimOrder();
  if (!ids.length) { bar.hidden = true; bar.innerHTML = ""; return; }
  const t = state.triage, all = !!state.queueAll;
  const states = (state.view && state.view.claim_states) || {};
  const textOf = {};
  for (const seg of ((state.view && state.view.segments) || [])) if (seg.kind === "claim") textOf[seg.claim_id] = seg.text;
  const need = t ? (t.needs_attention || 0) : 0;
  const calm = need === 0;
  const head = need
    ? `<div class="tlbl">⚠ ${need} of ${t.total} claim(s) worth your attention
        <span class="tdim">· ${t.clean} clean · risk ${t.score}/100</span></div>`
    : `<div class="tlbl ok">✓ ${ids.length} claim(s) in this manuscript — nothing flagged for attention.</div>`;
  const toggle = `<div class="qtoggle">
    <button type="button" class="qtab${all ? "" : " on"}" data-queue="attention">Needs attention${t ? ` (${need})` : ""}</button>
    <button type="button" class="qtab${all ? " on" : ""}" data-queue="all">All claims (${ids.length})</button></div>`;
  let body;
  if (!all) {
    const items = (t && t.items) || [];
    body = items.length
      ? items.map((it) => `<button type="button" class="trow" data-claim="${esc(it.claim_id)}" title="${esc(it.action || "")}">
          ${it.fatal ? '<span class="tfatal" aria-hidden="true">‼</span> ' : ""}<span class="treason">${esc(it.reason)}</span>
          <span class="tclaim">${esc((it.claim_text || textOf[it.claim_id] || "").slice(0, 72))}</span></button>`).join("")
      : `<div class="note">Nothing needs attention. Switch to <b>All claims</b> to browse the manuscript.</div>`;
  } else {
    body = `<div class="qlist">` + ids.map((id) => {
      const st = states[id] || {};
      const code = (isDecided(st.state) && st.code) ? st.code : "··";
      const active = id === state.activeClaim ? " active" : "";
      return `<button type="button" class="qrow${active}" data-claim="${esc(id)}">
        <span class="qcode ${STATE_CLASS[code] || "s-pend"}">[${esc(code.padEnd(2))}]</span>
        <span class="qtext">${esc((textOf[id] || id).slice(0, 84))}</span></button>`;
    }).join("") + `</div>`;
  }
  bar.classList.toggle("calm", calm);
  bar.innerHTML = head + toggle + body;
  bar.hidden = false;
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
    const aria = decided ? ({ oo: "accepted", o: "needs support", r: "review needed", d: "decided", u: "untestable" }[st.code] || "decided") : "pending";
    // an accepted claim is a cited passage: tag it so copying carries the citation
    const ref = st.cite ? citeOf(st.cite) : "";
    const cite = ref ? ` data-citation="${esc(ref)}"` : "";
    // advisory: an assessment predates the current wording — flag it inline
    const stale = st.has_stale_bonds
      ? `<span class="stalemark" aria-hidden="true" title="Reworded since assessed — re-check">⚠</span>` : "";
    const ariaStale = st.has_stale_bonds ? " (reworded since assessed)" : "";
    return `<span class="claim ${cls}${active}" data-claim="${esc(seg.claim_id)}"${cite} tabindex="0" role="button" aria-label="${esc("claim " + aria + ariaStale + ": " + seg.text)}">${esc(seg.text)}<span class="code" aria-hidden="true">${esc(code)}</span>${stale}</span>`;
  }).join("");
  doc.innerHTML = html;
  if (v.mode === "reconstructed") {
    doc.insertAdjacentHTML("beforebegin", "");
    $("#doc").innerHTML = `<div class="recon-note">✓ Your claims, ratings, and saved citations are stored automatically — nothing here is lost.
      Below are your saved claims. To see each one highlighted inside your original manuscript,
      <button class="linklike" id="reconOpen">📁 open your document</button>.</div>` + html;
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



/* ---------- events ---------- */
/* Citation-on-copy: copying text from a cited passage carries its source, like the
 * "read more at…" pattern. When the whole selection sits inside an element tagged with
 * data-citation (an accepted claim, or a quoted source excerpt/abstract), append the
 * reference to both clipboard formats. Self-contained — no network, no external deps. */
