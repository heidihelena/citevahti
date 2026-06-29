/* CiteVahti panel — review card phase blocks: the Rate / Decide / Write / Done panels
 * renderCard() shows per the server-provided step. Part of the card (see card.js). */

function rateBlock(cand) {
  const r = cand.rating;
  const btns = SUPPORT.map(([v, l, d], i) => {
    const chosen = r && r.human === v ? " chosen" : "";
    return `<button class="rate-btn${chosen}" data-rate="${v}" title="${esc(d)}"><span class="hk">${i + 1}</span>${l}</button>`;
  }).join("");
  const opts = `<option value="">– not scored</option>` +
    FIT_SCORES.map(([v, l]) => `<option value="${v}">${l}</option>`).join("");
  const fit = `<div class="fitblock">
    <div class="fithead"><span class="lbl" style="margin:0">Optional fit check</span>
      <details class="fithelp"><summary>?</summary>
        <div class="body">How well does this paper match the claim, on each dimension? Scored
          <b>0</b> (no/off-topic), <b>1</b> (partial/indirect) or <b>2</b> (strong/direct) — leave
          blank to skip. It's an optional note for yourself; it doesn't change the verdict.</div></details></div>
    <div class="fitrow">` +
    PICO.map(([k, lab, help]) => `<label class="fitlab" title="${esc(help)}">${lab}
      <select data-fit="${k}" aria-label="${esc(help)}">${opts}</select></label>`).join("") + `</div></div>`;
  const defs = `<details class="fithelp"><summary>What the ratings mean</summary><div class="body">` +
    SUPPORT.map(([, l, d]) => `<div><b>${l}</b> — ${esc(d)}</div>`).join("") + `</div></details>`;
  return `<div class="next"><div class="ask">Your blind support rating</div>
    <div class="why">Press <kbd>1</kbd>–<kbd>7</kbd> or click. The AI second rating stays hidden until yours is recorded.</div>
    <div class="rates">${btns}</div>${defs}${fit}</div>`;
}

function decideBlock(cand) {
  const r = cand.rating;
  const cmp = r.comparison_status || (r.ai ? "—" : "");
  const decBtns = DECISIONS.map(([v, l, g]) => `<button class="btn ghost" data-decide="${v}">${l} <span class="hk">[${g}]</span></button>`).join("");
  const adj = (cmp === "discordant" && !r.final_value)
    ? `<div class="note">You and the AI disagree — your decision adjudicates; the reason is audited.</div>` : "";
  // No AI second opinion yet → offer CiteVahti's own (local/api) run. Blinded:
  // the human rating is already locked. The MCP assistant can also provide it.
  const getAi = r.ai ? "" : `<div class="getai">
    <button class="btn ghost" data-act="run-ai" title="Ask CiteVahti's configured local/external model for a blinded second opinion">✦ Get AI second opinion</button>
    <span class="note dim">Optional. Or your assistant provides it over MCP. Configure a model in ✦ AI.</span></div>`;
  return `<div class="next"><div class="ask">${r.ai ? "Reveal &amp; decide" : "Decide now, or get an AI second opinion"}</div>
    <div class="why">${r.ai
      ? "Your blind rating is in. Here is the AI second opinion."
      : "Your blind rating is in. No AI second opinion has been recorded yet — decide on yours, or get one below."}</div>
    <div class="compare">
      <div class="col you"><div class="who">You</div><div class="val">${esc(SUP_LABEL[r.human] || r.human)}</div></div>
      <div class="col"><div class="who">AI (2nd)</div><div class="val">${r.ai ? esc(SUP_LABEL[r.ai] || r.ai) : '<span class="dim">not recorded yet</span>'}</div></div>
    </div>
    ${cmp ? `<span class="verdict-tag ${cmp}">${esc(cmp)}</span>` : ""}
    ${getAi}
    <div class="lbl">Record the verdict</div>
    <div class="decrow"><input type="text" id="decReason" aria-label="Decision reason (optional — recorded in the audit trail)" placeholder="reason — optional; a sensible default is recorded if blank" /></div>
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
          <input id="zoteroKey" type="password" aria-label="Zotero API key with write access" placeholder="Zotero API key (write access)" />
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
    const resolved = state.view && state.view.mode === "file";
    // No manuscript file bound -> the .md edit can't be applied; don't offer a Preview
    // that the server would reject. Point to the folder picker instead.
    if (!resolved) {
      const dir = esc((state.ctx && state.ctx.manuscripts_dir) || "");
      return `<div class="next">${head}
        <div class="note">Open your manuscript to apply this ${kind} — bind the folder that contains it, then preview the change. (The decision is already recorded; this only writes the wording into your <span class="mono">.md</span>.)</div>
        <div class="actions"><button class="btn primary" data-browse="${dir}">Open manuscript folder…</button></div></div>`;
    }
    // revise: an editable box pre-filled with the current wording (or a pending proposal)
    const editor = kind === "revise" && !state.pendingDocToken
      ? `<div class="lbl">New wording</div><textarea id="revText" class="revbox" aria-label="New wording">${esc(claim.proposed_revision || claim.claim_text)}</textarea>` : "";
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
  const undo = recoverableTxn() ? `<button class="btn ghost" data-act="zundo">Undo Zotero write</button>`
    : state.docTxn ? `<button class="btn ghost" data-act="docundo">Undo document edit</button>` : "";
  return `<div class="next"><div class="done-banner">✓ ${what} — recorded with an undo path.</div>
    <div class="actions">${undo}<button class="btn primary" data-act="next">Next claim <span class="hk">↵</span></button></div></div>`;
}
