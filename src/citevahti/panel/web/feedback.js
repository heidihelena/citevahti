/* CiteVahti panel — user feedback surfaces: the agent footer line, inline card errors,
 * and the dismissible notification toast (replaces blocking alert()s). Classic script;
 * depends on util.js (esc, $) + state.js, so it loads after them and before app.js. */

function setAgentLine(html) {
  const el = $("#agent"); if (el) el.innerHTML = `<span class="who">CiteVahti ▸</span> <span class="pill">${html}</span>`;
}

function renderAgent(ph, claim, cand) {
  const code = cand && cand.evidence && cand.evidence.final_decision;
  const lines = {
    rate: `Read the evidence, then record your blind rating. The panel won't show my rating until yours is in, and the ledger logs the order — so your blind-first rating is on the record.`,
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

function showErr(m) { const e = $("#cardErr"); if (e) { e.textContent = m; e.scrollIntoView({ block: "nearest" }); } }

/* Inline, dismissible notification — replaces blocking alert()s. The server's error
 * payload already carries a plain "next action" remediation (api() appends it to the
 * message), so an error toast states what happened, why, and what to do — with an
 * optional Retry. `kind: "ok"` auto-dismisses; errors stay until dismissed/retried. */
function clearNotify() { const b = $("#notify"); if (b) { clearTimeout(b._t); b.hidden = true; b.innerHTML = ""; } }
function notify(msg, opts = {}) {
  const box = $("#notify"); if (!box) { return; }     // headless/fallback
  const kind = opts.kind === "ok" ? "ok" : "error";
  // success is informational — announce politely; errors interrupt (assertive).
  box.setAttribute("role", kind === "ok" ? "status" : "alert");
  box.setAttribute("aria-live", kind === "ok" ? "polite" : "assertive");
  box.innerHTML = `<div class="toast ${kind}">
    <span class="toast-msg">${esc(msg)}</span>
    ${opts.retry ? `<button class="btn ghost toast-btn" data-toast-retry="1">Retry</button>` : ""}
    <button class="toast-x" data-toast-close="1" aria-label="Dismiss" title="Dismiss">✕</button></div>`;
  box.hidden = false;
  const retry = box.querySelector("[data-toast-retry]");
  if (retry) retry.onclick = () => { clearNotify(); opts.retry(); };
  box.querySelector("[data-toast-close]").onclick = clearNotify;
  clearTimeout(box._t);
  // sticky toasts stay until the next notify()/clearNotify() (e.g. a long Pandoc fetch)
  if (kind === "ok" && !opts.sticky) box._t = setTimeout(clearNotify, 5000);
}
