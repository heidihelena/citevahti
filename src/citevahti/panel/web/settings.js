/* CiteVahti panel — Settings surface — AI second opinion + theme.
 * Split out of surfaces.js; classic script, loads before app.js. */

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
      <p class="note">Check PyPI for a newer CiteVahti release. Read-only — it sends nothing
        about you and never installs. By default it runs only when you click.</p>
      <div class="actions"><button class="btn ghost" data-act="check-update">⬆ Check for updates</button></div>
      <label class="hkoff"><input type="checkbox" id="autoUpdChk"
        ${state.ctx && state.ctx.auto_update_check ? "checked" : ""}/> also check once each time
        the panel opens (one request to pypi.org; a quiet ⬆ badge appears if a newer
        version exists)</label>
    </div>
    <div id="settingsAi"></div>
  </div>`;
  openAiSettings($("#settingsAi"));   // hosts #aiModal inline within the AI segment
}


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
    <div class="modal-head"><h2 class="modal-title" id="aiModal-title">AI second opinion</h2><button class="chip-btn" data-ai-close="1" aria-label="Close">✕</button></div>
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
