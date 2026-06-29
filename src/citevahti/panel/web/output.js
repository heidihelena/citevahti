/* CiteVahti panel — Output surface — report exports (Markdown / PDF / Word / packet) and the import-Word entry.
 * Split out of surfaces.js; classic script, loads before app.js. */

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
  try {
    const r = await api("POST", "/api/report/docx", {});
    closeExportModal();
    setAgentLine(`Word report saved (${r.claim_count} claim(s)) → ${esc(r.output_file)}`);
    notify(`Word report saved (${r.claim_count} claim(s)): ${r.output_file}`, { kind: "ok" });
  } catch (e) { notify(e.message); }   // surfaces the "install citevahti[docx]" hint if absent
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
