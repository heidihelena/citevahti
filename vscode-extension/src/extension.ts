import * as vscode from "vscode";
import { execFile } from "child_process";
import { randomBytes } from "crypto";

// The claim states (ADR-0002 + untestable), mapped to the CiteVahti palette.
// Editor highlights: yellow = usable evidence, lilac = human action, no green/red.
const STATE = {
  accepted:          { code: "oo", label: "Accepted",                bg: "rgba(201,138,0,0.18)",  ruler: "#C98A00" },
  needs_support:     { code: "o",  label: "No accepted reference yet", bg: "rgba(30,158,138,0.18)", ruler: "#1E9E8A" },
  review_needed:     { code: "r",  label: "Needs a second look",      bg: "rgba(139,111,201,0.22)", ruler: "#8B6FC9" },
  decision_recorded: { code: "d",  label: "Reviewed — not cited",     bg: "rgba(194,77,126,0.18)", ruler: "#C24D7E" },
  untestable:        { code: "u",  label: "Out of indexed scope",     bg: "rgba(91,85,112,0.16)",  ruler: "#5B5570" },
} as const;
type StateKey = keyof typeof STATE;

// The human's keystroke actions on a candidate -> a final decision (the human is
// the decider; the extension drives the CLI, never the agent surface). The label/cls
// are local styling; the verdict CODES and DECISION strings are the engine's vocabulary
// and are refreshed from `citevahti vocabulary` at activation (verdictDecisions) so this
// map can't silently drift from schemas/decision.py. The literals here are the fallback
// when the CLI vocabulary can't be read.
const ACTIONS = {
  oo: { decision: "accept",               label: "Accept",  cls: "accepted" },
  o:  { decision: "accepted_with_caution", label: "Caution", cls: "needs_support" },
  r:  { decision: "needs_second_review",   label: "Review",  cls: "review_needed" },
  d:  { decision: "reject",                label: "Reject",  cls: "decision_recorded" },
} as const;

// code -> decision, sourced from the engine at activation (see loadVocabulary).
const verdictDecisions: Record<string, string> =
  Object.fromEntries(Object.entries(ACTIONS).map(([k, v]) => [k, v.decision]));

function verdictDecision(code: keyof typeof ACTIONS): string {
  return verdictDecisions[code] ?? ACTIONS[code].decision;
}

// Pull the verdict vocabulary from the engine so the extension renders the same
// decisions the ledger accepts. Best-effort: on any failure we keep the fallback map.
async function loadVocabulary(): Promise<void> {
  try {
    const { code, stdout } = await runCli(["vocabulary"]);
    if (code !== 0) return;
    const vocab = JSON.parse(stdout) as { verdicts?: { code: string; decision: string }[] };
    for (const v of vocab.verdicts ?? []) {
      if (v.code && v.decision) verdictDecisions[v.code] = v.decision;
      if (v.code && !(v.code in ACTIONS)) {
        console.warn(`CiteVahti: engine verdict "${v.code}" has no UI button — extension may be out of date.`);
      }
    }
  } catch { /* keep the built-in fallback */ }
}

// The controlled blind support vocabulary (schemas/claim_support.py SUPPORT_VALUES).
// The human records one of these FIRST — before any decision and before the AI's
// rating is unblinded. Digit keys 1–6 mirror this order for keyboard raters.
const SUPPORT_VALUES = [
  ["directly_supports", "Directly supports"],
  ["partially_supports", "Partially"],
  ["indirectly_supports", "Indirectly"],
  ["does_not_support", "Does not support"],
  ["contradicts", "Contradicts"],
  ["unclear", "Unclear"],
] as const;

interface FitScores {
  population_fit?: number | null; intervention_fit?: number | null;
  outcome_fit?: number | null; claim_fit?: number | null;
}
interface Evidence {
  candidate_id: string; decision_id?: string | null; rating_id?: string | null;
  pmid?: string; doi?: string; title?: string;
  human_support?: string | null; ai_support?: string | null; final_decision?: string | null;
  fit?: FitScores | null; fit_total?: number | null; excerpt?: string | null;
}
interface ReportRow {
  claim_id: string; claim_text: string; manuscript_location?: string;
  state: StateKey; code: string; candidate_count: number; accepted_count: number;
  evidence: Evidence[];
  proposed_revision?: string | null; proposed_revision_by?: string | null;
}
interface Report { total: number; counts: Record<string, number>; rows: ReportRow[]; }

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

const decoTypes: Record<StateKey, vscode.TextEditorDecorationType> = Object.fromEntries(
  (Object.keys(STATE) as StateKey[]).map((s) => [s, vscode.window.createTextEditorDecorationType({
    backgroundColor: STATE[s].bg,
    overviewRulerColor: STATE[s].ruler,
    overviewRulerLane: vscode.OverviewRulerLane.Right,
    borderRadius: "3px",
    rangeBehavior: vscode.DecorationRangeBehavior.ClosedClosed,
  })])
) as Record<StateKey, vscode.TextEditorDecorationType>;

function cliPath(): string {
  return vscode.workspace.getConfiguration("citevahti").get<string>("cliPath") || "citevahti";
}
function projectRoot(): string {
  const cfg = vscode.workspace.getConfiguration("citevahti").get<string>("root");
  if (cfg) return cfg;
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? ".";
}

function runCli(args: string[], env?: Record<string, string>): Promise<{ code: number; stdout: string; stderr: string }> {
  // `env` passes secrets to the child WITHOUT putting them on argv (no process-list leak).
  const opts: any = { maxBuffer: 8 << 20, encoding: "utf8" };
  if (env) opts.env = { ...process.env, ...env };
  return new Promise((resolve) => {
    execFile(cliPath(), ["--root", projectRoot(), ...args], opts,
      (err, stdout, stderr) =>
        resolve({ code: err && typeof (err as any).code === "number" ? (err as any).code : (err ? 1 : 0),
                  stdout: String(stdout ?? ""), stderr: String(stderr ?? "") }));
  });
}

// Guided one-paste Zotero connection (ADR-0005): open the pre-filled key page,
// take the paste, validate + store via the CLI. The key goes to the child via env,
// never argv, never logs, never settings.
async function connectZotero() {
  const base = "https://www.zotero.org/settings/keys/new?name=CiteVahti&library_access=1&notes_access=1&write_access=1";
  const go = await vscode.window.showInformationMessage(
    "Connect Zotero: I'll open the key page (name + write permission pre-filled). " +
    "Click “Save Key”, copy the key, then paste it back here. Do you write to a shared/group library?",
    "My library only", "Include shared/group");
  if (go !== "My library only" && go !== "Include shared/group") return;
  const group = go === "Include shared/group";
  const url = group ? base + "&all_groups=write" : base;
  await vscode.env.openExternal(vscode.Uri.parse(url));
  const key = await vscode.window.showInputBox({
    prompt: "Paste your Zotero key (stored only in your OS keychain)",
    password: true, ignoreFocusOut: true, placeHolder: "the key shown on the Zotero page",
  });
  if (!key || !key.trim()) return;
  const { code, stdout, stderr } = await runCli(
    ["connect-zotero", "--no-open"], { CITEVAHTI_ZOTERO_WRITE_KEY: key.trim() });
  if (code === 0) {
    const personalNo = /personal library write\s*:\s*NO/i.test(stdout);
    const groupNote = group ? " (confirm the group was granted write on the page)" : "";
    if (personalNo) {
      vscode.window.showWarningMessage("CiteVahti: connected, but the key has NO personal-library write. Re-connect and tick write access.");
    } else {
      vscode.window.showInformationMessage(`CiteVahti: ✓ Zotero connected — write-back is ready.${groupNote}`);
    }
  } else {
    vscode.window.showErrorMessage(`CiteVahti: ${(stderr || stdout || "could not connect to Zotero").trim().split("\n")[0]}`);
  }
}

async function runReport(): Promise<Report> {
  const { stdout } = await runCli(["claim-report", "--json"]);
  return JSON.parse(stdout) as Report;   // exits non-zero when claims need attention; that's fine
}

// Highlight every occurrence of each claim in the active document, by state.
function decorate(report: Report) {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return;
  const text = editor.document.getText();
  const ranges: Record<StateKey, vscode.DecorationOptions[]> =
    { accepted: [], needs_support: [], review_needed: [], decision_recorded: [], untestable: [] };
  for (const row of report.rows) {
    const needle = row.claim_text.trim();
    if (!needle) continue;
    let i = text.indexOf(needle);
    while (i >= 0) {
      const range = new vscode.Range(editor.document.positionAt(i), editor.document.positionAt(i + needle.length));
      ranges[row.state].push({
        range,
        hoverMessage: `**[${STATE[row.state].code}] ${STATE[row.state].label}** — ` +
          `${row.accepted_count}/${row.candidate_count} accepted\n\n${row.claim_text}`,
      });
      i = text.indexOf(needle, i + needle.length);
    }
  }
  for (const s of Object.keys(STATE) as StateKey[]) editor.setDecorations(decoTypes[s], ranges[s]);
}

// PICO + claim fit subscores (0 poor / 1 partial / 2 good) → ✗ / ~ / ✓ chips.
const FIT_LABELS: [keyof FitScores, string][] = [
  ["population_fit", "Population"], ["intervention_fit", "Intervention"],
  ["outcome_fit", "Outcome"], ["claim_fit", "Claim fit"],
];
function fitGrade(n: number): string { return n >= 7 ? "Strong" : n >= 4 ? "Moderate" : n >= 1 ? "Weak" : "None"; }
function fitHtml(e: Evidence): string {
  if (!e.fit || e.fit_total == null) return "";   // blinded / not yet rated by the human
  const chips = FIT_LABELS.map(([k, label]) => {
    const v = e.fit?.[k];
    const cls = v == null ? "no" : v >= 2 ? "ok" : v >= 1 ? "partial" : "no";
    const sym = v == null ? "·" : v >= 2 ? "✓" : v >= 1 ? "~" : "✗";
    return `<span class="check ${cls}">${escapeHtml(label)} ${sym}</span>`;
  }).join("");
  return `<div class="checks">${chips}</div>` +
    `<div class="fit">Citation fit: <b>${fitGrade(e.fit_total)} (${e.fit_total}/8)</b></div>`;
}

function evidenceHtml(claimId: string, e: Evidence): string {
  const ids = [e.pmid ? `PMID ${escapeHtml(e.pmid)}` : "", e.doi ? `DOI ${escapeHtml(e.doi)}` : ""]
    .filter(Boolean).join(" · ");
  const human = e.human_support ? escapeHtml(e.human_support) : "—";
  const ai = e.ai_support === "hidden" ? "<i>hidden (blinded until you rate)</i>"
    : (e.ai_support ? escapeHtml(e.ai_support) : "—");
  const decided = e.final_decision ? ` · decision: <b>${escapeHtml(e.final_decision)}</b>` : "";
  const excerpt = e.excerpt ? `<div class="excerpt">“${escapeHtml(e.excerpt)}”</div>` : "";
  const data = `data-claim="${escapeHtml(claimId)}" data-cand="${escapeHtml(e.candidate_id)}"` +
    `${e.rating_id ? ` data-rating="${escapeHtml(e.rating_id)}"` : ""}`;
  // Rate-first gate: a blind human support rating must exist before the decision
  // buttons appear — the same rule the side panel enforces. Until then we show the
  // support-rating buttons (the blind step) and keep the verdict out of reach.
  const rated = !!e.human_support;
  const rateBtns = SUPPORT_VALUES.map(([v, label], i) =>
    `<button class="ratebtn" ${data} data-value="${v}" title="Record your blind support rating">` +
    `<span class="kbd">${i + 1}</span> ${label}</button>`).join(" ");
  const decideBtns = (Object.keys(ACTIONS) as (keyof typeof ACTIONS)[]).map((k) =>
    `<button class="act ${ACTIONS[k].cls}" ${data} data-decision="${verdictDecision(k)}"` +
    ` title="${ACTIONS[k].label}">[${k}] ${ACTIONS[k].label}</button>`).join(" ");
  const accepted = e.decision_id && (e.final_decision === "accept" || e.final_decision === "accepted_with_caution");
  const writeBtn = accepted
    ? `<button class="write" data-decision-id="${escapeHtml(e.decision_id!)}" title="Stage + commit to Zotero (preview first; undoable)">✓ Add to Zotero</button>` : "";
  const ratingBlock = rated ? "" :
    `<div class="ratelbl muted">Your support rating — blind, recorded before the AI’s is shown:</div>` +
    `<div class="rateacts">${rateBtns}</div>`;
  const decisionBlock = rated
    ? `<div class="acts">${decideBtns}${writeBtn}</div>`
    : `<div class="gatehint muted">Rate the support above to unlock Accept / Caution / Review / Reject.</div>`;
  return `<div class="cand" tabindex="0" data-rated="${rated ? "1" : "0"}" ${data}>
      <div class="paper">${escapeHtml(e.title || "(untitled)")}</div>
      <div class="meta">${ids}</div>
      ${excerpt}
      <div class="rate">human: <b>${human}</b> · AI: ${ai}${decided}</div>
      ${fitHtml(e)}
      ${ratingBlock}
      ${decisionBlock}
    </div>`;
}

// A pending rewrite, shown as a was/now diff with explicit accept/keep. The claim
// text is never edited silently — accepting applies a visible edit to the manuscript.
function revisionHtml(r: ReportRow): string {
  if (!r.proposed_revision) {
    return `<div class="revwrap"><button class="revise" data-claim="${escapeHtml(r.claim_id)}"` +
      ` data-text="${escapeHtml(r.claim_text)}" title="Suggest a rewrite of this claim">✎ Revise wording…</button>` +
      `<button class="changeref" data-claim="${escapeHtml(r.claim_id)}"` +
      ` title="Find another paper for this claim (search PubMed, add as candidates)">⇄ Change reference…</button></div>`;
  }
  const by = escapeHtml(r.proposed_revision_by || "human");
  const loc = escapeHtml(r.manuscript_location || "");
  return `<div class="diff">
    <div class="difftag">Proposed rewrite · ${by} · not applied</div>
    <div class="dline old"><span class="dmark">−</span> ${escapeHtml(r.claim_text)}</div>
    <div class="dline new"><span class="dmark">+</span> ${escapeHtml(r.proposed_revision)}</div>
    <div class="acts">
      <button class="accrev" data-claim="${escapeHtml(r.claim_id)}" data-old="${escapeHtml(r.claim_text)}"
        data-new="${escapeHtml(r.proposed_revision)}" data-location="${loc}"
        title="Apply this rewrite to the manuscript + claim">✓ Accept revision</button>
      <button class="keeprev" data-claim="${escapeHtml(r.claim_id)}" title="Discard the suggested rewrite">Keep original</button>
    </div></div>`;
}

function webviewHtml(report: Report): string {
  const nonce = randomBytes(16).toString("base64");
  const c = report.counts;
  const summary = (Object.keys(STATE) as StateKey[]).map((s) =>
    `<span class="chip ${s}"><b>[${STATE[s].code}]</b> ${STATE[s].label} ${c[s] ?? 0}</span>`).join(" ");
  const rows = report.rows.map((r) => `
    <details class="row ${r.state}${r.proposed_revision ? " has-rev" : ""}">
      <summary>
        <span class="chip ${r.state}"><b>[${STATE[r.state].code}]</b> ${STATE[r.state].label}</span>
        <span class="meta">${r.accepted_count}/${r.candidate_count} accepted${r.manuscript_location ? " · " + escapeHtml(r.manuscript_location) : ""}</span>
        ${r.proposed_revision ? '<span class="revchip" title="A rewrite is awaiting your review">✎ revision pending</span>' : ""}
        <span class="reveal" data-text="${escapeHtml(r.claim_text)}">reveal ↪</span>
        <div class="claim">${escapeHtml(r.claim_text)}</div>
      </summary>
      ${revisionHtml(r)}
      <div class="evidence">${r.evidence.length ? r.evidence.map((e) => evidenceHtml(r.claim_id, e)).join("")
        : "<p class='muted'>No references checked yet — use “⇄ Change reference…” to find one.</p>"}</div>
    </details>`).join("");
  return `<!doctype html><html><head><meta charset="utf-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
  <style nonce="${nonce}">
    :root{--amber:#C98A00;--teal:#1E9E8A;--violet:#8B6FC9;--rose:#C24D7E;}
    body{font:13px/1.5 -apple-system,Segoe UI,sans-serif;padding:14px;color:var(--vscode-foreground);}
    h2{margin:0 0 10px;font-size:15px;} .summary{margin-bottom:14px;display:flex;flex-wrap:wrap;gap:6px;}
    .muted{color:var(--vscode-descriptionForeground);}
    .chip{font:600 11px/1 ui-monospace,monospace;padding:4px 8px;border-radius:6px;border:1px solid;}
    .accepted{background:#FFF2D8;border-color:var(--amber);color:#5A4300;}
    .needs_support{background:#D8F4ED;border-color:var(--teal);color:#08544A;}
    .review_needed{background:#ECE3FF;border-color:var(--violet);color:#432C7A;}
    .decision_recorded{background:#FBE0EA;border-color:var(--rose);color:#7A1F45;}
    .row{padding:9px 11px;border:1px solid var(--vscode-panel-border);border-left-width:4px;border-radius:8px;margin-bottom:8px;}
    .row.accepted{border-left-color:var(--amber);} .row.needs_support{border-left-color:var(--teal);}
    .row.review_needed{border-left-color:var(--violet);} .row.decision_recorded{border-left-color:var(--rose);}
    summary{cursor:pointer;} .meta{color:var(--vscode-descriptionForeground);margin-left:8px;font-size:11px;}
    .reveal{margin-left:8px;font-size:11px;cursor:pointer;text-decoration:underline;}
    .claim{margin-top:5px;}
    .evidence{margin-top:8px;padding-left:6px;border-left:2px solid var(--vscode-panel-border);}
    .cand{padding:7px 8px;margin:6px 0;border:1px solid var(--vscode-panel-border);border-radius:7px;}
    .cand:focus{outline:2px solid var(--violet);}
    .paper{font-weight:600;} .rate{margin:3px 0;font-size:12px;}
    .excerpt{margin:4px 0;padding:5px 8px;border-left:2px solid var(--vscode-panel-border);font-style:italic;color:var(--vscode-descriptionForeground);}
    .checks{display:flex;flex-wrap:wrap;gap:4px;margin:4px 0;}
    .check{font:600 10px/1 ui-monospace,monospace;padding:3px 6px;border-radius:5px;border:1px solid var(--vscode-panel-border);}
    .check.ok{background:#D8F4ED;border-color:var(--teal);color:#08544A;}
    .check.partial{background:#FFF2D8;border-color:var(--amber);color:#5A4300;}
    .check.no{background:transparent;color:var(--vscode-descriptionForeground);}
    .fit{font-size:12px;margin:2px 0;}
    .acts{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px;}
    .ratelbl{font-size:11px;margin:6px 0 3px;}
    .rateacts{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:3px;}
    .ratebtn{font:600 11px/1 -apple-system,sans-serif;padding:4px 8px;border-radius:6px;border:1px solid var(--vscode-panel-border);background:transparent;color:var(--vscode-foreground);cursor:pointer;}
    .ratebtn:hover{border-color:var(--teal);color:var(--teal);}
    .ratebtn .kbd{display:inline-block;min-width:1em;text-align:center;font:600 10px/1 ui-monospace,monospace;opacity:.55;margin-right:2px;}
    .gatehint{font-size:11px;margin-top:4px;font-style:italic;}
    .act{font:600 11px/1 ui-monospace,monospace;padding:4px 8px;border-radius:6px;border:1px solid;cursor:pointer;background:transparent;}
    .act.accepted{border-color:var(--amber);color:var(--amber);}
    .act.needs_support{border-color:var(--teal);color:var(--teal);}
    .act.review_needed{border-color:var(--violet);color:var(--violet);}
    .act.decision_recorded{border-color:var(--rose);color:var(--rose);}
    .write{font:600 11px/1 -apple-system,sans-serif;padding:4px 10px;border-radius:6px;border:1px solid var(--amber);background:#FFF2D8;color:#5A4300;cursor:pointer;}
    .hint{margin-top:12px;font-size:11px;}
    .revchip{margin-left:8px;font:600 10px/1 ui-monospace,monospace;padding:3px 7px;border-radius:6px;background:#ECE3FF;border:1px solid var(--violet);color:#432C7A;}
    .revwrap{margin:6px 0 2px;display:flex;gap:6px;flex-wrap:wrap;} .revise{font:600 11px/1 -apple-system,sans-serif;padding:3px 9px;border-radius:6px;border:1px solid var(--violet);background:transparent;color:var(--violet);cursor:pointer;}
    .changeref{font:600 11px/1 -apple-system,sans-serif;padding:3px 9px;border-radius:6px;border:1px solid var(--teal);background:transparent;color:var(--teal);cursor:pointer;}
    .diff{margin:8px 0;padding:8px 10px;border:1px solid var(--violet);border-radius:8px;background:rgba(139,111,201,0.08);}
    .difftag{font:600 10px/1 ui-monospace,monospace;color:#432C7A;margin-bottom:6px;text-transform:uppercase;letter-spacing:.04em;}
    .dline{font:12px/1.4 ui-monospace,monospace;padding:2px 4px;border-radius:4px;white-space:pre-wrap;}
    .dline.old{background:rgba(194,77,126,0.12);color:#7A1F45;} .dline.new{background:rgba(30,158,138,0.14);color:#08544A;}
    .dmark{display:inline-block;width:1em;font-weight:700;opacity:.7;}
    .accrev{font:600 11px/1 -apple-system,sans-serif;padding:4px 10px;border-radius:6px;border:1px solid var(--teal);background:#D8F4ED;color:#08544A;cursor:pointer;}
    .keeprev{font:600 11px/1 -apple-system,sans-serif;padding:4px 10px;border-radius:6px;border:1px solid var(--vscode-panel-border);background:transparent;color:var(--vscode-foreground);cursor:pointer;}
  </style></head><body>
    <h2>${report.total} claim${report.total === 1 ? "" : "s"} in your manuscript</h2>
    <div class="summary">${summary}</div>
    ${rows || "<p>No claims yet. Add claims, then re-run.</p>"}
    <p class="hint muted">Open a claim, pick a reference, then <b>rate the support first</b> (keys <b>1</b>–<b>6</b>) — that’s your blind call, before the AI’s is shown. Only then do you decide: <b>o o</b> accept · <b>o</b> caution · <b>r</b> review · <b>d</b> reject. You decide — CiteVahti just records it, and every change can be undone.</p>
    <script nonce="${nonce}">
      const vscode = acquireVsCodeApi();
      function decide(el, decision){ vscode.postMessage({ type:"decide",
        claim: el.dataset.claim, cand: el.dataset.cand, rating: el.dataset.rating || null, decision }); }
      function rate(el, value){ vscode.postMessage({ type:"rate",
        claim: el.dataset.claim, cand: el.dataset.cand, rating: el.dataset.rating || null, value }); }
      for (const b of document.querySelectorAll(".act"))
        b.addEventListener("click", () => decide(b, b.dataset.decision));
      for (const b of document.querySelectorAll(".ratebtn"))
        b.addEventListener("click", () => rate(b, b.dataset.value));
      for (const w of document.querySelectorAll(".write"))
        w.addEventListener("click", () => vscode.postMessage({ type:"commit", decisionId: w.dataset.decisionId }));
      for (const b of document.querySelectorAll(".revise"))
        b.addEventListener("click", () => vscode.postMessage({ type:"propose-revision", claim: b.dataset.claim, text: b.dataset.text }));
      for (const b of document.querySelectorAll(".accrev"))
        b.addEventListener("click", () => vscode.postMessage({ type:"accept-revision",
          claim: b.dataset.claim, oldText: b.dataset.old, newText: b.dataset.new,
          location: b.dataset.location || null }));
      for (const b of document.querySelectorAll(".keeprev"))
        b.addEventListener("click", () => vscode.postMessage({ type:"reject-revision", claim: b.dataset.claim }));
      for (const b of document.querySelectorAll(".changeref"))
        b.addEventListener("click", () => vscode.postMessage({ type:"change-reference", claim: b.dataset.claim }));
      for (const r of document.querySelectorAll(".reveal"))
        r.addEventListener("click", (ev) => { ev.preventDefault();
          vscode.postMessage({ type:"reveal", text: r.dataset.text }); });
      let pendingO = 0;
      function clearPendingO() {
        if (pendingO) { clearTimeout(pendingO); pendingO = 0; }
      }
      const RATE_KEYS = ${JSON.stringify(SUPPORT_VALUES.map(([v]) => v))};
      document.addEventListener("keydown", (ev) => {
        const cand = document.activeElement?.closest?.(".cand");
        if (!cand) return;
        const rated = cand.dataset.rated === "1";
        // Rate-first: before a blind rating exists, 1–6 record it and the verdict
        // keys are inert. After it exists, o/o/r/d decide (the old flow).
        if (!rated) {
          const i = parseInt(ev.key, 10) - 1;
          if (i >= 0 && i < RATE_KEYS.length) { ev.preventDefault(); rate(cand, RATE_KEYS[i]); }
          return;
        }
        const A = { r:"needs_second_review", d:"reject" };
        if (ev.key === "o") {
          ev.preventDefault();
          if (pendingO) {
            clearPendingO();
            decide(cand, "accept");
          } else {
            pendingO = setTimeout(() => {
              pendingO = 0;
              decide(cand, "accepted_with_caution");
            }, 450);
          }
        } else if (ev.key === "r" || ev.key === "d") {
          clearPendingO();
          decide(cand, A[ev.key]);
          ev.preventDefault();
        }
      });
    </script></body></html>`;
}

let panel: vscode.WebviewPanel | undefined;

async function refresh() {
  let report: Report;
  try { report = await runReport(); }
  catch (e) {
    vscode.window.showErrorMessage(`CiteVahti: could not run claim-report (${e}). Set citevahti.cliPath / citevahti.root.`);
    return;
  }
  decorate(report);
  if (panel) panel.webview.html = webviewHtml(report);
}

function revealInEditor(text: string) {
  const editor = vscode.window.activeTextEditor;
  if (!editor || !text) return;
  const i = editor.document.getText().indexOf(text.trim());
  if (i < 0) return;
  const range = new vscode.Range(editor.document.positionAt(i),
    editor.document.positionAt(i + text.trim().length));
  editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
  editor.selection = new vscode.Selection(range.start, range.end);
}

async function decide(claim: string, cand: string, rating: string | null, decision: string) {
  const reason = await vscode.window.showInputBox({
    prompt: `Reason for "${decision}" (recorded in the audit trail)`,
    value: "Reviewed in VS Code",
  });
  if (reason === undefined) return;   // cancelled
  const args = ["claim-decide", "--claim-id", claim, "--candidate-id", cand,
    "--decision", decision, "--reason", reason || "Reviewed in VS Code"];
  if (rating) args.push("--rating-id", rating);
  const { code, stdout, stderr } = await runCli(args);
  if (code !== 0) {
    vscode.window.showErrorMessage(`CiteVahti: ${(stderr || stdout || "decision failed").trim().split("\n")[0]}`);
  } else {
    vscode.window.showInformationMessage(`CiteVahti: recorded "${decision}".`);
  }
  await refresh();
}

// The blind support rating — recorded BEFORE any decision and before the AI's
// rating is unblinded. Starts the rating if one doesn't exist yet, then commits +
// locks the human value (the store refuses to overwrite it).
async function rate(claim: string, cand: string, rating: string | null, value: string) {
  let ratingId = rating;
  if (!ratingId) {
    const started = await runCli(["claim-support-start", "--claim-id", claim, "--candidate-id", cand]);
    if (started.code !== 0) {
      vscode.window.showErrorMessage(
        `CiteVahti: ${(started.stderr || started.stdout || "could not start rating").trim().split("\n")[0]}`);
      return;
    }
    // stdout: "claim-support rating started: <rating_id>"
    ratingId = (started.stdout.split("started:")[1] || "").trim().split(/\s+/)[0] || null;
    if (!ratingId) {
      vscode.window.showErrorMessage("CiteVahti: could not read the new rating id.");
      return;
    }
  }
  const { code, stdout, stderr } = await runCli(
    ["claim-support-commit-human", "--rating-id", ratingId, "--value", value]);
  if (code !== 0) {
    vscode.window.showErrorMessage(`CiteVahti: ${(stderr || stdout || "rating failed").trim().split("\n")[0]}`);
  } else {
    vscode.window.showInformationMessage(
      `CiteVahti: recorded your support rating "${value}". The AI second opinion is now unblinded.`);
  }
  await refresh();
}

function collectionKey(): string | undefined {
  return vscode.workspace.getConfiguration("citevahti").get<string>("collectionKey") || undefined;
}

// Optional write target: "personal" or "group:<id>". Empty -> the CLI uses the
// library configured at onboarding (Config.default_library).
function library(): string | undefined {
  return vscode.workspace.getConfiguration("citevahti").get<string>("library") || undefined;
}

// Preview the decision-gated write, confirm, then commit. Never a silent write.
async function commit(decisionId: string) {
  const args = ["claim-commit", "--decision-id", decisionId, "--json"];
  const coll = collectionKey();
  if (coll) args.push("--collection-key", coll);
  const lib = library();
  if (lib) args.push("--library", lib);
  const prev = await runCli(args);
  let diff: any;
  try { diff = JSON.parse(prev.stdout); }
  catch { vscode.window.showErrorMessage("CiteVahti: could not preview the write."); return; }
  if (!diff.backend_available) {
    const pick = await vscode.window.showWarningMessage(
      "CiteVahti: Zotero isn't connected yet. Connect it once (one paste) to enable write-back.",
      "Connect Zotero");
    if (pick === "Connect Zotero") await connectZotero();
    return;
  }
  if (!diff.confirm_token) {
    vscode.window.showErrorMessage(`CiteVahti: ${(diff.remediation || diff.error_code || "write preview was not confirmable")}`);
    return;
  }
  const changes = (diff.proposed_changes || []).join("\n");
  const warns = (diff.warnings || []).join("\n");
  const target = diff.structured?.collection_key || coll || "(no collection key configured)";
  const lib2 = diff.library || lib || "personal";
  const ok = await vscode.window.showWarningMessage(
    `Add to Zotero?\n\nLibrary: ${lib2}\nCollection: ${target}\n\n${changes}${warns ? "\n\n⚠ " + warns : ""}`,
    { modal: true }, "Add to Zotero");
  if (ok !== "Add to Zotero") return;
  await doCommit(decisionId, false, diff.confirm_token);
}

async function doCommit(decisionId: string, override: boolean, confirmToken: string) {
  const args = ["claim-commit", "--decision-id", decisionId, "--commit", "--json"];
  const coll = collectionKey();
  if (coll) args.push("--collection-key", coll);
  const lib = library();
  if (lib) args.push("--library", lib);
  args.push("--confirm-token", confirmToken);
  if (override) args.push("--allow-unverified-dedupe");
  const { stdout } = await runCli(args);
  let txn: any;
  try { txn = JSON.parse(stdout); }
  catch { vscode.window.showErrorMessage("CiteVahti: write failed (no result)."); await refresh(); return; }

  if (txn.status === "committed") {
    const keys = (txn.result?.created_keys || []).join(", ");
    const undo = await vscode.window.showInformationMessage(
      `Added to Zotero${keys ? " (" + keys + ")" : ""}${txn.collection_key ? " in " + txn.collection_key : ""}. ` +
      `Transaction ${txn.transaction_id}.`, "Undo");
    if (undo === "Undo") {
      const u = await runCli(["txn-undo", "--transaction-id", txn.transaction_id, "--json"]);
      let ut: any = {}; try { ut = JSON.parse(u.stdout); } catch { /* ignore */ }
      vscode.window.showInformationMessage(ut.status === "undone"
        ? "Undone — the reference was removed from Zotero." : "CiteVahti: undo did not complete.");
    }
  } else if (txn.error_code === "dedupe_unverified") {
    const o = await vscode.window.showWarningMessage(
      "Couldn't verify the paper isn't already in your Zotero library (search unavailable). Add anyway?",
      "Override and add");
    if (o === "Override and add") { await doCommit(decisionId, true, confirmToken); return; }
  } else {
    vscode.window.showErrorMessage(`CiteVahti: ${(txn.remediation || txn.error_code || "write failed")}`);
  }
  await refresh();
}

// Let the human suggest a rewrite. Records a pending revision (applies nothing);
// the diff then renders with accept/keep.
async function proposeRevision(claim: string, current: string) {
  const next = await vscode.window.showInputBox({
    prompt: "Suggest a rewrite — review the diff before it's applied",
    value: current, valueSelection: [0, current.length],
  });
  if (next === undefined || next.trim() === "" || next.trim() === current.trim()) return;
  const { code, stdout, stderr } = await runCli(
    ["claim-propose-revision", "--claim-id", claim, "--text", next.trim()]);
  if (code !== 0)
    vscode.window.showErrorMessage(`CiteVahti: ${(stderr || stdout || "could not propose revision").trim().split("\n")[0]}`);
  await refresh();
}

// Accept = a visible edit. Replace the claim text in the manuscript (WorkspaceEdit),
// then update the stored claim. Never silent: the human clicked Accept on the diff.
function fileFromManuscriptLocation(location: string | null | undefined): string | undefined {
  const raw = String(location || "").split(":")[0].trim();
  return raw || undefined;
}

async function editorForRevision(oldText: string, location?: string | null): Promise<vscode.TextEditor | undefined> {
  const active = vscode.window.activeTextEditor;
  if (active?.document.getText().includes(oldText)) return active;
  const file = fileFromManuscriptLocation(location);
  if (!file) return active;
  const uri = file.startsWith("/")
    ? vscode.Uri.file(file)
    : (vscode.workspace.workspaceFolders?.[0]
        ? vscode.Uri.joinPath(vscode.workspace.workspaceFolders[0].uri, file)
        : undefined);
  if (!uri) return active;
  const doc = await vscode.workspace.openTextDocument(uri);
  return vscode.window.showTextDocument(doc, { preview: false });
}

// Durable manuscript backups — the extension's OWN safety, independent of the panel
// (not every user runs the panel). VS Code's native undo is session-only, so before
// any revision edit we snapshot the file to .citevahti/manuscript_backups, mirroring
// the panel's .md backup, and expose a revert command for a cross-session undo.
function backupDir(uri: vscode.Uri): vscode.Uri | undefined {
  const root = vscode.workspace.getWorkspaceFolder(uri)?.uri
    ?? vscode.workspace.workspaceFolders?.[0]?.uri;
  return root ? vscode.Uri.joinPath(root, ".citevahti", "manuscript_backups") : undefined;
}
async function backupManuscript(doc: vscode.TextDocument): Promise<vscode.Uri | undefined> {
  try {
    const dir = backupDir(doc.uri);
    if (!dir) return undefined;
    await vscode.workspace.fs.createDirectory(dir);
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const name = doc.uri.path.split("/").pop() || "manuscript.md";
    const dest = vscode.Uri.joinPath(dir, `${name}.${stamp}.bak`);
    await vscode.workspace.fs.writeFile(dest, Buffer.from(doc.getText(), "utf8"));
    return dest;
  } catch { return undefined; }
}
async function revertManuscriptEdit() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) { vscode.window.showWarningMessage("CiteVahti: open the manuscript to revert."); return; }
  const doc = editor.document;
  const dir = backupDir(doc.uri);
  const name = doc.uri.path.split("/").pop() || "";
  let entries: [string, vscode.FileType][] = [];
  try { if (dir) entries = await vscode.workspace.fs.readDirectory(dir); } catch { /* none */ }
  const mine = entries.map(([n]) => n).filter((n) => n.startsWith(name + ".") && n.endsWith(".bak")).sort();
  const latest = mine[mine.length - 1];
  if (!dir || !latest) { vscode.window.showWarningMessage("CiteVahti: no manuscript backup found for this file."); return; }
  const pick = await vscode.window.showWarningMessage(
    `Restore "${name}" from backup ${latest}? Current contents will be replaced.`, "Restore");
  if (pick !== "Restore") return;
  const bytes = await vscode.workspace.fs.readFile(vscode.Uri.joinPath(dir, latest));
  const whole = new vscode.Range(doc.positionAt(0), doc.positionAt(doc.getText().length));
  const edit = new vscode.WorkspaceEdit();
  edit.replace(doc.uri, whole, Buffer.from(bytes).toString("utf8"));
  await vscode.workspace.applyEdit(edit);
  vscode.window.showInformationMessage(`CiteVahti: restored ${name} from ${latest}.`);
}

async function acceptRevision(claim: string, oldText: string, newText: string, location?: string | null) {
  const editor = await editorForRevision(oldText, location);
  if (!editor) {
    vscode.window.showWarningMessage("CiteVahti: open the manuscript before accepting a revision.");
    return;
  }
  if (!oldText) {
    vscode.window.showWarningMessage("CiteVahti: revision is missing the original claim text.");
    return;
  }

  const doc = editor.document;
  const selected = doc.getText(editor.selection);
  let range: vscode.Range | undefined;
  if (selected === oldText) {
    range = new vscode.Range(editor.selection.start, editor.selection.end);
  } else {
    const text = doc.getText();
    const first = text.indexOf(oldText);
    if (first < 0) {
      vscode.window.showWarningMessage("CiteVahti: could not find the old claim text in this file. Claim state was not changed.");
      return;
    }
    const second = text.indexOf(oldText, first + oldText.length);
    if (second >= 0) {
      const pick = await vscode.window.showWarningMessage(
        "This claim text appears more than once. Select the intended manuscript span, then accept the revision again.",
        "Reveal first match");
      if (pick === "Reveal first match") revealInEditor(oldText);
      return;
    }
    range = new vscode.Range(doc.positionAt(first), doc.positionAt(first + oldText.length));
  }

  const backup = await backupManuscript(doc);   // durable snapshot before we mutate the .md
  const edit = new vscode.WorkspaceEdit();
  edit.replace(doc.uri, range, newText);
  const applied = await vscode.workspace.applyEdit(edit);
  if (!applied) {
    vscode.window.showErrorMessage("CiteVahti: VS Code did not apply the manuscript revision. Claim state was not changed.");
    return;
  }

  const { code, stdout, stderr } = await runCli(
    ["claim-accept-revision", "--claim-id", claim, "--expected-text", newText]);
  if (code !== 0) {
    const startOffset = doc.offsetAt(range.start);
    const rollback = new vscode.WorkspaceEdit();
    rollback.replace(doc.uri,
      new vscode.Range(doc.positionAt(startOffset), doc.positionAt(startOffset + newText.length)),
      oldText);
    const rolledBack = await vscode.workspace.applyEdit(rollback);
    vscode.window.showErrorMessage(`CiteVahti: ${(stderr || stdout || "could not apply revision").trim().split("\n")[0]}`);
    if (!rolledBack) {
      vscode.window.showWarningMessage("CiteVahti: rollback failed; review the manuscript and claim state before continuing.");
    }
  } else {
    const note = backup
      ? ` Backup saved (${backup.path.split("/").pop()}); revert via “CiteVahti: Revert manuscript edit”.`
      : "";
    vscode.window.showInformationMessage("Revision applied to the manuscript and the claim." + note);
  }
  await refresh();
}

// "Change reference": find another paper for this claim. Searches PubMed (the
// exact query, never rewritten), lets the human pick which staged hits to link,
// and adds them as candidates. Swapping AMONG already-linked candidates is done
// directly on each candidate card; this adds NEW ones. Links only — no rating,
// no decision, no Zotero write happens here.
interface HitPick extends vscode.QuickPickItem { recordId: string; }

async function changeReference(claim: string) {
  const query = await vscode.window.showInputBox({
    prompt: "Find another reference — PubMed query (sent verbatim, never rewritten)",
    placeHolder: "e.g. low-dose CT screening lung cancer mortality",
    ignoreFocusOut: true,
  });
  if (!query || !query.trim()) return;
  const search = await runCli(["literature-search", "--query", query.trim(), "--json"]);
  let res: any;
  try { res = JSON.parse(search.stdout); }
  catch { vscode.window.showErrorMessage("CiteVahti: search failed (no result). Check citevahti.cliPath / NCBI access."); return; }
  if (res.status !== "ok") {
    vscode.window.showErrorMessage(`CiteVahti: ${(res.remediation || res.error_code || "search failed")}`);
    return;
  }
  const hits: any[] = res.hits || [];
  if (!hits.length) { vscode.window.showInformationMessage("CiteVahti: no results for that query."); return; }
  if (res.review_required)
    vscode.window.showWarningMessage("PubMed re-translated your query — confirm the results match your intent before adding.");
  const items: HitPick[] = hits.map((h) => ({
    label: h.title || "(untitled)",
    description: [h.pmid ? "PMID " + h.pmid : "", h.doi ? "DOI " + h.doi : "", h.dedupe_status]
      .filter(Boolean).join(" · "),
    picked: h.dedupe_status === "new",
    recordId: h.record_id,
  }));
  const picks = await vscode.window.showQuickPick(items, {
    canPickMany: true, title: `Add references to the claim (${hits.length} found)`,
    placeHolder: "Select the paper(s) to link as candidates — rate them afterwards on the card",
  });
  if (!picks || !picks.length) return;
  const args = ["claim-link-candidates", "--claim-id", claim, "--intake-batch-id", res.batch_id, "--json"];
  for (const p of picks) args.push("--record-id", p.recordId);
  const link = await runCli(args);
  if (link.code === 0) {
    let linked: any = {};
    try { linked = JSON.parse(link.stdout); } catch { /* ignore */ }
    const n = linked.linked ?? picks.length;
    const dup = linked.skipped_duplicates ? ` (${linked.skipped_duplicates} already linked)` : "";
    vscode.window.showInformationMessage(
      `CiteVahti: linked ${n} candidate(s)${dup} — rate them on the card to set support.`);
  } else {
    vscode.window.showErrorMessage(`CiteVahti: ${(link.stderr || link.stdout || "could not link candidates").trim().split("\n")[0]}`);
  }
  await refresh();
}

async function rejectRevision(claim: string) {
  const { code, stdout, stderr } = await runCli(["claim-reject-revision", "--claim-id", claim]);
  if (code !== 0)
    vscode.window.showErrorMessage(`CiteVahti: ${(stderr || stdout || "could not reject revision").trim().split("\n")[0]}`);
  await refresh();
}

async function verifyClaims() {
  if (!panel) {
    panel = vscode.window.createWebviewPanel("citevahti", "Citation Integrity",
      vscode.ViewColumn.Beside, { enableScripts: true });
    panel.onDidDispose(() => (panel = undefined));
    panel.webview.onDidReceiveMessage((m) => {
      if (m?.type === "reveal") revealInEditor(String(m.text || ""));
      else if (m?.type === "rate") rate(String(m.claim), String(m.cand), m.rating ?? null, String(m.value));
      else if (m?.type === "decide") decide(String(m.claim), String(m.cand), m.rating ?? null, String(m.decision));
      else if (m?.type === "commit") commit(String(m.decisionId));
      else if (m?.type === "propose-revision") proposeRevision(String(m.claim), String(m.text || ""));
      else if (m?.type === "accept-revision") acceptRevision(
        String(m.claim), String(m.oldText || ""), String(m.newText || ""), m.location ?? null);
      else if (m?.type === "reject-revision") rejectRevision(String(m.claim));
      else if (m?.type === "change-reference") changeReference(String(m.claim));
    });
  }
  await refresh();
}

// ───────────────────────── Guided "Start manuscript review" ─────────────────
// One humane front door: a checklist that runs the setup checks for you and
// repairs them with a click. The researcher never types `init`, never sees
// `.citevahti/`, and only meets Zotero write-back at the end (it's optional).
interface Preflight {
  project_initialized: boolean;
  project_dir: string;
  zotero: { reachable: boolean; version: string | null };
  better_bibtex: { reachable: boolean; version: string | null };
  zotero_write_ready: boolean;
  claims: { total: number; accepted: number; needs_support: number;
            review_needed: number; decision_recorded: number; with_candidates: number } | null;
}

async function runPreflight(): Promise<Preflight | null> {
  const { stdout } = await runCli(["preflight"]);
  try { return JSON.parse(stdout) as Preflight; } catch { return null; }
}

function manuscriptIsOpen(): boolean {
  return vscode.window.visibleTextEditors.some((e) => e.document.uri.scheme === "file");
}

function openZotero() {
  if (process.platform === "darwin") execFile("open", ["-a", "Zotero"], () => undefined);
  else vscode.window.showInformationMessage("Open Zotero Desktop to add references back to Zotero.");
}

// Add a claim, defaulting to the sentence the user has selected in the manuscript.
async function addClaim() {
  const ed = vscode.window.visibleTextEditors.find((e) => e.document.uri.scheme === "file");
  const sel = ed && !ed.selection.isEmpty ? ed.document.getText(ed.selection).trim() : "";
  const text = await vscode.window.showInputBox({
    prompt: "Add a claim to check — paste or type the sentence from your manuscript",
    value: sel, ignoreFocusOut: true,
  });
  if (!text || !text.trim()) return;
  const r = await runCli(["claim-add", "--text", text.trim(), "--type", "background"]);
  if (r.code !== 0)
    vscode.window.showErrorMessage(`CiteVahti: ${(r.stderr || r.stdout || "could not add the claim").trim().split("\n")[0]}`);
}

let reviewPanel: vscode.WebviewPanel | undefined;

async function startReview() {
  if (!reviewPanel) {
    reviewPanel = vscode.window.createWebviewPanel(
      "citevahtiReview", "CiteVahti — Start review", vscode.ViewColumn.Beside, { enableScripts: true });
    reviewPanel.onDidDispose(() => (reviewPanel = undefined));
    reviewPanel.webview.onDidReceiveMessage(async (m) => {
      switch (m?.type) {
        case "setup-project": {
          const r = await runCli(["init"]);
          vscode.window.showInformationMessage(
            r.code === 0 ? "CiteVahti: your review workspace is ready." : "CiteVahti: couldn't set up the workspace.");
          break;
        }
        case "open-zotero": openZotero(); break;
        case "connect-zotero": await connectZotero(); break;
        case "add-claim": await addClaim(); break;
        case "start-review": await verifyClaims(); break;
        case "refresh": break;
      }
      await refreshReview();
    });
  }
  await refreshReview();
  reviewPanel.reveal(vscode.ViewColumn.Beside);
}

async function refreshReview() {
  if (!reviewPanel) return;
  reviewPanel.webview.html = reviewHtml(await runPreflight(), manuscriptIsOpen());
}

function checkRow(ok: boolean, optional: boolean, title: string, note: string,
                  fix?: { label: string; type: string }): string {
  const mark = ok ? "✓" : optional ? "○" : "!";
  const cls = ok ? "ok" : optional ? "opt" : "todo";
  const btn = !ok && fix ? `<button class="fix" data-type="${fix.type}">${escapeHtml(fix.label)}</button>` : "";
  return `<div class="chk ${cls}"><span class="mk">${mark}</span>` +
    `<div class="body"><div class="t">${escapeHtml(title)}</div><div class="n">${escapeHtml(note)}</div></div>${btn}</div>`;
}

function reviewHtml(pf: Preflight | null, manuscript: boolean): string {
  const nonce = randomBytes(16).toString("base64");
  const head = `<!doctype html><html><head><meta charset="utf-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
    <style nonce="${nonce}">
      :root{--violet:#8B6FC9;--teal:#1E9E8A;--amber:#C98A00;}
      body{font:13px/1.5 -apple-system,Segoe UI,sans-serif;padding:18px;color:var(--vscode-foreground);}
      h2{font-size:16px;margin:0 0 4px;} .sub{color:var(--vscode-descriptionForeground);margin:0 0 16px;}
      .chk{display:flex;align-items:flex-start;gap:10px;padding:10px 12px;border:1px solid var(--vscode-panel-border);border-radius:9px;margin-bottom:8px;}
      .mk{flex:0 0 20px;height:20px;line-height:20px;text-align:center;border-radius:50%;font-weight:700;font-size:12px;}
      .ok .mk{background:#D8F4ED;color:#08544A;} .todo .mk{background:#FBE0EA;color:#7A1F45;} .opt .mk{background:#ECE3FF;color:#432C7A;}
      .body{flex:1;} .t{font-weight:600;} .n{color:var(--vscode-descriptionForeground);font-size:12px;margin-top:1px;}
      .fix{align-self:center;font:600 12px/1 -apple-system,sans-serif;padding:6px 12px;border-radius:7px;border:1px solid var(--violet);background:transparent;color:var(--violet);cursor:pointer;white-space:nowrap;}
      .go{margin-top:14px;width:100%;font:700 14px/1 -apple-system,sans-serif;padding:12px;border-radius:9px;border:0;background:var(--violet);color:#fff;cursor:pointer;}
      .go[disabled]{opacity:.45;cursor:not-allowed;}
      .gohint{text-align:center;color:var(--vscode-descriptionForeground);font-size:12px;margin-top:8px;}
    </style></head><body>`;
  if (!pf) {
    return head + `<h2>CiteVahti can’t find its helper yet</h2>
      <p class="sub">Set <b>citevahti.cliPath</b> in Settings to your CiteVahti command, then reopen this.</p>
      <button class="go" id="refresh">Try again</button>
      <script nonce="${nonce}">const v=acquireVsCodeApi();
        document.getElementById('refresh').onclick=()=>v.postMessage({type:'refresh'});</script></body></html>`;
  }
  const total = pf.claims?.total ?? 0;
  const withRefs = pf.claims?.with_candidates ?? 0;
  const ready = pf.project_initialized && manuscript && total > 0;
  const rows = [
    checkRow(manuscript, false, "Manuscript open",
      manuscript ? "A manuscript file is open." : "Open the document you want to check, then refresh."),
    checkRow(pf.project_initialized, false, "CiteVahti ready",
      pf.project_initialized ? "Your review workspace is set up." : "One-time setup for this folder.",
      { label: "Set up", type: "setup-project" }),
    checkRow(total > 0, false, "Claims to review",
      total > 0 ? `${total} claim${total === 1 ? "" : "s"} found · ${withRefs} already have references`
                : "No claims yet — add the sentences you want to check.",
      { label: "Add a claim", type: "add-claim" }),
    checkRow(pf.zotero.reachable, true, "Zotero running (optional)",
      pf.zotero.reachable ? `Connected for reading${pf.zotero.version ? " · v" + pf.zotero.version : ""}.`
                          : "Only needed to add references back to Zotero.",
      { label: "Open Zotero", type: "open-zotero" }),
    checkRow(pf.zotero_write_ready, true, "Saving references to Zotero (optional)",
      pf.zotero_write_ready ? "Ready — accepted references can be saved to Zotero."
                            : "Paste a Zotero key once to enable this. You can do it later.",
      { label: "Connect", type: "connect-zotero" }),
  ].join("");
  return head + `<h2>Start manuscript review</h2>
    <p class="sub">CiteVahti checks your setup and fixes what’s missing. You stay in control of every decision.</p>
    ${rows}
    <button class="go" id="go" ${ready ? "" : "disabled"}>Start reviewing${total > 0 ? ` (${total})` : ""}</button>
    <p class="gohint">${ready ? "Opens your claims highlighted in the manuscript."
      : "Open a manuscript, set up CiteVahti, and add at least one claim to begin."}</p>
    <script nonce="${nonce}">
      const v = acquireVsCodeApi();
      for (const b of document.querySelectorAll(".fix"))
        b.addEventListener("click", () => v.postMessage({ type: b.dataset.type }));
      const go = document.getElementById("go");
      if (go && !go.disabled) go.addEventListener("click", () => v.postMessage({ type: "start-review" }));
    </script></body></html>`;
}

export function activate(context: vscode.ExtensionContext) {
  void loadVocabulary();   // refresh verdict decisions from the engine (best-effort)
  context.subscriptions.push(...Object.values(decoTypes));
  context.subscriptions.push(vscode.commands.registerCommand("citevahti.startReview", startReview));
  context.subscriptions.push(vscode.commands.registerCommand("citevahti.verifyClaims", verifyClaims));
  context.subscriptions.push(vscode.commands.registerCommand("citevahti.connectZotero", connectZotero));
  context.subscriptions.push(vscode.commands.registerCommand("citevahti.revertManuscriptEdit", revertManuscriptEdit));
}

export function deactivate() {}
