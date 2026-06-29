/* CiteVahti panel — leaf helpers (DOM + formatting). No app state, no API; a classic
 * script loaded right after state.js. Everything here is a pure utility other modules
 * build on, so it must load before them. */

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const $ = (sel) => document.querySelector(sel);

// One loading pattern (design system §9): spinner + label. opts.card wraps it in a
// modal-card so it can drop straight into a modal/surface-host while data loads.
function loadingHTML(label, opts) {
  const inner = `<div class="cv-loading${opts && opts.card ? " is-card" : ""}">`
    + `<span class="cv-spin" aria-hidden="true"></span><span>${esc(label || "Loading…")}</span></div>`;
  return opts && opts.card ? `<div class="modal-card">${inner}</div>` : inner;
}

/* A one-line reference from whatever identifiers a candidate carries — honest with
 * partial metadata. Used both to tag cited passages (data-citation) and, on copy, to
 * append the source to the clipboard. */
function citeOf(c) {
  if (!c) return "";
  const bits = [];
  if (c.title) bits.push(String(c.title).trim().replace(/\.+$/, ""));
  const meta = [c.journal, c.year].filter(Boolean).join(" ");
  if (meta) bits.push(meta);
  if (c.doi) bits.push("https://doi.org/" + c.doi);
  else if (c.pmid) bits.push("PMID " + c.pmid);
  return bits.join(". ");
}

function doiUrl(doi) {
  const d = String(doi).trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, "").replace(/^doi:/i, "");
  return "https://doi.org/" + d;
}

// CSS.escape isn't in every embedded webview; fall back to a minimal escaper for ids.
function cssEscape(s) {
  return (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/["\\]/g, "\\$&");
}

async function copyText(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) return await navigator.clipboard.writeText(text);
  } catch {}
  const ta = document.createElement("textarea");      // fallback for non-secure contexts
  ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select();
  try { document.execCommand("copy"); } finally { ta.remove(); }
}

function downloadJson(obj, filename) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}
