/* CiteVahti panel — Manuscripts surface — intake, setup-recovery, claim-extraction hand-off, and bringing a manuscript in (paste / drag / import).
 * Split out of surfaces.js; classic script, loads before app.js. */

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
