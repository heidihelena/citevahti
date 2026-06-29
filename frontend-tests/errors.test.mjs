/* 4 · Error-path tests — every failure resolves to something the user can act on:
 * an inline message, a recovery screen, a help card, or an announced toast. Never a crash
 * or a dead spinner. */
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { mount, closeAll } from "./harness.mjs";

after(closeAll);

test("saving with empty fields shows an inline error, not a crash", async () => {
  const h = await mount();
  await h.waitFor(() => h.$("#pasteName"));
  h.click(h.$("#pasteSave"));                                  // no name, no text
  await h.waitFor(() => h.$("#pasteResult").textContent.length > 0);
  assert.match(h.$("#pasteResult").textContent, /name/i);
  h.$("#pasteName").value = "x.md";
  h.click(h.$("#pasteSave"));                                  // name but no text
  await h.waitFor(() => /paste/i.test(h.$("#pasteResult").textContent));
  assert.match(h.$("#pasteResult").textContent, /paste/i);
});

test("an export failure surfaces a recoverable error, not a silent fail", async () => {
  const h = await mount({ "POST /api/report/docx": {
    __status: 500, __body: { message: "Word export needs citevahti[docx]" } } });
  h.click(h.$('.surfnav-tab[data-surface="output"]'));
  await h.waitFor(() => h.byAct("export-word"));
  h.click(h.byAct("export-word"));
  await h.waitFor(() => /citevahti\[docx\]/.test(h.$("#outputResult").textContent));
  assert.match(h.$("#outputResult").innerHTML, /cv-error/);     // a visible error block
  assert.match(h.$("#outputResult").textContent, /Word export needs/);
});

test("an unset-up folder gets a no-terminal recovery, not the `citevahti init` error", async () => {
  const h = await mount({ "GET /api/context": { __status: 400, __body: {
    error: "ValueError", code: "not_initialized",
    message: "/x/fresh/.citevahti is not initialized; run `citevahti init` first" } } });
  await h.waitFor(() => /isn.t set up/i.test(h.$("#manuscripts").textContent));
  const ms = h.$("#manuscripts");
  assert.match(ms.textContent, /no Terminal needed/i);
  assert.ok(h.byAct("setup-folder"), "offers a one-click 'Set up this folder'");
  assert.ok(!/run `citevahti init`/.test(ms.textContent), "the shell command is not shown");
});

test("the claim-extraction wait resolves to help and can be stopped — never a dead spinner", async () => {
  const h = await mount({ "POST /api/manuscripts/paste": { ok: true, filename: "d.md", next_prompt: "Extract…" } });
  await h.waitFor(() => h.$("#pasteName"));
  h.$("#pasteName").value = "d.md"; h.$("#pasteBody").value = "# t\n\nclaim";
  h.click(h.$("#pasteSave"));
  await h.waitFor(() => h.$("#awaitState"));
  assert.match(h.$("#awaitState").textContent, /Waiting for claims/);
  // fire the ~90s timeout state (the tick threshold is a constant; the STATE is the behaviour)
  h.run("showAwaitHelp()");
  const help = h.$("#awaitState");
  assert.match(help.textContent, /Still waiting/i);
  assert.ok(help.querySelector('[data-act="copy-handoff"]'), "offers to copy the prompt again");
  const finish = help.querySelector('[data-act="stop-awaiting"]');
  assert.ok(finish, "offers Save & finish later");
  h.click(finish);
  await h.waitFor(() => /saved/i.test(h.$("#awaitState").textContent));
  assert.equal(h.run("state.awaiting"), false, "polling actually stops");
});

test("a reveal (Show in Finder) failure is announced, not swallowed", async () => {
  const h = await mount({
    "POST /api/report/docx": { claim_count: 1, output_file: "/x/demo/r.docx" },
    "POST /api/reveal": { __status: 500, __body: { message: "couldn't open the file manager" } },
  });
  h.click(h.$('.surfnav-tab[data-surface="output"]'));
  await h.waitFor(() => h.byAct("export-word"));
  h.click(h.byAct("export-word"));
  await h.waitFor(() => h.$('[data-act="reveal"]'));
  h.click(h.$('[data-act="reveal"]'));
  await h.waitFor(() => /file manager/.test(h.$("#notify").textContent));
  assert.equal(h.$("#notify").getAttribute("role"), "alert");   // errors interrupt (assertive)
});
