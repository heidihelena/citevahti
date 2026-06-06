/* CiteVahti UI mockup — ADR-0002 fit-code review layer.
 * Four operational codes over the ledger:
 *   [oo] supported -> accept       [o ] partly -> accepted_with_caution
 *   [r ] revise    -> 2nd review   [d ] delete -> reject (remove candidate)
 * Palette: yellow = evidence usable, lilac = human action, ink+white = structure. */

const FIT = {
  supported: { code: "oo", label: "Supported", cls: "zs-supported",
    tip: "Marked as usable evidence — directly supports the claim. Adds the verified citation to Zotero through the decision-gated, undoable transaction." },
  partial: { code: "o ", label: "Partly supported", cls: "zs-partial",
    tip: "Partial fit — supports a narrower or adjacent claim. Cite with caution or revise the claim wording." },
  revise: { code: "r ", label: "Revise", cls: "zs-revise",
    tip: "Work remains — claim or source needs human review/editing before it can be cited. Not an error; common." },
  delete: { code: "d ", label: "Unsupported", cls: "zs-delete",
    tip: "Remove this source candidate from the claim's evidence list. The claim and the sentence stay." },
};

/* eye colour by state (brackets stay ink); yellow = usable, lilac = action */
const MARK_EYE = {
  neutral: "#8B6FC9", supported: "#C98A00", partial: "#1E9E8A", revise: "#8B6FC9", delete: "#C24D7E",
};

const claims = [
  { text: "Low-dose CT screening reduces lung cancer mortality in high-risk populations.",
    citation: "None", status: "revise", action: "Verify claim" },
  { text: "Smoking-related comorbidities detected on LDCT can shape screening implementation.",
    citation: "PMID 42217822", status: "supported", action: "Add to Zotero" },
  { text: "Prehabilitation improves surgical readiness for early-stage lung cancer resections.",
    citation: "Candidate staged", status: "partial", action: "Revise claim" },
  { text: "Every incidental pulmonary nodule should be treated as cancer until proven otherwise.",
    citation: "Candidate flagged", status: "delete", action: "Remove candidate" },
];

const evidence = [
  { claim: claims[1].text,
    title: "Smoking-Related Comorbidities Detected Through Low-dose CT Lung Cancer Screening",
    authors: "Revel, Goo, Vliegenthart, Silva, Snoeckx", journal: "Chest, 2026",
    pmid: "42217822", doi: "10.1016/j.chest.2026.05.028",
    abstract: "Low-dose CT lung cancer screening frequently detects additional smoking-related findings including emphysema, coronary artery calcium, and interstitial lung abnormalities.",
    quality: "Review article", alreadyInZotero: "Yes",
    whyFound: "PubMed exact query + claim keywords: screening, LDCT, pulmonary findings",
    aiPreliminary: "Directly supports the implementation claim.",
    finalSupportRating: "Directly supports claim", citationFitScore: 8 },
  { claim: claims[2].text,
    title: "Prehabilitation for lung cancer surgery: pragmatic implementation and perioperative outcomes",
    authors: "Hansen, Patel, Moreau", journal: "Journal of Thoracic Oncology, 2025",
    pmid: "41900124", doi: "10.5555/prehab-demo",
    abstract: "Multimodal prehabilitation was associated with better functional status before surgery, but the evidence was heterogeneous and limited to single-center implementation cohorts.",
    quality: "Observational cohort", alreadyInZotero: "No",
    whyFound: "Surveillance query: lung cancer prehabilitation surgery implementation",
    aiPreliminary: "Supports a narrower perioperative version of the claim.",
    finalSupportRating: "Partially supports claim", citationFitScore: 5 },
  { claim: claims[0].text,
    title: "National Lung Screening Trial: reduced lung-cancer mortality with low-dose CT screening",
    authors: "Aberle, Adams, Berg, et al.", journal: "N Engl J Med, 2011",
    pmid: "21714641", doi: "10.1056/NEJMoa1102873",
    abstract: "Screening with low-dose CT reduced lung-cancer mortality versus chest radiography in high-risk participants; population and follow-up specifics require reviewer confirmation against the manuscript claim.",
    quality: "Randomized trial", alreadyInZotero: "No",
    whyFound: "Claim keywords: LDCT, mortality, high-risk — landmark RCT candidate",
    aiPreliminary: "Likely supports, but population framing needs a human check.",
    finalSupportRating: "Unclear, needs review", citationFitScore: 6 },
  { claim: claims[3].text,
    title: "Management of incidental pulmonary nodules detected outside screening programs",
    authors: "Khan, Liu, Morgan", journal: "Radiology Clinics, 2024",
    pmid: "41199102", doi: "10.5555/nodule-demo",
    abstract: "Most incidental nodules are benign; risk stratification and longitudinal follow-up are recommended rather than assuming malignancy for all detected nodules.",
    quality: "Guideline review", alreadyInZotero: "No",
    whyFound: "Candidate linked by nodule management terms",
    aiPreliminary: "Contradicts the claim wording.",
    finalSupportRating: "Does not support claim", citationFitScore: 2 },
];

const auditRows = [
  { action: "Validated write", status: "supported", paper: "Smoking-related comorbidities → Lung Cancer",
    claim: "LDCT implementation claim", ids: "PMID 42217822 / DOI 10.1016…",
    session: "user-review-18", transaction: "txn-66eb168d08", undo: "Available" },
  { action: "Sent to human review", status: "revise", paper: "NLST landmark RCT → (held)",
    claim: "LDCT mortality claim", ids: "PMID 21714641 / DOI 10.1056…",
    session: "reviewer-a", transaction: "pending", undo: "Not written" },
  { action: "Removed candidate", status: "delete", paper: "Incidental nodule review",
    claim: "Nodule wording claim", ids: "PMID 41199102 / DOI 10.5555…",
    session: "citevahti-agent", transaction: "none", undo: "Not written" },
];

/* the [oo] mark: citation brackets around two eyes; eyes coloured by state */
function markSvg(state = "neutral") {
  const eye = MARK_EYE[state] || MARK_EYE.neutral;
  return `
    <svg width="100%" height="100%" viewBox="0 0 64 64" fill="none" role="img" aria-label="CiteVahti ${state}">
      <g fill="currentColor">
        <rect x="12" y="14" width="6" height="36"/><rect x="12" y="14" width="15" height="6"/><rect x="12" y="44" width="15" height="6"/>
        <rect x="46" y="14" width="6" height="36"/><rect x="37" y="14" width="15" height="6"/><rect x="37" y="44" width="15" height="6"/>
      </g>
      <g fill="${eye}">
        <path d="M24 28 L29 24 L31 32 L26 35 Z"/>
        <path d="M40 28 L35 24 L33 32 L38 35 Z"/>
      </g>
    </svg>`;
}

function statusBadge(status) {
  const m = FIT[status] || FIT.revise;
  return `<span class="claim-status-badge ${m.cls}" title="${m.tip}">
      <span class="zs-code">[${m.code}]</span><span>${m.label}</span>
    </span>`;
}

function citationFitLabel(total) {
  if (total >= 7) return "Strong citation fit";
  if (total >= 4) return "Moderate citation fit";
  if (total >= 1) return "Weak citation fit";
  return "No citation fit";
}

function deriveStatus({ finalSupportRating, citationFitScore }) {
  if (finalSupportRating === "Unclear, needs review") return "revise";
  if (finalSupportRating === "Does not support claim" || finalSupportRating === "Contradicts claim") return "delete";
  if (finalSupportRating === "Directly supports claim" && citationFitScore >= 7) return "supported";
  if (finalSupportRating === "Partially supports claim" || finalSupportRating === "Indirectly supports claim" || citationFitScore >= 4) return "partial";
  return "revise";
}

function safetyMessage(status) {
  return {
    supported: { cls: "supported", text: "Marked as usable evidence. “Add to Zotero” runs the decision-gated, undoable write — nothing is written silently." },
    partial: { cls: "partial", text: "Partial fit. Cite with caution, or revise the manuscript wording so the claim matches the evidence." },
    revise: { cls: "revise", text: "Work remains — a human must review/edit the claim or rating before this can be cited. Not an error." },
    delete: { cls: "delete", text: "Remove this source candidate from the claim’s evidence list. The claim text and sentence stay; nothing in Zotero is deleted." },
  }[status];
}

/* per-state actions: the mission rule forbids "Add to Zotero" unless supporting */
function cardActions(status) {
  if (status === "supported") return `<button class="primary-button" type="button">Add to Zotero</button><button class="ghost-button" type="button">Open paper</button>`;
  if (status === "partial") return `<button class="primary-button" type="button">Add with caution</button><button class="ghost-button" type="button">Revise claim</button>`;
  if (status === "revise") return `<button class="primary-button" type="button">Revise claim</button><button class="ghost-button" type="button">Change reference</button>`;
  return `<button class="primary-button" type="button">Remove candidate from claim</button><button class="ghost-button" type="button">Remove candidate + revise claim</button>`;
}

function renderMarks() {
  document.querySelectorAll("[data-logo]").forEach((n) => { n.innerHTML = markSvg(n.dataset.logo); });
}

function renderClaims() {
  document.querySelector("#claims-list").innerHTML = claims.map((c) => `
    <div class="claims-row" role="row">
      <div role="cell"><p class="claim-title">${c.text}</p></div>
      <span class="muted" role="cell">${c.citation}</span>
      <span role="cell">${statusBadge(c.status)}</span>
      <span role="cell"><button class="link-button" type="button" data-tab-link="evidence">${c.action}</button></span>
    </div>`).join("");
}

function renderEvidence() {
  const humanRated = document.querySelector("#human-rating-toggle").checked;
  document.querySelector("#evidence-list").innerHTML = evidence.map((item) => {
    const status = deriveStatus(item);
    const msg = safetyMessage(status);
    const ai = humanRated ? item.aiPreliminary : "Hidden during blinded validation";
    return `
      <article class="evidence-card">
        <div class="evidence-main">
          <div class="evidence-kicker">
            <span class="evidence-status-mark" style="color:var(--zs-ink)">${markSvg(status)}</span>
            ${statusBadge(status)}
          </div>
          <h3>${item.claim}</h3>
          <p class="paper-title">${item.title}</p>
          <div class="meta-grid">
            <div class="meta-item"><span class="meta-label">Authors</span><span class="meta-value">${item.authors}</span></div>
            <div class="meta-item"><span class="meta-label">Journal and year</span><span class="meta-value">${item.journal}</span></div>
            <div class="meta-item"><span class="meta-label">PMID</span><span class="meta-value">${item.pmid}</span></div>
            <div class="meta-item"><span class="meta-label">DOI</span><span class="meta-value">${item.doi}</span></div>
          </div>
          <p class="abstract-snippet">${item.abstract}</p>
        </div>
        <aside class="evidence-side" aria-label="Evidence rating details">
          <div class="rating-row"><span>Evidence quality signal</span><strong>${item.quality}</strong></div>
          <div class="rating-row"><span>Already in Zotero?</span><strong>${item.alreadyInZotero}</strong></div>
          <div class="rating-row"><span>Why CiteVahti found it</span><strong>${item.whyFound}</strong></div>
          <div class="rating-row"><span>AI rating (blinded)</span><strong>${ai}</strong></div>
          <div class="rating-row"><span>Citation fit</span><strong>${citationFitLabel(item.citationFitScore)} (${item.citationFitScore}/8)</strong></div>
          <div class="rating-row"><span>Final support status</span><strong>${FIT[status].label}</strong></div>
          <p class="safety-message ${msg.cls}">${msg.text}</p>
          <div class="evidence-card-actions">${cardActions(status)}</div>
        </aside>
      </article>`;
  }).join("");
}

function renderAudit() {
  document.querySelector("#audit-list").innerHTML = auditRows.map((row) => `
    <div class="audit-row" role="row">
      <span role="cell">${statusBadge(row.status)}<br><span class="muted">${row.action}</span></span>
      <span role="cell">${row.paper}</span>
      <span role="cell">${row.claim}</span>
      <span role="cell" class="muted">${row.ids}</span>
      <span role="cell">${row.session}</span>
      <span role="cell">${row.transaction}</span>
      <span role="cell"><button class="link-button" type="button" ${row.undo === "Available" ? "" : "disabled"}>${row.undo === "Available" ? "Undo" : row.undo}</button></span>
    </div>`).join("");
}

function setActiveTab(tabId) {
  const titles = { setup: "Connection & safety", claims: "Verify claims", evidence: "Find evidence", changes: "Review changes" };
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === tabId));
  document.querySelectorAll("[data-tab-link]").forEach((b) => b.classList.toggle("active", b.dataset.tabLink === tabId));
  document.querySelector("#page-title").textContent = titles[tabId] || "CiteVahti";
}

document.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-tab-link]");
  if (!trigger) return;
  event.preventDefault();
  setActiveTab(trigger.dataset.tabLink);
});

document.querySelector("#human-rating-toggle").addEventListener("change", renderEvidence);

renderMarks();
renderClaims();
renderEvidence();
renderAudit();
