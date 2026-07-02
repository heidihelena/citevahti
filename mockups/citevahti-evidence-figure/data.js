/* Mock ledger for the publication-figure system (same data as the evidence-map
 * mockup, plus a short `gloss` per claim so the figure can label claims readably
 * while the full wording lives in the auto-generated caption key).
 *
 * The live panel would build this from GET /api/evidence-map — an EvidenceMap
 * (schemas/evidence_map.py) assembled from the ledger's claims, candidates,
 * ratings and decisions. Nothing here is real; domain = thoracic-oncology LDCT. */

const SNAPSHOT = "2026-07-02";  // ledger data-cutoff label stamped on the figure

const SUPPORT = {
  directly_supports:   { label: "Directly supports",   pol: "+" },
  partially_supports:  { label: "Partially supports",  pol: "+" },
  indirectly_supports: { label: "Indirectly supports", pol: "+" },
  does_not_support:    { label: "Does not support",    pol: "−" },
  contradicts:         { label: "Contradicts",         pol: "−" },
  unclear:             { label: "Unclear",             pol: "?" },
  null:                { label: "Not yet rated",        pol: "·" },
};

/* Verdict encoding. Two REDUNDANT non-colour channels so the figure survives
 * greyscale print and colour-vision deficiency: a line dash pattern AND the
 * bracketed status code, both tied to colour in the legend. */
const VERDICT = {
  accept:  { code: "oo", label: "Accept",       hue: "#C98A00", mono: "#111111", dash: "",       w: 2.4 },
  caution: { code: "o ", label: "Caution",      hue: "#1E9E8A", mono: "#555555", dash: "",       w: 1.5 },
  review:  { code: "r ", label: "Needs review", hue: "#8B6FC9", mono: "#333333", dash: "6 3",    w: 1.9 },
  reject:  { code: "d ", label: "Reject",       hue: "#C24D7E", mono: "#111111", dash: "1.5 3",  w: 1.9 },
  unrated: { code: "  ", label: "Unrated",      hue: "#8478A6", mono: "#9A9AA4", dash: "2 4",    w: 1.2 },
};
const VERDICT_ORDER = ["accept", "caution", "review", "reject", "unrated"];

/* AI support value → the verdict-equivalent hue family (for AI-view mode) */
const SUPPORT_VERDICT = {
  directly_supports: "accept", partially_supports: "caution", indirectly_supports: "caution",
  unclear: "review", does_not_support: "review", contradicts: "reject", null: "unrated",
};

const PAPERS = {
  p_nlst:    { short: "NLST",         venue: "NEJM 2011", pmid: "21714641", type: "RCT" },
  p_nelson:  { short: "NELSON",       venue: "NEJM 2020", pmid: "31995683", type: "RCT" },
  p_como:    { short: "Comorbid-LDCT", venue: "Chest 2026", pmid: "42217822", type: "Cohort" },
  p_fleisch: { short: "Fleischner",   venue: "Radiology 2017", pmid: "28240562", type: "Guideline" },
  p_nodule:  { short: "Nodule-Mgmt",  venue: "Radiol Clin 2024", pmid: "41199102", type: "Review", retracted: true },
  p_g8:      { short: "G8-Screen",    venue: "Ann Oncol 2014", pmid: "25015334", type: "Cohort" },
  p_overdx:  { short: "Overdiagnosis", venue: "JAMA IM 2019", pmid: "30721260", type: "Modelling" },
  p_uptake:  { short: "Uptake-EU",    venue: "Lancet Onc 2023", pmid: "37541270", type: "Cohort" },
  p_pytx:    { short: "Pack-Years",   venue: "Thorax 2022", pmid: "34675103", type: "Cohort" },
  p_costef:  { short: "Cost-Eff",     venue: "Eur Resp J 2021", pmid: "33986032", type: "Modelling" },
};

const CLAIMS = {
  c1: { gloss: "LDCT lowers lung-cancer mortality", text: "Low-dose CT screening reduces lung-cancer mortality in high-risk populations" },
  c2: { gloss: "LDCT reveals comorbidities", text: "LDCT frequently detects smoking-related comorbidities that shape implementation" },
  c3: { gloss: "Every nodule is cancer until disproven", text: "Every incidental pulmonary nodule should be treated as cancer until proven otherwise" },
  c4: { gloss: "Volumetric assessment cuts false positives", text: "Volumetric nodule assessment lowers the false-positive rate versus diameter alone" },
  c5: { gloss: "National LDCT is cost-effective", text: "National LDCT programmes are cost-effective at current eligibility thresholds" },
};

const EDGES = [
  { claim: "c1", paper: "p_nlst",   human: "directly_supports",   ai: "directly_supports",   decision: "accept" },
  { claim: "c1", paper: "p_nelson", human: "directly_supports",   ai: "directly_supports",   decision: "accept" },
  { claim: "c1", paper: "p_overdx", human: "partially_supports",  ai: "does_not_support",    decision: "caution" },
  { claim: "c2", paper: "p_como",   human: "partially_supports",  ai: "partially_supports",  decision: "caution" },
  { claim: "c2", paper: "p_uptake", human: "indirectly_supports", ai: "partially_supports",  decision: "caution" },
  { claim: "c2", paper: "p_nlst",   human: "indirectly_supports", ai: "indirectly_supports", decision: "accept" },
  { claim: "c3", paper: "p_nodule",  human: "contradicts",        ai: "contradicts",         decision: "reject" },
  { claim: "c3", paper: "p_fleisch", human: "does_not_support",   ai: "contradicts",         decision: "review" },
  { claim: "c4", paper: "p_nelson",  human: "directly_supports",  ai: "partially_supports",  decision: "accept" },
  { claim: "c4", paper: "p_fleisch", human: "partially_supports", ai: "partially_supports",  decision: "caution" },
  { claim: "c4", paper: "p_nodule",  human: null,                 ai: "unclear",             decision: "unrated" },
  { claim: "c5", paper: "p_costef",  human: "directly_supports",  ai: "directly_supports",   decision: "accept" },
  { claim: "c5", paper: "p_pytx",    human: "indirectly_supports", ai: "unclear",            decision: "review" },
  { claim: "c5", paper: "p_g8",      human: null,                 ai: null,                  decision: "unrated" },
];
