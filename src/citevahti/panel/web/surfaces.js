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
