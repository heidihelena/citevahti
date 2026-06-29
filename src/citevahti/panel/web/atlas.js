/* CiteVahti panel — Atlas surface — the local evidence map + de-identified Atlas contribution (warehouse).
 * Split out of surfaces.js; classic script, loads before app.js. */

/* ---------- Atlas surface (local evidence map + contribution) ----------
 * Hosts the warehouse modal inline; its ✕/Done route back via leaveModal(). */
function renderAtlasSurface() {
  const host = $("#atlas"); if (!host) return;
  host.innerHTML = "";
  openWarehouse(host);
}


/* ---------- de-identified warehouse + Atlas contribution (download-only) ---- */
async function openWarehouse(host) {
  const box = modalShell("whModal", host);
  box.innerHTML = loadingHTML("Loading…", { card: true });
  try { renderWarehouse(box, await api("GET", "/api/warehouse")); }
  catch (e) { box.innerHTML = `<div class="modal-card"><div class="err">${esc(e.message)}</div>
    <div class="modal-foot"><button class="btn ghost" data-wh-close="1">Close</button></div></div>`; }
}

function renderWarehouse(box, st) {
  const on = !!st.enabled, text = !!st.include_claim_text;
  const bundle = state.lastBundle;
  box.innerHTML = `<div class="modal-card wh">
    <div class="modal-head"><b>Local evidence map</b><button class="chip-btn" data-wh-close="1">✕</button></div>
    <div class="note"><b>Stored on this computer. Nothing uploaded.</b> An opt-in, de-identified record of your
      claim-test work — claim <b>hash</b> (not text), public PMID/DOI, and the ratings. Off by default.</div>
    <label class="wh-toggle"><input type="checkbox" id="whEnabled" ${on ? "checked" : ""}>
      <span><b>Collect de-identified records</b> — ${st.record_count} stored</span></label>
    <label class="wh-toggle${on ? "" : " dim"}"><input type="checkbox" id="whText" ${text ? "checked" : ""} ${on ? "" : "disabled"}>
      <span>Also store the <b>raw claim text</b> <span class="sensitive">sensitive — separate opt-in</span></span></label>
    <div class="actions">
      <button class="btn ghost" data-wh="export" ${on ? "" : "disabled"}>Export records (local file)</button>
      <button class="btn ghost danger" data-wh="purge" ${st.record_count ? "" : "disabled"}>Purge (withdraw)</button></div>

    <div class="lbl cv-mt-lg">Contribute to Atlas</div>
    <div class="note">Build a de-identified bundle to <b>download</b>. Nothing is transmitted — there is
      no upload from here. Composed vs decomposed and case are normalized so your claim hashes match
      across tools (spec v1).</div>
    <details class="context"><summary>What contributing means — privacy</summary><div class="body">
      <p class="note"><b>De-identified, not anonymous.</b> A contribution carries your pseudonymous
        contributor id + consent record, and per judgment a <b>keyed claim index</b> (not the text),
        the <b>public</b> PMID/DOI, study type, and the ratings. The contributor id and consent ledger
        are <b>personal data</b> — we say "de-identified", never "anonymous".</p>
      <p class="note"><b>Full claim text + evidence snippet</b> ride along only under the separate
        opt-in above. <b>Never contribute</b> patient-identifiable data, confidential registry data,
        or substantial copyrighted full text.</p>
      <p class="note"><b>Your control:</b> preview the exact payload before anything leaves; every
        contribution is <b>revocable</b>. Aggregate views expose an edge only at <b>≥ 5 independent
        contributors</b>. The actual send + commercial-use opt-in happen at the contribution step,
        governed by the notice.</p>
      <p class="note"><a href="https://github.com/heidihelena/citevahti/blob/main/docs/CONTRIBUTOR_PRIVACY.md"
        target="_blank" rel="noopener">Read the full privacy notice ↗</a> · controller: Vahtian — privacy@vahtian.com</p>
    </div></details>
    <div class="actions">
      <button class="btn primary" data-wh="preview" ${on && st.record_count ? "" : "disabled"}>Preview bundle</button>
      ${bundle ? `<button class="btn ghost" data-wh="download">⬇ Download bundle (${bundle.count})</button>` : ""}</div>
    ${bundle ? `<div class="note ok" id="whBundleNote"><b>${esc(bundle.contribution_id)}</b> · ${bundle.count} record(s) · ${esc(bundle.sensitivity)}
      · sha256 ${esc(String(bundle.content_hash).slice(0, 12))}…<br>${esc(bundle.consent_receipt.egress)}</div>` : ""}
    <details class="context"><summary>Revoke a contribution</summary><div class="body">
      <input id="whRevokeId" type="text" aria-label="Contribution id to revoke" placeholder="contribution_id (contrib_…)" />
      <div class="actions"><button class="btn ghost" data-wh="revoke">Download revocation</button></div></div></details>
    <div class="modal-foot"><button class="btn primary" data-wh-close="1">Done</button></div></div>`;
}

async function whConfigure(patch) {
  try { const st = await api("POST", "/api/warehouse/configure", patch);
    state.lastBundle = null; renderWarehouse($("#whModal"), st); }
  catch (e) { notify(e.message); }
}

async function whAction(act) {
  const box = $("#whModal");
  try {
    if (act === "export") {
      const r = await api("POST", "/api/warehouse/export", {});
      notify(`Exported ${r.record_count} record(s) to ${r.output_file}`, { kind: "ok" });
    } else if (act === "purge") {
      if (!confirm("Erase the local warehouse? This withdraws every de-identified record.")) return;
      await api("POST", "/api/warehouse/purge", {}); state.lastBundle = null;
      renderWarehouse(box, await api("GET", "/api/warehouse"));
    } else if (act === "preview") {
      const text = $("#whText") && $("#whText").checked;
      state.lastBundle = await api("POST", "/api/atlas/contribution-preview", { allow_claim_text: !!text });
      renderWarehouse(box, await api("GET", "/api/warehouse"));
    } else if (act === "download") {
      if (state.lastBundle) downloadJson(state.lastBundle, `${state.lastBundle.contribution_id}.json`);
    } else if (act === "revoke") {
      const id = (($("#whRevokeId") || {}).value || "").trim();
      if (!id) { notify("Paste the contribution_id to revoke."); return; }
      const req = await api("POST", "/api/atlas/revoke", { contribution_id: id });
      downloadJson(req, `revocation-${id}.json`);
    }
  } catch (e) { notify(e.message); }
}

function closeWarehouse() { leaveModal("whModal", () => { state.lastBundle = null; }); }
