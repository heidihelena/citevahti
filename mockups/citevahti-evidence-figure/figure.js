/* Publication-figure system for the local claim–evidence map.
 *
 * Renders the Spine (the layout I'd publish as Lancet editor) as a SELF-CONTAINED,
 * print-grade SVG: colour + dash both encode verdict (survives greyscale and colour-
 * vision deficiency), the legend / N / retraction key / honest-framing note live
 * INSIDE the figure (figures travel apart from captions), and it exports to vector
 * SVG or print-to-PDF at real journal column widths. Deterministic; offline; no libs.
 *
 * Two modes: "adjudicated" (the honest primary — human decisions) and "AI view"
 * (AI ratings, revealed only after a human judgement — unjudged links stay ghosts). */

const SVGNS = "http://www.w3.org/2000/svg";
const VB = { w: 900, h: 650 };
const WIDTHS = { single: { mm: 89, label: "Single column · 89 mm" },
  onehalf: { mm: 120, label: "1.5 column · 120 mm" }, double: { mm: 183, label: "Double column · 183 mm" } };

const state = { width: "double", mono: false, mode: "adjudicated" };

const judged = (e) => e.decision !== "unrated";
/* the verdict that drives this edge's hue/dash in the current mode */
function verdictKey(e) {
  if (state.mode === "ai") return judged(e) ? SUPPORT_VERDICT[e.ai == null ? "null" : e.ai] : "unrated";
  return e.decision;
}
function palette() {
  return state.mono
    ? { ink: "#111", muted: "#555", line: "#CBCBCB", claimFill: "#ECECEC", claimStroke: "#333",
        paperStroke: "#555", retr: "#111", accent: "#111" }
    : { ink: "#1A1A1F", muted: "#6B6B73", line: "#E2E2E7", claimFill: "#EFE7FC", claimStroke: "#6B4E9E",
        paperStroke: "#6B6B73", retr: "#C24D7E", accent: "#4B1778" };
}
const vColor = (k) => (state.mono ? VERDICT[k].mono : VERDICT[k].hue);

function el(tag, attrs, kids) {
  const n = document.createElementNS(SVGNS, tag);
  for (const k in (attrs || {})) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
  for (const c of (kids || [])) n.appendChild(c);
  return n;
}
function txt(x, y, s, cls, fill, anchor) {
  const t = el("text", { x, y, class: cls, fill, "text-anchor": anchor });
  t.textContent = s; return t;
}

/* embedded typography (colours stay literal attributes → standalone download) */
const STYLE = `text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}
.t-panel{font-size:20px;font-weight:800}.t-title{font-size:16px;font-weight:700}.t-sub{font-size:11px}
.t-hdr{font-size:10px;font-weight:700;letter-spacing:.06em}.t-node{font-size:11px;font-weight:700}
.t-gloss{font-size:10px;font-weight:400}.t-venue{font-size:9px}.t-code{font-size:9.5px;font-weight:700;font-family:ui-monospace,Menlo,monospace}
.t-n{font-size:9.5px;font-weight:600}.t-foot{font-size:9px}`;

function buildFigure() {
  const P = palette();
  const svg = el("svg", { viewBox: `0 0 ${VB.w} ${VB.h}`, role: "img",
    "aria-label": "Local claim–evidence map" });
  svg.appendChild(el("style", {}, [document.createTextNode(STYLE)]));
  svg.appendChild(el("rect", { x: 0, y: 0, width: VB.w, height: VB.h, fill: "#FFFFFF" }));

  // header
  svg.appendChild(txt(28, 34, "A", "t-panel", P.ink));
  svg.appendChild(txt(60, 32, "Local claim–evidence map", "t-title", P.ink));
  svg.appendChild(txt(60, 49, `Each asserted claim tested against its cited papers · ${state.mode === "ai" ? "machine (AI) ratings" : "adjudicated human judgements"} · ledger snapshot ${SNAPSHOT}`, "t-sub", P.muted));

  const claims = Object.keys(CLAIMS);
  const papers = [...new Set(EDGES.map((e) => e.paper))];
  const xC = 306, xP = 594, plotTop = 104, rowH = 40;
  const yP = {}; papers.forEach((p, i) => (yP[p] = plotTop + i * rowH));
  // order papers to minimise crossings, then re-lay them out
  papers.sort((a, b) => meanY(a, claims, plotTop) - meanY(b, claims, plotTop));
  papers.forEach((p, i) => (yP[p] = plotTop + i * rowH));
  const plotBot = plotTop + (papers.length - 1) * rowH;
  const yC = {}; claims.forEach((c, i) => (yC[c] = plotTop + (i * (plotBot - plotTop)) / (claims.length - 1)));

  // column headers
  svg.appendChild(txt(xC - 4, plotTop - 16, "CLAIMS", "t-hdr", P.muted, "end"));
  svg.appendChild(txt(xP + 4, plotTop - 16, "CITED PAPERS", "t-hdr", P.muted, "start"));

  // edges
  for (const e of EDGES) {
    const k = verdictKey(e), V = VERDICT[k];
    const ghost = state.mode === "ai" && !judged(e);
    const y1 = yC[e.claim], y2 = yP[e.paper];
    svg.appendChild(el("path", {
      d: `M${xC},${y1} C${(xC + xP) / 2},${y1} ${(xC + xP) / 2},${y2} ${xP},${y2}`,
      fill: "none", stroke: ghost ? P.muted : vColor(k),
      "stroke-width": ghost ? 1.1 : V.w, "stroke-dasharray": ghost ? "2 4" : V.dash,
      "stroke-linecap": "round", opacity: ghost ? 0.6 : 1 }));
  }

  // claim nodes (numbered + short gloss; full text goes in the caption key)
  claims.forEach((c, i) => {
    const y = yC[c];
    svg.appendChild(el("circle", { cx: xC, cy: y, r: 6, fill: P.claimFill, stroke: P.claimStroke, "stroke-width": 2 }));
    const t = el("text", { x: xC - 14, y: y + 4, class: "t-node", fill: P.ink, "text-anchor": "end" });
    t.appendChild(el("tspan", { class: "t-node", fill: P.accent }, [tspanText(`C${i + 1}`)]));
    t.appendChild(el("tspan", { class: "t-gloss", fill: P.muted }, [tspanText("  " + CLAIMS[c].gloss)]));
    svg.appendChild(t);
  });

  // paper nodes
  for (const p of papers) {
    const y = yP[p], pr = PAPERS[p], retr = pr.retracted;
    svg.appendChild(el("circle", { cx: xP, cy: y, r: 6, fill: "#FFFFFF", stroke: retr ? P.retr : P.paperStroke, "stroke-width": retr ? 2 : 1.5 }));
    if (retr) svg.appendChild(el("circle", { cx: xP, cy: y, r: 9, fill: "none", stroke: P.retr, "stroke-width": 1.2, "stroke-dasharray": "2 2" }));
    svg.appendChild(txt(xP + 14, y - 1, (retr ? "⊘ " : "") + pr.short, "t-node", retr ? P.retr : P.ink, "start"));
    svg.appendChild(txt(xP + 14, y + 11, `${pr.venue} · ${pr.type}`, "t-venue", P.muted, "start"));
  }

  // legend — colour + dash + code + label, tied together
  const lgY = plotBot + 44;
  svg.appendChild(txt(28, lgY - 16, "VERDICT", "t-hdr", P.muted, "start"));
  VERDICT_ORDER.forEach((k, i) => {
    const V = VERDICT[k], x = 28 + i * 172;
    svg.appendChild(el("path", { d: `M${x},${lgY} L${x + 26},${lgY}`, stroke: vColor(k),
      "stroke-width": V.w, "stroke-dasharray": V.dash, "stroke-linecap": "round" }));
    svg.appendChild(txt(x + 33, lgY + 4, `[${V.code || "  "}]`, "t-code", P.ink, "start"));
    svg.appendChild(txt(x + 62, lgY + 4, V.label, "t-sub", P.ink, "start"));
  });

  // retraction + AI keys
  let ky = lgY + 26;
  svg.appendChild(txt(28, ky, "⊘  Retracted source (retraction scan) — shown independent of any rating", "t-foot", P.retr, "start"));
  if (state.mode === "ai") {
    ky += 14;
    svg.appendChild(txt(28, ky, "Grey dashed — link awaiting human judgement; AI rating stays blinded until you judge it", "t-foot", P.muted, "start"));
  }

  // N + honest framing
  const nLinks = EDGES.length;
  svg.appendChild(txt(28, VB.h - 46, `N = ${claims.length} claims · ${papers.length} cited papers · ${nLinks} tested links`, "t-n", P.ink, "start"));
  svg.appendChild(txt(28, VB.h - 30, "This figure displays adjudicated human judgements recorded in the local ledger.", "t-foot", P.muted, "start"));
  svg.appendChild(txt(28, VB.h - 18, "It does not assert that any claim is true; it shows which cited papers were tested, and the verdict reached.", "t-foot", P.muted, "start"));

  return svg;
}
function tspanText(s) { return document.createTextNode(s); }
function meanY(paper, claims, plotTop) {
  const idx = {}; claims.forEach((c, i) => (idx[c] = i));
  const ys = EDGES.filter((e) => e.paper === paper).map((e) => idx[e.claim]);
  return ys.reduce((a, b) => a + b, 0) / ys.length;
}

/* ---------- export ---------- */
function currentSvgMarkup() {
  const svg = buildFigure();
  const wmm = WIDTHS[state.width].mm;
  svg.setAttribute("xmlns", SVGNS);
  svg.setAttribute("width", wmm + "mm");
  svg.setAttribute("height", ((wmm * VB.h) / VB.w).toFixed(1) + "mm");
  return '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(svg);
}
function downloadSVG() {
  const blob = new Blob([currentSvgMarkup()], { type: "image/svg+xml;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = `citevahti-evidence-figure-${state.mode}.svg`;
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(a.href);
}
function captionText() {
  const claims = Object.keys(CLAIMS);
  const key = claims.map((c, i) => `C${i + 1}, ${CLAIMS[c].text}`).join("; ");
  const modeLine = state.mode === "ai"
    ? "Links are coloured and line-styled by the machine (AI) support rating, revealed only where a human judgement already exists; links awaiting human judgement are shown as grey dashed lines."
    : "Each link is coloured and line-styled by the adjudicated human verdict (see legend).";
  return `Figure 1. Local claim–evidence map. Bipartite plot of each asserted claim (left, C1–C${claims.length}) `
    + `against the cited papers tested to support it (right). ${modeLine} ⊘ marks a retracted source `
    + `(retraction scan), shown independent of any rating. Colour and dash pattern both encode the verdict so the `
    + `figure is legible in greyscale and for colour-vision-deficient readers. The figure displays adjudicated human `
    + `judgements recorded in the local ledger and does not assert that any claim is true. `
    + `N = ${claims.length} claims, ${new Set(EDGES.map((e) => e.paper)).size} cited papers, ${EDGES.length} tested links. `
    + `Ledger snapshot ${SNAPSHOT}. Claim key: ${key}.`;
}

/* ---------- shell ---------- */
function render() {
  const host = document.getElementById("figure");
  host.innerHTML = "";
  host.appendChild(buildFigure());
  document.getElementById("caption").textContent = captionText();
  document.getElementById("sheet").style.setProperty("--fig-w", WIDTHS[state.width].mm + "mm");
}
function seg(groupId, key, val) {
  document.querySelectorAll(`#${groupId} button`).forEach((b) => b.setAttribute("aria-pressed", b.dataset[key] === val));
}
function boot() {
  document.querySelectorAll("#widthCtl button").forEach((b) => b.onclick = () => { state.width = b.dataset.w; seg("widthCtl", "w", state.width); render(); });
  document.querySelectorAll("#modeCtl button").forEach((b) => b.onclick = () => { state.mode = b.dataset.m; seg("modeCtl", "m", state.mode); render(); });
  document.querySelectorAll("#inkCtl button").forEach((b) => b.onclick = () => { state.mono = b.dataset.ink === "mono"; seg("inkCtl", "ink", state.mono ? "mono" : "colour"); render(); });
  document.getElementById("dlSvg").onclick = downloadSVG;
  document.getElementById("printPdf").onclick = () => window.print();
  document.getElementById("copyCap").onclick = async () => {
    try { await navigator.clipboard.writeText(captionText()); flash("copyCap", "Copied ✓"); }
    catch { const t = document.getElementById("caption"); const r = document.createRange(); r.selectNodeContents(t);
      const s = getSelection(); s.removeAllRanges(); s.addRange(r); flash("copyCap", "Selected — ⌘C"); }
  };
  render();
}
function flash(id, msg) { const b = document.getElementById(id), o = b.textContent; b.textContent = msg; setTimeout(() => (b.textContent = o), 1400); }
document.addEventListener("DOMContentLoaded", boot);
