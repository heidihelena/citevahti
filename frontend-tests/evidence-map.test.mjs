/* Atlas evidence-map surface — renders the Spine graph from GET /api/evidence-map,
 * honours the blinding rule in AI view (unjudged/abstained links stay ghosts), flags
 * retracted papers, and exports a standalone publication SVG. Exercised through the DOM. */
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { mount, closeAll } from "./harness.mjs";

after(closeAll);

const MAP = {
  claims: [
    { id: "c1", text: "Low-dose CT screening reduces lung-cancer mortality.", type: "effectiveness", location: "Intro", state: "accepted", code: "oo", untestable: false },
    { id: "c2", text: "Every incidental nodule is cancer until disproven.", type: "background", location: "Disc", state: "decision_recorded", code: "d", untestable: false },
    { id: "c3", text: "Volumetric assessment lowers false positives.", type: "diagnostic_accuracy", location: "Methods", state: "needs_support", code: "o", untestable: false },
  ],
  papers: [
    { id: "pmid:1", title: "NLST", pmid: "1", doi: "10.1/a", journal: "NEJM", year: 2011, retracted: false },
    { id: "pmid:2", title: "Retracted nodule review", pmid: "2", doi: "10.1/b", journal: "Radiol", year: 2024, retracted: true },
    { id: "pmid:3", title: "NELSON", pmid: "3", doi: "10.1/c", journal: "NEJM", year: 2020, retracted: false },
  ],
  edges: [
    { claim_id: "c1", paper_id: "pmid:1", human_support: "directly_supports", ai_support: "directly_supports", decision: "accept", final_decision: "accept", agreement: "concordant", stale: false },
    { claim_id: "c2", paper_id: "pmid:2", human_support: "contradicts", ai_support: "contradicts", decision: "reject", final_decision: "reject", agreement: "concordant", stale: false },
    { claim_id: "c3", paper_id: "pmid:3", human_support: null, ai_support: "hidden", decision: "unrated", final_decision: null, agreement: null, stale: false },
  ],
  counts: { claims: 3, papers: 3, links: 3 },
  generated_at: "2026-07-02T10:00:00Z",
};

async function openAtlas() {
  const h = await mount({ "GET /api/evidence-map": MAP });
  h.click(h.$('.surfnav-tab[data-surface="atlas"]'));
  await h.waitFor(() => h.$$("#emStage .em-node").length > 0);
  return h;
}

test("Atlas renders the Spine graph from the evidence-map endpoint", async () => {
  const h = await openAtlas();
  assert.equal(h.$$("#emStage .em-node").length, 6);       // 3 claims + 3 papers
  assert.equal(h.$$("#emStage .em-edge").length, 3);
  assert.equal(h.$$("#emStage .em-node.em-retracted").length, 1);   // the retracted paper
  assert.ok(/Local evidence map/.test(h.text()));
});

test("clicking a paper reveals its links and the retraction flag", async () => {
  const h = await openAtlas();
  const retr = h.$('.em-node.em-retracted');
  h.click(retr);
  await h.waitFor(() => h.$("#emDetail") && h.$("#emDetail").classList.contains("show"));
  const d = h.$("#emDetail").textContent;
  assert.ok(/Retracted/.test(d));                          // the ⊘ flag is spelled out
  assert.ok(/Reject/.test(d));                             // its verdict badge
});

test("AI view keeps unjudged links blinded (ghost + no AI value)", async () => {
  const h = await openAtlas();
  h.click(h.byText(/^AI view$/));
  await h.waitFor(() => h.$$("#emStage .em-edge.em-ghost").length > 0);
  // the unrated c3->pmid:3 link is a ghost
  assert.ok(h.$$("#emStage .em-edge.em-ghost").length >= 1);
  // inspect the unrated claim: the flyout must NOT leak an AI value
  h.click(h.$('.em-node[data-em-id="c3"]'));
  await h.waitFor(() => h.$("#emDetail") && h.$("#emDetail").classList.contains("show"));
  assert.ok(/hidden until you judge/.test(h.$("#emDetail").textContent));
});

test("figure export builds a valid standalone SVG with N and honest framing", async () => {
  const h = await openAtlas();
  const svg = h.run("new XMLSerializer().serializeToString(emBuildFigure(false))");
  assert.ok(/^<svg/.test(svg) || /<svg/.test(svg));
  assert.ok(!/var\(--/.test(svg));                         // literal colours → standalone
  assert.ok(/N = 3 claims/.test(svg));
  assert.ok(/does not assert that any claim is true/.test(svg));
  const cap = h.run("emFigureCaption()");
  assert.ok(/Claim key: C1,/.test(cap) && /Figure 1\./.test(cap));
});
