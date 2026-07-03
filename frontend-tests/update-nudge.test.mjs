/* The opt-in launch-time update check: OFF by default (no phone-home on boot — a
 * documented promise), a quiet header badge when opted in and a newer version exists,
 * and a Settings checkbox that persists the choice server-side. */
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { mount, closeAll } from "./harness.mjs";

after(closeAll);

test("by default the panel makes NO update request at boot", async () => {
  const h = await mount();                       // DEFAULTS: auto_update_check absent/false
  await h.waitFor(() => h.$("#surfnav") && !h.$("#surfnav").hidden);
  assert.ok(!h.log.includes("GET /api/check-update"),
    "boot must not contact PyPI unless the user opted in");
  assert.equal(h.$("#updateBadge"), null);
});

test("opted in + newer version => one check and a quiet header badge to Settings", async () => {
  const h = await mount({
    "GET /api/context": { root: "/x/demo", claim_total: 0,
                          manuscripts_dir: "/x/demo/manuscripts", auto_update_check: true },
    "GET /api/check-update": { checked: true, update_available: true,
                               current: "0.45.0", latest: "9.9.9",
                               message: "CiteVahti 9.9.9 is available." },
  });
  await h.waitFor(() => h.$("#updateBadge"));
  assert.equal(h.log.filter((l) => l === "GET /api/check-update").length, 1,
    "exactly one disclosed request per panel open");
  assert.match(h.$("#updateBadge").textContent, /9\.9\.9 available/);
  h.click(h.$("#updateBadge"));
  assert.equal(h.surface(), "settings", "the badge routes to the update steps");
});

test("opted in but up to date (or PyPI unreachable) stays silent", async () => {
  const h = await mount({
    "GET /api/context": { root: "/x/demo", claim_total: 0,
                          manuscripts_dir: "/x/demo/manuscripts", auto_update_check: true },
    "GET /api/check-update": { checked: true, update_available: false,
                               current: "0.45.0", latest: "0.45.0", message: "Up to date." },
  });
  await h.waitFor(() => h.log.includes("GET /api/check-update"));
  assert.equal(h.$("#updateBadge"), null, "no update, no badge, no noise");
});

test("the Settings checkbox persists the choice via POST /api/prefs/update-check", async () => {
  const h = await mount({
    "POST /api/prefs/update-check": (opts) => ({ enabled: JSON.parse(opts.body).enabled }),
  });
  h.click(h.$('.surfnav-tab[data-surface="settings"]'));
  await h.waitFor(() => h.$("#autoUpdChk"));
  assert.equal(h.$("#autoUpdChk").checked, false, "default off");
  h.$("#autoUpdChk").checked = true;
  h.$("#autoUpdChk").dispatchEvent(new h.window.Event("change", { bubbles: true }));
  await h.waitFor(() => h.log.includes("POST /api/prefs/update-check"));
  await h.waitFor(() => /check PyPI/i.test(h.$("#notify").textContent));
});
