/* CiteVahti panel — review card: edit-claim, evidence history, the post-rating lexical
 * check, and the audit print. Part of the card (see card.js). */

function toggleEditClaim() {
  const box = $("#claimEdit"); if (!box) return;
  if (box.innerHTML) { return cancelEditClaim(); }
  const claim = state.claim && state.claim.claim; if (!claim) return;
  state.pendingDocToken = null;
  const resolved = state.view && state.view.mode === "file";
  const ta = `<textarea id="editClaimText" class="revbox" aria-label="Edit claim text">${esc(claim.claim_text)}</textarea>`;
  const note = resolved
    ? `<div class="note">CiteVahti backs up the manuscript file first and the edit is undoable.</div>`
    : `<div class="note">Your document isn't open, so this saves the new wording to your ledger (recorded as a revision). Open your document to also update the manuscript file.</div>`;
  const act = resolved
    ? `<button class="btn primary" data-act="claimedit-preview">Preview change</button>`
    : `<button class="btn primary" data-act="claimedit-save">Save claim</button>`;
  box.innerHTML = `<div class="claimeditor"><div class="lbl">Edit the claim</div>${ta}${note}
    <div class="actions">${act}<button class="btn ghost" data-act="claimedit-cancel">Cancel</button></div></div>`;
  const t = $("#editClaimText"); if (t) t.focus();
}
function cancelEditClaim() { state.pendingDocToken = null; const b = $("#claimEdit"); if (b) b.innerHTML = ""; }

async function editClaimPreview() {
  const replacement = (($("#editClaimText") || {}).value || "").trim();
  if (!replacement) { showErr("Type the new wording first."); return; }
  try {
    const p = await api("POST", "/api/document/preview-edit",
                        { claim_id: state.activeClaim, kind: "revise", replacement });
    state.pendingDocToken = p.token;
    const box = $("#claimEdit");
    box.innerHTML = `<div class="claimeditor"><div class="lbl">Preview change</div>
      <div id="claimEditDiff"></div>
      <div class="actions"><button class="btn primary" data-act="claimedit-commit">Confirm &amp; save</button>
        <button class="btn ghost" data-act="claimedit-cancel">Cancel</button></div></div>`;
    renderDiff(p.diff, "#claimEditDiff");
  } catch (e) { showErr(e.message); }
}
async function editClaimCommit() {
  if (!state.pendingDocToken) return;
  try {
    const r = await api("POST", "/api/document/commit-edit", { token: state.pendingDocToken });
    state.docTxn = r.transaction_id; state.pendingDocToken = null;
    await loadManuscript(state.activeMs);     // refresh the prose with the new wording
    await selectClaim(state.activeClaim);     // refresh the card's claim text
    loadAudit();                              // the revision appended an audit entry
  } catch (e) { showErr(e.message); }
}
async function editClaimSaveLedger() {
  const replacement = (($("#editClaimText") || {}).value || "").trim();
  if (!replacement) { showErr("Type the new wording first."); return; }
  try {
    await api("POST", `/api/claims/${encodeURIComponent(state.activeClaim)}/revise`, { replacement });
    await loadManuscripts();                  // claim text changed across the list + view
    await selectClaim(state.activeClaim);
  } catch (e) { showErr(e.message); }
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
    const conflictTag = r.contradiction ? `<span class="tag stale">⚠ may contradict</span>` : "";
    // a deterministic, inspectable "may contradict" hint — shows the negation cue
    // that flipped polarity and the opposing sentence; advisory, never a verdict
    const conflict = r.contradiction
      ? `<div class="polconflict">⚠ A passage may contradict the claim${r.polarity_cue ? ` — negation cue: <strong>“${esc(r.polarity_cue)}”</strong>` : ""}. Review before deciding.`
        + (r.opposing_quote ? `<div class="note">“${esc(r.opposing_quote)}”</div>` : "") + `</div>`
      : "";
    box.innerHTML = `<div class="checks">${tag}${conflictTag}<span class="fittag">coverage ${Math.round(r.coverage * 100)}%</span></div>`
      + conflict
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
    <div class="actions" style="margin-top:10px">
      <button class="btn ghost" data-act="print-audit" title="Open a printable report of this claim's audit trail">🖨 Print report</button></div>
  </div></details>`;
}

/* a clean, printable audit report for the active claim: the claim text, every
 * decision + Zotero write with who/when/reason, and the chain-verified status.
 * Opens in a new window and triggers the browser's print dialog (→ PDF or paper). */
function printAudit() {
  const h = state.history, claim = state.claim && state.claim.claim;
  if (!h || !claim) return;
  const rows = [];
  for (const d of (h.decisions || [])) rows.push({ at: d.at,
    text: `Decision: ${d.final_decision}${d.final_support_status ? " · " + d.final_support_status : ""} — ${d.decided_by}${d.agreement_status ? " · " + d.agreement_status : ""}`,
    sub: d.reason || "" });
  for (const t of (h.transactions || [])) rows.push({ at: t.at,
    text: `Zotero write: ${t.status}${t.keys ? " · " + (Array.isArray(t.keys) ? t.keys.join(", ") : t.keys) : ""}`,
    sub: t.undone_at ? "undone " + timeShort(t.undone_at) : "" });
  rows.sort((a, b) => String(a.at || "").localeCompare(String(b.at || "")));
  const chain = state.audit ? (state.audit.intact ? "verified ✓" : "⚠ TAMPERED") : "not checked";
  const esc2 = (s) => esc(String(s == null ? "" : s));
  const body = `<h1>CiteVahti — claim audit report</h1>
    <p class="meta">Ledger: ${esc2(state.ctx && state.ctx.root)}<br>Manuscript: ${esc2(claim.manuscript_location || state.activeMs)}
      <br>Claim id: ${esc2(claim.claim_id)} &nbsp; · &nbsp; Audit chain: ${chain}</p>
    <h2>Claim</h2><blockquote>${esc2(claim.claim_text)}</blockquote>
    <h2>Trail (${rows.length})</h2>
    <table><thead><tr><th>When</th><th>Event</th><th>Detail</th></tr></thead><tbody>
    ${rows.map((r) => `<tr><td class="t">${esc2(r.at)}</td><td>${esc2(r.text)}</td><td>${esc2(r.sub)}</td></tr>`).join("")}
    </tbody></table>
    <p class="foot">Printed from the CiteVahti panel. The audit chain is append-only; "verified ✓" means the recorded hash chain is intact.</p>`;
  const w = window.open("", "_blank");
  if (!w) { showErr("Pop-up blocked — allow pop-ups to print the report."); return; }
  w.document.write(`<!doctype html><meta charset=utf-8><title>CiteVahti audit — ${esc2(claim.claim_id)}</title>
    <style>body{font:14px/1.5 -apple-system,Segoe UI,sans-serif;color:#111;max-width:760px;margin:32px auto;padding:0 20px}
    h1{font-size:18px}h2{font-size:14px;margin-top:22px;border-bottom:1px solid #ccc;padding-bottom:4px}
    .meta{color:#555;font-size:12px}blockquote{border-left:3px solid #6B4E9E;margin:0;padding:6px 14px;background:#f5f1fc}
    table{width:100%;border-collapse:collapse;font-size:12px}th,td{text-align:left;border-bottom:1px solid #e2e2e7;padding:6px 8px;vertical-align:top}
    td.t{white-space:nowrap;color:#555;font-family:ui-monospace,Menlo,monospace}.foot{color:#777;font-size:11px;margin-top:24px}</style>
    ${body}`);
  w.document.close(); w.focus(); w.print();
}
