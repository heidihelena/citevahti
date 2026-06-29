/* CiteVahti panel — loopback API transport (extracted from app.js).
 * A classic (non-module) script loaded BEFORE app.js. Defines the shared `api()`
 * helper and the per-session CSRF token. No DOM access, no top-level side effects. */

// Per-session CSRF token, fetched once on boot and echoed on every state-changing request.
// GET reads don't need it; the server requires it on POSTs (see panel/server.py).
let CSRF = "";
async function loadSessionToken() {
  try { CSRF = (await api("GET", "/api/session")).csrf_token || ""; }
  catch { CSRF = ""; }   // older server without /api/session → POSTs still work there
}

async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  // attach the session token to mutating requests so the server's CSRF check passes
  if (method !== "GET" && CSRF) opts.headers["X-CiteVahti-Token"] = CSRF;
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const base = data.message || data.error || `HTTP ${res.status}`;
    const err = new Error(data.remediation ? `${base} — ${data.remediation}` : base);
    err.code = data.code || data.error || "";   // structured code, for callers that branch on it
    err.remediation = data.remediation || "";
    err.status = res.status;
    throw err;
  }
  return data;
}
