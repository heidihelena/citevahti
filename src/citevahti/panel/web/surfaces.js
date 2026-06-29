/* CiteVahti panel — top-level surface renderers: the Manuscripts intake / setup-recovery
 * / claim-extraction hand-off, plus the Checks / Atlas / Output / Settings shells that
 * renderSurface() (app.js) dispatches to. The modal-content helpers they call (runTests,
 * openWarehouse, openAiSettings, export*) still live in app.js. Classic script. */

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

/* ---- surface modal-content helpers (folded in from app.js, slice b) ----
 * The Output/Prompts/Checks/Atlas/Settings modal bodies that the shells above host
 * inline (runTests, openWarehouse, openAiSettings, export*, prompts, theme). The
 * central registerActions() and the few remaining glue helpers stay in app.js. */

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
