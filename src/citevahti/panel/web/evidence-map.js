/* Atlas evidence-map surface — the local claim<->evidence graph (Spine layout) plus a
 * publication-figure export. Read-only: it renders what GET /api/evidence-map returns
 * (the engine already applies the blinding rule, so an unjudged link arrives with its
 * AI value "hidden"). Nodes = claims + deduped cited papers; edges are coloured AND
 * dash-styled by the decision so the picture survives greyscale. The interactive map is
 * theme-aware (design tokens); the exported figure is a standalone SVG with literal
 * colours so the downloaded file renders anywhere. No external libraries — plain SVG.
 *
 * Globals kept to the entry points (renderEvidenceMapInto) + the em* action helpers;
 * everything else is EM_/em-prefixed to avoid clashing in the shared script scope. */

const SVGNS_EM = "http://www.w3.org/2000/svg";

/* verdict → hue class (theme token) + literal hue/mono + dash (greyscale-safe) + width */
const EM_VERDICT = {
  accept:  { code: "oo", label: "Accept",       cls: "em-supported", hue: "#C98A00", mono: "#111111", dash: "",      w: 2.4 },
  caution: { code: "o ", label: "Caution",      cls: "em-partial",   hue: "#1E9E8A", mono: "#555555", dash: "",      w: 1.6 },
  review:  { code: "r ", label: "Needs review", cls: "em-revise",    hue: "#8B6FC9", mono: "#333333", dash: "6 3",   w: 1.9 },
  reject:  { code: "d ", label: "Reject",       cls: "em-reject",    hue: "#C24D7E", mono: "#111111", dash: "1.5 3", w: 1.9 },
  unrated: { code: "  ", label: "Unrated",      cls: "em-pending",   hue: "#8478A6", mono: "#9A9AA4", dash: "2 4",   w: 1.2 },
};
const EM_ORDER = ["accept", "caution", "review", "reject", "unrated"];
/* AI support value → the verdict-equivalent hue family (AI-view mode) */
const EM_SUPPORT_VERDICT = { directly_supports: "accept", partially_supports: "caution",
  indirectly_supports: "caution", unclear: "review", does_not_support: "review", contradicts: "reject" };

const emState = { mode: "adjudicated", sel: null, data: null };

const emClamp = (s, n) => (!s ? "" : s.length > n ? s.slice(0, n - 1) + "…" : s);
function emEl(tag, attrs, kids) {
  const n = document.createElementNS(SVGNS_EM, tag);
  for (const k in (attrs || {})) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
  for (const c of (kids || [])) n.appendChild(c);
  return n;
}
const emSupLabel = (v) => (v == null ? "Not yet rated" : (typeof SUP_LABEL !== "undefined" && SUP_LABEL[v]) || v);
const emPaperShort = (p) => emClamp(p.title || (p.pmid ? "PMID " + p.pmid : "Untitled"), 30);
const emPaperVenue = (p) => [p.journal, p.year].filter(Boolean).join(" ") || (p.pmid ? "PMID " + p.pmid : "");
const emJudged = (e) => e.decision !== "unrated";
const emAiHidden = (e) => e.ai_support == null || e.ai_support === "hidden";
/* the verdict that drives an edge in the current mode. AI view recolours by the AI
 * rating, but only where the human has judged AND the AI actually opined; an unjudged
 * link (AI blinded) or a judged link the AI abstained on stays a neutral ghost. */
function emVerdict(e) {
  if (emState.mode === "ai") {
    if (!emJudged(e) || emAiHidden(e)) return "unrated";
    return EM_SUPPORT_VERDICT[e.ai_support] || "review";
  }
  return e.decision;
}
/* a link drawn as a neutral grey "no AI signal" ghost (AI-view only) */
const emGhost = (e) => emState.mode === "ai" && (!emJudged(e) || emAiHidden(e));

/* ---------- data helpers ---------- */
function emIndex() {
  const d = emState.data;
  const claims = d.claims, claimById = Object.fromEntries(claims.map((c) => [c.id, c]));
  const paperById = Object.fromEntries(d.papers.map((p) => [p.id, p]));
  return { claims, papers: d.papers, edges: d.edges, claimById, paperById };
}
function emEdgesFor(id) { return emState.data.edges.filter((e) => e.claim_id === id || e.paper_id === id); }

/* ============================ interactive Spine ============================ */
function emRenderMap() {
  const stage = document.getElementById("emStage"); if (!stage) return;
  const { claims, edges, paperById } = emIndex();
  const papers = [...new Set(edges.map((e) => e.paper_id))].map((id) => paperById[id]);
  if (!claims.length) {
    stage.innerHTML = `<div class="cv-empty"><div class="cv-empty-title">No claims yet</div>
      Extract claims from a manuscript, then link and rate the papers cited for them — the map fills in as you go.</div>`;
    return;
  }
  const W = 900, rowH = 44, top = 40;
  const yP = {}; papers.forEach((p, i) => (yP[p.id] = top + i * rowH));
  papers.sort((a, b) => emMeanClaimY(a.id, claims, top) - emMeanClaimY(b.id, claims, top));
  papers.forEach((p, i) => (yP[p.id] = top + i * rowH));
  const rows = Math.max(claims.length, papers.length);
  const H = top + (rows - 1) * rowH + 40;
  const bot = top + (papers.length - 1) * rowH;
  const yC = {}; claims.forEach((c, i) => (yC[c.id] = claims.length === 1 ? (top + bot) / 2 : top + (i * (bot - top)) / (claims.length - 1)));
  const xC = 300, xP = 600;

  const svg = emEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "em-svg", role: "img", "aria-label": "Local claim–evidence map" });
  svg.appendChild(emText(xC - 4, top - 18, "CLAIMS", "em-hdr", "end"));
  svg.appendChild(emText(xP + 4, top - 18, "CITED PAPERS", "em-hdr", "start"));

  const eLayer = emEl("g"), nLayer = emEl("g");
  for (const e of edges) {
    const k = emVerdict(e), V = EM_VERDICT[k], ghost = emGhost(e);
    const y1 = yC[e.claim_id], y2 = yP[e.paper_id];
    if (y1 == null || y2 == null) continue;
    eLayer.appendChild(emEl("path", { class: "em-edge " + (ghost ? "em-ghost" : V.cls),
      "data-em-edge": e.claim_id + "|" + e.paper_id,
      d: `M${xC},${y1} C${(xC + xP) / 2},${y1} ${(xC + xP) / 2},${y2} ${xP},${y2}`,
      "stroke-width": ghost ? 1.1 : V.w, "stroke-dasharray": ghost ? "2 4" : V.dash }));
  }
  claims.forEach((c, i) => emSpineNode(nLayer, c.id, "claim", xC, yC[c.id], "C" + (i + 1), emClamp(c.text, 42), c.location || ""));
  for (const p of papers) emSpineNode(nLayer, p.id, "paper", xP, yP[p.id], emPaperShort(p), null, emPaperVenue(p), p.retracted);
  svg.appendChild(eLayer); svg.appendChild(nLayer);

  stage.classList.toggle("has-sel", !!emState.sel);
  stage.innerHTML = ""; stage.appendChild(svg);
  const fly = document.createElement("div"); fly.className = "em-detail"; fly.id = "emDetail"; stage.appendChild(fly);
  svg.addEventListener("click", emStageClick);
  if (emState.sel) emApplySel(emState.sel);
}
function emMeanClaimY(pid, claims, top) {
  const idx = Object.fromEntries(claims.map((c, i) => [c.id, i]));
  const ys = emState.data.edges.filter((e) => e.paper_id === pid).map((e) => idx[e.claim_id]).filter((v) => v != null);
  return ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : 0;
}
function emSpineNode(layer, id, kind, x, y, label, sub1, sub2, retr) {
  const side = kind === "claim" ? "left" : "right";
  const g = emEl("g", { class: "em-node em-" + kind + (retr ? " em-retracted" : ""), "data-em-id": id, transform: `translate(${x},${y})` }, [
    emEl("circle", { class: "em-halo", r: 12 }), emEl("circle", { class: "em-disc", r: 6.5 }),
  ]);
  if (retr) g.appendChild(emEl("circle", { class: "em-retr-ring", r: 9.5 }));
  const anchor = side === "left" ? "end" : "start", dx = side === "left" ? -14 : 14;
  const t = emText(dx, sub2 || sub1 ? -1 : 4, (retr ? "⊘ " : "") + label, "em-nlabel", anchor);
  g.appendChild(t);
  if (sub1) { const s = emText(dx, 12, sub1, "em-nsub", anchor); g.appendChild(s); }
  if (sub2) { const s = emText(dx, 12, sub2, "em-nsub", anchor); g.appendChild(s); }
  layer.appendChild(g);
}
function emText(x, y, s, cls, anchor) { const t = emEl("text", { x, y, class: cls, "text-anchor": anchor }); t.textContent = s; return t; }

/* ---------- selection + inspect ---------- */
function emStageClick(ev) {
  const node = ev.target.closest("[data-em-id]");
  if (!node) { emClearSel(); return; }
  const id = node.getAttribute("data-em-id");
  emState.sel === id ? emClearSel() : emApplySel(id);
}
function emClearSel() {
  emState.sel = null;
  const stage = document.getElementById("emStage"); if (!stage) return;
  stage.classList.remove("has-sel");
  stage.querySelectorAll(".em-node").forEach((n) => n.classList.remove("sel", "adj"));
  stage.querySelectorAll(".em-edge").forEach((e) => e.classList.remove("on"));
  const d = document.getElementById("emDetail"); if (d) d.classList.remove("show");
}
function emApplySel(id) {
  emState.sel = id;
  const stage = document.getElementById("emStage"); if (!stage) return;
  stage.classList.add("has-sel");
  const es = emEdgesFor(id), adj = new Set();
  es.forEach((e) => { adj.add(e.claim_id); adj.add(e.paper_id); });
  stage.querySelectorAll(".em-node").forEach((n) => {
    const nid = n.getAttribute("data-em-id");
    n.classList.toggle("sel", nid === id); n.classList.toggle("adj", nid !== id && adj.has(nid));
  });
  stage.querySelectorAll(".em-edge").forEach((x) => {
    const key = x.getAttribute("data-em-edge");
    x.classList.toggle("on", es.some((e) => e.claim_id + "|" + e.paper_id === key));
  });
  emShowDetail(id);
}
function emShowDetail(id) {
  const d = document.getElementById("emDetail"); if (!d) return;
  const { claimById, paperById } = emIndex();
  const es = emEdgesFor(id), isClaim = !!claimById[id];
  let head, rows;
  if (isClaim) {
    const c = claimById[id];
    head = `<div class="em-kind">Claim · ${esc(claimTypeLabel(c.type))}${c.location ? " · " + esc(c.location) : ""}</div>
      <h3>${esc(c.text)}</h3><div class="em-meta">${es.length} cited paper(s) tested against this claim</div>`;
    rows = es.map((e) => emEdgeRow(emPaperShort(paperById[e.paper_id]) + (paperById[e.paper_id].retracted ? " ⊘" : ""), emPaperVenue(paperById[e.paper_id]), e)).join("");
  } else {
    const p = paperById[id];
    head = `<div class="em-kind">Paper${p.journal ? " · " + esc(p.journal) : ""}${p.year ? " " + p.year : ""}</div>
      <h3>${esc(p.title || "Untitled")}</h3>
      ${p.retracted ? `<div class="em-retr-flag">⊘ Retracted — flagged by the retraction scan, independent of any rating</div>` : ""}
      <div class="em-meta">${p.pmid ? "PMID " + esc(p.pmid) + " · " : ""}cited for ${es.length} claim(s)</div>`;
    rows = es.map((e) => emEdgeRow(emClamp(claimById[e.claim_id].text, 44), claimById[e.claim_id].location || "", e)).join("");
  }
  d.innerHTML = `<button class="em-close" data-em-close="1" aria-label="Close">✕</button>${head}${rows}`;
  d.classList.add("show");
  const btn = d.querySelector("[data-em-close]"); if (btn) btn.onclick = emClearSel;
}
function emEdgeRow(title, sub, e) {
  const V = EM_VERDICT[e.decision];
  let ai;
  if (!emJudged(e)) ai = `<span class="em-ai muted">AI opinion hidden until you judge · blinded</span>`;
  else if (emAiHidden(e)) ai = `<span class="em-ai muted">AI abstained</span>`;
  else {
    const concurs = EM_SUPPORT_VERDICT[e.human_support] === EM_SUPPORT_VERDICT[e.ai_support];
    ai = `<span class="em-ai">AI: ${esc(emSupLabel(e.ai_support))} · <em class="${concurs ? "em-tag-ok" : "em-tag-warn"}">${concurs ? "AI concurs" : "AI differs"}</em></span>`;
  }
  return `<div class="em-edgerow"><div class="em-txt"><b>${esc(title)}</b>
    <span>${esc(sub)}${sub ? " · " : ""}you: ${esc(emSupLabel(e.human_support))}</span>${ai}</div>
    <span class="cv-badge ${V.cls === "em-supported" ? "is-supported" : V.cls === "em-partial" ? "is-partial" : V.cls === "em-revise" ? "is-revise" : V.cls === "em-reject" ? "is-reject" : "is-pending"}">[${V.code || "  "}] ${V.label}</span></div>`;
}

/* ============================ publication figure ============================ */
const EM_FIG = { W: 900, H: 650 };
const EM_WIDTHS = { single: 89, onehalf: 120, double: 183 };
function emFigurePalette(mono) {
  return mono
    ? { ink: "#111", muted: "#555", line: "#CBCBCB", claimFill: "#ECECEC", claimStroke: "#333", paperStroke: "#555", retr: "#111", accent: "#111" }
    : { ink: "#1A1A1F", muted: "#6B6B73", line: "#E2E2E7", claimFill: "#EFE7FC", claimStroke: "#6B4E9E", paperStroke: "#6B6B73", retr: "#C24D7E", accent: "#4B1778" };
}
const EM_FIG_STYLE = `text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}
.f-panel{font-size:20px;font-weight:800}.f-title{font-size:16px;font-weight:700}.f-sub{font-size:11px}
.f-hdr{font-size:10px;font-weight:700;letter-spacing:.06em}.f-node{font-size:11px;font-weight:700}
.f-gloss{font-size:10px;font-weight:400}.f-venue{font-size:9px}.f-code{font-size:9.5px;font-weight:700;font-family:ui-monospace,Menlo,monospace}
.f-n{font-size:9.5px;font-weight:600}.f-foot{font-size:9px}`;

/* builds the standalone publication SVG element (literal colours) */
function emBuildFigure(mono) {
  const P = emFigurePalette(mono), d = emState.data, { claimById, paperById } = emIndex();
  const claimsArr = d.claims, snapshot = (d.generated_at || "").slice(0, 10);
  const svg = emEl("svg", { viewBox: `0 0 ${EM_FIG.W} ${EM_FIG.H}`, role: "img", "aria-label": "Local claim–evidence map" });
  svg.appendChild(emEl("style", {}, [document.createTextNode(EM_FIG_STYLE)]));
  svg.appendChild(emEl("rect", { x: 0, y: 0, width: EM_FIG.W, height: EM_FIG.H, fill: "#FFFFFF" }));
  const T = (x, y, s, cls, fill, anchor) => { const t = emEl("text", { x, y, class: cls, fill, "text-anchor": anchor }); t.textContent = s; return t; };

  svg.appendChild(T(28, 34, "A", "f-panel", P.ink));
  svg.appendChild(T(60, 32, "Local claim–evidence map", "f-title", P.ink));
  svg.appendChild(T(60, 49, `Each asserted claim tested against its cited papers · ${emState.mode === "ai" ? "machine (AI) ratings" : "adjudicated human judgements"}${snapshot ? " · ledger snapshot " + snapshot : ""}`, "f-sub", P.muted));

  const claims = claimsArr.map((c) => c.id);
  const papers = [...new Set(d.edges.map((e) => e.paper_id))];
  const xC = 306, xP = 594, top = 104, rowH = 40;
  const idx = Object.fromEntries(claims.map((c, i) => [c, i]));
  const mean = (pid) => { const ys = d.edges.filter((e) => e.paper_id === pid).map((e) => idx[e.claim_id]); return ys.reduce((a, b) => a + b, 0) / (ys.length || 1); };
  papers.sort((a, b) => mean(a) - mean(b));
  const yP = {}; papers.forEach((p, i) => (yP[p] = top + i * rowH));
  const bot = top + (papers.length - 1) * rowH;
  const yC = {}; claims.forEach((c, i) => (yC[c] = claims.length === 1 ? (top + bot) / 2 : top + (i * (bot - top)) / (claims.length - 1)));

  svg.appendChild(T(xC - 4, top - 16, "CLAIMS", "f-hdr", P.muted, "end"));
  svg.appendChild(T(xP + 4, top - 16, "CITED PAPERS", "f-hdr", P.muted, "start"));
  for (const e of d.edges) {
    const k = emVerdict(e), V = EM_VERDICT[k], ghost = emGhost(e);
    const y1 = yC[e.claim_id], y2 = yP[e.paper_id]; if (y1 == null || y2 == null) continue;
    svg.appendChild(emEl("path", { d: `M${xC},${y1} C${(xC + xP) / 2},${y1} ${(xC + xP) / 2},${y2} ${xP},${y2}`,
      fill: "none", stroke: ghost ? P.muted : (mono ? V.mono : V.hue), "stroke-linecap": "round",
      "stroke-width": ghost ? 1.1 : V.w, "stroke-dasharray": ghost ? "2 4" : V.dash, opacity: ghost ? 0.6 : 1 }));
  }
  claims.forEach((c, i) => {
    const y = yC[c];
    svg.appendChild(emEl("circle", { cx: xC, cy: y, r: 6, fill: P.claimFill, stroke: P.claimStroke, "stroke-width": 2 }));
    const t = emEl("text", { x: xC - 14, y: y + 4, class: "f-node", fill: P.ink, "text-anchor": "end" });
    t.appendChild(emEl("tspan", { class: "f-node", fill: P.accent }, [document.createTextNode("C" + (i + 1))]));
    t.appendChild(emEl("tspan", { class: "f-gloss", fill: P.muted }, [document.createTextNode("  " + emClamp(claimById[c].text, 34))]));
    svg.appendChild(t);
  });
  for (const pid of papers) {
    const p = paperById[pid], y = yP[pid], retr = p.retracted;
    svg.appendChild(emEl("circle", { cx: xP, cy: y, r: 6, fill: "#FFFFFF", stroke: retr ? P.retr : P.paperStroke, "stroke-width": retr ? 2 : 1.5 }));
    if (retr) svg.appendChild(emEl("circle", { cx: xP, cy: y, r: 9, fill: "none", stroke: P.retr, "stroke-width": 1.2, "stroke-dasharray": "2 2" }));
    svg.appendChild(T(xP + 14, y - 1, (retr ? "⊘ " : "") + emPaperShort(p), "f-node", retr ? P.retr : P.ink, "start"));
    svg.appendChild(T(xP + 14, y + 11, emPaperVenue(p), "f-venue", P.muted, "start"));
  }
  const lgY = bot + 44;
  svg.appendChild(T(28, lgY - 16, "VERDICT", "f-hdr", P.muted, "start"));
  EM_ORDER.forEach((k, i) => {
    const V = EM_VERDICT[k], x = 28 + i * 172;
    svg.appendChild(emEl("path", { d: `M${x},${lgY} L${x + 26},${lgY}`, stroke: mono ? V.mono : V.hue, "stroke-width": V.w, "stroke-dasharray": V.dash, "stroke-linecap": "round" }));
    svg.appendChild(T(x + 33, lgY + 4, `[${V.code || "  "}]`, "f-code", P.ink, "start"));
    svg.appendChild(T(x + 62, lgY + 4, V.label, "f-sub", P.ink, "start"));
  });
  let ky = lgY + 26;
  svg.appendChild(T(28, ky, "⊘  Retracted source (retraction scan) — shown independent of any rating", "f-foot", P.retr, "start"));
  if (emState.mode === "ai") { ky += 14; svg.appendChild(T(28, ky, "Grey dashed — link awaiting human judgement; AI rating stays blinded until you judge it", "f-foot", P.muted, "start")); }
  svg.appendChild(T(28, EM_FIG.H - 46, `N = ${d.counts.claims} claims · ${d.counts.papers} cited papers · ${d.counts.links} tested links`, "f-n", P.ink, "start"));
  const foot1 = emState.mode === "ai"
    ? "This figure displays the machine (AI) second-opinion ratings, shown only where a human judgement exists."
    : "This figure displays adjudicated human judgements recorded in the local ledger.";
  svg.appendChild(T(28, EM_FIG.H - 30, foot1, "f-foot", P.muted, "start"));
  svg.appendChild(T(28, EM_FIG.H - 18, "It does not assert that any claim is true; it shows which cited papers were tested, and the verdict reached.", "f-foot", P.muted, "start"));
  return svg;
}
function emFigureMarkup(mono) {
  const svg = emBuildFigure(mono), mm = EM_WIDTHS[emState.figWidth || "double"];
  svg.setAttribute("xmlns", SVGNS_EM);
  svg.setAttribute("width", mm + "mm");
  svg.setAttribute("height", ((mm * EM_FIG.H) / EM_FIG.W).toFixed(1) + "mm");
  return '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(svg);
}
function emFigureCaption() {
  const d = emState.data;
  const key = d.claims.map((c, i) => `C${i + 1}, ${c.text}`).join("; ");
  const modeLine = emState.mode === "ai"
    ? "Links are coloured and line-styled by the machine (AI) support rating, revealed only where a human judgement exists; links awaiting human judgement are shown as grey dashed lines."
    : "Each link is coloured and line-styled by the adjudicated human verdict (see legend).";
  return `Figure 1. Local claim–evidence map. Bipartite plot of each asserted claim (left, C1–C${d.claims.length}) `
    + `against the cited papers tested to support it (right). ${modeLine} ⊘ marks a retracted source (retraction scan), `
    + `shown independent of any rating. Colour and dash pattern both encode the verdict so the figure is legible in `
    + `greyscale and for colour-vision-deficient readers. The figure displays adjudicated human judgements recorded in `
    + `the local ledger and does not assert that any claim is true. N = ${d.counts.claims} claims, ${d.counts.papers} `
    + `cited papers, ${d.counts.links} tested links.${d.generated_at ? " Ledger snapshot " + d.generated_at.slice(0, 10) + "." : ""} Claim key: ${key}.`;
}

/* ---------- surface shell + controls ---------- */
function renderEvidenceMapInto(host) {
  host.innerHTML = loadingHTML("Loading evidence map…", { card: true });
  api("GET", "/api/evidence-map").then((data) => {
    emState.data = data; emState.sel = null;
    host.innerHTML = `<div class="em-wrap">
      <div class="em-bar">
        <div class="seg-ctl em-modes" id="emModes" role="group" aria-label="Mapping">
          <button class="chip-btn" data-act="em-mode" data-mode="adjudicated" aria-pressed="true">Your decisions</button>
          <button class="chip-btn" data-act="em-mode" data-mode="ai" aria-pressed="false">AI view</button>
        </div>
        <span class="note em-count">${data.counts.claims} claims · ${data.counts.papers} papers · ${data.counts.links} links</span>
        <span class="cv-wrap" style="flex:1"></span>
        <button class="chip-btn" data-act="em-figure">🖼 Export figure</button>
      </div>
      <div class="em-stage" id="emStage"></div>
      <p class="note">Click a claim or paper to inspect its links. Colour <b>and</b> dash both encode the verdict, so it reads in greyscale. In <b>AI view</b> the AI rating shows only after you've judged a link; unjudged links stay grey (blinded). <b>Export figure</b> builds a publication-ready SVG.</p>
    </div>`;
    emRenderMap();
  }).catch((e) => { host.innerHTML = `<div class="cv-error">${esc(e.message)}</div>`; });
}
function emSetMode(mode) {
  emState.mode = mode; emState.sel = null;
  document.querySelectorAll("#emModes [data-em-mode]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.emMode === mode)));
  emRenderMap();
}
/* export modal: width + colour/greyscale + download SVG / print / copy caption */
function emOpenFigure() {
  emState.figWidth = emState.figWidth || "double"; emState.figMono = emState.figMono || false;
  const box = modalShell("emFigModal");
  const draw = () => {
    const holder = box.querySelector("#emFigHolder"); holder.innerHTML = "";
    holder.appendChild(emBuildFigure(emState.figMono));
    box.querySelector("#emFigCap").textContent = emFigureCaption();
  };
  box.innerHTML = `<div class="modal-card em-figcard">
    <div class="modal-head"><h2 class="modal-title">Publication figure</h2><button class="chip-btn" data-em-close="1" aria-label="Close">✕</button></div>
    <div class="em-figbar">
      <div class="seg-ctl" id="emFigWidth"><button class="chip-btn" data-emw="single">89mm</button><button class="chip-btn" data-emw="onehalf">120mm</button><button class="chip-btn" data-emw="double">183mm</button></div>
      <div class="seg-ctl" id="emFigInk"><button class="chip-btn" data-emi="colour">Colour</button><button class="chip-btn" data-emi="mono">Greyscale</button></div>
      <span class="cv-wrap" style="flex:1"></span>
      <button class="btn primary" data-em-dl="1">⬇ SVG</button>
      <button class="btn ghost" data-em-print="1">🖶 Print / PDF</button>
    </div>
    <div class="em-figholder" id="emFigHolder"></div>
    <div class="em-capwrap"><div class="lbl">Caption — copy for submission</div>
      <button class="btn ghost" data-em-cap="1">Copy caption</button><p class="note em-cap" id="emFigCap"></p></div>
    <div class="modal-foot"><button class="btn primary" data-em-close="1">Done</button></div></div>`;
  const syncSeg = () => {
    box.querySelectorAll("#emFigWidth [data-emw]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.emw === emState.figWidth)));
    box.querySelectorAll("#emFigInk [data-emi]").forEach((b) => b.setAttribute("aria-pressed", String((b.dataset.emi === "mono") === emState.figMono)));
  };
  box.querySelectorAll("#emFigWidth [data-emw]").forEach((b) => b.onclick = () => { emState.figWidth = b.dataset.emw; syncSeg(); draw(); });
  box.querySelectorAll("#emFigInk [data-emi]").forEach((b) => b.onclick = () => { emState.figMono = b.dataset.emi === "mono"; syncSeg(); draw(); });
  box.querySelector("[data-em-dl]").onclick = emDownloadFigure;
  box.querySelector("[data-em-print]").onclick = emPrintFigure;
  box.querySelector("[data-em-cap]").onclick = () => copyText(emFigureCaption());
  box.querySelectorAll("[data-em-close]").forEach((b) => b.onclick = () => leaveModal("emFigModal"));
  syncSeg(); draw();
}
function emDownloadFigure() {
  const blob = new Blob([emFigureMarkup(emState.figMono)], { type: "image/svg+xml;charset=utf-8" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
  a.download = `evidence-map-${emState.mode}.svg`; document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(a.href);
}
function emPrintFigure() {
  const w = window.open("", "_blank"); if (!w) { notify("Allow pop-ups to print the figure.", { kind: "error" }); return; }
  w.document.write(`<!doctype html><title>Evidence-map figure</title><style>@page{margin:12mm}body{margin:0}</style>${emFigureMarkup(emState.figMono)}`);
  w.document.close(); w.focus(); setTimeout(() => w.print(), 250);
}

/* register the surface actions (mode toggle + figure export) with the delegated
 * click dispatcher; node clicks are handled by a listener on the SVG itself. */
if (typeof registerActions === "function") registerActions({
  "em-mode": (el) => emSetMode(el.dataset.mode),
  "em-figure": () => emOpenFigure(),
});
