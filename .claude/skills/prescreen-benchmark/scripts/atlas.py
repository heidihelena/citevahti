#!/usr/bin/env python3
"""Generate a self-contained, publication-style Atlas HTML from a results.json.

Usage: python3 atlas.py <results.json> <out.html>   (paths are CWD-relative)
Add a META entry below for a nicer masthead on a new theme; the fallback works
for any theme without one.
"""
import json, html, sys
from pathlib import Path

RESULTS_FILE = sys.argv[1] if len(sys.argv) > 1 else "results.json"
OUT_FILE = sys.argv[2] if len(sys.argv) > 2 else "atlas.html"
R = json.loads(Path(RESULTS_FILE).read_text())

META = {
    "lung-nodule-management": {
        "eyebrow": "Lung-nodule management",
        "subject": "a lung-nodule management claim",
        "sources": "Fleischner&nbsp;2017, Lung-RADS, USPSTF, NLST, NELSON, BTS/Brock"},
    "lung-cancer-risk-factors": {
        "eyebrow": "Lung-cancer risk factors",
        "subject": "a lung-cancer risk-factor claim",
        "sources": "IARC monographs, US Surgeon General, WHO/EPA, ATBC/CARET trials"},
    "lung-cancer-neoadjuvant": {
        "eyebrow": "Neoadjuvant / perioperative NSCLC",
        "subject": "a neoadjuvant lung-cancer claim",
        "sources": "CheckMate&nbsp;816, KEYNOTE-671, AEGEAN, NADIM&nbsp;II, NCCN/IASLC"},
}
M = META.get(R["theme"], {"eyebrow": R["theme"], "subject": "a claim",
                          "sources": "the cited evidence"})

V = {"supports": ("supports", "#9a7a1e"), "contrasts": ("contrasts", "#b04a3f"),
     "unclear": ("unclear", "#6a52a3"), "not_relevant": ("not relevant", "#64707a"),
     "unparseable": ("unparseable", "#3f464d")}
MODELS = R["models"]
PRETTY = {"claude-fable-5": "Claude Fable 5", "qwen3:14b": "qwen3:14b", "hermes3:8b": "hermes3:8b"}
ROLE = {"claude-fable-5": "reference peer", "qwen3:14b": "local · 14B", "hermes3:8b": "local · 8B"}

def esc(s): return html.escape(str(s))

def chip(v):
    label, c = V.get(v, (v, "#3f464d"))
    return f'<span class="chip" style="--c:{c}">{esc(label)}</span>'

def kword(k):
    if k is None: return "n/a"
    if k >= 0.81: return "almost perfect"
    if k >= 0.61: return "substantial"
    if k >= 0.41: return "moderate"
    if k >= 0.21: return "fair"
    return "slight"

# scoreboard cards — models under test first, reference peer last
order = ["qwen3:14b", "hermes3:8b", "claude-fable-5"]
cards = []
for m in order:
    s = R["stats"]["vs_anchor"][m]
    k = s["cohens_kappa"]
    lat = R["stats"]["timing_secs"].get(m)
    latline = (f'{lat["mean"]}s median-ish / claim' if lat else "no local inference")
    cards.append(
        f'<article class="card">'
        f'<div class="chd"><span class="cname">{esc(PRETTY[m])}</span>'
        f'<span class="crole">{esc(ROLE[m])}</span></div>'
        f'<div class="cbig">{s["accuracy_vs_anchor"]:.0%}</div>'
        f'<div class="clab">agreement with the guideline anchor</div>'
        f'<div class="cmeta"><span>&kappa; {k if k is not None else "n/a"}</span>'
        f'<span class="dot">&middot;</span><span>{esc(kword(k))}</span></div>'
        f'<div class="cfoot">{esc(latline)} &middot; parseable {esc(s["parseable"])}</div>'
        f'</article>')

# evidence rows
rows = []
for r in R["rows"]:
    dis = any(r["ratings"][m] != r["ref"] for m in MODELS)
    cells = ""
    for m in MODELS:
        v = r["ratings"][m]
        off = " off" if v != r["ref"] else ""
        cells += f'<td class="rc{off}">{chip(v)}</td>'
    rows.append(
        f'<tr class="{"dis" if dis else ""}">'
        f'<td class="id">{esc(r["id"])}</td>'
        f'<td class="cl"><div class="ct">{esc(r["claim"])}</div>'
        f'<div class="sr">{esc(r["source"])}</div></td>'
        f'<td class="an">{chip(r["ref"])}</td>{cells}</tr>')

# disagreement reading
dislist = []
for r in R["rows"]:
    for m in MODELS:
        if r["ratings"][m] != r["ref"]:
            dislist.append(f'<b>{esc(r["id"])}</b> &mdash; {esc(PRETTY[m])} said '
                           f'&ldquo;{esc(V[r["ratings"][m]][0])}&rdquo; where the anchor is '
                           f'&ldquo;{esc(V[r["ref"]][0])}&rdquo; '
                           f'(<span class="q">{esc(r["claim"][:90])}&hellip;</span>)')

total_miss = len(dislist)
unclear_miss = sum(1 for r in R["rows"] for m in MODELS
                   if r["ratings"][m] != r["ref"] and r["ref"] == "unclear")

pw = "".join(
    f'<tr><td>{esc(PRETTY.get(a,a))} &harr; {esc(PRETTY.get(b,b))}</td>'
    f'<td class="num">{v["agreement"]:.0%}</td><td class="num">{v["cohens_kappa"]}</td></tr>'
    for name, v in R["stats"]["pairwise"].items() for a, b in [name.split(" vs ")])

thead = "".join(f'<th class="rh">{esc(PRETTY[m])}</th>' for m in MODELS)
legend = " ".join(chip(v) for v in R["vocabulary"])
tim = R["stats"]["timing_secs"]
timline = " &nbsp;·&nbsp; ".join(
    f'{esc(m)} mean {t["mean"]}s (span {t["min"]}&ndash;{t["max"]}s)' for m, t in tim.items())

HTML = f"""<main class="atlas">
  <header class="mast">
    <div class="eyebrow">CiteVahti &middot; Evidence Atlas &middot; {M["eyebrow"]}</div>
    <h1>Can a laptop-sized model prescreen a citation?</h1>
    <p class="stand">Two local models running on one machine &mdash; <b>qwen3:14b</b> and
      <b>hermes3:8b</b> &mdash; were asked to judge whether a cited source
      <i>supports</i> {M["subject"]}, alongside Claude Fable 5.
      Each verdict is measured against an independent, evidence-derived anchor
      ({M["sources"]}).</p>
    <p class="caveat">The anchor records claim&harr;source <i>support</i>, not clinical
      truth about patients. Every model here &mdash; Claude included &mdash; is a
      prescreener scored against that anchor. <b>Agreement is not accuracy.</b></p>
  </header>

  <section class="board">{''.join(cards)}</section>

  <section class="block">
    <div class="bh"><h2>Evidence map</h2><div class="legend">{legend}</div></div>
    <div class="scroll">
      <table class="map">
        <thead><tr><th>#</th><th>Claim &amp; cited source</th>
          <th class="rh anchorh">anchor</th>{thead}</tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    <p class="fn">Rows with a red stripe hold at least one model verdict that departs from
      the anchor; the departing cell is outlined. {R['n_pairs']} claim&harr;source pairs,
      rated blind.</p>
  </section>

  <section class="block two">
    <div>
      <h2>Where they diverged</h2>
      <ul class="div">{''.join(f'<li>{d}</li>' for d in dislist) or '<li>No divergences from the anchor.</li>'}</ul>
      <p class="fn">Of {total_miss} verdicts that departed from the anchor, {unclear_miss} fall on the
        <i>unclear</i> cases &mdash; both local models force an on-topic-but-unresolved claim into
        &ldquo;supports&rdquo; or &ldquo;contrasts&rdquo; rather than flagging that the source does
        not settle it. The rest are a weaker model waving through a claim that <i>overstates</i> or
        <i>contradicts</i> its source. That epistemic-humility gap is exactly why the human rates
        first and the AI stays advisory.</p>
    </div>
    <div>
      <h2>Rater-to-rater</h2>
      <table class="pw"><thead><tr><th>pair</th><th class="num">agree</th><th class="num">&kappa;</th></tr></thead>
        <tbody>{pw}</tbody></table>
      <p class="fn">Local inference latency: {timline}. qwen3:14b needs
        thinking disabled (<code>think:false</code>) to answer as a rater.</p>
    </div>
  </section>

  <footer class="foot">
    <span>Built with CiteVahti &middot; models served locally via Ollama, blind to each other and to the anchor</span>
    <span>Corpus persisted as CiteVahti <code>ValidationRecord</code> JSONL &middot; 2026-07-09</span>
  </footer>
</main>

<style>
  .atlas {{ --paper:#f5f6f4; --card:#fff; --ink:#17212b; --soft:#4a5763; --faint:#8a97a1;
    --rule:#e2e6e4; --accent:#0e6b73;
    max-width: 1120px; margin: 0 auto; padding: 2.4rem 1.4rem 3rem; color: var(--ink);
    background: var(--paper); box-sizing: border-box;
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; line-height: 1.55;
    font-feature-settings: "kern"; }}
  .atlas *, .atlas *::before {{ box-sizing: border-box; }}
  .serif {{ font-family: "Iowan Old Style","Palatino Linotype",Palatino,Georgia,ui-serif,serif; }}
  .mast {{ border-bottom: 2px solid var(--ink); padding-bottom: 1.5rem; }}
  .eyebrow {{ font-size: .72rem; letter-spacing: .13em; text-transform: uppercase;
    color: var(--accent); font-weight: 600; }}
  .mast h1 {{ font-family: "Iowan Old Style","Palatino Linotype",Palatino,Georgia,ui-serif,serif;
    font-weight: 600; font-size: clamp(1.7rem, 4vw, 2.7rem); line-height: 1.1; margin: .5rem 0 .8rem;
    text-wrap: balance; letter-spacing: -.01em; }}
  .stand {{ max-width: 60ch; font-size: 1.02rem; color: var(--soft); margin: 0 0 .7rem; }}
  .caveat {{ max-width: 60ch; font-size: .9rem; color: var(--ink);
    border-left: 3px solid var(--accent); padding: .1rem 0 .1rem .8rem; margin: 0; }}
  .stand b, .caveat b {{ color: var(--ink); }}
  .board {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin: 1.8rem 0; }}
  .card {{ background: var(--card); border: 1px solid var(--rule); border-radius: 3px;
    padding: 1.1rem 1.2rem; box-shadow: 0 1px 0 rgba(23,33,43,.03); }}
  .chd {{ display: flex; justify-content: space-between; align-items: baseline; gap: .5rem; }}
  .cname {{ font-weight: 650; font-size: 1.02rem; }}
  .crole {{ font-size: .68rem; letter-spacing: .05em; text-transform: uppercase; color: var(--faint);
    white-space: nowrap; }}
  .cbig {{ font-family: "Iowan Old Style",Palatino,Georgia,ui-serif,serif; font-size: 2.9rem;
    font-weight: 600; color: var(--accent); line-height: 1; margin: .5rem 0 .1rem;
    font-variant-numeric: tabular-nums; }}
  .clab {{ font-size: .82rem; color: var(--soft); }}
  .cmeta {{ display: flex; gap: .4rem; align-items: baseline; margin-top: .6rem; font-size: .9rem;
    font-variant-numeric: tabular-nums; }}
  .cmeta .dot {{ color: var(--faint); }}
  .cfoot {{ margin-top: .5rem; padding-top: .5rem; border-top: 1px solid var(--rule);
    font-size: .76rem; color: var(--faint); }}
  .block {{ margin-top: 2.2rem; }}
  .bh {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: .6rem; }}
  h2 {{ font-family: "Iowan Old Style",Palatino,Georgia,ui-serif,serif; font-weight: 600;
    font-size: 1.25rem; margin: 0 0 .2rem; }}
  .legend {{ display: flex; gap: .35rem; flex-wrap: wrap; }}
  .scroll {{ overflow-x: auto; margin-top: .8rem; border: 1px solid var(--rule); border-radius: 3px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .87rem; background: var(--card); }}
  .map th, .map td {{ text-align: left; padding: .6rem .7rem; border-bottom: 1px solid var(--rule);
    vertical-align: top; }}
  .map thead th {{ font-size: .68rem; text-transform: uppercase; letter-spacing: .06em;
    color: var(--faint); font-weight: 600; background: #eef1ef; position: sticky; top: 0; }}
  .rh {{ text-align: left; }}
  .anchorh {{ color: var(--accent); }}
  .id {{ color: var(--faint); font-variant-numeric: tabular-nums; font-family: ui-monospace, Menlo, monospace;
    font-size: .78rem; }}
  .cl .ct {{ max-width: 46ch; }}
  .cl .sr {{ color: var(--faint); font-size: .77rem; margin-top: .25rem; }}
  .map tbody tr.dis {{ box-shadow: inset 3px 0 0 var(--c-contrast, #b04a3f); }}
  td.rc.off .chip {{ outline: 1.5px solid #b04a3f; outline-offset: 1px; }}
  .chip {{ display: inline-block; padding: .1rem .5rem; border-radius: 3px; font-size: .77rem;
    white-space: nowrap; color: var(--c);
    background: color-mix(in srgb, var(--c) 12%, #fff);
    border: 1px solid color-mix(in srgb, var(--c) 34%, #fff); font-weight: 550; }}
  .fn {{ font-size: .8rem; color: var(--faint); margin: .7rem 0 0; max-width: 68ch; }}
  .two {{ display: grid; grid-template-columns: 1.4fr 1fr; gap: 2rem; align-items: start; }}
  ul.div {{ list-style: none; padding: 0; margin: .6rem 0 0; display: flex; flex-direction: column; gap: .5rem; }}
  ul.div li {{ font-size: .87rem; color: var(--soft); padding-left: .9rem; position: relative; }}
  ul.div li::before {{ content: ""; position: absolute; left: 0; top: .55em; width: .35rem; height: .35rem;
    background: #b04a3f; border-radius: 50%; }}
  ul.div b {{ color: var(--ink); font-variant-numeric: tabular-nums; }}
  .q {{ font-style: italic; color: var(--faint); }}
  .pw {{ margin-top: .6rem; border: 1px solid var(--rule); border-radius: 3px; }}
  .pw th, .pw td {{ padding: .45rem .7rem; border-bottom: 1px solid var(--rule); text-align: left;
    font-size: .84rem; }}
  .pw thead th {{ font-size: .68rem; text-transform: uppercase; letter-spacing: .05em; color: var(--faint); }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  code {{ font-family: ui-monospace, Menlo, monospace; font-size: .82em;
    background: #eef1ef; padding: .05rem .3rem; border-radius: 3px; }}
  .foot {{ display: flex; justify-content: space-between; flex-wrap: wrap; gap: .5rem;
    margin-top: 2.4rem; padding-top: 1rem; border-top: 1px solid var(--rule);
    font-size: .76rem; color: var(--faint); }}
  @media (max-width: 720px) {{
    .board {{ grid-template-columns: 1fr; }}
    .two {{ grid-template-columns: 1fr; gap: 1.4rem; }}
  }}
</style>
"""
Path(OUT_FILE).write_text(HTML)
print(f"Wrote {OUT_FILE}", len(HTML), "bytes")
