/* CiteVahti panel — Prompts modal — preprogrammed MCP prompts and the copy-to-chat helpers.
 * Split out of surfaces.js; classic script, loads before app.js. */

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
    <div class="modal-head"><h2 class="modal-title" id="promptsModal-title">Prompts &amp; chat</h2>
      <button class="chip-btn" data-prompts-close="1" aria-label="Close">✕</button></div>
    <div class="note">Preprogrammed skills — copy one for your chat client, or run it against
      your configured model (a local Ollama model keeps everything on your machine). The model
      is advisory; you still rate and decide. It never sets a rating or writes anything.
      <b>Replies here are advice only</b> — a connected chat client (e.g. Claude Desktop) runs
      the skills with real tools, and <b>Checks</b> runs the claim tests themselves.</div>
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
      if (label) {
        // Honesty line for prompt RUNS: a bare model can only narrate these skills, and a
        // reply that *describes* running the claim tests reads as if they actually ran (a
        // real pilot-user confusion). Say plainly what did and did not happen, and where
        // the real run lives.
        pending.insertAdjacentHTML("afterend",
          `<div class="note chat-advisory">Advice only — nothing was run or recorded.
            To really run claim tests use <b>Checks</b>; a connected chat client
            (e.g. Claude Desktop) can run the full skill with tools.</div>`);
      }
    }
  } catch (e) { pending.textContent = "chat failed: " + e.message; }
  log.scrollTop = log.scrollHeight;
}
