/* The three silent dead-ends from the 2026-07-02 founder session — each must now SAY
 * what's wrong and what works, instead of quietly doing nothing:
 *   1. a manuscript whose FILE can't be found (it moved out of the bound folder);
 *   2. a real manuscript with ZERO claims (nothing extracted yet);
 *   3. review keyboard shortcuts pressed when there are no claims to act on. */
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { mount, closeAll } from "./harness.mjs";

after(closeAll);

const CLAIM_SEG = { kind: "claim", text: "Telehealth reduces readmissions.", claim_id: "c1" };

test("an unresolved manuscript names the missing file AND the folder it looked in", async () => {
  const h = await mount({
    "GET /api/context": { root: "/x/demo", claim_total: 1, manuscripts_dir: "/x/demo/manuscripts" },
    "GET /api/manuscripts": {
      manuscripts: [{ manuscript_id: "paper.md", claim_count: 1, resolved: false }],
      active: "paper.md", manuscripts_dir: "/x/demo/manuscripts",
    },
    "GET /api/manuscript/paper.md": {
      manuscript_id: "paper.md", mode: "reconstructed",
      segments: [CLAIM_SEG], claim_states: {}, unmatched: [],
    },
  });
  await h.waitFor(() => h.$("#doc .recon-note"));
  const note = h.$("#doc .recon-note").textContent;
  assert.match(note, /wasn't found in/, "must say the file is missing, not just reassure");
  assert.match(note, /paper\.md/, "must name the file");
  assert.match(note, /\/x\/demo\/manuscripts/, "must name the folder the panel looked in");
  assert.match(note, /nothing here is lost/, "the reassurance stays");
});

test("chat-saved claims (a §-style id, no file) keep the open-your-document guidance", async () => {
  const h = await mount({
    "GET /api/context": { root: "/x/demo", claim_total: 1, manuscripts_dir: "/x/demo/manuscripts" },
    "GET /api/manuscripts": {
      manuscripts: [{ manuscript_id: "§2 Background", claim_count: 1, resolved: false }],
      active: "§2 Background", manuscripts_dir: "/x/demo/manuscripts",
    },
    "GET /api/manuscript/%C2%A72%20Background": {
      manuscript_id: "§2 Background", mode: "reconstructed",
      segments: [CLAIM_SEG], claim_states: {}, unmatched: [],
    },
  });
  await h.waitFor(() => h.$("#doc .recon-note"));
  const note = h.$("#doc .recon-note").textContent;
  assert.match(note, /saved from chat/, "a section reference is not a missing file");
  assert.doesNotMatch(note, /wasn't found in/);
});

function zeroClaimsRoutes() {
  return {
    "GET /api/context": { root: "/x/demo", claim_total: 24, manuscripts_dir: "/x/demo/manuscripts" },
    "GET /api/manuscripts": {
      manuscripts: [{ manuscript_id: "fresh.md", claim_count: 0, resolved: true }],
      active: "fresh.md", manuscripts_dir: "/x/demo/manuscripts",
    },
    "GET /api/manuscript/fresh.md": {
      manuscript_id: "fresh.md", mode: "file", resolved_path: "/x/demo/manuscripts/fresh.md",
      segments: [{ kind: "text", text: "A fresh manuscript, prose only." }],
      claim_states: {}, unmatched: [],
    },
  };
}

test("a real manuscript with zero claims says how to extract them", async () => {
  const h = await mount(zeroClaimsRoutes());
  await h.waitFor(() => h.$("#doc .recon-note"));
  const note = h.$("#doc .recon-note").textContent;
  assert.match(note, /No claims yet/i);
  assert.match(note, /run_claim_tests/, "must name the chat prompt that extracts claims");
  assert.match(note, /＋ Claim/, "must name the manual path");
  assert.match(h.$("#doc").textContent, /prose only/i, "the document itself still renders");
});

test("a review shortcut with no claims explains itself once instead of doing nothing", async () => {
  const h = await mount(zeroClaimsRoutes());
  await h.waitFor(() => h.$("#doc .recon-note"));
  h.press("j");
  await h.waitFor(() => /shortcuts act on claims/i.test(h.$("#notify").textContent));
  assert.match(h.$("#notify").textContent, /run_claim_tests/);
  assert.equal(h.run("state._hintedNoClaims"), true);
  // a second press stays quiet (the hint is once per page, not a nag)
  h.run('document.querySelector("#notify").innerHTML = ""');
  h.press("k");
  assert.equal(h.$("#notify").textContent, "", "the hint must not repeat on every keypress");
});
