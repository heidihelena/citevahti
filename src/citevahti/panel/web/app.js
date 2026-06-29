/* CiteVahti inline review (ADR-0002/0007) — the default panel, wired to the
 * loopback API. The review happens inside the manuscript: claim spans are
 * highlighted in place; an action-first card walks one obvious next step at a time
 * (Rate → Reveal → Decide → Write). Blinding is enforced server-side — the API
 * never returns the AI rating until a human rating exists, so this UI cannot
 * reveal it early. Zotero writes and document edits are previewed then confirmed,
 * and undoable. Connect actions store secrets via the engine; keys never round-trip
 * back to the browser. */

/* Shared building blocks now live in classic scripts loaded before this one (index.html
 * order: state.js → util.js → api.js → modal.js → feedback.js → events.js → app.js).
 * They share the global scope, so these symbols are available here unchanged:
 *   state.js    — state, SUPPORT, DECISIONS, PICO, …
 *   util.js     — esc, $, loadingHTML, citeOf, doiUrl, cssEscape, copyText, downloadJson
 *   api.js      — api, CSRF
 *   modal.js    — modalShell, closeModalEl, leaveModal
 *   feedback.js — notify, clearNotify, showErr, setAgentLine, renderAgent
 *   events.js   — registerActions + the delegated click listener */

/* ---------- boot ---------- */
async function boot() {
  applyTheme();
  drawLogos();
  await loadSessionToken();   // before anything that could POST — mutating requests need the token
  setupDropzone();   // before the first-run early return — dropping your first manuscript is the point
  try { state.ctx = await api("GET", "/api/context"); }
  catch (e) {
    // A fresh folder that was never set up: offer a one-click, no-terminal recovery
    // instead of telling the user to run `citevahti init` in a shell they can't find.
    if (e.code === "not_initialized") { const n = $("#surfnav"); if (n) n.hidden = false; return renderSetupNeeded(); }
    $("#card").innerHTML = `<div class="err">Can't reach the review panel — ${esc(e.message)}</div>`;
    return;
  }
  renderLedger();
  await loadHealth();
  loadAudit();
  const nav = $("#surfnav"); if (nav) nav.hidden = false;   // the surface router is live now
  // An empty ledger opens on the Manuscripts surface (intake); otherwise the review
  // workspace. Either way both surfaces stay reachable from the header nav.
  if (!state.ctx.claim_total) return renderSurface("manuscripts");
  renderSurface("workspace");
  await loadManuscripts();
  applyDeepLink();
}

/* Top-level surface router. Two surfaces today: the review "workspace" (the split
 * editor + evidence card) and "manuscripts" (intake, ledger switching, source
 * connections). Both live inside #split; we toggle which is shown via a data-surface
 * attribute rather than destroying the workspace DOM, so the Manuscripts surface is
 * reachable any time — not just on an empty first run. */
const SURFACES = ["manuscripts", "checks", "atlas", "output", "settings"];
// Toggle which surface is visible + sync the nav, WITHOUT (re)rendering its content.
// Used by renderSurface and by the setup/hand-off screens that fill #manuscripts themselves.
function showSurfaceShell(name) {
  state.surface = name;
  const split = $("#split"); if (split) split.dataset.surface = name;
  SURFACES.forEach((s) => { const el = $("#" + s); if (el) el.hidden = (s !== name); });
  const nav = $("#surfnav");
  if (nav) nav.querySelectorAll("[data-surface]").forEach((b) =>
    b.setAttribute("aria-current", String(b.dataset.surface === name)));
}
function renderSurface(name) {
  showSurfaceShell(name);
  ({ manuscripts: renderManuscripts, checks: renderChecksSurface, atlas: renderAtlasSurface,
     output: renderOutputSurface, settings: renderSettingsSurface }[name] || (() => {}))();
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

// Open a manuscript file from the picker OR a drag-and-drop, routed into the same
// import-review flow. .docx is converted server-side; .md/.markdown/.txt open as-is.
async function importFile(file) {
  if (!file) return;
  const name = file.name || "manuscript";
  try {
    if (/\.docx$/i.test(name)) {
      const dataUrl = await new Promise((res, rej) => {
        const fr = new FileReader();
        fr.onload = () => res(fr.result); fr.onerror = () => rej(new Error("could not read the file"));
        fr.readAsDataURL(file);
      });
      const b64 = String(dataUrl).split(",", 2)[1] || "";
      const r = await api("POST", "/api/manuscripts/import-docx", { docx_base64: b64 });
      openImportReview(name.replace(/\.docx$/i, "") + ".md", r.markdown || "");
    } else if (/\.(md|markdown|txt)$/i.test(name)) {
      const text = await file.text();
      openImportReview(name.replace(/\.(markdown|txt)$/i, ".md"), text);
    } else {
      notify("Drop a manuscript: .md, .markdown, .txt, or .docx.");
    }
  } catch (e) { notify(e.message); }
}

function importWord() {
  const inp = document.createElement("input");
  inp.type = "file"; inp.accept = ".docx,.md,.markdown,.txt";
  inp.onchange = () => importFile(inp.files && inp.files[0]);
  inp.click();
}

/* Drag-and-drop a manuscript anywhere on the window (works in the browser and the
 * native desktop webview): a full-window dropzone that feeds importFile(). */
function setupDropzone() {
  if ($("#dropzone")) return;
  const ov = document.createElement("div");
  ov.id = "dropzone"; ov.className = "dropzone-overlay"; ov.hidden = true;
  ov.innerHTML = `<div class="dz-card">Drop a manuscript to open it
    <span class="dz-sub">.md · .markdown · .txt · .docx</span></div>`;
  document.body.appendChild(ov);
  let depth = 0;
  const hasFiles = (e) => e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files");
  window.addEventListener("dragenter", (e) => { if (hasFiles(e)) { depth++; ov.hidden = false; } });
  window.addEventListener("dragover", (e) => { if (!ov.hidden) e.preventDefault(); });
  window.addEventListener("dragleave", () => { depth = Math.max(0, depth - 1); if (!depth) ov.hidden = true; });
  window.addEventListener("drop", (e) => {
    if (hasFiles(e)) {
      e.preventDefault(); depth = 0; ov.hidden = true;
      importFile(e.dataTransfer.files[0]);
    }
  });
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
/* Prompt panel — the preprogrammed agent skills (run claim tests, screen a topic, check a
 * paragraph, methods statement) in one place; copy one to paste into a chat client or a
 * local model. Read-only text from /api/prompts; runs no model itself. */
async function openPrompts() {
  const tm = $("#toolsmenu"); if (tm) tm.removeAttribute("open");
  let data;
  try { data = await api("GET", "/api/prompts"); }
  catch (e) { notify(e.message); return; }
  const box = modalShell("promptsModal");
  let lastGroup = null;
  const cards = (data.prompts || []).map((p, i) => {
    const hdr = p.group && p.group !== lastGroup ? `<div class="pc-group">${esc(p.group)}</div>` : "";
    lastGroup = p.group;
    return hdr + `
    <div class="promptcard">
      <div class="pc-head"><b>${esc(p.label)}</b> <span class="pc-name">${esc(p.name)}</span></div>
      <div class="note">${esc(p.description)}</div>
      <div class="actions"><button class="btn ghost" data-copy-prompt="${i}">⧉ Copy</button>
        <button class="btn ghost" data-run-prompt="${i}" title="Run this skill against your configured model">▷ Run in chat</button></div>
    </div>`;
  }).join("");
  box.innerHTML = `<div class="modal-card">
    <div class="modal-head"><b>Prompts &amp; chat</b>
      <button class="chip-btn" data-prompts-close="1" aria-label="Close">✕</button></div>
    <div class="note">Preprogrammed skills — copy one for your chat client, or run it against
      your configured model (a local Ollama model keeps everything on your machine). The model
      is advisory; you still rate and decide. It never sets a rating or writes anything.</div>
    ${cards}
    <div id="promptsResult" class="note"></div>
    <div class="chatbox">
      <div id="chatlog" class="chatlog" aria-live="polite"></div>
      <div class="chatrow">
        <input id="chatInput" type="text" aria-label="Message the model"
          placeholder="Ask the model… (local-first with Ollama)" />
        <button class="btn primary" id="chatSend">Send</button>
      </div>
    </div></div>`;
  box.querySelectorAll("[data-copy-prompt]").forEach((b) => {
    b.onclick = async () => {
      const p = data.prompts[+b.dataset.copyPrompt];
      await copyText(p.text);
      const r = $("#promptsResult");
      if (r) r.innerHTML = `✓ Copied the <b>${esc(p.name)}</b> prompt — paste it into your chat client.`;
    };
  });
  box.querySelectorAll("[data-run-prompt]").forEach((b) => {
    const p = data.prompts[+b.dataset.runPrompt];
    b.onclick = async () => {
      let msg = p.text;
      if (p.name === "draft_from_claims") {   // pull the vetted claims so there's nothing to paste
        try {
          const ctx = await api("GET", "/api/draft-context");
          msg += "\n\nMy accepted claims to draft from:\n" + formatDraftContext(ctx);
        } catch (e) { /* fall back to the bare prompt */ }
      }
      sendChat(msg, p.label);
    };
  });
  const x = box.querySelector("[data-prompts-close]"); if (x) x.onclick = () => closeModalEl(box);
  const send = $("#chatSend"), inp = $("#chatInput");
  if (send && inp) {
    send.onclick = () => { const m = inp.value.trim(); if (m) { inp.value = ""; sendChat(m); } };
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") send.onclick(); });
  }
}

/* Format the accepted claims for the draft skill — an uncited accepted claim is shown as
 * "needs a source", never given an invented citekey. */
function formatDraftContext(ctx) {
  const claims = (ctx && ctx.claims) || [];
  if (!claims.length) return "(no accepted claims yet — accept some citations first)";
  return claims.map((c) => c.cited
    ? `- ${c.claim_text} [@${c.citekey}]`
    : `- ${c.claim_text} (needs a source — ${c.reason || "uncited"})`).join("\n");
}

/* Small chat with the configured model (local Ollama / LM Studio / API key). Advisory text
 * only — the server records nothing, calls no tools, and writes nothing. */
async function sendChat(message, label) {
  const log = $("#chatlog"); if (!log) return;
  const shown = label ? `Run: ${label}` : message;
  log.insertAdjacentHTML("beforeend",
    `<div class="chat-you">${esc(shown)}</div><div class="chat-ai">…</div>`);
  const pending = log.lastElementChild;
  log.scrollTop = log.scrollHeight;
  try {
    const r = await api("POST", "/api/chat", { message });
    if (r.status === "ai_off") {
      // turn the dead-end into a next action: open AI settings (recommends a local model)
      pending.innerHTML = esc(r.message || "No model is configured.") +
        ` <button class="btn ghost" id="aiOffSetup" title="Pick a model — a local Ollama model keeps everything on your machine">⚙ Set up a model</button>`;
      const b = pending.querySelector("#aiOffSetup");
      if (b) b.onclick = () => { const pm = $("#promptsModal"); if (pm) closeModalEl(pm); openAiSettings(); };
    } else {
      pending.textContent = r.reply || "(no reply)";
    }
  } catch (e) { pending.textContent = "chat failed: " + e.message; }
  log.scrollTop = log.scrollHeight;
}

async function saveImported() {
  const filename = (($("#imName") || {}).value || "").trim();
  const content = ($("#imBody") || {}).value || "";
  if (!filename) { ($("#imName") || {}).focus && $("#imName").focus(); return; }
  try {
    const r = await api("POST", "/api/manuscripts/paste", { filename, content });
    closeImportModal();
    // Same hand-off as the paste path: claims are extracted in the chat assistant, then the
    // review opens itself. (If this manuscript already has claims, loadManuscripts shows them.)
    renderHandoff(r);
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

/* ---------- the manuscript "unit test" suite ---------- */
// each claim is a test case: does it meet its references, and are the citations real?
const TEST_CHECK_LABELS = {
  has_reference: "has a reference", reviewed: "reviewed",
  supported: "reference supports the claim", citation_identified: "citation has a DOI/PMID",
  not_retracted: "citation not retracted", citation_real: "citation is real",
  in_scope: "in indexed scope",
};
const TEST_BADGE = { pass: "PASS", fail: "FAIL", skip: "SKIP" };


async function runTests(online, host) {
  const box = modalShell("testModal", host || testSurfaceHost());
  box.innerHTML = loadingHTML(online ? "Checking claims — verifying citations online (this can take a moment)…" : "Checking claims…", { card: true });
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
    <div class="modal-head"><b>Claim checks</b><button class="chip-btn" data-test-close="1">✕</button></div>
    <div class="tsummary ${allGreen ? "ok" : "bad"}"><b>${s.passed}</b> passed · <b>${s.failed}</b> failed · <b>${s.skipped}</b> skipped — of ${s.total} claims</div>
    <div class="note">${s.online ? "Citations verified online — real and not retracted." : "Structural checks only. Citations were not verified online."}</div>
    ${warn}
    <div class="tlist">${rows || '<div class="note">No claims to test yet.</div>'}</div>
    <div class="modal-foot">
      ${s.online ? "" : `<button class="btn ghost" data-test-online="1">Also verify citations online</button>`}
      <button class="btn primary" data-test-close="1">Done</button></div></div>`;
}
function closeTests() { leaveModal("testModal"); }
// Where unit-test results render: a dedicated slot in the Checks surface (falls back to
// a real modal only if the surface isn't mounted, e.g. a deep-linked call).
function testSurfaceHost() { return $("#checksTestResults") || $("#checks") || null; }

/* ---------- de-identified warehouse + Atlas contribution (download-only) ---- */
async function openWarehouse(host) {
  const box = modalShell("whModal", host);
  box.innerHTML = loadingHTML("Loading…", { card: true });
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

    <div class="lbl cv-mt-lg">Contribute to Atlas</div>
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
function closeWarehouse() { leaveModal("whModal", () => { state.lastBundle = null; }); }

/* ---------- AI second opinion settings ----------
 * Privacy-first. Most users drive CiteVahti through an assistant over MCP, which
 * submits the blinded rating with no key (subscription pays) — so the MCP path is
 * framed first and the off/local/api modes are for CiteVahti's OWN call. The API
 * key is NEVER entered here: it lives in the keychain/env (we only show presence). */
async function openAiSettings(host) {
  const box = modalShell("aiModal", host);
  box.innerHTML = loadingHTML("Loading…", { card: true });
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
function closeAiSettings() { leaveModal("aiModal"); }

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
  // selectClaim now switches to the claim's manuscript itself, so a deep-link to a
  // claim in another manuscript works instead of being silently dropped.
  if (focus) selectClaim(focus);
  if (q.get("legend") === "1") {
    $("#legend").removeAttribute("hidden");
    $("#legendBtn").setAttribute("aria-expanded", "true");
  }
}

async function loadHealth() {
  try { state.health = await api("GET", "/api/health"); } catch { state.health = null; }
  renderConns();
  renderBetaBadge();
}

/* Show the running version on the BETA chip, so a stale build is obvious at a glance. */
function renderBetaBadge() {
  const b = document.querySelector(".beta-badge");
  const v = state.health && state.health.version;
  if (b && v) {
    b.textContent = "BETA · v" + v;
    b.title = "CiteVahti " + v + " (beta) — free to use for testing and research feedback";
  }
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

async function loadManuscripts(preferId) {
  const data = await api("GET", "/api/manuscripts");
  state.manuscripts = data.manuscripts || [];
  state.ctx.manuscripts_dir = data.manuscripts_dir;
  const has = (id) => id && state.manuscripts.some((m) => m.manuscript_id === id);
  // One precedence for "what am I working on": a just-added/imported manuscript →
  // the one already open this session → the one last worked on (persisted across
  // reloads) → the first in the list. Closes the "reload snaps back to the stale one".
  state.activeMs =
    (has(preferId) && preferId) ||
    (has(state.activeMs) && state.activeMs) ||
    (has(data.active) && data.active) ||
    (state.manuscripts[0] && state.manuscripts[0].manuscript_id) ||
    null;
  if (state.activeMs) await loadManuscript(state.activeMs);
  renderMsBar();
}

async function loadManuscript(id) {
  state.activeMs = id;
  state.view = await api("GET", `/api/manuscript/${encodeURIComponent(id)}`);
  $("#msName").textContent = id;
  renderDoc(); renderProgress();
  if (state.manuscripts.length) renderMsBar();   // keep the switcher highlight on the active one (e.g. after a cross-manuscript jump)
  loadTriage();   // surface "what needs you", worst-first (fire-and-forget)
}

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
  // empty state: no claims yet AND no documents in the bound folder — say so and point
  // at the action, instead of rendering a blank label.
  const switcher = state.manuscripts.length
    ? `<span class="msswitch"><span class="lbl">Manuscript</span>${picks}</span>`
    : `<span class="msswitch empty"><span class="lbl">No manuscript yet</span>
        <span class="mshint">Open your document folder, or add a claim to begin.</span></span>`;
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
  box.innerHTML = loadingHTML("Loading…", { card: true });
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
  try {
    await api("POST", "/api/manuscripts/bind", { dir });
    closeBrowse();
    await loadManuscripts();
    // binding a folder means "work on what's in here" — jump to a manuscript that
    // actually lives in it, not the reconstructed-from-claims one you came from.
    const inFolder = state.manuscripts.find((m) => m.resolved);
    if (inFolder && inFolder.manuscript_id !== state.activeMs) {
      await loadManuscript(inFolder.manuscript_id);
    }
  } catch (e) { notify(e.message); }
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
    <div class="note">Keep it <b>atomic</b> — one population · one intervention · one outcome · one support question. Split compound sentences into separate claims.</div>
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

/* ---------- Manuscripts surface (intake / ledgers / sources) ----------
 * Formerly the first-run takeover that overwrote #split; now it renders into its own
 * surface container so it's reachable any time via the header nav (renderSurface). */
async function renderManuscripts() {
  let ledgers = [];
  try { ledgers = (await api("GET", "/api/ledgers")).ledgers || []; } catch {}
  const others = ledgers.filter((l) => l.claims > 0 && l.root !== state.ctx.root);
  const rows = ledgers.map((l) =>
    `<div class="ledrow"><span class="path">${esc(l.root)}</span><span class="n">${l.claims} claims</span>
      ${l.root !== state.ctx.root && l.claims > 0 ? `<button class="btn ghost" data-switch="${esc(l.root)}">Switch here</button>` : (l.root === state.ctx.root ? `<span class="note">active</span>` : "")}</div>`).join("");
  $("#manuscripts").innerHTML = `<div class="firstrun">
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
      <p class="note"><b>Drag a <code>.md</code> or <code>.docx</code> onto this window</b>, or paste your
      Markdown below — CiteVahti saves it and remembers where it lives. You'll get the exact prompt to
      paste into your chat client to extract claims next.</p>
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

/* ---------- Checks surface (unit tests + maintenance scans) ----------
 * Promoted from the test-results modal + the four Tools-menu scan buttons. Unit-test
 * results render inline into #checksTestResults (runTests targets it via testSurfaceHost). */
function renderChecksSurface() {
  const host = $("#checks"); if (!host) return;
  host.innerHTML = `<div class="surfacepad">
    <h2>Checks</h2>
    <div class="seg">
      <div class="lbl">Claim checks</div>
      <p class="note">Does every claim meet its references, and are the citations real? Offline checks
        run instantly; the online run also verifies each citation exists and isn't retracted.</p>
      <div class="actions cv-wrap">
        <button class="btn primary" data-act="run-tests">✓ Check claims (offline)</button>
        <button class="btn ghost" data-act="run-tests-online">Check claims + verify citations online</button>
      </div>
      <div id="checksTestResults"></div>
    </div>
    <div class="seg">
      <div class="lbl">Maintenance scans</div>
      <p class="note">Housekeeping over your candidate evidence. Each one reports; none decides.</p>
      <div class="actions cv-wrap">
        <button class="btn ghost" data-act="resolve-dois">⟳ Resolve DOIs</button>
        <button class="btn ghost" data-act="recheck-library">⟳ Re-check library</button>
        <button class="btn ghost" data-act="scan-retractions">⚠ Scan retractions</button>
        <button class="btn ghost" data-act="scan-licenses">⚖ Scan licences</button>
      </div>
    </div>
  </div>`;
}

/* ---------- Atlas surface (local evidence map + contribution) ----------
 * Hosts the warehouse modal inline; its ✕/Done route back via leaveModal(). */
function renderAtlasSurface() {
  const host = $("#atlas"); if (!host) return;
  host.innerHTML = "";
  openWarehouse(host);
}

/* ---------- Output surface (export + cite-stable) ----------
 * Promoted from the Export modal + the Tools-menu cite-stable export. All buttons reuse
 * the existing delegated data-act handlers — no new export logic. */
function renderOutputSurface() {
  const host = $("#output"); if (!host) return;
  host.innerHTML = `<div class="surfacepad">
    <h2>Output</h2>
    <div class="seg">
      <div class="lbl">Citation-integrity report &amp; review trail</div>
      <p class="note">For a supervisor, co-author, or journal. Local; nothing is transmitted.</p>
      <div class="actions cv-wrap">
        <button class="btn ghost" data-act="export-md">⬇ Markdown (.md)</button>
        <button class="btn ghost" data-act="export-pdf">⎙ PDF — print / Save as PDF</button>
        <button class="btn ghost" data-act="export-word">📄 Word (.docx)</button>
        <button class="btn primary" data-act="export-packet">⛁ Review packet (.zip)</button>
      </div>
    </div>
    <div class="seg">
      <div class="lbl">Cite-stable manuscript</div>
      <p class="note">Embed <code>[@citekey]</code> for every accepted claim into your .md and write
        references.bib (and a Word .docx if Pandoc is installed) — citations that survive copy-paste
        and conversion to Word.</p>
      <div class="actions"><button class="btn ghost" data-act="cite-export">⎘ Cite-stable export</button></div>
    </div>
    <div class="seg">
      <div class="lbl">Bring a manuscript in</div>
      <div class="actions"><button class="btn ghost" data-act="import-word">📄 Import Word (.docx) → review</button></div>
    </div>
  </div>`;
}

/* ---------- Settings surface ----------
 * AI second opinion (hosted inline) + theme, keyboard shortcuts, and the update check —
 * gathered from the scattered header/Tools controls into one home. */
function renderSettingsSurface() {
  const host = $("#settings"); if (!host) return;
  const dark = document.documentElement.classList.contains("zs-dark");
  host.innerHTML = `<div class="surfacepad">
    <h2>Settings</h2>
    <div class="seg">
      <div class="lbl">Appearance &amp; shortcuts</div>
      <div class="actions"><button class="btn ghost" data-act="toggle-theme">${dark ? "◑ Light theme" : "◑ Dark theme"}</button></div>
      <label class="hkoff"><input type="checkbox" id="hkToggle2" ${state.hotkeysOff ? "checked" : ""}/> turn keyboard shortcuts off</label>
    </div>
    <div class="seg">
      <div class="lbl">Updates</div>
      <p class="note">Check PyPI for a newer CiteVahti release. Read-only and only when you click — it
        sends nothing about you and never installs.</p>
      <div class="actions"><button class="btn ghost" data-act="check-update">⬆ Check for updates</button></div>
    </div>
    <div id="settingsAi"></div>
  </div>`;
  openAiSettings($("#settingsAi"));   // hosts #aiModal inline within the AI segment
}

async function savePastedManuscript() {
  const filename = (($("#pasteName") || {}).value || "").trim();
  const content = ($("#pasteBody") || {}).value || "";
  const out = $("#pasteResult");
  if (!filename) { out.innerHTML = `<div class="note">Give the file a name first.</div>`; return; }
  if (!content.trim()) { out.innerHTML = `<div class="note">Paste some Markdown first.</div>`; return; }
  try {
    const r = await api("POST", "/api/manuscripts/paste", { filename, content });
    renderHandoff(r);
  } catch (e) { out.innerHTML = `<div class="note">${esc(e.message)}</div>`; }
}

/* ---------- "This folder isn't set up" recovery (replaces the `citevahti init` error) ----
 * Reached from boot() when /api/context returns not_initialized — i.e. the panel was opened
 * in a folder that was never set up. One click sets it up; no terminal involved. */
async function renderSetupNeeded() {
  const host = $("#manuscripts"); if (!host) return;
  let active = "", others = [];
  try { const lg = await api("GET", "/api/ledgers"); active = lg.active || ""; others = (lg.ledgers || []).filter((l) => l.claims > 0); } catch {}
  const rows = others.map((l) =>
    `<div class="ledrow"><span class="path">${esc(l.root)}</span><span class="n">${l.claims} claims</span>
       <button class="btn ghost" data-switch="${esc(l.root)}">Open this one</button></div>`).join("");
  showSurfaceShell("manuscripts");
  host.innerHTML = `<div class="firstrun">
    <h2>This folder isn't set up for CiteVahti yet</h2>
    <p class="note">CiteVahti keeps each project's claims, ratings, and audit trail inside the folder
      you open it from. This one${active ? ` (<code>${esc(active)}</code>)` : ""} is empty —
      <b>no Terminal needed</b>, just pick one below.</p>
    <div class="panel-box">
      <div class="lbl">Start a review in this folder</div>
      <p class="note">Sets up CiteVahti here so you can add a manuscript and begin.</p>
      <div class="actions"><button class="btn primary" data-act="setup-folder">Set up this folder</button></div>
      <div id="setupResult"></div>
    </div>
    ${others.length ? `<div class="panel-box"><div class="lbl">…or open a project you already started</div>${rows}</div>` : ""}
  </div>`;
}
async function setupFolder() {
  const out = $("#setupResult");
  if (out) out.innerHTML = loadingHTML("Setting up…");
  try {
    await api("POST", "/api/setup", {});
    if (out) out.innerHTML = `<div class="note ok">Done — opening your review…</div>`;
    location.reload();   // re-boot: /api/context now succeeds and routes to the intake
  } catch (e) { if (out) out.innerHTML = `<div class="note">Couldn't set up this folder — ${esc(e.message)}</div>`; }
}

/* ---------- claim-extraction hand-off (the panel never calls an AI itself) ----------
 * After a manuscript is saved (paste OR drag/import), claims are pulled by the user's chat
 * assistant over MCP — a separate app. Make that explicit, hand over the exact prompt, and
 * POLL the local ledger so the review opens itself the moment the claims land — no reload. */
function renderHandoff(r) {
  const host = $("#manuscripts"); if (!host) return;
  const prompt = r.next_prompt || `Extract the verifiable claims from ${r.filename || "this manuscript"} and add each one with CiteVahti.`;
  showSurfaceShell("manuscripts");
  host.innerHTML = `<div class="firstrun">
    <h2>Extracting claims from ${esc(r.filename || "your manuscript")}</h2>
    <p class="note">CiteVahti never calls an AI itself — your <b>chat assistant</b> (Claude / Cowork)
      pulls the claims out, using CiteVahti's tools over MCP.</p>
    <div class="panel-box">
      <div class="lbl">1 · Paste this into your chat assistant</div>
      <textarea class="revbox" readonly onclick="this.select()">${esc(prompt)}</textarea>
      <div class="actions"><button class="btn ghost" data-act="copy-handoff">⧉ Copy prompt</button></div>
    </div>
    <div class="cv-loading is-prominent cv-mt-lg"><span class="cv-spin" aria-hidden="true"></span>
      <span><b>Waiting for claims…</b> keep this panel open — your review opens automatically the moment they arrive.</span></div>
    <p class="note">Already reviewing another project? The <b>Manuscripts</b> tab lets you switch.</p>
  </div>`;
  startAwaitingClaims();
}
function copyHandoff() {
  const ta = document.querySelector("#manuscripts .revbox"); if (!ta) return;
  ta.focus(); ta.select();
  try { document.execCommand("copy"); notify("Prompt copied — paste it into your chat assistant.", { kind: "ok" }); } catch {}
}
// Local-only poll (loopback, never egress) for claims arriving from the chat assistant.
function startAwaitingClaims() {
  if (state.awaiting) return;
  state.awaiting = true;
  let tries = 0;
  const poll = async () => {
    if (!state.awaiting) return;
    tries += 1;
    try {
      const ctx = await api("GET", "/api/context");
      if (ctx && ctx.claim_total) {
        stopAwaitingClaims();
        state.ctx = ctx;
        notify(`${ctx.claim_total} claim(s) received — opening your review.`, { kind: "ok" });
        renderSurface("workspace");
        await loadManuscripts();
        applyDeepLink();
        return;
      }
    } catch { /* folder may still be initialising — keep waiting */ }
    if (!state.awaiting) return;
    if (tries >= 150) { stopAwaitingClaims(); return; }   // ~10 min cap (150 × 4s)
    state.awaitTimer = setTimeout(poll, 4000);
  };
  state.awaitTimer = setTimeout(poll, 4000);
}
function stopAwaitingClaims() { state.awaiting = false; if (state.awaitTimer) clearTimeout(state.awaitTimer); state.awaitTimer = null; }

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

/* [data-act] handlers, registered with the delegated click listener in events.js.
 * Handlers receive (el) — the matched [data-act] element. As components are split into
 * their own files (later slices) these registrations move next to the code they call. */
registerActions({
  "connect-zotero": () => connect("zotero"), "connect-zotero-oauth": connectOAuth, search: doSearch,
  "open-zotero": () => openInZotero(activeCand()), "zot-evidence": openZotEvidence, lexcheck: runLexCheck,
  "print-audit": printAudit,
  "edit-claim": toggleEditClaim, "claimedit-preview": editClaimPreview, "claimedit-commit": editClaimCommit,
  "claimedit-save": editClaimSaveLedger, "claimedit-cancel": cancelEditClaim,
  "save-claim": saveClaim, "cancel-claim": () => { $("#addClaimBox").innerHTML = ""; },
  zpreview, zcommit, zcancel: () => { resetWrite(); renderCard(); },
  zundo, docpreview: (el) => docPreview(el.dataset.kind), doccommit: docCommit, doccancel: () => { resetWrite(); renderCard(); },
  docundo: docUndo, unlink: unlinkCandidate, gonext: goToNextClaim, exportreport: exportReport,
  "run-ai": runAiSecondOpinion,
  "export-md": exportReport, "export-pdf": exportPdf, "export-packet": exportPacket,
  "export-word": exportDocx, "import-word": importWord, "cite-export": citeExport,
  // Checks surface: unit tests + maintenance scans (same actions as the header/Tools controls)
  "run-tests": () => runTests(false), "run-tests-online": () => runTests(true),
  "resolve-dois": () => runScan("resolve-dois"), "recheck-library": () => runScan("recheck-library"),
  "scan-retractions": () => runScan("scan-retractions"), "scan-licenses": () => runScan("scan-licenses"),
  // Setup recovery + claim-extraction hand-off
  "setup-folder": setupFolder, "copy-handoff": copyHandoff,
  // Settings surface
  "check-update": checkForUpdates,
  "toggle-theme": (el) => { const d = toggleTheme(); el.textContent = d ? "◑ Light theme" : "◑ Dark theme"; },
  next: () => { const n = nextPending(); if (n) selectClaim(n); },
});
// User-initiated update check: the ONLY moment the panel talks to PyPI, and only on this
// click — never on load — so it doesn't weaken the no-silent-egress posture. Read-only.
async function checkForUpdates() {
  const tm = $("#toolsmenu"); if (tm) tm.removeAttribute("open");
  notify("Checking PyPI for a newer version…", { kind: "ok", sticky: true });
  try {
    const r = await api("GET", "/api/check-update");
    // checked=false means we couldn't reach PyPI — say so plainly, not as a crash.
    // update_available stays sticky so the user can read the upgrade steps; up-to-date
    // auto-dismisses.
    notify(r.message, r.checked ? { kind: "ok", sticky: !!r.update_available }
                                : { kind: "error" });
  } catch (e) { notify(e.message); }
}
$("#reload").addEventListener("click", () => { loadManuscripts(); loadAudit(); });
$("#prompts").addEventListener("click", openPrompts);
// The Run-unit-tests CTA opens the Checks surface and runs immediately. Export, AI,
// evidence map, scans, cite-stable, updates and theme moved out of the header entirely —
// they live on the Checks/Atlas/Output/Settings surfaces now (see the data-act handlers).
$("#runTests").addEventListener("click", () => { renderSurface("checks"); runTests(false); });
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
  // the Settings-surface copy of the keyboard-shortcuts toggle
  if (e.target.id === "hkToggle2") return void setHotkeysOff(e.target.checked);
});
$("#auditBadge").addEventListener("click", () => loadAudit());
$("#legendBtn").addEventListener("click", () => {
  const el = $("#legend"), opening = el.hasAttribute("hidden");
  el.toggleAttribute("hidden");
  $("#legendBtn").setAttribute("aria-expanded", String(opening));
});
// keyboard-shortcut toggle, persisted across sessions (for people writing in the panel).
// Two checkboxes share it now — the legend (#hkToggle) and Settings (#hkToggle2) — so a
// single setter keeps them, state, and localStorage in sync.
function setHotkeysOff(v) {
  state.hotkeysOff = v;
  try { localStorage.setItem("citevahti.hotkeysOff", v ? "1" : "0"); } catch {}
  const a = $("#hkToggle"), b = $("#hkToggle2");
  if (a) a.checked = v; if (b) b.checked = v;
}
(function initHotkeyToggle() {
  try { state.hotkeysOff = localStorage.getItem("citevahti.hotkeysOff") === "1"; } catch { state.hotkeysOff = false; }
  const cb = $("#hkToggle"); if (!cb) return;
  cb.checked = state.hotkeysOff;
  cb.addEventListener("change", () => setHotkeysOff(cb.checked));
})();
async function maintenance(path, label, fmt) {
  try {
    const r = await api("POST", path, {});
    notify(fmt(r), { kind: "ok" });
    await loadManuscripts();
    if (state.activeClaim) await selectClaim(state.activeClaim);
  } catch (e) { notify(`${label} failed: ${e.message}`, { retry: () => maintenance(path, label, fmt) }); }
}
// One registry for the maintenance scans, shared by the Tools-menu buttons and the
// Checks surface (data-act="…") so the two entry points can't drift apart.
const SCANS = {
  "resolve-dois": ["/api/candidates/resolve-dois", "Resolve DOIs",
    (r) => `Resolved ${r.resolved || 0} missing DOI(s) from PMIDs.`],
  "recheck-library": ["/api/candidates/recheck-library", "Re-check library",
    (r) => `Checked ${r.checked || 0} candidate(s); ${r.flagged || 0} now flagged as already in Zotero.`],
  "scan-retractions": ["/api/candidates/scan-retractions", "Scan retractions",
    (r) => `Checked ${r.checked || 0} candidate(s); ${r.flagged || 0} flagged as RETRACTED.`],
  "scan-licenses": ["/api/candidates/scan-licenses", "Scan licences",
    (r) => `Checked ${r.checked || 0} candidate(s); reuse rights filled for ${r.filled || 0}.`],
};
// Triggered from the Checks surface via data-act="resolve-dois" etc. (no header buttons).
function runScan(key) { const s = SCANS[key]; if (s) maintenance(s[0], s[1], s[2]); }
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
// citeExport() is invoked from the Output surface via data-act="cite-export".
// Shared by the header ◑ button and the Settings surface; returns the new dark state.
function toggleTheme() {
  const dark = document.documentElement.classList.toggle("zs-dark");
  try { localStorage.setItem("cv-theme", dark ? "dark" : "light"); } catch { /* private mode */ }
  syncThemeLabel();
  return dark;
}
// toggleTheme() is invoked from the Settings surface via data-act="toggle-theme".
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
  // claim navigation/rating only makes sense on the review workspace; on other surfaces
  // (Checks, Settings, …) the manuscript isn't shown, so don't move the selection underneath.
  if (state.surface !== "workspace") return;
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
