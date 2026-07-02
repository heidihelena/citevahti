/* Local evidence map — mockup renderer. Three variants over one shared ledger
 * (data.js). Everything is plain SVG built by hand; no external library, no
 * network, deterministic layout (no Math.random / Date.now) so the picture is
 * stable across reloads. Read-only: clicking selects/inspects, nothing mutates.
 *
 *   Constellation  whole-corpus node-link map (overview)
 *   Spine          claims ↔ papers bipartite columns (structured, legible)
 *   Orbit          one claim in focus, its papers as an ego-network (drill-down)
 *
 * Verdict hue is taken from the decision on each edge and is ALWAYS paired with
 * the bracketed code, exactly as on the manuscript — colour is never the only cue. */

const SVGNS = "http://www.w3.org/2000/svg";
const HUE = { supported: "h-supported", partial: "h-partial", revise: "h-revise", delete: "h-delete", pending: "h-pending" };
const clampText = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

/* nodes: claims + the papers that actually appear on an edge */
function buildGraph() {
  const nodes = new Map();
  for (const id in CLAIMS) nodes.set(id, { id, kind: "claim", ...CLAIMS[id] });
  for (const e of EDGES) if (!nodes.has(e.paper)) nodes.set(e.paper, { id: e.paper, kind: "paper", ...PAPERS[e.paper] });
  const deg = {};
  for (const e of EDGES) { deg[e.claim] = (deg[e.claim] || 0) + 1; deg[e.paper] = (deg[e.paper] || 0) + 1; }
  return { nodes, edges: EDGES.map((e, i) => ({ ...e, id: "e" + i })), deg };
}

function el(tag, attrs, kids) {
  const n = document.createElementNS(SVGNS, tag);
  for (const k in (attrs || {})) n.setAttribute(k, attrs[k]);
  for (const c of (kids || [])) n.appendChild(c);
  return n;
}
function verdictHueClass(decision) { return HUE[VERDICT[decision].key]; }
function hueVarFor(cls, prop) {
  const probe = document.createElement("div");
  probe.className = cls; document.body.appendChild(probe);
  const v = getComputedStyle(probe).getPropertyValue(prop).trim();
  probe.remove(); return v;
}

/* AI second opinion (blinding-safe: this is a POST-review map, so the AI rating
 * is no longer hidden — but it must never look like a verdict). The AI produces a
 * claim-SUPPORT value, not a decision; map it to the same hue family a decision
 * would land on, then draw it faint (25%) beside the human edge. Colour never the
 * only cue: the flyout spells out the AI label + whether it concurs. */
const SUPPORT_HUE = {
  directly_supports: "supported", partially_supports: "partial", indirectly_supports: "partial",
  unclear: "pending", does_not_support: "revise", contradicts: "delete", null: "pending",
};
function aiHueClass(v) { return HUE[SUPPORT_HUE[v == null ? "null" : v]]; }
function aiAgree(e) {
  if (e.ai == null) return { t: "AI abstained", k: "muted" };
  return SUPPORT_HUE[e.human] === SUPPORT_HUE[e.ai] ? { t: "AI concurs", k: "ok" } : { t: "AI differs", k: "warn" };
}
const edgeW = (e) => (e.decision === "unrated" ? 1.4 : 2.4);
const edgeDash = (e) => (e.decision === "unrated" ? "3 4" : "");
/* the human has judged this link → the AI opinion may be revealed (blinding-safe) */
const judged = (e) => e.decision !== "unrated";
function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

/* Appearance of the PRIMARY edge, per AI mode.
 *  off / overlay : coloured by YOUR decision (AI, if any, is a separate faint strand)
 *  view          : coloured by the AI's rating — but only where you've already judged;
 *                  unjudged links stay a neutral "awaiting your judgement" ghost. */
function mainEdge(e) {
  if (state.aiMode === "view") {
    if (!judged(e)) return { stroke: cssVar("--zs-muted"), width: 1.4, dash: "3 4", ghost: true };
    if (e.ai == null) return { stroke: cssVar("--zs-muted"), width: 2, dash: "2 3" };
    return { stroke: hueVarFor(aiHueClass(e.ai), "--hue"), width: 2.4, dash: "" };
  }
  return { stroke: hueVarFor(verdictHueClass(e.decision), "--hue"), width: edgeW(e), dash: edgeDash(e) };
}
/* draw the faint 25% AI strand? overlay mode only, and only after you've judged */
const showAIStrand = (e) => state.aiMode === "overlay" && judged(e) && e.ai != null;
/* unit perpendicular offset so the AI strand runs parallel to, not over, the human edge */
function perp(x1, y1, x2, y2, off) {
  const dx = x2 - x1, dy = y2 - y1, d = Math.hypot(dx, dy) || 1;
  return [(-dy / d) * off, (dx / d) * off];
}

/* ----- shared selection + detail ----- */
const state = { variant: "constellation", sel: null, aiMode: "off" };

function edgesFor(id) { return G.edges.filter((e) => e.claim === id || e.paper === id); }

function showDetail(stage, id) {
  const d = stage.querySelector(".detail");
  const node = G.nodes.get(id);
  const es = edgesFor(id);
  let head, rows;
  const retrFlag = `<div class="retr-flag">⊘ Retracted — flagged by the retraction scan, independent of any rating</div>`;
  if (node.kind === "claim") {
    head = `<div class="kind">Claim · ${node.type.replace(/_/g, " ")} · ${node.loc}</div><h3>${node.text}</h3>
      <div class="meta">${es.length} cited paper(s) tested against this claim</div>`;
    rows = es.map((e) => edgeRow(PAPERS[e.paper].short + (PAPERS[e.paper].retracted ? " ⊘" : ""), PAPERS[e.paper].venue, e)).join("");
  } else {
    head = `<div class="kind">Paper · ${node.type} · ${node.venue}</div><h3>${node.title}</h3>
      ${node.retracted ? retrFlag : ""}
      <div class="meta">${node.short} · PMID ${node.pmid} · cited for ${es.length} claim(s)</div>`;
    rows = es.map((e) => edgeRow(clampText(CLAIMS[e.claim].text, 44), CLAIMS[e.claim].loc, e)).join("");
  }
  d.innerHTML = `<button class="close" aria-label="Close">✕</button>${head}${rows}`;
  d.classList.add("show");
  d.querySelector(".close").onclick = () => clearSel(stage);
}

function edgeRow(title, sub, e) {
  const v = VERDICT[e.decision];
  const supp = SUPPORT[e.human == null ? "null" : e.human];
  // AI opinion stays hidden until you've judged the link (blinding-safe)
  let aiLine;
  if (!judged(e)) {
    aiLine = `<span class="ai muted">AI opinion hidden until you judge · blinded</span>`;
  } else {
    const ai = SUPPORT[e.ai == null ? "null" : e.ai];
    const ag = aiAgree(e);
    aiLine = `<span class="ai">AI: ${ai.label} · <em class="tag-${ag.k}">${ag.t}</em></span>`;
  }
  return `<div class="edgerow"><div class="txt"><b>${title}</b>
    <span>${sub} · you: ${supp.label} (${supp.pol})</span>
    ${aiLine}</div>
    <span class="cv-badge ${verdictHueClass(e.decision)}">[${v.code}] ${v.label}</span></div>`;
}

function clearSel(stage) {
  state.sel = null;
  stage.classList.remove("has-sel");
  stage.querySelectorAll(".node").forEach((n) => n.classList.remove("sel", "adj"));
  stage.querySelectorAll(".edge").forEach((x) => x.classList.remove("on"));
  const d = stage.querySelector(".detail"); if (d) d.classList.remove("show");
}

function applySel(stage, id) {
  state.sel = id;
  stage.classList.add("has-sel");
  const es = edgesFor(id);
  const adj = new Set(); es.forEach((e) => { adj.add(e.claim); adj.add(e.paper); });
  stage.querySelectorAll(".node").forEach((n) => {
    const nid = n.dataset.id;
    n.classList.toggle("sel", nid === id);
    n.classList.toggle("adj", nid !== id && adj.has(nid));
  });
  stage.querySelectorAll(".edge").forEach((x) => x.classList.toggle("on", es.some((e) => e.id === x.dataset.id)));
  showDetail(stage, id);
}

function wireNode(stage, g, id) {
  g.dataset.id = id;
  g.addEventListener("click", (ev) => { ev.stopPropagation(); state.sel === id ? clearSel(stage) : applySel(stage, id); });
}

/* ========================================================================
   Variant 1 — Constellation: force-directed whole-corpus map
   ===================================================================== */
function renderConstellation(stage) {
  const W = 1040, H = 620, svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Evidence map" });
  const ids = [...G.nodes.keys()];
  // deterministic seed positions on a circle (index-based, no randomness)
  const pos = {}; ids.forEach((id, i) => {
    const a = (i / ids.length) * Math.PI * 2;
    pos[id] = { x: W / 2 + Math.cos(a) * 230, y: H / 2 + Math.sin(a) * 190, vx: 0, vy: 0 };
  });
  // tiny spring/repulsion sim, fixed iterations → stable layout
  const links = G.edges.map((e) => [e.claim, e.paper]);
  for (let it = 0; it < 320; it++) {
    for (let a = 0; a < ids.length; a++) for (let b = a + 1; b < ids.length; b++) {
      const p = pos[ids[a]], q = pos[ids[b]];
      let dx = p.x - q.x, dy = p.y - q.y, d2 = dx * dx + dy * dy || 1, d = Math.sqrt(d2);
      const rep = 5200 / d2; const ux = dx / d, uy = dy / d;
      p.vx += ux * rep; p.vy += uy * rep; q.vx -= ux * rep; q.vy -= uy * rep;
    }
    for (const [u, v] of links) {
      const p = pos[u], q = pos[v]; let dx = q.x - p.x, dy = q.y - p.y, d = Math.hypot(dx, dy) || 1;
      const f = (d - 150) * 0.012; const ux = dx / d, uy = dy / d;
      p.vx += ux * f; p.vy += uy * f; q.vx -= ux * f; q.vy -= uy * f;
    }
    for (const id of ids) { const p = pos[id];
      p.vx += (W / 2 - p.x) * 0.004; p.vy += (H / 2 - p.y) * 0.004;
      p.x += p.vx *= 0.82; p.y += p.vy *= 0.82;
      p.x = Math.max(60, Math.min(W - 60, p.x)); p.y = Math.max(48, Math.min(H - 48, p.y));
    }
  }
  const eLayer = el("g"), nLayer = el("g");
  for (const e of G.edges) {
    const p = pos[e.claim], q = pos[e.paper];
    const m = mainEdge(e);
    eLayer.appendChild(el("path", { class: "edge" + (m.ghost ? " ghost" : ""), "data-id": e.id,
      d: `M${p.x},${p.y} Q${(p.x + q.x) / 2},${(p.y + q.y) / 2 - 24} ${q.x},${q.y}`,
      stroke: m.stroke, "stroke-width": m.width, "stroke-dasharray": m.dash }));
    if (showAIStrand(e)) {
      const [ox, oy] = perp(p.x, p.y, q.x, q.y, 6);
      eLayer.appendChild(el("path", { class: "edge ai", "data-id": e.id,
        d: `M${p.x + ox},${p.y + oy} Q${(p.x + q.x) / 2 + ox},${(p.y + q.y) / 2 - 24 + oy} ${q.x + ox},${q.y + oy}`,
        stroke: hueVarFor(aiHueClass(e.ai), "--hue"), "stroke-width": 2 }));
    }
  }
  for (const id of ids) drawNodeDisc(nLayer, stage, id, pos[id].x, pos[id].y);
  svg.appendChild(eLayer); svg.appendChild(nLayer);
  stage.querySelector(".host").appendChild(svg);
}

function drawNodeDisc(layer, stage, id, x, y) {
  const node = G.nodes.get(id), claim = node.kind === "claim";
  const retr = !claim && node.retracted;
  const r = claim ? 15 + Math.min(G.deg[id] || 0, 5) * 2 : 9;
  const g = el("g", { class: "node " + node.kind + (retr ? " retracted" : ""), transform: `translate(${x},${y})` }, [
    el("circle", { class: "halo", r: r + 6 }),
    el("circle", { class: "disc", r }),
  ]);
  if (retr) {
    g.appendChild(el("circle", { class: "retr-ring", r: r + 3 }));
    const badge = el("text", { class: "retr-badge", "text-anchor": "middle", y: -(r + 7) });
    badge.textContent = "⊘ retracted"; g.appendChild(badge);
  }
  const t = el("text", { "text-anchor": "middle", y: claim ? 4 : r + 13 }, []);
  t.textContent = claim ? "C" + id.slice(1) : clampText(node.short, 12);
  if (!claim) t.setAttribute("class", "sub");
  g.appendChild(t);
  wireNode(stage, g, id);
  layer.appendChild(g);
}

/* ========================================================================
   Variant 2 — Spine: claims (left) ↔ papers (right), edges = verdicts
   ===================================================================== */
function renderSpine(stage) {
  const claims = [...Object.keys(CLAIMS)];
  const papers = [...new Set(G.edges.map((e) => e.paper))];
  const rowH = 74, padTop = 54, W = 1040;
  const H = padTop + Math.max(claims.length, papers.length) * rowH + 20;
  const xL = 300, xR = 760;
  const yC = {}, yP = {};
  claims.forEach((c, i) => (yC[c] = padTop + i * rowH));
  // order papers to reduce crossings: by mean y of the claims that cite them
  papers.sort((a, b) => meanClaimY(a, yC) - meanClaimY(b, yC));
  papers.forEach((p, i) => (yP[p] = padTop + i * rowH));

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Evidence map (spine)" });
  const head = el("g");
  head.appendChild(text(xL - 150, 28, "Claims (the spine)", "col-head"));
  head.appendChild(text(xR + 22, 28, "Cited papers", "col-head"));
  svg.appendChild(head);

  const eLayer = el("g");
  for (const e of G.edges) {
    const y1 = yC[e.claim], y2 = yP[e.paper];
    const m = mainEdge(e);
    eLayer.appendChild(el("path", { class: "edge" + (m.ghost ? " ghost" : ""), "data-id": e.id,
      d: `M${xL},${y1} C${(xL + xR) / 2},${y1} ${(xL + xR) / 2},${y2} ${xR},${y2}`,
      stroke: m.stroke, "stroke-width": m.width, "stroke-dasharray": m.dash }));
    if (showAIStrand(e)) {
      const [ox, oy] = perp(xL, y1, xR, y2, 6);
      eLayer.appendChild(el("path", { class: "edge ai", "data-id": e.id,
        d: `M${xL + ox},${y1 + oy} C${(xL + xR) / 2 + ox},${y1 + oy} ${(xL + xR) / 2 + ox},${y2 + oy} ${xR + ox},${y2 + oy}`,
        stroke: hueVarFor(aiHueClass(e.ai), "--hue"), "stroke-width": 2 }));
    }
  }
  svg.appendChild(eLayer);

  const nLayer = el("g");
  for (const c of claims) nLayer.appendChild(spineNode(stage, c, xL, yC[c], "claim", "left"));
  for (const p of papers) nLayer.appendChild(spineNode(stage, p, xR, yP[p], "paper", "right"));
  svg.appendChild(nLayer);
  stage.querySelector(".host").appendChild(svg);
}
function meanClaimY(paper, yC) {
  const ys = G.edges.filter((e) => e.paper === paper).map((e) => yC[e.claim]);
  return ys.reduce((a, b) => a + b, 0) / ys.length;
}
function spineNode(stage, id, x, y, kind, side) {
  const node = G.nodes.get(id);
  const retr = kind === "paper" && node.retracted;
  const g = el("g", { class: "node " + kind + (retr ? " retracted" : ""), transform: `translate(${x},${y})` }, [
    el("circle", { class: "halo", r: 12 }),
    el("circle", { class: "disc", r: 6.5 }),
  ]);
  if (retr) g.appendChild(el("circle", { class: "retr-ring", r: 9.5 }));
  const anchor = side === "left" ? "end" : "start", dx = side === "left" ? -14 : 14;
  const title = (kind === "claim" ? clampText(node.text, 40) : node.short) + (retr ? " ⊘" : "");
  const sub = kind === "claim" ? node.loc : node.venue;
  const tt = text(dx, -1, title); tt.setAttribute("text-anchor", anchor); g.appendChild(tt);
  const ss = text(dx, 12, sub, "sub"); ss.setAttribute("text-anchor", anchor); g.appendChild(ss);
  wireNode(stage, g, id);
  return g;
}
function text(x, y, s, cls) { const t = el("text", { x, y }); if (cls) t.setAttribute("class", cls); t.textContent = s; return t; }

/* ========================================================================
   Variant 3 — Orbit: one claim centred, its papers as an ego-network,
   grouped into verdict sectors, radius ~ support strength
   ===================================================================== */
function renderOrbit(stage, focus) {
  focus = focus || state.orbitFocus || "c1"; state.orbitFocus = focus;
  const W = 1040, H = 620, cx = W / 2, cy = H / 2 + 6;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Evidence map (orbit)" });

  // faint guide rings
  const rings = el("g");
  [90, 165, 235].forEach((r) => rings.appendChild(el("circle", { cx, cy, r, fill: "none",
    stroke: "var(--zs-line)", "stroke-width": 1 })));
  svg.appendChild(rings);

  const es = G.edges.filter((e) => e.claim === focus);
  // sector per verdict; radius by support polarity (+ near, − far, unrated outer)
  const sectors = { accept: -Math.PI * 0.45, caution: -Math.PI * 0.05, review: Math.PI * 0.35, reject: Math.PI * 0.75, unrated: Math.PI * 1.15 };
  const rByPol = { "+": 120, "?": 180, "−": 230, "·": 235 };
  const byV = {}; es.forEach((e) => (byV[e.decision] = byV[e.decision] || []).push(e));

  const eLayer = el("g"), nLayer = el("g");
  for (const dec in byV) {
    const grp = byV[dec]; const base = sectors[dec];
    grp.forEach((e, i) => {
      const spread = (i - (grp.length - 1) / 2) * 0.36;
      const ang = base + spread;
      const pol = SUPPORT[e.human == null ? "null" : e.human].pol;
      const r = rByPol[pol] || 200;
      const x = cx + Math.cos(ang) * r, y = cy + Math.sin(ang) * r;
      const m = mainEdge(e);
      eLayer.appendChild(el("path", { class: "edge on" + (m.ghost ? " ghost" : ""), "data-id": e.id,
        d: `M${cx},${cy} L${x},${y}`, stroke: m.stroke, "stroke-width": m.width, "stroke-dasharray": m.dash }));
      if (showAIStrand(e)) {
        const [ox, oy] = perp(cx, cy, x, y, 6);
        eLayer.appendChild(el("path", { class: "edge ai on", "data-id": e.id,
          d: `M${cx + ox},${cy + oy} L${x + ox},${y + oy}`,
          stroke: hueVarFor(aiHueClass(e.ai), "--hue"), "stroke-width": 2 }));
      }
      drawNodeDisc(nLayer, stage, e.paper, x, y);
    });
  }
  // centre claim
  drawNodeDisc(nLayer, stage, focus, cx, cy);
  svg.appendChild(eLayer); svg.appendChild(nLayer);
  stage.querySelector(".host").appendChild(svg);

  // claim picker rail
  const rail = document.getElementById("orbitRail");
  rail.innerHTML = "";
  for (const c of Object.keys(CLAIMS)) {
    const b = document.createElement("button");
    b.className = "chip-btn"; b.textContent = "C" + c.slice(1) + " · " + clampText(CLAIMS[c].text, 34);
    if (c === focus) b.setAttribute("aria-pressed", "true"), b.style.borderColor = "var(--zs-brand)";
    b.onclick = () => { state.orbitFocus = c; draw(); };
    rail.appendChild(b);
  }
}

/* ---------------- shell ---------------- */
const G = buildGraph();

const AI_BANNER = {
  overlay: "Overlay · the faint 25% strand beside your edge is the AI's second opinion — shown only for links you've already judged. Your decision is the solid edge.",
  view: "AI view · edges are coloured by the AI's rating, revealed only for links you've already judged. Grey dashed = awaiting your judgement (AI stays blinded).",
};

function draw() {
  const stage = document.getElementById("stage");
  clearSel(stage);
  stage.querySelector(".host").innerHTML = "";
  document.getElementById("orbitRail").style.display = state.variant === "orbit" ? "flex" : "none";
  const banner = document.getElementById("aiBanner");
  banner.hidden = state.aiMode === "off";
  banner.textContent = AI_BANNER[state.aiMode] || "";
  stage.classList.toggle("ai-view", state.aiMode === "view");
  if (state.variant === "constellation") renderConstellation(stage);
  else if (state.variant === "spine") renderSpine(stage);
  else renderOrbit(stage);
}

function boot() {
  // legend
  const leg = document.getElementById("legend");
  leg.innerHTML = VERDICT_ORDER.map((k) => {
    const v = VERDICT[k], cls = HUE[v.key];
    const c = hueVarFor(cls, "--hue");
    return `<span class="legchip"><span class="dot" style="border-color:${c};background:${hueVarFor(cls, "--hue-bg")}"></span>
      <code style="color:${hueVarFor(cls, "--hue-tx")}">[${v.code || "&nbsp;&nbsp;"}]</code> ${v.label}</span>`;
  }).join("") + `<span class="sep"></span><span class="meta">● claim &nbsp; ○ paper &nbsp; <b class="retr-mark">⊘</b> retracted &nbsp; · · · unrated &nbsp; ${G.edges.length} links · read-only</span>`;

  document.querySelectorAll("#switch button").forEach((b) => {
    b.onclick = () => {
      state.variant = b.dataset.v;
      document.querySelectorAll("#switch button").forEach((x) => x.setAttribute("aria-pressed", x === b));
      draw();
    };
  });
  document.querySelectorAll("#aiModes button").forEach((b) => {
    b.onclick = () => {
      state.aiMode = b.dataset.m;
      document.querySelectorAll("#aiModes button").forEach((x) => x.setAttribute("aria-pressed", x === b));
      draw();
    };
  });
  document.getElementById("theme").onclick = () => {
    const dark = document.documentElement.classList.toggle("zs-dark");
    document.getElementById("theme").textContent = dark ? "◑ Dark" : "◐ Light";
    draw();
  };
  document.getElementById("stage").addEventListener("click", () => clearSel(document.getElementById("stage")));
  draw();
}
document.addEventListener("DOMContentLoaded", boot);
