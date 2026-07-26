/* 1 · Unit tests — pure logic whose OUTPUT the user sees (recency labels, project names,
 * the plain-language audit vocabulary, one-line references, the Show-in-Finder card). */
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { mount, closeAll } from "./harness.mjs";

let t;
before(async () => { t = (await mount()).t(); });
after(closeAll);

test("relTime renders human recency", () => {
  const now = Math.floor(Date.now() / 1000);
  assert.equal(t.relTime(now - 5), "just now");
  assert.equal(t.relTime(now - 2 * 3600), "2 hours ago");
  assert.equal(t.relTime(now - 1 * 86400), "1 day ago");
  assert.equal(t.relTime(now - 3 * 86400), "3 days ago");
  assert.equal(t.relTime(0), "");                       // unknown time → nothing, not "Jan 1 1970"
});

test("projectName is the folder name, not the full path", () => {
  assert.equal(t.projectName("/Users/x/Documents/telehealth-review"), "telehealth-review");
  assert.equal(t.projectName("/Users/x/lung/"), "lung");
  assert.equal(t.projectName(""), "");
});

test("humanEvent turns audit events into plain language", () => {
  assert.equal(t.humanEvent("decision.final"), "Recorded a decision");
  assert.equal(t.humanEvent("store.init"), "Project created");
  assert.equal(t.humanEvent("claim.write"), "Claim added");
  assert.equal(t.humanEvent("claim_support.save"), "Recorded a support rating");
  assert.equal(t.humanEvent("some.weird_event"), "Some Weird Event");  // never a raw token
});

test("citeOf builds a one-line reference, DOI preferred over PMID", () => {
  assert.equal(t.citeOf({ title: "Telephone follow-up.", journal: "BMJ", year: 2021, doi: "10.1/x" }),
               "Telephone follow-up. BMJ 2021. https://doi.org/10.1/x");
  assert.equal(t.citeOf({ title: "A trial", pmid: "30000004" }), "A trial. PMID 30000004");
  assert.equal(t.citeOf(null), "");
});

test("savedToFolderCard offers Show-in-Finder for the file just written", () => {
  const html = t.savedToFolderCard("Word review record", "/x/demo/report.docx");
  assert.match(html, /Show in Finder/);
  assert.match(html, /data-act="reveal"/);
  assert.match(html, /data-reveal="\/x\/demo\/report\.docx"/);
});

test("isDecided treats any non-pending state as decided", () => {
  assert.equal(t.isDecided("needs_support"), false);   // the pending state
  assert.equal(t.isDecided("accepted"), true);
  assert.equal(t.isDecided("decision_recorded"), true);
  assert.equal(t.isDecided(undefined), false);
});

/* The Reveal & decide panel has to tell three different "no AI value" events apart. Two of
 * them are honest outcomes; a reply cut off at the token ceiling is a SETUP problem the
 * operator has to act on, and used to render identically to "no AI run yet". */
const rated = (extra) => ({ rating: { human: "directly_supports", ai: null, ...extra } });

test("a cut-off AI reply reads as a setup problem, with the fix", () => {
  const html = t.decideBlock(rated({ ai_present: true, ai_abstained: true,
    ai_config_issue: "truncated_reply", comparison_status: "ai_abstained" }));
  assert.match(html, /cut off before answering/);
  assert.match(html, /never judged this item/);
  assert.match(html, /ai_connection\.max_reply_tokens/);        // the actionable fix, named
  assert.match(html, /class="configwarn"/);                     // visually separated row
  assert.match(html, /class="col cut"/);                        // and marked in the AI column
  assert.doesNotMatch(html, /not recorded yet/);                // no longer reads as "none yet"
  assert.match(html, /no AI rating — check AI settings/);       // the raw ledger code is not shown
});

test("a genuine abstention stays an abstention — no setup warning", () => {
  const html = t.decideBlock(rated({ ai_present: true, ai_abstained: true,
    ai_config_issue: null, comparison_status: "ai_abstained" }));
  assert.match(html, /abstained — no rating given/);
  assert.doesNotMatch(html, /configwarn/);
  assert.doesNotMatch(html, /max_reply_tokens/);
  assert.doesNotMatch(html, /cut off/);
});

test("no AI run yet still offers the second opinion, unchanged", () => {
  const html = t.decideBlock(rated({ ai_present: false, ai_abstained: false, ai_config_issue: null }));
  assert.match(html, /not recorded yet/);
  assert.match(html, /data-act="run-ai"/);
  assert.doesNotMatch(html, /configwarn/);
});

test("an AI value that landed is compared as before", () => {
  const html = t.decideBlock({ rating: { human: "directly_supports", ai: "does_not_support",
    ai_present: true, ai_abstained: false, ai_config_issue: null, comparison_status: "discordant" } });
  assert.match(html, /verdict-tag discordant/);
  assert.doesNotMatch(html, /configwarn/);
  assert.doesNotMatch(html, /data-act="run-ai"/);               // no re-run offered once rated
});
