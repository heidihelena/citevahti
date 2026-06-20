/* CiteVahti inline review (ADR-0002/0007) — the default panel, wired to the
 * loopback API. The review happens inside the manuscript: claim spans are
 * highlighted in place; an action-first card walks one obvious next step at a time
 * (Rate → Reveal → Decide → Write). Blinding is enforced server-side — the API
 * never returns the AI rating until a human rating exists, so this UI cannot
 * reveal it early. Zotero writes and document edits are previewed then confirmed,
 * and undoable. Connect actions store secrets via the engine; keys never round-trip
 * back to the browser. */

const SUPPORT = [
  ["directly_supports", "Directly supports", "the paper directly supports this claim"],
  ["partially_supports", "Partially supports", "the paper supports part of this claim"],
  ["indirectly_supports", "Indirectly supports", "the paper supports this claim only indirectly"],
  ["overstated", "Overstated", "the paper supports a weaker version of this claim"],
  ["does_not_support", "Does not support", "the paper does not support this claim"],
  ["contradicts", "Contradicts", "the paper contradicts this claim"],
  ["unclear", "Unclear", "the paper's support for this claim is genuinely unclear"],
];
const SUP_LABEL = Object.fromEntries(SUPPORT.map(([v, l]) => [v, l]));
const SUP_DEF = Object.fromEntries(SUPPORT.map(([v, , d]) => [v, d]));
// Human-readable claim-type labels; the enum is stored, only the label is shown.
const CLAIM_TYPE_LABEL = {
  effectiveness: "Treatment effect", diagnostic_accuracy: "Diagnostic accuracy",
  prognosis: "Prognosis", risk_factor: "Risk factor", mechanism: "Mechanism",
  background: "Background claim", guideline_recommendation: "Guideline recommendation",
  implementation: "Implementation", other: "Other",
};
const claimTypeLabel = (t) => CLAIM_TYPE_LABEL[t] || t || "";
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
// PICO fit dimensions: key, short label, and a plain explanation of what to judge.
const PICO = [
  ["population_fit", "P", "Population — does the paper study the same people/setting the claim is about?"],
  ["intervention_fit", "I", "Intervention / exposure — does the paper test the same thing the claim is about?"],
  ["outcome_fit", "O", "Outcome — does the paper measure the outcome the claim is about?"],
  ["claim_fit", "Claim", "Overall — does this paper actually address this specific claim?"],
];
// What each 0/1/2 fit score means (the scale was ambiguous as bare numbers).
const FIT_SCORES = [["0", "0 — no / off-topic"], ["1", "1 — partial / indirect"], ["2", "2 — strong / direct"]];
const fitWord = (n) => n >= 7 ? "Strong" : n >= 4 ? "Moderate" : n >= 1 ? "Weak" : "None";

const state = {
  ctx: null, health: null, manuscripts: [], activeMs: null, view: null,
  activeClaim: null, claim: null, candIdx: 0, done: new Set(),
  lastTxn: null, docTxn: null, pendingDocToken: null,
};
let oTimer = null;   // double-tap "o" (decide phase): single = caution [o], double = accept [oo]

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

/* A one-line reference from whatever identifiers a candidate carries — honest with
 * partial metadata. Used both to tag cited passages (data-citation) and, on copy, to
 * append the source to the clipboard. */
function citeOf(c) {
  if (!c) return "";
  const bits = [];
  if (c.title) bits.push(String(c.title).trim().replace(/\.+$/, ""));
  const meta = [c.journal, c.year].filter(Boolean).join(" ");
  if (meta) bits.push(meta);
  if (c.doi) bits.push("https://doi.org/" + c.doi);
  else if (c.pmid) bits.push("PMID " + c.pmid);
  return bits.join(". ");
}

/* ---------- boot ---------- */
async function boot() {
  applyTheme();
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

/* The "what's next" wizard: the single next action for the whole project, from the
 * resolver (GET /api/next, i.e. workflow.project_status). One banner, one button —
 * the guided thread for someone who's never run the rate→decide→write→cite loop.
 * Read-only and blinding-safe; it only routes, it never mutates. */
async function loadNext() {
  try { state.next = await api("GET", "/api/next"); } catch { state.next = null; }
  renderNext();
}
function renderNext() {
  const box = $("#nextstep"); if (!box) return;
  const n = state.next && state.next.next;
  // first-run (init / add_claims) is handled by the full-page first-run screen
  if (!n || n.kind === "init" || n.kind === "add_claims") { box.hidden = true; return; }
  const blockers = (state.next && state.next.blockers) || [];
  const needsZotero = blockers.includes("zotero_not_write_ready");
  let cta = "";
  if (n.kind === "rate" && n.claim_id) {
    cta = `<button class="btn primary" data-act="gonext">Go to the next claim <span class="hk">→</span></button>`;
  } else if (n.kind === "report") {
    cta = `<button class="btn ghost" data-act="exportreport">Export report</button>`;
  }
  const step = n.kind === "report" ? `<span class="ns-step ns-done">✓ all decided</span>` : `<span class="ns-step">Next</span>`;
  const blockerLine = needsZotero
    ? `<div class="ns-blocker">Citing is gated on Zotero — <a data-connect="zotero">connect it</a> to enable the write-back step (rating and deciding work without it).</div>`
    : "";
  box.hidden = false;
  box.innerHTML = `${step}<span class="ns-label">${esc(n.label)}</span>${cta}${blockerLine}`;
}
function goToNextClaim() {
  const id = state.next && state.next.next && state.next.next.claim_id;
  if (!id) return;
  selectClaim(id);
  const span = document.querySelector(`.claim[data-claim="${cssEscape(id)}"]`);
  if (span) span.scrollIntoView({ behavior: "smooth", block: "center" });
}
// Download a timestamped, audit-anchored citation-integrity report — no terminal needed.
// In an age of AI, this is a timestamped audit record of the review work: the report embeds
// its generation time and the hash-chained audit head, documenting that this review was
// done, in this order. Available any time from the header (⎙ Report) and as the wizard's
// final step.
async function exportReport() {
  try {
    const r = await api("GET", "/api/report");
    const blob = new Blob([r.markdown || ""], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const stamp = String(r.generated_at || new Date().toISOString()).replace(/[:.]/g, "-").slice(0, 19);
    const a = document.createElement("a");
    a.href = url; a.download = `citation-integrity-report-${stamp}.md`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    // reinforce the proof: surface the timestamp + audit-chain state on save
    const intact = r.audit_intact === false ? "⚠ audit chain BROKEN"
      : r.audit_intact ? `audit chain intact ✓ (${r.audit_entries} entries)` : "";
    setAgentLine(`Report saved — generated ${esc(r.generated_at || "now")}${intact ? " · " + intact : ""}.`);
  } catch (e) { notify(e.message); }
}

/* ---------- export menu: Markdown · PDF (print) · review packet (.zip) ----------
 * Researchers live in Word/PDF; these bridge out without leaving local-first. PDF is
 * the browser's own "Save as PDF" on a print-styled render — zero dependencies. */
function openExportModal() {
  const box = modalShell("exportModal");
  box.innerHTML = `<div class="modal-card">
    <div class="modal-head"><b>Export</b><button class="chip-btn" data-export-close="1">✕</button></div>
    <div class="note">The Citation-Integrity Report and review trail — for a supervisor, co-author,
      or journal. Local; nothing is transmitted.</div>
    <div class="actions" style="flex-direction:column;align-items:stretch;gap:8px;margin-top:10px">
      <button class="btn ghost" data-act="export-md">⬇ Markdown (.md)</button>
      <button class="btn ghost" data-act="export-pdf">⎙ PDF — print / Save as PDF</button>
      <button class="btn ghost" data-act="export-word">📄 Word (.docx)</button>
      <button class="btn primary" data-act="export-packet">⛁ Review packet (.zip)</button>
    </div>
    <div class="lbl" style="margin-top:12px">Bring a manuscript in</div>
    <div class="actions" style="margin-top:4px"><button class="btn ghost" data-act="import-word">📄 Import Word (.docx) → review</button></div>
    <div class="note dim" style="margin-top:6px">Word in/out needs the <span class="mono">docx</span> extra
      (<span class="mono">pip install 'citevahti[docx]'</span>) — you'll get a clear note if it's missing.</div>
    <div class="modal-foot"><button class="btn ghost" data-export-close="1">Done</button></div></div>`;
}
function closeExportModal() { closeModalEl($("#exportModal")); }

async function exportDocx() {
  try {
    const r = await api("POST", "/api/report/docx", {});
    closeExportModal();
    setAgentLine(`Word report saved (${r.claim_count} claim(s)) → ${esc(r.output_file)}`);
    notify(`Word report saved (${r.claim_count} claim(s)): ${r.output_file}`, { kind: "ok" });
  } catch (e) { notify(e.message); }   // surfaces the "install citevahti[docx]" hint if absent
}

function importWord() {
  const inp = document.createElement("input");
  inp.type = "file"; inp.accept = ".docx";
  inp.onchange = async () => {
    const file = inp.files && inp.files[0]; if (!file) return;
    try {
      const dataUrl = await new Promise((res, rej) => {
        const fr = new FileReader();
        fr.onload = () => res(fr.result); fr.onerror = () => rej(new Error("could not read the file"));
        fr.readAsDataURL(file);
      });
      const b64 = String(dataUrl).split(",", 2)[1] || "";
      const r = await api("POST", "/api/manuscripts/import-docx", { docx_base64: b64 });
      openImportReview(file.name.replace(/\.docx$/i, "") + ".md", r.markdown || "");
    } catch (e) { notify(e.message); }
  };
  inp.click();
}

function openImportReview(filename, markdown) {
  closeExportModal();
  const box = modalShell("importModal");
  box.innerHTML = `<div class="modal-card">
    <div class="modal-head"><b>Import Word → review</b><button class="chip-btn" data-import-close="1">✕</button></div>
    <div class="note">Converted from .docx to Markdown. Review it, then save — claim extraction runs in your chat client afterwards.</div>
    <div class="lbl">Filename</div><input id="imName" type="text" aria-label="Filename" value="${esc(filename)}" />
    <div class="lbl">Manuscript (Markdown)</div>
    <textarea id="imBody" class="revbox" aria-label="Manuscript (Markdown)" style="min-height:220px">${esc(markdown)}</textarea>
    <div class="modal-foot"><button class="btn primary" data-import-save="1">Save document</button>
      <button class="btn" data-import-prompt="1" title="Copy the run_claim_tests prompt (with this text) to paste into your chat client">⧉ Copy claim-tests prompt</button>
      <button class="btn ghost" data-import-close="1">Cancel</button></div>
    <div id="imPromptResult" class="note"></div></div>`;
}
function closeImportModal() { closeModalEl($("#importModal")); }

/* Close the Word → claims loop: hand the reviewer the exact run_claim_tests prompt,
 * pre-filled with the imported text, ready to paste into chat (the panel never calls
 * an AI itself). The choreography text is built server-side — one source of truth. */
async function copyClaimTestsPrompt() {
  const out = $("#imPromptResult");
  const manuscript = ($("#imBody") || {}).value || "";
  try {
    const r = await api("POST", "/api/claim-tests-prompt", { manuscript });
    await copyText(r.prompt || "");
    if (out) out.innerHTML = `✓ Copied the <b>${esc(r.name || "run_claim_tests")}</b> prompt — paste it into your chat client to start the review.`;
  } catch (e) { if (out) out.innerHTML = `<span class="err">${esc(e.message)}</span>`; }
}
/* Layer-0 topic screening (ADR-0008): hand the reviewer the exact screen_topic prompt for
 * a topic, ready to paste into chat. The assistant proposes candidate claims + nearby
 * evidence (leads, not verdicts) and hands off to run_claim_tests; the panel never calls an
 * AI itself. The choreography text is built server-side — one source of truth. */
async function copyScreenTopicPrompt() {
  const out = $("#screenResult");
  const topic = (($("#screenTopic") || {}).value || "").trim();
  if (!topic) { if (out) out.innerHTML = `<span class="err">Type a topic first.</span>`; return; }
  try {
    const r = await api("POST", "/api/topic-screen-prompt", { topic });
    await copyText(r.prompt || "");
    if (out) out.innerHTML = `✓ Copied the <b>${esc(r.name || "screen_topic")}</b> prompt — paste it into your chat client to screen this topic.`;
  } catch (e) { if (out) out.innerHTML = `<span class="err">${esc(e.message)}</span>`; }
}
async function copyText(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) return await navigator.clipboard.writeText(text);
  } catch {}
  const ta = document.createElement("textarea");      // fallback for non-secure contexts
  ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select();
  try { document.execCommand("copy"); } finally { ta.remove(); }
}
async function saveImported() {
  const filename = (($("#imName") || {}).value || "").trim();
  const content = ($("#imBody") || {}).value || "";
  if (!filename) { ($("#imName") || {}).focus && $("#imName").focus(); return; }
  try {
    const r = await api("POST", "/api/manuscripts/paste", { filename, content });
    closeImportModal();
    await loadManuscripts();
    setAgentLine(`Imported ${esc(r.filename)} — ${esc(r.next_prompt || "extract claims next")}`);
  } catch (e) { notify(e.message); }
}

async function exportPdf() {
  try {
    const r = await api("GET", "/api/report");
    const w = window.open("", "_blank");
    if (!w) { notify("Allow pop-ups to print the report to PDF, or use Markdown export."); return; }
    w.document.write(r.html || "<p>(empty report)</p>");
    w.document.close(); w.focus();
    setTimeout(() => { try { w.print(); } catch {} }, 350);   // render, then open the print dialog
  } catch (e) { notify(e.message); }
}
async function exportPacket() {
  try {
    const r = await api("POST", "/api/report/packet", {});
    closeExportModal();
    setAgentLine(`Review packet saved (${r.claim_count} claim(s)) → ${esc(r.output_file)}`);
    notify(`Review packet saved (${r.claim_count} claim(s)): ${r.output_file}`, { kind: "ok" });
  } catch (e) { notify(e.message); }
}

function setAgentLine(html) {
  const el = $("#agent"); if (el) el.innerHTML = `<span class="who">CiteVahti ▸</span> <span class="pill">${html}</span>`;
}

/* ---------- the manuscript "unit test" suite ---------- */
// each claim is a test case: does it meet its references, and are the citations real?
const TEST_CHECK_LABELS = {
  has_reference: "has a reference", reviewed: "reviewed",
  supported: "reference supports the claim", citation_identified: "citation has a DOI/PMID",
  not_retracted: "citation not retracted", citation_real: "citation is real",
  in_scope: "in indexed scope",
};
const TEST_BADGE = { pass: "PASS", fail: "FAIL", skip: "SKIP" };

/* ---------- modal a11y ----------
 * Every overlay goes through modalShell()/closeModalEl() so it announces as a
 * dialog, moves focus inside on open, and restores focus to the opener on close.
 * Escape + a Tab focus-trap are handled in the global keydown listener. */
let _modalReturnFocus = null;
function modalShell(id) {
  let box = document.getElementById(id);
  if (!box) {
    box = document.createElement("div");
    box.id = id;
    box.className = "modal";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.tabIndex = -1;
    document.body.appendChild(box);
  }
  _modalReturnFocus = document.activeElement;          // restore on close
  setTimeout(() => { try { box.focus(); } catch {} }, 0);
  return box;
}
function closeModalEl(box) {
  if (!box) return;
  box.remove();
  const back = _modalReturnFocus; _modalReturnFocus = null;
  if (back && back.focus) { try { back.focus(); } catch {} }
}

async function runTests(online) {
  const box = modalShell("testModal");
  box.innerHTML = `<div class="modal-card"><div class="note">Running unit tests${online ? " — verifying citations online (this can take a moment)…" : "…"}</div></div>`;
  try {
    const s = await api("POST", "/api/test-suite", { online: !!online, manuscript_id: state.activeMs || null });
    renderTestResults(box, s);
  } catch (e) {
    box.innerHTML = `<div class="modal-card"><div class="err">${esc(e.message)}</div>
      <div class="modal-foot"><button class="btn ghost" data-test-close="1">Close</button></div></div>`;
  }
}
function renderTestResults(box, s) {
  const rows = (s.claims || []).map((c) => {
    const fails = (c.checks || []).filter((k) => k.status === "fail");
    const detail = fails.length
      ? `<div class="tfail">${fails.map((k) => `✗ ${esc(TEST_CHECK_LABELS[k.name] || k.name)}${k.detail ? " — " + esc(k.detail) : ""}`).join("<br>")}</div>` : "";
    const text = c.claim_text.length > 90 ? c.claim_text.slice(0, 88) + "…" : c.claim_text;
    return `<div class="trow ${c.status}"><button class="trowtop" data-test-focus="${esc(c.claim_id)}"
        title="Open this claim">${`<span class="tbadge ${c.status}">${TEST_BADGE[c.status]}</span>`} <span class="ttext">${esc(text)}</span></button>${detail}</div>`;
  }).join("");
  const allGreen = s.failed === 0;
  const errs = s.online_errors || [];
  // a swallowed online-check failure means citation_real / not_retracted ran on stale
  // data — warn so a degraded run isn't mistaken for a clean one.
  const warn = errs.length
    ? `<div class="twarn">⚠ Online checks couldn't complete — citation verification is incomplete:
        <ul>${errs.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>
        citation checks may be stale; treat this run as inconclusive.</div>` : "";
  box.innerHTML = `<div class="modal-card test">
    <div class="modal-head"><b>Manuscript unit tests</b><button class="chip-btn" data-test-close="1">✕</button></div>
    <div class="tsummary ${allGreen ? "ok" : "bad"}"><b>${s.passed}</b> passed · <b>${s.failed}</b> failed · <b>${s.skipped}</b> skipped — of ${s.total} claims</div>
    <div class="note">${s.online ? "Citations verified online — real and not retracted." : "Structural checks only. Citations were not verified online."}</div>
    ${warn}
    <div class="tlist">${rows || '<div class="note">No claims to test yet.</div>'}</div>
    <div class="modal-foot">
      ${s.online ? "" : `<button class="btn ghost" data-test-online="1">Also verify citations online</button>`}
      <button class="btn primary" data-test-close="1">Done</button></div></div>`;
}
function closeTests() { closeModalEl($("#testModal")); }

/* ---------- de-identified warehouse + Atlas contribution (download-only) ---- */
function downloadJson(obj, filename) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}
async function openWarehouse() {
  const box = modalShell("whModal");
  box.innerHTML = `<div class="modal-card"><div class="note">Loading…</div></div>`;
  try { renderWarehouse(box, await api("GET", "/api/warehouse")); }
  catch (e) { box.innerHTML = `<div class="modal-card"><div class="err">${esc(e.message)}</div>
    <div class="modal-foot"><button class="btn ghost" data-wh-close="1">Close</button></div></div>`; }
}
function renderWarehouse(box, st) {
  const on = !!st.enabled, text = !!st.include_claim_text;
  const bundle = state.lastBundle;
  box.innerHTML = `<div class="modal-card wh">
    <div class="modal-head"><b>Local evidence map</b><button class="chip-btn" data-wh-close="1">✕</button></div>
    <div class="note"><b>Stored on this computer. Nothing uploaded.</b> An opt-in, de-identified record of your
      claim-test work — claim <b>hash</b> (not text), public PMID/DOI, and the ratings. Off by default.</div>
    <label class="wh-toggle"><input type="checkbox" id="whEnabled" ${on ? "checked" : ""}>
      <span><b>Collect de-identified records</b> — ${st.record_count} stored</span></label>
    <label class="wh-toggle${on ? "" : " dim"}"><input type="checkbox" id="whText" ${text ? "checked" : ""} ${on ? "" : "disabled"}>
      <span>Also store the <b>raw claim text</b> <span class="sensitive">sensitive — separate opt-in</span></span></label>
    <div class="actions">
      <button class="btn ghost" data-wh="export" ${on ? "" : "disabled"}>Export records (local file)</button>
      <button class="btn ghost danger" data-wh="purge" ${st.record_count ? "" : "disabled"}>Purge (withdraw)</button></div>

    <div class="lbl" style="margin-top:14px">Contribute to Atlas</div>
    <div class="note">Build a de-identified bundle to <b>download</b>. Nothing is transmitted — there is
      no upload from here. Composed vs decomposed and case are normalized so your claim hashes match
      across tools (spec v1).</div>
    <details class="context"><summary>What contributing means — privacy</summary><div class="body">
      <p class="note"><b>De-identified, not anonymous.</b> A contribution carries your pseudonymous
        contributor id + consent record, and per judgment a <b>keyed claim index</b> (not the text),
        the <b>public</b> PMID/DOI, study type, and the ratings. The contributor id and consent ledger
        are <b>personal data</b> — we say "de-identified", never "anonymous".</p>
      <p class="note"><b>Full claim text + evidence snippet</b> ride along only under the separate
        opt-in above. <b>Never contribute</b> patient-identifiable data, confidential registry data,
        or substantial copyrighted full text.</p>
      <p class="note"><b>Your control:</b> preview the exact payload before anything leaves; every
        contribution is <b>revocable</b>. Aggregate views expose an edge only at <b>≥ 5 independent
        contributors</b>. The actual send + commercial-use opt-in happen at the contribution step,
        governed by the notice.</p>
      <p class="note"><a href="https://github.com/heidihelena/citevahti/blob/main/docs/CONTRIBUTOR_PRIVACY.md"
        target="_blank" rel="noopener">Read the full privacy notice ↗</a> · controller: Vahtian — privacy@vahtian.com</p>
    </div></details>
    <div class="actions">
      <button class="btn primary" data-wh="preview" ${on && st.record_count ? "" : "disabled"}>Preview bundle</button>
      ${bundle ? `<button class="btn ghost" data-wh="download">⬇ Download bundle (${bundle.count})</button>` : ""}</div>
    ${bundle ? `<div class="note ok" id="whBundleNote"><b>${esc(bundle.contribution_id)}</b> · ${bundle.count} record(s) · ${esc(bundle.sensitivity)}
      · sha256 ${esc(String(bundle.content_hash).slice(0, 12))}…<br>${esc(bundle.consent_receipt.egress)}</div>` : ""}
    <details class="context"><summary>Revoke a contribution</summary><div class="body">
      <input id="whRevokeId" type="text" aria-label="Contribution id to revoke" placeholder="contribution_id (contrib_…)" />
      <div class="actions"><button class="btn ghost" data-wh="revoke">Download revocation</button></div></div></details>
    <div class="modal-foot"><button class="btn primary" data-wh-close="1">Done</button></div></div>`;
}
async function whConfigure(patch) {
  try { const st = await api("POST", "/api/warehouse/configure", patch);
    state.lastBundle = null; renderWarehouse($("#whModal"), st); }
  catch (e) { notify(e.message); }
}
async function whAction(act) {
  const box = $("#whModal");
  try {
    if (act === "export") {
      const r = await api("POST", "/api/warehouse/export", {});
      notify(`Exported ${r.record_count} record(s) to ${r.output_file}`, { kind: "ok" });
    } else if (act === "purge") {
      if (!confirm("Erase the local warehouse? This withdraws every de-identified record.")) return;
      await api("POST", "/api/warehouse/purge", {}); state.lastBundle = null;
      renderWarehouse(box, await api("GET", "/api/warehouse"));
    } else if (act === "preview") {
      const text = $("#whText") && $("#whText").checked;
      state.lastBundle = await api("POST", "/api/atlas/contribution-preview", { allow_claim_text: !!text });
      renderWarehouse(box, await api("GET", "/api/warehouse"));
    } else if (act === "download") {
      if (state.lastBundle) downloadJson(state.lastBundle, `${state.lastBundle.contribution_id}.json`);
    } else if (act === "revoke") {
      const id = (($("#whRevokeId") || {}).value || "").trim();
      if (!id) { notify("Paste the contribution_id to revoke."); return; }
      const req = await api("POST", "/api/atlas/revoke", { contribution_id: id });
      downloadJson(req, `revocation-${id}.json`);
    }
  } catch (e) { notify(e.message); }
}
function closeWarehouse() { state.lastBundle = null; closeModalEl($("#whModal")); }

/* ---------- AI second opinion settings ----------
 * Privacy-first. Most users drive CiteVahti through an assistant over MCP, which
 * submits the blinded rating with no key (subscription pays) — so the MCP path is
 * framed first and the off/local/api modes are for CiteVahti's OWN call. The API
 * key is NEVER entered here: it lives in the keychain/env (we only show presence). */
async function openAiSettings() {
  const box = modalShell("aiModal");
  box.innerHTML = `<div class="modal-card"><div class="note">Loading…</div></div>`;
  try {
    const cfg = await api("GET", "/api/ai-config");
    let models = [], suggested = "";
    if (cfg.mode === "local") {
      try { const r = await api("GET", "/api/ai/local-models"); models = r.models || []; suggested = r.suggested || ""; } catch {}
    }
    state.aiModels = models; state.aiSuggested = suggested;
    renderAiSettings(box, cfg, models, suggested);
  } catch (e) {
    box.innerHTML = `<div class="modal-card"><div class="err">${esc(e.message)}</div>
      <div class="modal-foot"><button class="btn ghost" data-ai-close="1">Close</button></div></div>`;
  }
}
function renderAiSettings(box, cfg, models, suggested) {
  models = models || []; suggested = suggested || cfg.model_id || "";
  const m = cfg.mode;
  const opt = (v, on) => `<input type="radio" name="aiMode" value="${v}" ${on ? "checked" : ""}>`;
  const known = models.some((x) => x.name === cfg.model_id);
  const localCfg = m !== "local" ? "" : `<div class="ai-cfg">
    <div class="lbl">Local model</div>
    <div class="note">${models.length
      ? `On this machine: ${models.length} model(s). Qwen is offered first — it tends to beat llama at the term-extraction that claim-checking is.`
      : `Ollama not detected. Start it (or type a name); CiteVahti uses the model when it's available.`}</div>
    <select id="aiModelSel">
      ${models.map((x) => `<option value="${esc(x.name)}" ${x.name === cfg.model_id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}
      ${(!known && cfg.model_id && !cfg.model_id.startsWith("PENDING")) ? `<option value="${esc(cfg.model_id)}" selected>${esc(cfg.model_id)} (configured)</option>` : ""}
      ${(!models.length && suggested) ? `<option value="${esc(suggested)}" selected>${esc(suggested)}</option>` : ""}
    </select>
    <input id="aiEndpoint" type="text" aria-label="Local AI endpoint URL" placeholder="http://localhost:11434/v1/chat/completions" value="${esc(cfg.endpoint || "")}">
    <div class="note">${cfg.model_pinned ? `Pinned for audit: <b>${esc(cfg.model_snapshot)}</b> ✓` : `Pick a model to pin it (the Ollama digest is recorded automatically).`}</div>
  </div>`;
  const apiCfg = m !== "api" ? "" : `<div class="ai-cfg">
    <div class="lbl">Provider &amp; model</div>
    <select id="aiProvider">
      <option value="anthropic" ${cfg.provider === "anthropic" ? "selected" : ""}>Anthropic</option>
      <option value="openai" ${cfg.provider !== "anthropic" ? "selected" : ""}>OpenAI-compatible</option></select>
    <input id="aiModelId" type="text" aria-label="Model id" placeholder="model id (e.g. claude-…, gpt-…)" value="${esc(cfg.model_id && !cfg.model_id.startsWith("PENDING") ? cfg.model_id : "")}">
    <input id="aiEndpoint" type="text" aria-label="API endpoint URL (https only)" placeholder="https://… (https only)" value="${esc(cfg.endpoint || "")}">
    <div class="note ${cfg.api_key_present ? "ok" : "warn"}">${cfg.api_key_present
      ? "API key: configured (in your keychain / env)."
      : "API key not set — store <b>CITEVAHTI_AI_API_KEY</b> in your env or keychain. The key is never saved in config or sent through this panel."}</div>
  </div>`;
  box.innerHTML = `<div class="modal-card ai">
    <div class="modal-head"><b>AI second opinion</b><button class="chip-btn" data-ai-close="1">✕</button></div>
    <div class="note">Privacy-first &middot; optional. <b>You rate first — the AI is a blinded second opinion.</b>
      Bring your own model or API key. No hidden AI subscription.</div>
    <div class="note ok"><b>Working through an assistant (Cowork / Claude via MCP)?</b> It already gives the
      blinded second opinion through CiteVahti's MCP tools — nothing to set up here, paid by your assistant
      subscription. The modes below are only for when CiteVahti makes its <i>own</i> call (standalone, or
      high-volume local screening).</div>
    <div class="ai-modes">
      <label class="ai-mode">${opt("off", m === "off")}<span><b>Off</b> — human-only (or your MCP assistant provides it).</span></label>
      <label class="ai-mode">${opt("local", m === "local")}<span><b>Local AI</b> — a model on your machine or network (Ollama). No API key; nothing leaves your device. Best for high-volume screening.</span></label>
      <label class="ai-mode">${opt("api", m === "api")}<span><b>My API key</b> — an external provider (OpenAI / Anthropic / compatible) with your own key.</span></label>
    </div>
    ${localCfg}${apiCfg}
    <div class="modal-foot"><button class="btn primary" data-ai-close="1">Done</button></div></div>`;
}
async function aiConfigure(patch) {
  try {
    const cfg = await api("POST", "/api/ai-config", patch);
    let models = state.aiModels || [], suggested = state.aiSuggested || "";
    if (cfg.mode === "local") {
      try { const r = await api("GET", "/api/ai/local-models"); models = r.models || []; suggested = r.suggested || ""; } catch {}
      state.aiModels = models; state.aiSuggested = suggested;
    }
    renderAiSettings($("#aiModal"), cfg, models, suggested);
  } catch (e) { notify(e.message); }
}
function closeAiSettings() { closeModalEl($("#aiModal")); }
// CSS.escape isn't in every embedded webview; fall back to a minimal escaper for ids.
function cssEscape(s) {
  return (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/["\\]/g, "\\$&");
}

/* Theme: light by default (the base stylesheet; .zs-dark is the override, and
 * index.html ships no default class). A ?theme=light|dark override wins
 * (deterministic for screenshots and deep links); otherwise a previously toggled
 * theme is restored from localStorage, so the choice survives a reload. */
function applyTheme() {
  let saved = null;
  try { saved = localStorage.getItem("cv-theme"); } catch { /* private mode */ }
  const q = new URLSearchParams(location.search).get("theme");
  const pref = (q === "light" || q === "dark") ? q : saved;
  if (pref === "light") document.documentElement.classList.remove("zs-dark");
  else if (pref === "dark") document.documentElement.classList.add("zs-dark");
  syncThemeLabel();
}
function syncThemeLabel() {
  const btn = $("#theme"); if (!btn) return;
  btn.textContent = document.documentElement.classList.contains("zs-dark") ? "◐ Light" : "◑ Dark";
}

// Optional URL hooks so a specific review state can be linked or screenshotted:
//   ?focus=<claim_id>   open that claim's card   ?legend=1   open the legend
//   ?theme=light|dark   force the theme (see applyTheme)
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
  loadNext();        // mutations (and reload) flow through here — refresh "what's next" with them
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
    `<button type="button" class="conn ${ok ? "ok" : "off"}" data-connect="${key}"
       aria-label="${esc(label)} — ${ok ? "connected" : "connect"}"><span class="led"></span>${label}${ok ? "" : " — connect"}</button>`;
  $("#conns").innerHTML = chip("zotero", "Zotero", canWrite) + chip("pubmed", "PubMed", pubmedOk);
}

function renderMsBar() {
  const picks = state.manuscripts.map((m) =>
    `<button class="mspick${m.manuscript_id === state.activeMs ? " active" : ""}" data-ms="${esc(m.manuscript_id)}"
       title="${esc(m.manuscript_id)} — ${m.claim_count} claim(s) saved${m.resolved ? "" : "; original document not open yet"}">
      ${esc(m.manuscript_id)} <span class="n">${m.claim_count}</span>${m.resolved ? "" : ' <span class="needsdoc">⚠ document not open</span>'}</button>`).join("");
  const switcher = state.manuscripts.length
    ? `<span class="msswitch"><span class="lbl">Manuscript</span>${picks}</span>` : "";
  const dir = state.ctx.manuscripts_dir || "";
  const bind = `<span class="bind"><button class="chip-btn" id="addClaim">＋ Claim</button>
    <button class="chip-btn primary-chip" id="browseBtn" title="Choose the folder your manuscript file is in — no typing">📁 Open my document…</button>
    <input id="bindDir" type="text" aria-label="Ledger folder path" placeholder="…or paste a folder path" value="${esc(dir)}" />
    <button class="chip-btn" id="bindBtn" title="Use the pasted path">Use path</button></span>`;
  $("#msbar").innerHTML = switcher + bind;
  const name = $("#msName"); if (name) name.textContent = state.activeMs || "manuscript";
}

/* ---------- folder picker: click through the filesystem, no path typing ---- */
async function openBrowse(path) {
  const box = modalShell("browseModal");
  box.innerHTML = `<div class="modal-card"><div class="note">Loading…</div></div>`;
  try {
    const r = await api("POST", "/api/fs/browse", { path: path || null });
    state.browsePath = r.path;
    const up = r.parent ? `<button class="browse-row up" data-browse="${esc(r.parent)}">⬆ ${esc(r.parent)}</button>` : "";
    const rows = (r.dirs || []).map((d) =>
      `<button class="browse-row" data-browse="${esc(d.path)}">📁 ${esc(d.name)}${d.manuscript_count ? ` <span class="n">${d.manuscript_count} doc${d.manuscript_count > 1 ? "s" : ""}</span>` : ""}</button>`).join("");
    box.innerHTML = `<div class="modal-card">
      <div class="modal-head"><b>Open your manuscript — choose the folder it's in</b>
        <button class="chip-btn" data-browse-close="1">✕</button></div>
      <div class="browse-here">${esc(r.path)}${r.manuscript_count ? ` · <b>${r.manuscript_count}</b> manuscript file(s) here` : " · no manuscript files here"}</div>
      <div class="browse-list">${up}${rows || '<div class="note">No sub-folders.</div>'}</div>
      <div class="modal-foot">
        <button class="btn primary" data-browse-use="${esc(r.path)}">Use this folder</button>
        <button class="btn ghost" data-browse-close="1">Cancel</button></div></div>`;
  } catch (e) { box.innerHTML = `<div class="modal-card"><div class="err">${esc(e.message)}</div>
    <div class="modal-foot"><button class="btn ghost" data-browse-close="1">Close</button></div></div>`; }
}
function closeBrowse() { closeModalEl($("#browseModal")); }
async function useBrowseFolder(dir) {
  try { await api("POST", "/api/manuscripts/bind", { dir }); closeBrowse(); await loadManuscripts(); }
  catch (e) { notify(e.message); }
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
    <textarea id="newClaimText" class="revbox" aria-label="Claim text" placeholder="claim text — or select a sentence in the manuscript first">${esc(sel)}</textarea>
    <div class="row">
      <select id="newClaimType">${CLAIM_TYPES.map((t) => `<option value="${t}">${claimTypeLabel(t)}</option>`).join("")}</select>
      <button class="btn primary" data-act="save-claim">Add claim</button>
      <button class="btn ghost" data-act="cancel-claim">Cancel</button>
    </div></div>`;
  const ta = $("#newClaimText"); if (ta) ta.focus();
}
async function saveClaim() {
  const text = (($("#newClaimText") || {}).value || "").trim();
  const type = ($("#newClaimType") || {}).value || "other";
  if (!text) { notify("Enter the claim text first."); return; }
  try {
    const r = await api("POST", "/api/claims", { claim_text: text, claim_type: type,
      manuscript_id: state.activeMs, manuscript_location: state.activeMs });
    $("#addClaimBox").innerHTML = "";
    await loadManuscripts();
    if (r.claim_id) await selectClaim(r.claim_id);
  } catch (e) { notify("Add claim failed: " + e.message); }
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

/* ---------- claim card ---------- */
async function selectClaim(id) {
  const sameClaim = id === state.activeClaim;
  state.activeClaim = id;
  // moving to a different claim: drop the in-session write/undo/timer state so a global
  // key (u undo, the o double-tap) can't act on the claim you just navigated away from.
  // (Undo is still recoverable per-claim from the audit trail via recoverableTxn().)
  if (!sameClaim) { state.candIdx = 0; resetWrite(); state.lastTxn = null; state.docTxn = null; clearTimeout(oTimer); oTimer = null; }   // keep the candidate in view on a same-claim refresh
  renderDoc(); renderProgress();
  try { state.claim = await api("GET", `/api/claims/${encodeURIComponent(id)}`); }
  catch (e) { $("#card").innerHTML = `<div class="err">${esc(e.message)}</div>`; return; }
  try { state.history = await api("GET", `/api/claims/${encodeURIComponent(id)}/history`); }
  catch { state.history = null; }
  renderCard();
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
    <div class="decrow"><input type="text" id="decReason" aria-label="Decision reason — recorded in the audit trail" placeholder="reason (recorded in the audit trail)" /></div>
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

/* ---------- actions ---------- */
function resetWrite() { state.pendingZtoken = null; state.previewNote = ""; state.pendingDocToken = null; }
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

function connect(which) {
  // the inline write-step field (if present) connects directly; otherwise the
  // header chip / first-run opens a proper modal with password inputs (not a prompt).
  if (which === "zotero") {
    const inline = (($("#zoteroKey") || {}).value || "").trim();
    if (inline) return void _applyConnect("zotero", { key: inline });
  }
  openConnectModal(which);
}

async function _applyConnect(which, payload) {
  try {
    let health;
    if (which === "zotero") {
      const r = await api("POST", "/api/connect/zotero", { api_key: payload.key });
      health = r.health;
    } else {
      const r = await api("POST", "/api/connect/pubmed",
                          { email: payload.email, api_key: payload.apiKey || undefined });
      health = r.health;
    }
    state.health = health || state.health;
    renderConns();
    const canWrite = (state.health && state.health.can_write || []).length > 0;
    if (which === "zotero" && !canWrite)
      notify("Zotero key accepted but no write access detected — check the key has write permission to your library.");
    if (state.activeClaim) renderCard();
  } catch (e) {
    notify("Connect " + which + " failed: " + e.message);   // surface the real reason
  }
}

function openConnectModal(which) {
  const isZ = which === "zotero";
  const box = modalShell("connectModal");
  box.innerHTML = `<div class="modal-card">
    <div class="modal-head"><b>Connect ${isZ ? "Zotero" : "PubMed (NCBI)"}</b><button class="chip-btn" data-connect-close="1">✕</button></div>
    ${isZ
      ? `<div class="lbl">Zotero API key — write access</div>
         <input id="cmKey" type="password" autocomplete="off" spellcheck="false" aria-label="Zotero API key with write access" placeholder="Zotero API key" />
         <div class="actions" style="margin-top:8px"><a class="btn ghost" href="https://www.zotero.org/settings/keys/new" target="_blank" rel="noopener">Get a key ↗</a></div>`
      : `<div class="lbl">Contact email — required by NCBI</div>
         <input id="cmEmail" type="email" autocomplete="off" spellcheck="false" aria-label="Contact email — required by NCBI" placeholder="you@institution.edu" />
         <div class="lbl" style="margin-top:10px">NCBI API key — optional, raises your rate limit</div>
         <input id="cmKey" type="password" autocomplete="off" spellcheck="false" aria-label="NCBI API key — optional" placeholder="optional" />`}
    <div class="note ok">Stored in your OS keychain. Never written to the ledger.</div>
    <div class="modal-foot"><button class="btn primary" data-connect-submit="${which}">Connect</button>
      <button class="btn ghost" data-connect-close="1">Cancel</button></div></div>`;
}
function closeConnectModal() { closeModalEl($("#connectModal")); }
async function submitConnect(which) {
  const key = (($("#cmKey") || {}).value || "").trim();
  if (which === "zotero") {
    if (!key) { ($("#cmKey") || {}).focus && $("#cmKey").focus(); return; }
    closeConnectModal();
    await _applyConnect("zotero", { key });
  } else {
    const email = (($("#cmEmail") || {}).value || "").trim();
    if (!email) { ($("#cmEmail") || {}).focus && $("#cmEmail").focus(); return; }
    closeConnectModal();
    await _applyConnect("pubmed", { email, apiKey: key });
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
  } catch (e) { notify("Zotero OAuth: " + e.message); }
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
      const meta = [h.journal, h.year, h.pmid && ("PMID " + h.pmid)].filter(Boolean).join(" · ");
      const inzot = h.dedupe_status === "already_in_library" ? `<span class="tag inzot">in Zotero</span>` : "";
      const doi = h.doi ? `<a class="doi" href="${esc(doiUrl(h.doi))}" target="_blank" rel="noopener" title="Open the DOI">DOI ${esc(h.doi)} ↗</a>` : "";
      const abs = h.abstract ? `<details class="abs"><summary>Abstract</summary><div class="excerpt">${esc(h.abstract)}</div></details>` : "";
      const inLib = h.dedupe_status === "already_in_library";
      return `<div class="result"><div class="rmeta"><b>${esc(h.title || "(untitled)")}</b> ${inzot}
        <div class="note">${esc(meta)}${meta && doi ? " · " : ""}${doi}</div>${abs}</div>
        <div class="ractions">
          <button class="btn ghost" data-link="${esc(h.record_id)}">Link to claim</button>
          ${inLib ? `<span class="note">already saved</span>`
                  : `<button class="btn ghost" data-zsave="${esc(h.record_id)}" title="Adds this paper to your Zotero library — it does NOT mark the claim supported (rate and decide for that)">＋ Add paper to Zotero</button>`}
        </div></div>`;
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

/* normalise a DOI (bare, or with a doi:/URL prefix) to an openable doi.org link */
function doiUrl(doi) {
  const d = String(doi).trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, "").replace(/^doi:/i, "");
  return "https://doi.org/" + d;
}

/* direct "Save to Zotero" for a search hit — preview the write, then confirm.
 * Honors the same nothing-written-silently gate as the claim write: preview
 * returns a confirm_token; the actual add needs it. */
async function zsave(recordId, btn) {
  const canWrite = (state.health && state.health.can_write || []).length > 0;
  if (!canWrite) { showErr("Connect Zotero (with write access) first — see the Zotero chip."); return; }
  if (!state.searchBatch) { showErr("Run the search again, then save."); return; }
  try {
    const p = await api("POST", "/api/intake/preview", { batch_id: state.searchBatch, record_ids: [recordId] });
    const token = p.confirm_token || p.approval_token;
    const n = (p.to_create != null ? p.to_create : (p.would_create != null ? p.would_create : 1));
    const dup = p.skipped_duplicates || p.duplicates || 0;
    if (!token) {
      if (dup && !n) { if (btn) { btn.textContent = "already in Zotero"; btn.disabled = true; } return; }
      showErr("Could not prepare the Zotero write (no confirm token returned)."); return;
    }
    if (!confirm(`Add this paper to your Zotero library?${dup ? `\n(${dup} duplicate skipped.)` : ""}`)) return;
    const r = await api("POST", "/api/intake/commit", { batch_id: state.searchBatch, record_ids: [recordId], confirm_token: token });
    const ok = (r.status === "committed") || r.created_keys || r.pushed;
    if (btn) { btn.textContent = ok ? "✓ Saved to Zotero" : "save failed"; btn.disabled = !!ok; }
    if (!ok) showErr(`Save not committed: ${r.error_code || r.status || "unknown"}`);
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
    <div class="beta-banner"><b>CiteVahti is in beta — free to use.</b> Local-first: your manuscript
      and ratings stay on your device unless you choose to use an external AI model.</div>
    <h2>Start your review</h2>
    <p class="note"><b>1.</b> Add your manuscript → <b>2.</b> extract claims (in your chat client) →
      <b>3.</b> review the first claim. The panel never calls an AI itself.</p>
    ${others.length ? `<div class="panel-box wrong-ledger">
      <div class="lbl">Looking for earlier work?</div>
      <p class="note">This ledger (<b>${esc(state.ctx.root)}</b>) is empty — your claims may be in another ledger:</p>
      ${rows}</div>` : ""}
    <div class="panel-box">
      <div class="lbl">1 · Add your manuscript</div>
      <p class="note">Paste your manuscript Markdown — CiteVahti saves it and remembers where it lives.
      You'll get the exact prompt to paste into your chat client to extract claims next.</p>
      <input id="pasteName" type="text" aria-label="Manuscript filename" placeholder="filename, e.g. my-draft.md" />
      <textarea id="pasteBody" class="revbox" aria-label="Manuscript Markdown" placeholder="# Title&#10;&#10;Paste your Markdown here…"></textarea>
      <div class="actions"><button class="btn primary" id="pasteSave">Save my document</button></div>
      <div id="pasteResult"></div>
    </div>
    <details class="firstrun-more">
      <summary>I don't have a manuscript yet</summary>
      <div class="panel-box">
        <div class="lbl">Screen a topic</div>
        <p class="note">Hand your chat client a screening prompt for a topic — it proposes candidate
        claims to assess and nearby evidence. <b>Leads, not verdicts</b>; you still rate each one first.</p>
        <input id="screenTopic" type="text" aria-label="Topic to screen" placeholder="e.g. low-dose CT screening in heavy smokers" />
        <div class="actions"><button class="btn ghost" id="screenTopicBtn" title="Copy the screen_topic prompt to paste into your chat client">⧉ Copy screen-topic prompt</button></div>
        <div id="screenResult" class="note"></div>
      </div>
      <div class="panel-box">
        <div class="lbl">Add claims directly · connect sources</div>
        <p class="note">From your chat client run the <b>run_claim_tests</b> prompt, or use the CLI:
        <br><code>citevahti claim-add --text "…" --type interpretation</code></p>
        <div class="actions">
          <button class="btn ghost" data-connect="zotero">Connect Zotero</button>
          <button class="btn ghost" data-connect="pubmed">Connect PubMed</button>
        </div>
      </div>
    </details></div>`;
}

async function savePastedManuscript() {
  const filename = (($("#pasteName") || {}).value || "").trim();
  const content = ($("#pasteBody") || {}).value || "";
  const out = $("#pasteResult");
  if (!filename) { out.innerHTML = `<div class="note">Give the file a name first.</div>`; return; }
  if (!content.trim()) { out.innerHTML = `<div class="note">Paste some Markdown first.</div>`; return; }
  try {
    const r = await api("POST", "/api/manuscripts/paste", { filename, content });
    out.innerHTML = `<div class="note ok">Saved <b>${esc(r.filename)}</b> in
      <code>${esc(r.manuscripts_dir)}</code>.</div>
      <div class="lbl" style="margin-top:8px">Next: extract claims in your chat client</div>
      <p class="note">Paste this prompt to CiteVahti over MCP — the panel will fill in
      once claims are staged:</p>
      <textarea class="revbox" readonly onclick="this.select()">${esc(r.next_prompt)}</textarea>`;
  } catch (e) { out.innerHTML = `<div class="note">${esc(e.message)}</div>`; }
}

/* ---------- events ---------- */
/* Citation-on-copy: copying text from a cited passage carries its source, like the
 * "read more at…" pattern. When the whole selection sits inside an element tagged with
 * data-citation (an accepted claim, or a quoted source excerpt/abstract), append the
 * reference to both clipboard formats. Self-contained — no network, no external deps. */
document.addEventListener("copy", (e) => {
  const sel = window.getSelection();
  if (!sel || !sel.rangeCount || sel.isCollapsed) return;
  const start = sel.anchorNode, end = sel.focusNode;
  const host = start && (start.nodeType === 1 ? start : start.parentElement);
  const cite = host && host.closest("[data-citation]");
  if (!cite || !end || !cite.contains(end)) return;   // both ends must be inside the passage
  const ref = cite.getAttribute("data-citation");
  if (!ref || !e.clipboardData) return;
  const text = sel.toString().trim();
  if (!text) return;
  e.clipboardData.setData("text/plain", `${text}\n\n— ${ref}`);
  e.clipboardData.setData("text/html", `${esc(text)} <cite>(${esc(ref)})</cite>`);
  e.preventDefault();
});

document.addEventListener("click", (e) => {
  const sw = e.target.closest("[data-switch]"); if (sw) return switchRoot(sw.dataset.switch);
  const cn = e.target.closest("[data-connect]"); if (cn) return void connect(cn.dataset.connect);
  if (e.target.closest("[data-connect-close]")) return void closeConnectModal();
  if (e.target.closest("[data-export-close]")) return void closeExportModal();
  if (e.target.closest("[data-import-close]")) return void closeImportModal();
  if (e.target.closest("[data-import-save]")) return void saveImported();
  if (e.target.closest("[data-import-prompt]")) return void copyClaimTestsPrompt();
  const cs = e.target.closest("[data-connect-submit]"); if (cs) return void submitConnect(cs.dataset.connectSubmit);
  const ms = e.target.closest("[data-ms]"); if (ms) return void loadManuscript(ms.dataset.ms).then(renderMsBar);
  if (e.target.id === "bindBtn") return void bindFolder();
  if (e.target.closest("#browseBtn") || e.target.closest("#reconOpen")) return void openBrowse(($("#bindDir") || {}).value || state.ctx.manuscripts_dir);
  const bn = e.target.closest("[data-browse]"); if (bn) return void openBrowse(bn.dataset.browse);
  const bu = e.target.closest("[data-browse-use]"); if (bu) return void useBrowseFolder(bu.dataset.browseUse);
  if (e.target.closest("[data-browse-close]")) return void closeBrowse();
  if (e.target.closest("[data-test-close]")) return void closeTests();
  if (e.target.closest("[data-test-online]")) return void runTests(true);
  const tf = e.target.closest("[data-test-focus]"); if (tf) { closeTests(); return void selectClaim(tf.dataset.testFocus); }
  if (e.target.closest("[data-wh-close]")) return void closeWarehouse();
  const wh = e.target.closest("[data-wh]"); if (wh) return void whAction(wh.dataset.wh);
  if (e.target.closest("[data-ai-close]")) return void closeAiSettings();
  if (e.target.id === "pasteSave") return void savePastedManuscript();
  if (e.target.id === "screenTopicBtn") return void copyScreenTopicPrompt();
  if (e.target.id === "addClaim") return void toggleAddClaim();
  const sp = e.target.closest("[data-claim]"); if (sp) return void selectClaim(sp.dataset.claim);
  const cp = e.target.closest("[data-cand]"); if (cp) { state.candIdx = +cp.dataset.cand; resetWrite(); return renderCard(); }
  const rb = e.target.closest("[data-rate]"); if (rb) return void rate(rb.dataset.rate);
  const dc = e.target.closest("[data-decide]"); if (dc) return void recordDecision(dc.dataset.decide);
  const lk = e.target.closest("[data-link]"); if (lk) return void linkRecord(lk.dataset.link);
  const zs = e.target.closest("[data-zsave]"); if (zs) return void zsave(zs.dataset.zsave, zs);
  const act = e.target.closest("[data-act]"); if (!act) return;
  ({ "connect-zotero": () => connect("zotero"), "connect-zotero-oauth": connectOAuth, search: doSearch,
     "open-zotero": () => openInZotero(activeCand()), "zot-evidence": openZotEvidence, lexcheck: runLexCheck,
     "print-audit": printAudit,
     "edit-claim": toggleEditClaim, "claimedit-preview": editClaimPreview, "claimedit-commit": editClaimCommit,
     "claimedit-save": editClaimSaveLedger, "claimedit-cancel": cancelEditClaim,
     "save-claim": saveClaim, "cancel-claim": () => { $("#addClaimBox").innerHTML = ""; },
     zpreview, zcommit, zcancel: () => { resetWrite(); renderCard(); },
     zundo, docpreview: () => docPreview(act.dataset.kind), doccommit: docCommit, doccancel: () => { resetWrite(); renderCard(); },
     docundo: docUndo, unlink: unlinkCandidate, gonext: goToNextClaim, exportreport: exportReport,
     "run-ai": runAiSecondOpinion,
     "export-md": exportReport, "export-pdf": exportPdf, "export-packet": exportPacket,
     "export-word": exportDocx, "import-word": importWord,
     next: () => { const n = nextPending(); if (n) selectClaim(n); } }[act.dataset.act] || (() => {}))();
});
$("#reload").addEventListener("click", () => { loadManuscripts(); loadAudit(); });
$("#report").addEventListener("click", openExportModal);
$("#runTests").addEventListener("click", () => runTests(false));
$("#warehouse").addEventListener("click", openWarehouse);
$("#aiSettings").addEventListener("click", openAiSettings);
// warehouse opt-in toggles (delegated — the modal is rendered dynamically)
document.addEventListener("change", (e) => {
  if (e.target.id === "whEnabled") return void whConfigure({ enabled: e.target.checked });
  if (e.target.id === "whText") return void whConfigure({ include_claim_text: e.target.checked });
  // AI settings (modal rendered dynamically) — persist on change
  if (e.target.name === "aiMode") return void aiConfigure({ mode: e.target.value });
  if (e.target.id === "aiModelSel") return void aiConfigure({ model_id: e.target.value });
  if (e.target.id === "aiProvider") return void aiConfigure({ provider: e.target.value });
  if (e.target.id === "aiModelId") return void aiConfigure({ model_id: e.target.value.trim() });
  if (e.target.id === "aiEndpoint") return void aiConfigure({ endpoint: e.target.value.trim() });
});
$("#auditBadge").addEventListener("click", () => loadAudit());
$("#legendBtn").addEventListener("click", () => {
  const el = $("#legend"), opening = el.hasAttribute("hidden");
  el.toggleAttribute("hidden");
  $("#legendBtn").setAttribute("aria-expanded", String(opening));
});
// keyboard-shortcut toggle, persisted across sessions (for people writing in the panel)
(function initHotkeyToggle() {
  try { state.hotkeysOff = localStorage.getItem("citevahti.hotkeysOff") === "1"; } catch { state.hotkeysOff = false; }
  const cb = $("#hkToggle"); if (!cb) return;
  cb.checked = state.hotkeysOff;
  cb.addEventListener("change", () => {
    state.hotkeysOff = cb.checked;
    try { localStorage.setItem("citevahti.hotkeysOff", cb.checked ? "1" : "0"); } catch {}
  });
})();
async function maintenance(path, label, fmt) {
  try {
    const r = await api("POST", path, {});
    notify(fmt(r), { kind: "ok" });
    await loadManuscripts();
    if (state.activeClaim) await selectClaim(state.activeClaim);
  } catch (e) { notify(`${label} failed: ${e.message}`, { retry: () => maintenance(path, label, fmt) }); }
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
async function citeExport() {
  if (!state.activeMs) { notify("Open a manuscript first."); return; }
  if (!(state.view && state.view.mode === "file")) {
    notify("Bind the manuscript's folder first so CiteVahti can write the cited copy beside it.");
    return;
  }
  try {
    // Warn before the one-time Pandoc fetch — the request below blocks while it downloads.
    const ps = await api("GET", "/api/pandoc/status").catch(() => ({ available: true }));
    if (!ps.available) {
      notify("Downloading Pandoc (one-time, ~100 MB) to build the Word file — this can take a "
             + "minute. The .md + .bib are written either way.", { kind: "ok", sticky: true });
    }
    const r = await api("POST", "/api/manuscripts/cite-export",
                        { manuscript_id: state.activeMs, docx: true });
    let msg = `Cited ${r.injected} accepted claim(s)`
      + (r.skipped ? `, ${r.skipped} skipped` : "")
      + (r.bbt_keys ? ` · ${r.bbt_keys} matched your Zotero citekeys` : "")
      + `. Wrote ${r.markdown_path}` + (r.bib_path ? " + references.bib" : "")
      + (r.docx_status === "ok" ? " + Word .docx"
         : r.docx_status && r.docx_status !== "no_citations"
           ? " (Word export unavailable — the .md + .bib are ready to convert)" : "");
    notify(msg, { kind: "ok" });
    (r.warnings || []).forEach((w) => console.warn("cite-export:", w));
  } catch (e) { notify("Cite-stable export failed: " + e.message, { retry: () => citeExport() }); }
}
$("#citeExport").addEventListener("click", citeExport);
$("#theme").addEventListener("click", () => {
  const dark = document.documentElement.classList.toggle("zs-dark");
  try { localStorage.setItem("cv-theme", dark ? "dark" : "light"); } catch { /* private mode */ }
  syncThemeLabel();
});
// "⋯ Tools" dropdown: close once an action runs, on outside-click, or on Escape
(() => {
  const tm = $("#toolsmenu"); if (!tm || !tm.querySelector) return;
  const pop = tm.querySelector(".menu-pop");
  if (pop && pop.addEventListener) pop.addEventListener("click", () => tm.removeAttribute("open"));
  document.addEventListener("click", (e) => { if (tm.open && tm.contains && !tm.contains(e.target)) tm.removeAttribute("open"); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && tm.open) tm.removeAttribute("open"); });
})();
document.addEventListener("keydown", (e) => {
  // modal-first: Escape dismisses the open dialog; Tab is trapped inside it
  const openModal = document.querySelector(".modal");
  if (openModal) {
    if (e.key === "Escape") {
      const close = { whModal: closeWarehouse, aiModal: closeAiSettings,
                      browseModal: closeBrowse, testModal: closeTests,
                      connectModal: closeConnectModal, exportModal: closeExportModal,
                      importModal: closeImportModal }[openModal.id];
      (close || (() => closeModalEl(openModal)))();
      return e.preventDefault();
    }
    if (e.key === "Tab") {
      const f = [...openModal.querySelectorAll(
        'button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')]
        .filter((el) => !el.disabled && el.offsetParent !== null);
      if (f.length) {
        const first = f[0], last = f[f.length - 1];
        if (document.activeElement === openModal) { first.focus(); return e.preventDefault(); }
        if (e.shiftKey && document.activeElement === first) { last.focus(); return e.preventDefault(); }
        if (!e.shiftKey && document.activeElement === last) { first.focus(); return e.preventDefault(); }
      }
    }
  }
  if (e.target.matches("input, textarea, select")) return;
  // a focused claim span is role="button": Enter/Space must activate it (intrinsic
  // button behaviour for keyboard users — works even when shortcuts are turned off).
  const focusedClaim = e.target.closest && e.target.closest("[data-claim]");
  if (focusedClaim && (e.key === "Enter" || e.key === " ")) {
    selectClaim(focusedClaim.dataset.claim); return e.preventDefault();
  }
  if (state.hotkeysOff) return;                          // user turned shortcuts off (writing mode)
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;   // letter keys are CapsLock-proof
  if (key === "?") { $("#legendBtn").click(); return e.preventDefault(); }              // ? help
  if (key === "u") {                                                                    // u undo last write/edit
    if (recoverableTxn()) { zundo(); return e.preventDefault(); }
    if (state.docTxn) { docUndo(); return e.preventDefault(); }
  }
  const ids = claimOrder(); if (!ids.length) return;   // document order, matching the eye
  const i = ids.indexOf(state.activeClaim);
  if (key === "j" || e.key === "ArrowDown") { selectClaim(ids[Math.min(i + 1, ids.length - 1)]); return e.preventDefault(); }
  if (key === "k" || e.key === "ArrowUp") { selectClaim(ids[Math.max(i - 1, 0)]); return e.preventDefault(); }
  const cand = activeCand(); if (!cand) return;
  if (e.shiftKey && key === "d") { unlinkCandidate(); return e.preventDefault(); }       // ⇧D guarded remove
  const ph = phaseOf(cand);
  if (ph === "rate" && /^[1-7]$/.test(e.key)) { rate(SUPPORT[+e.key - 1][0]); return e.preventDefault(); }   // 1–7 support rating
  if (ph === "decide") {                                                                // verdict keys: oo / o / r / d
    if (key === "r") { recordDecision("needs_second_review"); return e.preventDefault(); }
    if (key === "d") { recordDecision("reject"); return e.preventDefault(); }            // (⇧D handled above)
    if (key === "o") {
      if (e.repeat) return e.preventDefault();   // ignore auto-repeat so a held "o" isn't read as "oo"
      if (oTimer) { clearTimeout(oTimer); oTimer = null; recordDecision("accept"); }                         // "oo" → [oo]
      else { oTimer = setTimeout(() => { oTimer = null; recordDecision("accepted_with_caution"); }, 300); }   // "o"  → [o]
      return e.preventDefault();
    }
  }
  if (ph === "write") {
    if (key === "s") {                                                                  // s stage = preview (no-op if already staged)
      if (!state.pendingZtoken && !state.pendingDocToken) {
        const code = cand.evidence && cand.evidence.final_decision;
        if (code === "needs_second_review") docPreview("revise");
        else if (code === "reject") docPreview("strike");
        else zpreview();
      }
      return e.preventDefault();
    }
    if (key === "a") { const p = primary(); if (p) p(); return e.preventDefault(); }     // a apply / add to Zotero
  }
  if (e.key === "Enter") { const p = primary(); if (p) { p(); e.preventDefault(); } }    // ↵ primary action
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
  catch (e) { notify(e.message); }
}
async function switchRoot(root) {
  try { await api("POST", "/api/root", { root }); location.reload(); } catch (e) { notify(e.message); }
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
