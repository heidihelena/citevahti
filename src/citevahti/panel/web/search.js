/* CiteVahti panel — candidate evidence: search a source, link a result to the active
 * claim, or save a hit straight to Zotero (preview-gated). Part of the review card UI
 * (searchBlock/finderMore render in card.js; these are the actions). */

async function doSearch() {
  const q = (($("#searchQ") || {}).value || "").trim();
  const src = ($("#searchSrc") || {}).value || "pubmed";
  if (!q) return;
  const box = $("#searchResults"); if (box) box.innerHTML = `<div class="note">Searching ${esc(src)}…</div>`;
  try {
    const r = await api("POST", "/api/search", { query: q, source: src });
    state.searchBatch = r.batch_id;
    if (!r.hits || !r.hits.length) { if (box) box.innerHTML = `<div class="note">No results.</div>`; return; }
    if (box) box.innerHTML = r.hits.map((h) => {
      const meta = [h.journal, h.year, h.pmid && ("PMID " + h.pmid)].filter(Boolean).join(" · ");
      const inzot = h.dedupe_status === "already_in_library" ? `<span class="tag inzot">in Zotero</span>` : "";
      const doi = h.doi ? `<a class="doi" href="${esc(doiUrl(h.doi))}" target="_blank" rel="noopener" title="Open the DOI">DOI ${esc(h.doi)} ↗</a>` : "";
      const abs = h.abstract ? `<details class="abs"><summary>Abstract</summary><div class="excerpt">${esc(h.abstract)}</div></details>` : "";
      const inLib = h.dedupe_status === "already_in_library";
      return `<div class="result"><div class="rmeta"><b>${esc(h.title || "(untitled)")}</b> ${inzot}
        <div class="note">${esc(meta)}${meta && doi ? " · " : ""}${doi}</div>${abs}</div>
        <div class="ractions">
          <button class="btn ghost" data-link="${esc(h.record_id)}">Link to claim</button>
          ${inLib ? `<span class="note">already saved</span>`
                  : `<button class="btn ghost" data-zsave="${esc(h.record_id)}" title="Adds this paper to your Zotero library — it does NOT mark the claim supported (rate and decide for that)">＋ Add paper to Zotero</button>`}
        </div></div>`;
    }).join("");
  } catch (e) { if (box) box.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
}
async function linkRecord(recordId) {
  if (!state.searchBatch) return;
  try {
    await api("POST", "/api/link", { claim_id: state.activeClaim, batch_id: state.searchBatch, record_ids: [recordId] });
    state.searchBatch = null;
    await selectClaim(state.activeClaim);   // reload the card with the newly linked candidate
  } catch (e) { showErr(e.message); }
}

/* normalise a DOI (bare, or with a doi:/URL prefix) to an openable doi.org link */

/* direct "Save to Zotero" for a search hit — preview the write, then confirm.
 * Honors the same nothing-written-silently gate as the claim write: preview
 * returns a confirm_token; the actual add needs it. */
async function zsave(recordId, btn) {
  const canWrite = (state.health && state.health.can_write || []).length > 0;
  if (!canWrite) { showErr("Connect Zotero (with write access) first — see the Zotero chip."); return; }
  if (!state.searchBatch) { showErr("Run the search again, then save."); return; }
  try {
    const p = await api("POST", "/api/intake/preview", { batch_id: state.searchBatch, record_ids: [recordId] });
    const token = p.confirm_token || p.approval_token;
    const n = (p.to_create != null ? p.to_create : (p.would_create != null ? p.would_create : 1));
    const dup = p.skipped_duplicates || p.duplicates || 0;
    if (!token) {
      if (dup && !n) { if (btn) { btn.textContent = "already in Zotero"; btn.disabled = true; } return; }
      showErr("Could not prepare the Zotero write (no confirm token returned)."); return;
    }
    if (!confirm(`Add this paper to your Zotero library?${dup ? `\n(${dup} duplicate skipped.)` : ""}`)) return;
    const r = await api("POST", "/api/intake/commit", { batch_id: state.searchBatch, record_ids: [recordId], confirm_token: token });
    const ok = (r.status === "committed") || r.created_keys || r.pushed;
    if (btn) { btn.textContent = ok ? "✓ Saved to Zotero" : "save failed"; btn.disabled = !!ok; }
    if (!ok) showErr(`Save not committed: ${r.error_code || r.status || "unknown"}`);
  } catch (e) { showErr(e.message); }
}
