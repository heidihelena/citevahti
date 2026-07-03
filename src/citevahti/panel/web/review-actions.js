/* CiteVahti panel — the review state machine: rate → decide → write actions, their
 * Zotero/document write+undo, and navigation (nextPending/goToNextClaim/primary). These
 * mutate through the token-gated, blinded engine endpoints. Part of the card. */

/* ---------- actions ---------- */
function resetWrite() { state.pendingZtoken = null; state.previewNote = ""; state.pendingDocToken = null; }

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
async function runAiSecondOpinion() {
  const cand = activeCand(); if (!cand) return;
  try {
    const rid = await ensureRatingId(cand);
    await api("POST", `/api/ratings/${encodeURIComponent(rid)}/run-ai`, {});
    await selectClaim(state.activeClaim);   // reload → the AI value reveals (human is already in)
  } catch (e) {
    // off-mode (or no model) → point to the AI settings, don't dead-end
    showErr(e.message);
  }
}
const DECISION_REASON = {
  accept: "Accepted — the cited source supports the claim",
  accepted_with_caution: "Accepted with caution — partially supported",
  needs_second_review: "Flagged for a second review",
  reject: "Rejected — the cited source does not support the claim",
};
async function recordDecision(v) {
  const cand = activeCand(); if (!cand || !cand.rating) return;
  const field = $("#decReason");
  // Reason is OPTIONAL — if you don't type one, a sensible default is recorded so the
  // audit trail stays meaningful without making you type on every decision.
  const reason = (field && field.value || "").trim() || (DECISION_REASON[v] || ("Decision: " + v));
  if (field) field.classList.remove("need");
  try {
    await api("POST", "/api/decisions", { claim_id: state.activeClaim, candidate_id: cand.candidate_id,
      final_decision: v, decision_reason: reason, rating_id: cand.rating.rating_id });
    await loadManuscript(state.activeMs);   // refresh span colour
    await selectClaim(state.activeClaim);
    loadAudit();                            // a decision appended an audit entry
  } catch (e) { showErr(e.message); }
}
// guarded remove (⇧D): unlink the wrong paper from the claim. Audited and
// non-destructive — the claim and audit trail stay; only this paper leaves.
async function unlinkCandidate() {
  const cand = activeCand(); if (!cand) return;
  const label = cand.title || cand.pmid || cand.doi || cand.candidate_id;
  if (!confirm(`Remove this paper from the claim?\n\n${label}\n\nThe claim and the audit trail are kept — this only unlinks the paper from review.`)) return;
  try {
    await api("POST", "/api/candidates/unlink", { claim_id: state.activeClaim, candidate_id: cand.candidate_id });
    state.done.delete(state.activeClaim + ":" + cand.candidate_id);   // drop stale done-state for the removed paper
    state.candIdx = 0; resetWrite(); state.lastTxn = null; state.docTxn = null;
    await loadManuscript(state.activeMs);   // refresh span colour
    await selectClaim(state.activeClaim);
    loadAudit();                            // the unlink appended an audit entry
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
  const txn = recoverableTxn();
  if (!txn) return;
  const cand = activeCand();
  try {
    await api("POST", "/api/writes/undo", { transaction_id: txn });
    state.lastTxn = null;
    state.done.delete(state.activeClaim + ":" + (cand && cand.candidate_id));
    await selectClaim(state.activeClaim);   // reload the trail: the txn now reads 'undone' and the step falls back to write
    loadAudit();
  } catch (e) { showErr(e.message); }
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
function renderDiff(diff, sel = "#docDiff") {
  const box = $(sel); if (!box) return;
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

function goToNextClaim() {
  const id = state.next && state.next.next && state.next.next.claim_id;
  if (!id) return;
  selectClaim(id);
  const span = document.querySelector(`.claim[data-claim="${cssEscape(id)}"]`);
  if (span) span.scrollIntoView({ behavior: "smooth", block: "center" });
}

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

/* The review keyboard map — registered with the global keydown listener in events.js,
 * which has already handled the modal trap, the input guard, and claim Enter/Space and
 * checked hotkeysOff. Returns true once a key is handled (so events.js preventDefaults). */
registerKeys((e) => {
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;   // letter keys are CapsLock-proof
  if (key === "?") { $("#legendBtn").click(); e.preventDefault(); return true; }              // ? help
  if (key === "u") {                                                                          // u undo last write/edit
    if (recoverableTxn()) { zundo(); e.preventDefault(); return true; }
    if (state.docTxn) { docUndo(); e.preventDefault(); return true; }
  }
  // claim navigation/rating only makes sense on the review workspace; on other surfaces
  // (Checks, Settings, …) the manuscript isn't shown, so don't move the selection underneath.
  if (state.surface !== "workspace") return false;
  const ids = claimOrder();                                  // document order, matching the eye
  if (!ids.length) {
    // Review keys with no claims to act on: a silent no-op reads as "my shortcuts are
    // broken" (it read exactly that way in the field, 2026-07-02). Say why — once.
    if (/^[jk1-7ordsa]$/.test(key) || e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!state._hintedNoClaims) {
        state._hintedNoClaims = true;
        notify("Keyboard shortcuts act on claims — this manuscript has none yet. " +
               "Run the run_claim_tests prompt in your chat, or add one with ＋ Claim.",
               { kind: "ok" });
      }
      e.preventDefault(); return true;
    }
    return false;
  }
  const i = ids.indexOf(state.activeClaim);
  if (key === "j" || e.key === "ArrowDown") { selectClaim(ids[Math.min(i + 1, ids.length - 1)]); e.preventDefault(); return true; }
  if (key === "k" || e.key === "ArrowUp") { selectClaim(ids[Math.max(i - 1, 0)]); e.preventDefault(); return true; }
  const cand = activeCand(); if (!cand) return false;
  if (e.shiftKey && key === "d") { unlinkCandidate(); e.preventDefault(); return true; }       // ⇧D guarded remove
  const ph = phaseOf(cand);
  if (ph === "rate" && /^[1-7]$/.test(e.key)) { rate(SUPPORT[+e.key - 1][0]); e.preventDefault(); return true; }   // 1–7 support rating
  if (ph === "decide") {                                                                       // verdict keys: oo / o / r / d
    if (key === "r") { recordDecision("needs_second_review"); e.preventDefault(); return true; }
    if (key === "d") { recordDecision("reject"); e.preventDefault(); return true; }            // (⇧D handled above)
    if (key === "o") {
      if (e.repeat) { e.preventDefault(); return true; }   // ignore auto-repeat so a held "o" isn't read as "oo"
      if (oTimer) { clearTimeout(oTimer); oTimer = null; recordDecision("accept"); }                         // "oo" → [oo]
      else { oTimer = setTimeout(() => { oTimer = null; recordDecision("accepted_with_caution"); }, 300); }   // "o"  → [o]
      e.preventDefault(); return true;
    }
  }
  if (ph === "write") {
    if (key === "s") {                                                                         // s stage = preview (no-op if already staged)
      if (!state.pendingZtoken && !state.pendingDocToken) {
        const code = cand.evidence && cand.evidence.final_decision;
        if (code === "needs_second_review") docPreview("revise");
        else if (code === "reject") docPreview("strike");
        else zpreview();
      }
      e.preventDefault(); return true;
    }
    if (key === "a") { const p = primary(); if (p) p(); e.preventDefault(); return true; }      // a apply / add to Zotero
  }
  if (e.key === "Enter") { const p = primary(); if (p) { p(); e.preventDefault(); return true; } }  // ↵ primary action
  return false;
});
