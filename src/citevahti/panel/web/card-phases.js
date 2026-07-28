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

/* What to show in the "AI (2nd)" column when there is no AI value, and why it matters.
 * Three different events would otherwise look identical (a blank column):
 *   - no AI run at all              -> nothing to say
 *   - the AI ran and abstained      -> a rating outcome: it read this and would not judge
 *   - the AI call produced no reply -> a SETUP problem: it never judged
 * The third is the one an operator has to act on, so it gets its own wording plus the fix.
 * The server derives `ai_failure` (one of AI_FAILURE_KINDS) behind the blinding rule
 * (panel/server.py); this only renders it. */
const AI_FAILURE_CELL = {
  provider_error: "no reply from the model",
  truncated_reply: "cut off before answering",
  unparseable_reply: "unreadable reply",
  out_of_vocab_value: "answered off-scale",
};

/* Each failure kind names what actually broke and what to do about it. Deliberately
 * separated from the abstention wording: an abstention is the model's judgement, these
 * are the model never reaching one — so none of them says anything about the evidence. */
const AI_FAILURE_WARN = {
  provider_error: `<b>The model could not be reached, so it never judged this item.</b>
    Check that your local model is running and that the endpoint and model name under
    <b>✦ AI</b> are right, then get the second opinion again.`,
  truncated_reply: `<b>The model was cut off, so it never judged this item.</b>
    It hit its reply-token ceiling mid-answer. A reasoning (“thinking”) model spends reply
    tokens before it answers, so it needs more headroom. Either pick a model that answers
    directly (<b>✦ AI</b> → Local model), or raise
    <span class="mono">ai_connection.max_reply_tokens</span> in this review's
    <span class="mono">.citevahti/config.json</span>, then get the second opinion again.`,
  unparseable_reply: `<b>The model's reply could not be read, so nothing was judged.</b>
    It answered, but not in the expected format. This is often intermittent — getting the
    second opinion again usually works; a model that keeps doing it is a poor fit for this task.`,
  out_of_vocab_value: `<b>The model answered outside the rating scale, so nothing was recorded.</b>
    Its answer is deliberately not mapped onto the nearest allowed rating. Try the second
    opinion again, or pick a model that follows the scale (<b>✦ AI</b> → Local model).`,
};

function aiSecondCell(r) {
  if (r.ai) return esc(SUP_LABEL[r.ai] || r.ai);
  if (r.ai_failure)
    return `<span class="aicut">${esc(AI_FAILURE_CELL[r.ai_failure] || "no rating returned")}</span>`;
  if (r.ai_abstained) return `<span class="dim">abstained — no rating given</span>`;
  return `<span class="dim">not recorded yet</span>`;
}

function aiConfigWarn(r) {
  if (!r.ai_failure) return "";
  const body = AI_FAILURE_WARN[r.ai_failure]
    || `<b>The AI call produced no rating, so this item was never judged.</b>`;
  return `<div class="configwarn" role="status">⚠ ${body} This is a setup problem, not a
    rating, and not a signal about the evidence. Your own rating stands; nothing here was
    assessed by the AI.</div>`;
}

/* The comparison status is a ledger code; the card shows a reader's label for it. */
const CMP_LABEL = { concordant: "concordant", discordant: "discordant",
  ai_abstained: "AI abstained — nothing to compare",
  ai_failed: "no AI rating — the call failed", human_only: "your rating only" };

function cmpTag(r, cmp) {
  if (!cmp) return "";
  const label = r.ai_failure
    ? "no AI rating — check AI settings" : (CMP_LABEL[cmp] || cmp);
  return `<span class="verdict-tag ${esc(cmp)}">${esc(label)}</span>`;
}

/* The offer to run CiteVahti's own (local/api) model, worded by what already happened.
 * Blinded either way: the human rating is locked before this panel renders, and the MCP
 * assistant can supply the second opinion instead.
 *
 * Once the model HAS run, "Get AI second opinion" would be a lie — it was asked, and it
 * either declined or never reached an answer. The offer stays (the operator may switch
 * model or attach full text) but it names the prior run, so a re-run is a deliberate
 * second ask rather than a first one that appears never to have happened. */
/* What a re-run is worth, per failure kind — a failed call is the one case where asking
 * the same model the same question genuinely may land differently, so unlike an
 * abstention the re-run is worth encouraging. Each note points at that kind's own fix. */
const AI_FAILURE_RETRY_NOTE = {
  provider_error: `Nothing reached the model. Once it is reachable again, re-running should work.`,
  truncated_reply: `The run above was cut off before the model answered. Change the setting named above, then re-run.`,
  unparseable_reply: `The reply could not be read. This is often intermittent — re-running usually works.`,
  out_of_vocab_value: `The answer was off the rating scale. Re-running may land in scale; a model that keeps
    missing it is the wrong model for this task.`,
};

function getAiBlock(r) {
  if (r.ai) return "";                                  // a value landed; nothing to offer
  const [label, note] = r.ai_failure
    ? ["✦ Get the second opinion again",
       AI_FAILURE_RETRY_NOTE[r.ai_failure] || `The run above produced no rating. Re-running may work.`]
    : (r.ai_present && r.ai_abstained)
      ? ["✦ Ask the AI again",
         `The AI already ran on this paper and declined to rate it. Asking the same model the
          same question is likely to land the same way — switch model in ✦ AI, or give it the
          full text, if you want a different second opinion.`]
      : ["✦ Get AI second opinion",
         `Optional. Or your assistant provides it over MCP. Configure a model in ✦ AI.`];
  return `<div class="getai">
    <button class="btn ghost" data-act="run-ai" title="Ask CiteVahti's configured local/external model for a blinded second opinion">${label}</button>
    <span class="note dim">${note}</span></div>`;
}

function decideBlock(cand) {
  const r = cand.rating;
  const cmp = r.comparison_status || (r.ai ? "—" : "");
  const decBtns = DECISIONS.map(([v, l, g]) => `<button class="btn ghost" data-decide="${v}">${l} <span class="hk">[${g}]</span></button>`).join("");
  const adj = (cmp === "discordant" && !r.final_value)
    ? `<div class="note">You and the AI disagree — your decision adjudicates; the reason is audited.</div>` : "";
  const getAi = getAiBlock(r);
  const why = r.ai ? "Your blind rating is in. Here is the AI second opinion."
    : r.ai_failure
      ? "Your blind rating is in. The AI run did not produce a second opinion — check the setup note below."
      : r.ai_abstained
        ? "Your blind rating is in. The AI ran and abstained, so there is no second opinion to compare — decide on yours."
        : "Your blind rating is in. No AI second opinion has been recorded yet — decide on yours, or get one below.";
  // The heading has to survive the same test as the button: an AI that ran and gave
  // nothing is not an AI that was never asked, so only the never-asked case may offer
  // "get an AI second opinion" as the thing left to do.
  const ask = r.ai ? "Reveal &amp; decide"
    : r.ai_failure ? "Decide — the AI run produced nothing"
      : r.ai_abstained ? "Decide — the AI declined to rate this"
        : "Decide now, or get an AI second opinion";
  return `<div class="next"><div class="ask">${ask}</div>
    <div class="why">${why}</div>
    <div class="compare">
      <div class="col you"><div class="who">You</div><div class="val">${esc(SUP_LABEL[r.human] || r.human)}</div></div>
      <div class="col${r.ai_failure ? " cut" : ""}"><div class="who">AI (2nd)</div><div class="val">${aiSecondCell(r)}</div></div>
    </div>
    ${aiConfigWarn(r)}
    ${cmpTag(r, cmp)}
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
  // The decision just recorded covers THIS source only. Say so while the reviewer is
  // still on the claim — a decision on one co-cited paper says nothing about the others,
  // and this is the moment they would otherwise move on believing the claim is settled.
  const left = undecidedCands().length;
  const head = `<div class="ask">Decision: ${esc((cand.evidence && cand.evidence.final_decision) || "recorded")}
      <span class="dim">— for this source</span></div>` + (left
    ? `<div class="note">${left} more cited source${left > 1 ? "s" : ""} on this claim ${left > 1 ? "have" : "has"} no rating or decision yet.
        <button class="linklike" data-act="next-source">Judge the next one →</button></div>` : "");
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
  // This source is finished — the CLAIM is not, if it cites others you haven't judged.
  // Offer the next unjudged source as the primary action and say how many are left, so
  // "done" can never be read as "this claim is done" when it isn't.
  const left = undecidedCands().length;
  const onward = left
    ? `<button class="btn primary" data-act="next-source">Next source (${left} left on this claim) <span class="hk">↵</span></button>
       <button class="btn ghost" data-act="next">Skip to next claim</button>`
    : `<button class="btn primary" data-act="next">Next claim <span class="hk">↵</span></button>`;
  const note = left
    ? `<div class="note">This claim cites ${left} more source${left > 1 ? "s" : ""} with no rating or decision yet.
        Support is judged per source — the claim isn't settled until each one is.</div>` : "";
  return `<div class="next"><div class="done-banner">✓ ${what} — recorded with an undo path.</div>${note}
    <div class="actions">${undo}${onward}</div></div>`;
}
