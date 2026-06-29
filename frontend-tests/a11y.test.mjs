/* 5 · Accessibility-relevant tests — behaviour a screen-reader / keyboard user depends on:
 * named dialogs, Escape-to-close, a real button for the audit control, labelled regions,
 * and the legend toggle's exposed state. (Focus-trap and live-card errors need layout, so
 * they're covered in the Playwright pass.) */
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { mount, closeAll } from "./harness.mjs";

after(closeAll);

const promptRoutes = { "GET /api/prompts": { prompts: [] }, "GET /api/draft-context": {}, "POST /api/chat": {} };

test("a modal dialog has role=dialog + an accessible name from its heading", async () => {
  const h = await mount(promptRoutes);
  h.run("openPrompts()");
  await h.waitFor(() => h.$("#promptsModal") && h.$("#promptsModal-title"));
  const dlg = h.$("#promptsModal");
  assert.equal(dlg.getAttribute("role"), "dialog");
  assert.equal(dlg.getAttribute("aria-modal"), "true");
  const title = h.$("#" + dlg.getAttribute("aria-labelledby"));   // labelledby resolves…
  assert.ok(title && title.tagName === "H2");                     // …to a real heading…
  assert.ok(title.textContent.trim().length > 0);                // …with a non-empty name
});

test("Escape closes an open dialog", async () => {
  const h = await mount(promptRoutes);
  h.run("openPrompts()");
  await h.waitFor(() => h.$("#promptsModal"));
  h.press("Escape");
  await h.waitFor(() => !h.$("#promptsModal"));
  assert.equal(h.$("#promptsModal"), null);
});

test("the audit-record control is a keyboard button with a clear name, not a clickable span", async () => {
  const h = await mount();
  await h.waitFor(() => /Review record/.test(h.$("#auditBadge").textContent));
  const b = h.$("#auditBadge");
  assert.equal(b.tagName, "BUTTON");                              // Enter/Space + focus ring for free
  assert.match(b.getAttribute("aria-label"), /Review record/);   // glyphs don't become its name
});

test("surfaces are labelled regions and the notify bar is a live region", async () => {
  const h = await mount();
  for (const id of ["manuscripts", "checks", "atlas", "output", "settings"]) {
    assert.ok(h.$("#" + id).getAttribute("aria-label"), `#${id} is a labelled region`);
  }
  const n = h.$("#notify");
  assert.equal(n.getAttribute("role"), "alert");
  assert.ok(n.getAttribute("aria-live"), "notify announces");
});

test("the legend toggle exposes its expanded state and what it controls", async () => {
  const h = await mount();
  const btn = h.$("#legendBtn");
  assert.equal(btn.getAttribute("aria-controls"), "legend");
  assert.ok(h.$("#legend"), "the controlled region exists");
  assert.equal(btn.getAttribute("aria-expanded"), "false");
  h.click(btn);
  await h.waitFor(() => btn.getAttribute("aria-expanded") === "true");
});
