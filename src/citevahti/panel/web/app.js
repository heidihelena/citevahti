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
  maybeAutoUpdateCheck();   // fire-and-forget; only acts if the user opted in (Settings)
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
  // "review record" is what a researcher values (provenance), not "audit chain"
  el.textContent = a.intact ? `✓ Review record · ${a.entries}` : "⚠ Review record changed";
  el.setAttribute("aria-label", (a.intact ? `Review record intact — ${a.entries} steps logged`
                                          : "Review record changed outside CiteVahti") + " — open it");
}

/* The review record (audit trail) as a plain-language, timestamped timeline — the
 * provenance a clinician/registry cares about, not a hash-chain integrity badge. */
const REVIEW_EVENTS = {
  "store.init": "Project created", "claim.write": "Claim added",
  "intake.write": "Searched the literature", "candidate.link": "Linked evidence to a claim",
  "claim_support.save": "Recorded a support rating", "claim_support.ai": "AI gave a second opinion",
  "claim_support.adjudicate": "Adjudicated a disagreement",
  "decision.final": "Recorded a decision", "decision.record": "Recorded a decision",
  "zotero.transaction.commit": "Cited to Zotero", "writeback.commit": "Cited to Zotero",
  "document.edit": "Edited the manuscript", "claim.revise": "Reworded a claim",
  "transaction.undo": "Undid a step",
};
function humanEvent(ev) {
  return REVIEW_EVENTS[ev] || String(ev).replace(/[._]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
async function openReviewRecord() {
  const box = modalShell("reviewRecordModal");
  box.innerHTML = loadingHTML("Loading your review record…", { card: true });
  try {
    const r = await api("GET", "/api/audit/log");
    const rows = (r.entries || []).map((e) => {
      const p = e.payload || {};
      const det = [p.claim_type && claimTypeLabel(p.claim_type), p.comparison_status,
                   p.final_decision || p.decision, p.citekey && "@" + p.citekey].filter(Boolean);
      const when = e.ts ? new Date(e.ts).toLocaleString() : "";
      return `<div class="rr-row"><span class="rr-when">${esc(when)}</span>
        <span class="rr-what">${esc(humanEvent(e.event))}${det.length ? ` <span class="note">· ${esc(det.join(" · "))}</span>` : ""}</span></div>`;
    }).join("");
    const head = r.intact ? `<span class="tag ok">record intact ✓</span>`
                          : `<span class="tag nodoi">⚠ changed outside CiteVahti</span>`;
    box.innerHTML = `<div class="modal-card test">
      <div class="modal-head"><h2 class="modal-title" id="reviewRecordModal-title">Review record</h2><button class="chip-btn" data-act="close-record" aria-label="Close">✕</button></div>
      <div class="note">${head} · ${r.total} step(s) — a timestamped, tamper-evident record of what you reviewed, in order. On your Mac.</div>
      <div class="rr-list">${rows || '<div class="note">No steps logged yet.</div>'}</div>
      <div class="modal-foot">
        <button class="btn ghost" data-act="export-record">⬇ Export review record (PDF/zip)</button>
        <button class="btn primary" data-act="close-record">Done</button></div></div>`;
  } catch (e) { box.innerHTML = `<div class="modal-card"><div class="err">${esc(e.message)}</div>
    <div class="modal-foot"><button class="btn ghost" data-act="close-record">Close</button></div></div>`; }
}
function closeReviewRecord() { closeModalEl($("#reviewRecordModal")); }

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
      <div class="modal-head"><h2 class="modal-title" id="browseModal-title">Open your manuscript — choose the folder it's in</h2>
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
  // Intake (native file picker) + claim-extraction hand-off + setup recovery
  "choose-file": importWord, "setup-folder": setupFolder, "copy-handoff": copyHandoff,
  "stop-awaiting": finishLater,
  // Output: reveal a written file in the OS file manager
  reveal: (el) => revealFile(el.dataset.reveal),
  // Review record (audit timeline)
  "close-record": closeReviewRecord,
  "export-record": () => { closeReviewRecord(); renderSurface("output"); exportPacket(); },
  // Settings surface
  "check-update": checkForUpdates,
  "toggle-theme": (el) => { const d = toggleTheme(); el.textContent = d ? "◑ Light theme" : "◑ Dark theme"; },
  next: () => { const n = nextPending(); if (n) selectClaim(n); },
});
// User-initiated update check: the ONLY moment the panel talks to PyPI, and only on this
// click — never on load — so it doesn't weaken the no-silent-egress posture. Read-only.
/* Launch-time update check — STRICTLY opt-in (Settings checkbox, default off): one
 * request to pypi.org per panel open, only when the user chose it. Failure is silent —
 * a courtesy check must never disturb boot — and success is a quiet header badge, not
 * a toast. */
async function maybeAutoUpdateCheck() {
  if (!state.ctx || !state.ctx.auto_update_check) return;
  try {
    const r = await api("GET", "/api/check-update");
    if (r.checked && r.update_available) renderUpdateBadge(r.latest);
  } catch { /* offline or PyPI unreachable — say nothing */ }
}

function renderUpdateBadge(latest) {
  const host = $(".beta-badge");
  if (!host || $("#updateBadge")) return;
  host.insertAdjacentHTML("afterend",
    ` <button id="updateBadge" class="linklike"
        title="A newer CiteVahti is on PyPI — open Settings for the update steps">⬆ ${esc(latest)} available</button>`);
  $("#updateBadge").addEventListener("click", () => renderSurface("settings"));
}

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
  // opt-in launch-time update check (Settings) — persisted server-side in panel.json
  if (e.target.id === "autoUpdChk") {
    const enabled = e.target.checked;
    return void api("POST", "/api/prefs/update-check", { enabled })
      .then((r) => {
        state.ctx.auto_update_check = r.enabled;
        notify(r.enabled
          ? "Will check PyPI for a newer version once each time the panel opens."
          : "Launch-time update check off — the ⬆ Check for updates button still works.",
          { kind: "ok" });
      })
      .catch((err) => { e.target.checked = !enabled; notify(err.message); });
  }
});
$("#auditBadge").addEventListener("click", () => { loadAudit(); openReviewRecord(); });
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
    const wrote = `${r.injected} citation${r.injected === 1 ? "" : "s"} added`
      + (r.bib_path ? " + references.bib" : "")
      + (r.docx_status === "ok" ? " + Word .docx"
         : r.docx_status && r.docx_status !== "no_citations" ? " (.md + .bib ready to convert)" : "");
    setAgentLine(`Cite-stable export: ${esc(wrote)}.`);
    outputResult(savedToFolderCard(`Cite-stable manuscript — ${wrote}`, r.markdown_path),
      `Cite-stable manuscript saved: ${wrote}.`);
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
