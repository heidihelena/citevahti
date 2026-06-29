/* 2 · Component tests — key interactions, driven through the real DOM (click what the user
 * clicks, assert what the user sees). No internal state is asserted except the visible
 * surface the app exposes via the nav. */
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { mount, closeAll } from "./harness.mjs";

after(closeAll);

const now = Math.floor(Date.now() / 1000);
const withProjects = {
  "GET /api/ledgers": { active: "/x/telehealth", ledgers: [
    { root: "/x/telehealth", claims: 30, mtime: now - 3 * 86400 },
    { root: "/x/lung", claims: 12, mtime: now - 600 },
  ] },
};

test("intake leads with a native file picker and a 'Your reviews' list", async () => {
  const h = await mount(withProjects);
  await h.waitFor(() => h.$("#manuscripts").textContent.includes("Your reviews"));
  const ms = h.$("#manuscripts");
  assert.match(ms.textContent, /Your reviews/);
  assert.match(ms.textContent, /telehealth/);                 // project shown by folder name
  assert.match(ms.textContent, /3 days ago/);                 // recency, not a path
  assert.ok(h.byAct("choose-file"), "primary 'Choose a file' action is present");
  assert.match(h.byAct("choose-file").textContent, /Choose a file/);
  assert.ok(/or paste the text/i.test(ms.innerHTML), "paste is demoted behind a disclosure");
  assert.ok(!/citevahti claim-add/.test(ms.innerHTML), "no terminal/CLI instructions");
  assert.match(ms.textContent, /nothing uploaded/i);          // local-first reassurance
});

test("header nav switches between surfaces", async () => {
  const h = await mount();
  for (const name of ["checks", "atlas", "output", "settings", "manuscripts"]) {
    h.click(h.$(`.surfnav-tab[data-surface="${name}"]`));
    await h.waitFor(() => h.surface() === name && h.$("#" + name).innerHTML.length > 40);
    assert.equal(h.surface(), name);
    assert.equal(h.$("#" + name).hidden, false);
  }
});

test("saving a pasted manuscript hands off to the chat assistant with a waiting state", async () => {
  const h = await mount({
    "POST /api/manuscripts/paste": { ok: true, filename: "draft.md",
      next_prompt: "Extract the verifiable claims from draft.md and add each with CiteVahti." },
  });
  await h.waitFor(() => h.$("#pasteName"));
  h.$("#pasteName").value = "draft.md";
  h.$("#pasteBody").value = "# Title\n\nA verifiable claim.";
  h.click(h.$("#pasteSave"));
  await h.waitFor(() => /Extracting claims/.test(h.$("#manuscripts").textContent));
  const ms = h.$("#manuscripts");
  assert.match(ms.textContent, /Extracting claims from draft\.md/);
  assert.match(ms.textContent, /Waiting for claims/);          // explicit, not a blank panel
  assert.ok(h.byAct("copy-handoff"), "the exact prompt can be copied");
  assert.match(ms.querySelector(".revbox").value, /Extract the verifiable claims/);
});

test("the audit badge opens a plain-language 'Review record' timeline", async () => {
  const h = await mount({
    "GET /api/audit/log": { total: 3, intact: true, entries: [
      { seq: 3, ts: "2026-06-29T14:02:00", event: "decision.final", payload: { final_decision: "reject", claim_type: "effectiveness" } },
      { seq: 2, ts: "2026-06-29T14:01:00", event: "claim_support.save", payload: { comparison_status: "concordant" } },
      { seq: 1, ts: "2026-06-29T14:00:00", event: "store.init", payload: {} },
    ] },
  });
  await h.waitFor(() => /Review record/.test(h.$("#auditBadge").textContent));
  assert.match(h.$("#auditBadge").textContent, /Review record/);    // reframed from "audit"
  h.click(h.$("#auditBadge"));
  await h.waitFor(() => /Recorded a decision/.test((h.$("#reviewRecordModal") || {}).textContent || ""));
  const dlg = h.$("#reviewRecordModal");
  assert.match(dlg.textContent, /Recorded a decision/);             // humanized events, not raw tokens
  assert.match(dlg.textContent, /Recorded a support rating/);
  assert.match(dlg.textContent, /Project created/);
  assert.match(dlg.textContent, /record intact/);
  assert.ok(dlg.querySelector('[data-act="export-record"]'), "can export the record");
});

test("a disk-export ends in a result card with Show-in-Finder (not a raw path toast)", async () => {
  const h = await mount({
    "POST /api/report/docx": { claim_count: 5, output_file: "/x/demo/review-record.docx" },
  });
  h.click(h.$(`.surfnav-tab[data-surface="output"]`));
  await h.waitFor(() => h.byAct("export-word"));
  h.click(h.byAct("export-word"));
  await h.waitFor(() => /Saved/.test(h.$("#outputResult").textContent));
  const res = h.$("#outputResult");
  assert.match(res.textContent, /Word review record/);
  assert.match(res.textContent, /Show in Finder/);
  const reveal = res.querySelector('[data-act="reveal"]');
  assert.equal(reveal.getAttribute("data-reveal"), "/x/demo/review-record.docx");
});
