/* CiteVahti panel — source connections: Zotero & PubMed (paste-a-key + OAuth 1.0a).
 * Secrets are stored by the engine; keys never round-trip back to the browser.
 * Classic script; loads before app.js. */

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
