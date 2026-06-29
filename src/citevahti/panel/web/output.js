/* CiteVahti panel — Output surface — report exports (Markdown / PDF / Word / packet) and the import-Word entry.
 * Split out of surfaces.js; classic script, loads before app.js. */

/* ---------- Output surface (export + cite-stable) ----------
 * Promoted from the Export modal + the Tools-menu cite-stable export. All buttons reuse
 * the existing delegated data-act handlers — no new export logic. */
function renderOutputSurface() {
  const host = $("#output"); if (!host) return;
  host.innerHTML = `<div class="surfacepad">
    <h2>Output</h2>
    <div id="outputResult"></div>
    <div class="seg">
      <div class="lbl">Your review record</div>
      <p class="note">A timestamped, tamper-evident record of what you reviewed and in what order — for a
        supervisor, co-author, journal, or registry. Built on your Mac; nothing is transmitted.</p>
      <div class="actions cv-wrap">
        <button class="btn primary" data-act="export-packet">⛁ Review record (.zip)</button>
        <button class="btn ghost" data-act="export-word">📄 Word (.docx)</button>
        <button class="btn ghost" data-act="export-pdf">⎙ PDF</button>
        <button class="btn ghost" data-act="export-md">⬇ Markdown</button>
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

// Result of a write that landed on disk: name it in plain language + a Show-in-Finder button.
// Falls back to a toast when the Output surface isn't mounted (e.g. exportReport from a banner).
function outputResult(html, plainMsg) {
  const el = $("#outputResult");
  if (el) { el.innerHTML = html; el.scrollIntoView({ block: "nearest" }); }
  else if (plainMsg) notify(plainMsg, { kind: "ok" });
}
function savedToFolderCard(title, path) {
  return `<div class="cv-card is-ok"><div class="lbl ok">✓ Saved</div>
    <p class="note"><b>${esc(title)}</b> — in your project folder.</p>
    <div class="actions"><button class="btn" data-act="reveal" data-reveal="${esc(path)}">📁 Show in Finder</button></div></div>`;
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
    const intact = r.audit_intact === false ? "⚠ review record BROKEN"
      : r.audit_intact ? `record intact ✓ (${r.audit_entries} steps)` : "";
    setAgentLine(`Report saved — generated ${esc(r.generated_at || "now")}${intact ? " · " + intact : ""}.`);
    outputResult(`<div class="cv-card is-ok"><div class="lbl ok">✓ Saved to your Downloads</div>
      <p class="note">Markdown review record${intact ? " · " + intact : ""}.</p></div>`,
      "Markdown review record saved to your Downloads.");
  } catch (e) { outputResult(`<div class="cv-error">${esc(e.message)}</div>`, e.message); }
}


/* ---------- export menu: Markdown · PDF (print) · review packet (.zip) ----------
 * Researchers live in Word/PDF; these bridge out without leaving local-first. PDF is
 * the browser's own "Save as PDF" on a print-styled render — zero dependencies. */
function openExportModal() {
  const box = modalShell("exportModal");
  box.innerHTML = `<div class="modal-card">
    <div class="modal-head"><h2 class="modal-title" id="exportModal-title">Export</h2><button class="chip-btn" data-export-close="1" aria-label="Close">✕</button></div>
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
  outputResult(loadingHTML("Building your Word file… this can take a minute."));
  try {
    const r = await api("POST", "/api/report/docx", {});
    closeExportModal();
    const n = r.claim_count;
    outputResult(savedToFolderCard(`Word review record (${n} claim${n === 1 ? "" : "s"})`, r.output_file));
    setAgentLine(`Word report saved (${n} claim(s)).`);
  } catch (e) { outputResult(`<div class="cv-error">${esc(e.message)}</div>`, e.message); }   // shows the "install citevahti[docx]" hint if absent
}


async function exportPdf() {
  try {
    const r = await api("GET", "/api/report");
    const w = window.open("", "_blank");
    if (!w) { notify("Allow pop-ups to print the report to PDF, or use Markdown export."); return; }
    w.document.write(r.html || "<p>(empty report)</p>");
    w.document.close(); w.focus();
    setTimeout(() => { try { w.print(); } catch {} }, 350);   // render, then open the print dialog
    outputResult(`<div class="cv-card"><div class="lbl">⎙ Print dialog opened</div>
      <p class="note">Choose <b>Save as PDF</b> in the print dialog to keep a copy.</p></div>`);
  } catch (e) { outputResult(`<div class="cv-error">${esc(e.message)}</div>`, e.message); }
}

async function exportPacket() {
  outputResult(loadingHTML("Building your review record…"));
  try {
    const r = await api("POST", "/api/report/packet", {});
    closeExportModal();
    const n = r.claim_count;
    outputResult(savedToFolderCard(`Review record (${n} claim${n === 1 ? "" : "s"})`, r.output_file));
    setAgentLine(`Review packet saved (${n} claim(s)).`);
  } catch (e) { outputResult(`<div class="cv-error">${esc(e.message)}</div>`, e.message); }
}
