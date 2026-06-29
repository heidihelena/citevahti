/* CiteVahti panel — Checks surface — manuscript claim checks (unit tests) and their results.
 * Split out of surfaces.js; classic script, loads before app.js. */

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
    <div class="modal-head"><h2 class="modal-title" id="testModal-title">Claim checks</h2><button class="chip-btn" data-test-close="1" aria-label="Close">✕</button></div>
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
