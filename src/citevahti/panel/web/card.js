/* CiteVahti panel — the review card: selecting a claim and rendering its evidence +
 * decision panel (the Rate → Decide → Write → Done phase machine). Phase blocks live in
 * card-phases.js, the edit/history/lexcheck affordances in card-edit.js, and the
 * rate/decide/write actions in review-actions.js. Classic script; loads before app.js. */

/* ---------- claim card ---------- */
async function selectClaim(id) {
  // Load the claim FIRST so we know which manuscript it belongs to. A triage row or a
  // ?focus= deep-link can target a claim in a DIFFERENT manuscript than the one open
  // (each manuscript holds only a few claims — a primary outcome and a few secondary —
  // so the ledger spans several). Bring the document pane to that manuscript so the
  // highlighted prose and the claim card never desync.
  let claim;
  try { claim = await api("GET", `/api/claims/${encodeURIComponent(id)}`); }
  catch (e) { $("#card").innerHTML = `<div class="err">${esc(e.message)}</div>`; return; }
  const mid = claim.claim && claim.claim.manuscript_id;
  if (mid && mid !== state.activeMs && state.manuscripts.some((m) => m.manuscript_id === mid)) {
    await loadManuscript(mid);
  }
  const sameClaim = id === state.activeClaim;
  state.activeClaim = id;
  // A claim is selected → reveal the evidence pane (the split is single-column until now,
  // so the empty right pane never shows as a blank band).
  const sp = document.getElementById("split"); if (sp) sp.classList.add("has-detail");
  // moving to a different claim: drop the in-session write/undo/timer state so a global
  // key (u undo, the o double-tap) can't act on the claim you just navigated away from.
  // (Undo is still recoverable per-claim from the audit trail via recoverableTxn().)
  if (!sameClaim) { state.candIdx = 0; resetWrite(); state.lastTxn = null; state.docTxn = null; clearTimeout(oTimer); oTimer = null; }   // keep the candidate in view on a same-claim refresh
  state.claim = claim;
  renderDoc(); renderProgress();
  try { state.history = await api("GET", `/api/claims/${encodeURIComponent(id)}/history`); }
  catch { state.history = null; }
  renderCard();
  renderQueue();   // keep the queue's active-row highlight in sync (cheap; no refetch)
}
function activeCand() { return (state.claim && state.claim.candidates || [])[state.candIdx] || null; }
/* The committed, not-yet-undone Zotero write recorded for this candidate in the
 * claim's audit trail (per-claim, durable). Unlike state.lastTxn it survives
 * navigating away and back, so the write step — and its undo — can be recognised
 * on return. (Document edits aren't in the per-claim trail, only Zotero writes.) */
function committedZoteroTxn(cand) {
  if (!cand || !state.history) return null;
  return (state.history.transactions || []).find(
    (t) => t.candidate_id === cand.candidate_id && t.status === "committed" && !t.undone_at) || null;
}
/* The transaction the Undo button/`u` key should act on: the in-session write if
 * we just made one, else the recovered committed write for the active candidate. */
function recoverableTxn() {
  if (state.lastTxn) return state.lastTxn;
  const t = committedZoteroTxn(activeCand());
  return t ? t.transaction_id : null;
}
function phaseOf(cand) {
  const key = state.activeClaim + ":" + (cand && cand.candidate_id);
  if (state.done.has(key)) return "done";              // instant feedback right after a commit
  // the phase is computed server-side in one place (workflow.candidate_step) so every
  // surface agrees; the server already returns "done" for a committed, not-undone write.
  return (cand && cand.step && cand.step.phase) || "rate";
}

function stepper(active, hasAi) {
  // Conditional: the "AI second opinion" step only appears when an AI rating exists,
  // so the stepper never shows a "Reveal" step as done when nothing was revealed.
  const steps = hasAi
    ? [["rate", "Rate"], ["reveal", "AI second opinion"], ["decide", "Decide"], ["write", "Write"]]
    : [["rate", "Rate"], ["decide", "Decide"], ["write", "Write"]];
  const order = steps.map(([k]) => k);
  let idx = active === "done" ? steps.length : order.indexOf(active);
  if (idx === -1) idx = 0;          // 'reveal' is not a real phase; fall back to the start
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
    card.innerHTML = claimLineBlock(claim) +
      `<div class="note">No candidate evidence linked yet — find and link one below.</div>
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
  // remove is for the "wrong paper" case before a verdict is recorded; once a
  // decision exists (write/done) the engine refuses unlink, so hide it there.
  const removeRow = (ph === "rate" || ph === "decide")
    ? `<div class="removerow"><button class="btn ghost" data-act="unlink"
        title="Unlink this paper from the claim (keeps the claim and audit trail)">✕ Remove paper <span class="hk">⇧D</span></button></div>`
    : "";
  card.innerHTML = stepper(ph, !!(cand && cand.rating && cand.rating.ai_present)) + claimLineBlock(claim) +
    picker + candidateTags(cand) + removeRow + block + contextBlock(cand) + lexCheckBlock(ph) + historyBlock() + finderMore() + `<div class="err" id="cardErr"></div>`;
  renderAgent(ph, claim, cand);
}

/* the claim text + an always-available "Edit claim" action: a reviewer who reads
 * the evidence and realises the claim is overstated can reword it right here,
 * regardless of the rate/decide phase. Writes to the .md when the document is
 * open (previewed + undoable); otherwise saves the revision to the ledger. */
function claimLineBlock(claim) {
  // Advisory, non-blocking: an evidence assessment was formed against an older
  // wording of this claim. Nothing is invalidated — the human re-checks.
  const stale = claim.has_stale_bonds
    ? `<div class="stalewarn" title="A rating or decision was made against a previous wording of this claim">⚠ Claim reworded since it was assessed — re-check the evidence below.</div>`
    : "";
  return `<div class="lbl">Claim · ${esc(claimTypeLabel(claim.claim_type))}
      <button class="chip-btn tiny" data-act="edit-claim" title="Reword this claim after reading the evidence">✏ Edit claim</button></div>
    <div class="claimline">“${esc(claim.claim_text)}”</div>${stale}
    <div id="claimEdit"></div>`;
}

/* at-a-glance status for the active candidate: whether it's already in the Zotero
 * library (the write would dedupe-skip) and whether it has a DOI. */
function candidateTags(cand) {
  if (!cand) return "";
  const t = [];
  // organized-panel consensus (ADR-0008) — shown when 2+ independent reviewers rated this pair
  if (cand.panel) {
    const ag = cand.panel.raw_agreement != null ? `${Math.round(cand.panel.raw_agreement * 100)}% agree` : "";
    t.push(`<span class="tag panel" title="${cand.panel.n_raters} independent reviewers${ag ? " · " + ag : ""}">👥 ${esc(cand.panel.headline)} · ${esc(cand.panel.tier)}-level</span>`);
  }
  if (cand.retracted) t.push(`<span class="tag retracted">⚠ RETRACTED</span>`);
  if (cand.stale_bond) t.push(`<span class="tag stale" title="This paper was assessed against an older wording of the claim — re-check">⚠ claim reworded since</span>`);
  // reuse rights (licence scan): reported, never a reuse verdict. A CC licence is shown
  // plainly; a closed work is flagged neutrally; unknown shows nothing.
  if (cand.license) {
    t.push(`<span class="tag license" title="Open-access licence reported by OpenAlex — check the source's own terms before reuse">⚖ ${esc(cand.license)}</span>`);
  } else if (cand.oa_status === "closed") {
    t.push(`<span class="tag closed" title="OpenAlex reports no open licence — likely all-rights-reserved. Do not reuse without permission.">⚖ closed</span>`);
  }
  // evidence basis at rate time: be honest about what the judgment can rest on
  if (cand.evidence_basis === "abstract_only") {
    t.push(`<span class="tag abstractonly" title="You're rating against the abstract, not the full text. Confirm against the full text before relying on this citation.">◐ abstract only</span>`);
  } else if (cand.evidence_basis === "full_text") {
    t.push(`<span class="tag fulltext" title="A full-text passage is anchored to this rating.">● full-text passage</span>`);
  } else if (cand.evidence_basis === "no_text") {
    t.push(`<span class="tag notext" title="No abstract or passage staged — out of indexed scope.">○ no text staged</span>`);
  }
  if (cand.already_in_zotero) t.push(`<span class="tag inzot">✓ in Zotero</span>`);
  t.push(cand.doi ? `<span class="tag ok">DOI ✓</span>` : `<span class="tag nodoi">no DOI</span>`);
  return `<div class="ctags">${t.join("")}
    <button class="chip-btn" data-act="open-zotero" title="Open this reference's PDF in Zotero">Open in Zotero ↗</button></div>`;
}
async function openInZotero(cand) {
  if (!cand) return;
  try {
    const r = await api("POST", "/api/zotero/locate", { doi: cand.doi, title: cand.title, pmid: cand.pmid });
    if (!r.found) { notify("This reference isn't in your Zotero library yet."); return; }
    // trigger the zotero:// handler without navigating the panel away
    const a = document.createElement("a");
    a.href = `zotero://open-pdf/library/items/${r.key}`;
    a.click();
  } catch (e) { notify("Open in Zotero failed: " + e.message); }
}

/* find evidence: search PubMed or the Zotero library, then link a result as a
 * candidate — so the panel no longer sends you to the chat to attach evidence. */
function searchBlock() {
  return `<div class="finder">
    <div class="row">
      <input type="text" id="searchQ" aria-label="Search terms" placeholder="search terms…" />
      <select id="searchSrc"><option value="pubmed">PubMed</option><option value="openalex">OpenAlex</option><option value="semanticscholar">Semantic Scholar</option><option value="zotero">Zotero library</option></select>
      <button class="btn primary" data-act="search">Search</button>
    </div>
    <div id="searchResults" class="results"></div>
  </div>`;
}
function finderMore() {
  return `<details class="context"><summary>＋ Find more evidence</summary><div class="body">${searchBlock()}</div></details>`;
}

function contextBlock(cand) {
  const ev = cand.evidence || {};
  const ident = [cand.pmid && `PMID ${cand.pmid}`, cand.year].filter(Boolean).join(" · ");
  const doiLink = cand.doi
    ? `<a class="doi" href="${esc(doiUrl(cand.doi))}" target="_blank" rel="noopener" title="Open the DOI in your browser">DOI ${esc(cand.doi)} ↗</a>` : "";
  const picks = ev.fit ? PICO.map(([k, lab]) => {
    const val = ev.fit[k]; const cls = val == null ? "" : (val >= 2 ? "ok" : val >= 1 ? "" : "no");
    return `<span class="check ${cls}">${lab} ${val == null ? "–" : val}</span>`;
  }).join("") : "";
  const cit = ev.fit_total == null ? "" : `<span class="fittag">Citation fit ${fitWord(ev.fit_total)} (${ev.fit_total}/8)</span>`;
  // the abstract and supporting excerpt are verbatim source text — tag them so a copy
  // carries this candidate's citation (same data-citation hook as the claim spans)
  const dc = citeOf(cand) ? ` data-citation="${esc(citeOf(cand))}"` : "";
  return `<details class="context" open><summary>Evidence &amp; fit checks</summary><div class="body">
    <div class="lbl">Candidate source</div><div class="paper">${esc(cand.title || "(untitled)")}</div>
    <div class="note">${esc(cand.journal || "")}${ident ? " · " + esc(ident) : ""}${doiLink ? " · " + doiLink : ""}</div>
    ${cand.abstract ? `<div class="lbl">Abstract</div><div class="excerpt"${dc}>${esc(cand.abstract)}</div>` : ""}
    ${ev.excerpt ? `<div class="lbl">Supporting excerpt</div><div class="excerpt"${dc}>${esc(ev.excerpt)}</div>` : ""}
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
  box.innerHTML = loadingHTML("Loading from Zotero…");
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
