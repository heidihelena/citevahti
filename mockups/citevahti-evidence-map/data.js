/* Shared mock ledger for the evidence-map mockups.
 *
 * This is a STATIC stand-in for what the engine already stores in a ledger:
 *   - claims            (schemas/claim.py)            → nodes, type "claim"
 *   - claim↔paper cands (schemas/candidate.py)        → nodes, type "item" (paper)
 *   - claim-support     (schemas/rating.py)           → the human/AI ratings on an edge
 *   - final decisions   (schemas/decision.py)         → the edge's verdict + hue
 *
 * The real panel would build this from GET /api/evidence-map (an EvidenceMap:
 * nodes + links, schemas/evidence_map.py). No values here are real — the domain
 * (thoracic-oncology LDCT screening) mirrors the inline-v2 mockup so the two read
 * as the same product.
 *
 * Edge model (one per claim↔paper link):
 *   human / ai : a claim-support value (see SUPPORT)
 *   decision   : the human-owned terminal verdict → drives the hue
 *                accept | caution | review | reject | unrated (pending, no decision yet)
 *
 * A paper may carry `retracted: true` — set by the retraction scan
 * (schemas/candidate.py `retracted`, from OpenAlex is_retracted). This is a FACT,
 * not a judgement: it is shown on the map always, independent of (and before) any
 * human or AI rating. Nodule-Mgmt below is retracted and sits on both a judged
 * edge (c3, rejected) and an unjudged edge (c4, unrated) to show the flag holds
 * regardless of judgement.
 */

/* claim-support vocabulary (engine: claim_support values) */
const SUPPORT = {
  directly_supports:   { label: "Directly supports",   pol: "+" },
  partially_supports:  { label: "Partially supports",  pol: "+" },
  indirectly_supports: { label: "Indirectly supports", pol: "+" },
  does_not_support:    { label: "Does not support",    pol: "−" },
  contradicts:         { label: "Contradicts",         pol: "−" },
  unclear:             { label: "Unclear",             pol: "?" },
  null:                { label: "Not yet rated",        pol: "·" },
};

/* decision → verdict hue. Colour is NEVER the only cue: the bracketed code
 * ([oo]/[o ]/[r ]/[d ]/[  ]) rides with every hue, exactly as on the manuscript. */
const VERDICT = {
  accept:  { key: "supported", code: "oo", label: "Accept",      css: "is-supported" },
  caution: { key: "partial",   code: "o ", label: "Caution",     css: "is-partial" },
  review:  { key: "revise",    code: "r ", label: "Needs review", css: "is-revise" },
  reject:  { key: "delete",    code: "d ", label: "Reject",      css: "is-reject" },
  unrated: { key: "pending",   code: "  ", label: "Unrated",     css: "is-pending" },
};
const VERDICT_ORDER = ["accept", "caution", "review", "reject", "unrated"];

/* ---- papers (candidate sources; type "item") ---- */
const PAPERS = {
  p_nlst:    { short: "NLST",         title: "Reduced lung-cancer mortality with LDCT screening", venue: "NEJM 2011", pmid: "21714641", year: 2011, type: "RCT" },
  p_nelson:  { short: "NELSON",       title: "Volume CT screening in a randomised trial", venue: "NEJM 2020", pmid: "31995683", year: 2020, type: "RCT" },
  p_como:    { short: "Comorbid-LDCT", title: "Smoking-related comorbidities on LDCT", venue: "Chest 2026", pmid: "42217822", year: 2026, type: "Cohort" },
  p_fleisch: { short: "Fleischner",   title: "Management of incidental pulmonary nodules", venue: "Radiology 2017", pmid: "28240562", year: 2017, type: "Guideline" },
  p_nodule:  { short: "Nodule-Mgmt",  title: "Incidental pulmonary nodules — a review", venue: "Radiol Clin 2024", pmid: "41199102", year: 2024, type: "Review", retracted: true },
  p_g8:      { short: "G8-Screen",    title: "G8 geriatric screening before therapy", venue: "Ann Oncol 2014", pmid: "25015334", year: 2014, type: "Cohort" },
  p_overdx:  { short: "Overdiagnosis", title: "Overdiagnosis in LDCT screening programmes", venue: "JAMA IM 2019", pmid: "30721260", year: 2019, type: "Modelling" },
  p_uptake:  { short: "Uptake-EU",    title: "Screening uptake and implementation in Europe", venue: "Lancet Onc 2023", pmid: "37541270", year: 2023, type: "Cohort" },
  p_pytx:    { short: "Pack-Years",   title: "Pack-year thresholds and eligibility", venue: "Thorax 2022", pmid: "34675103", year: 2022, type: "Cohort" },
  p_costef:  { short: "Cost-Eff",     title: "Cost-effectiveness of national LDCT", venue: "Eur Resp J 2021", pmid: "33986032", year: 2021, type: "Modelling" },
};

/* ---- claims (the spine; type "claim") ---- */
const CLAIMS = {
  c1: { text: "Low-dose CT screening reduces lung-cancer mortality in high-risk populations", type: "effectiveness", loc: "Intro ¶2" },
  c2: { text: "LDCT frequently detects smoking-related comorbidities that shape implementation", type: "implementation", loc: "Discussion ¶3" },
  c3: { text: "Every incidental pulmonary nodule should be treated as cancer until proven otherwise", type: "background", loc: "Discussion ¶5" },
  c4: { text: "Volumetric nodule assessment lowers the false-positive rate versus diameter alone", type: "diagnostic_accuracy", loc: "Methods ¶1" },
  c5: { text: "National LDCT programmes are cost-effective at current eligibility thresholds", type: "effectiveness", loc: "Discussion ¶7" },
};

/* ---- edges: claim ↔ paper, with the ratings and the verdict ---- */
const EDGES = [
  // c1 — well-supported claim, two strong RCTs accepted, one cautioned
  { claim: "c1", paper: "p_nlst",   human: "directly_supports",   ai: "directly_supports",   decision: "accept" },
  { claim: "c1", paper: "p_nelson", human: "directly_supports",   ai: "directly_supports",   decision: "accept" },
  { claim: "c1", paper: "p_overdx", human: "partially_supports",  ai: "does_not_support",    decision: "caution" },

  // c2 — implementation claim, partial support, one shared paper (comorbidities)
  { claim: "c2", paper: "p_como",   human: "partially_supports",  ai: "partially_supports",  decision: "caution" },
  { claim: "c2", paper: "p_uptake", human: "indirectly_supports", ai: "partially_supports",  decision: "caution" },
  { claim: "c2", paper: "p_nlst",   human: "indirectly_supports", ai: "indirectly_supports", decision: "accept" },

  // c3 — overstated claim, contradicted → reject / revise
  { claim: "c3", paper: "p_nodule",  human: "contradicts",        ai: "contradicts",         decision: "reject" },
  { claim: "c3", paper: "p_fleisch", human: "does_not_support",   ai: "contradicts",         decision: "review" },

  // c4 — diagnostic-accuracy claim, mixed, one still unrated
  { claim: "c4", paper: "p_nelson",  human: "directly_supports",  ai: "partially_supports",  decision: "accept" },
  { claim: "c4", paper: "p_fleisch", human: "partially_supports", ai: "partially_supports",  decision: "caution" },
  { claim: "c4", paper: "p_nodule",  human: null,                 ai: "unclear",             decision: "unrated" },

  // c5 — cost-effectiveness, one accept, one still under review, one unrated candidate
  { claim: "c5", paper: "p_costef",  human: "directly_supports",  ai: "directly_supports",   decision: "accept" },
  { claim: "c5", paper: "p_pytx",    human: "indirectly_supports", ai: "unclear",            decision: "review" },
  { claim: "c5", paper: "p_g8",      human: null,                 ai: null,                  decision: "unrated" },
];
