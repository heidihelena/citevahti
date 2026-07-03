/* Backend-liveness watchdog (web/reconnect.js) — the page heals itself when the
 * engine dies or is replaced underneath it (the frozen-window incident, 2026-07-02). */
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { mount, closeAll } from "./harness.mjs";

after(closeAll);

test("connection loss shows the overlay; recovery on the same boot clears it", async () => {
  const backend = { down: false, boot_id: "boot-1" };
  const h = await mount({
    "GET /api/ping": () => {
      if (backend.down) throw new Error("connection refused");
      return { ok: true, boot_id: backend.boot_id };
    },
  });
  await h.run("__cvReconnect.beat()");                 // learns boot-1
  assert.equal(h.$("#reconnectOverlay"), null);

  backend.down = true;
  await h.run("__cvReconnect.beat()");                 // miss 1 — not yet (a blip is a blip)
  assert.equal(h.$("#reconnectOverlay"), null);
  await h.run("__cvReconnect.beat()");                 // miss 2 — say it out loud
  assert.ok(h.$("#reconnectOverlay"), "two consecutive misses must show the overlay");
  assert.match(h.$("#reconnectOverlay").textContent, /reconnecting/i);
  assert.match(h.$("#reconnectOverlay").textContent, /safe on disk/i);

  backend.down = false;                                // same process comes back
  await h.run("__cvReconnect.beat()");
  assert.equal(h.$("#reconnectOverlay"), null, "recovery on the same boot clears the overlay");
});

test("a NEW boot_id (engine replaced) reloads the page instead of driving a stale session", async () => {
  const backend = { boot_id: "boot-1" };
  const h = await mount({
    "GET /api/ping": () => ({ ok: true, boot_id: backend.boot_id }),
  });
  h.run("window.__reloaded = false; __cvReconnect._reload = () => { window.__reloaded = true; };");
  await h.run("__cvReconnect.beat()");                 // learns boot-1
  assert.equal(h.run("window.__reloaded"), false);

  backend.boot_id = "boot-2";                          // supervisor restarted the engine
  await h.run("__cvReconnect.beat()");
  assert.equal(h.run("window.__reloaded"), true,
    "a changed boot_id means fresh CSRF/state — the stale page must reload itself");
});

test("a non-CiteVahti answer on the port is left alone (no overlay, no reload)", async () => {
  const h = await mount({ "GET /api/ping": { hello: "world" } });
  h.run("window.__reloaded = false; __cvReconnect._reload = () => { window.__reloaded = true; };");
  await h.run("__cvReconnect.beat()");
  await h.run("__cvReconnect.beat()");
  assert.equal(h.$("#reconnectOverlay"), null);
  assert.equal(h.run("window.__reloaded"), false);
});
