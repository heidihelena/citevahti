# Local evidence map — mockups

Static, **mockups-first** exploration of the real claim↔evidence graph for the panel's
**Atlas** tab. Today that tab is titled "Local evidence map" but only renders the
de-identified warehouse toggles + the Contribute-to-Atlas flow — there is no actual
map. This is the map.

Follows the repo's established pattern (cf. `mockups/citevahti-inline-v2/`): plain
HTML/CSS/JS, no build step, **no external CDN / graph library** (the panel is offline)
— everything is hand-built SVG. Read-only, local-first, and styled entirely from the
shipping design tokens copied verbatim from `src/citevahti/panel/web/styles.css`
(`docs/DESIGN_SYSTEM.md`).

Open `index.html` directly in a browser (no server needed).

## What it shows

- **Nodes** — claims (lilac disc, `C1`…) and the cited papers tested against them (open circle).
- **Edges** — one per claim↔paper link, **coloured by your decision** and always paired
  with the bracketed code, so colour is never the only cue (same rule as the manuscript):

  | Verdict | Hue | Code |
  |---|---|---|
  | Accept | amber | `[oo]` |
  | Caution | teal | `[o ]` |
  | Needs review | violet | `[r ]` |
  | Reject | rose | `[d ]` |
  | Unrated (candidate, not yet judged) | lilac, **dashed** | `[  ]` |

- **Click** any node → its links light up, everything else dims, and a flyout lists each
  linked paper/claim with its **support rating** (directly/partially/…) and **verdict**.
  Click empty space to clear. Theme toggle mirrors the panel's light/dark.

All of this is powered by data the engine **already has** — no new capture. The live
panel would build it from an `EvidenceMap` (`schemas/evidence_map.py`: nodes + `supports`
links) assembled from the ledger's claims, candidates, ratings and decisions. `data.js`
is a static stand-in; the domain (thoracic-oncology LDCT screening) mirrors the inline-v2
mockup so the two read as one product.

## Showing the AI second opinion

A segmented control in the bar picks how much of the AI you see. **Your decisions** is the
default and the safe view — human decisions only. The other two reveal the AI:

- **+ AI 25%** — overlays the AI's rating as a **faint 25%-opacity parallel strand**
  beside each solid human edge. Deliberately subordinate: the AI reads as a *suggestion*,
  your decision is always the solid edge.
- **AI view** — a dedicated mode where edges are coloured by the *AI's* rating instead of
  your decision. Cleaner and safer than the overlay for studying the AI on its own, because
  the two are never visually blended. A banner names the mode so it's never mistaken for
  your verdicts.

The AI produces a claim-*support* value (not a decision), mapped to the same hue family a
decision would land on: directly-supports → amber, partially/indirectly → teal, unclear →
lilac, does-not-support → violet, contradicts → rose. The flyout states agreement in words
— **AI concurs** / **AI differs** — so colour is never the only cue.

### Blinding — the AI is revealed only *after* your judgement

In every mode, the AI's rating on a link stays hidden until **you** have judged that link.
A link you haven't rated shows as a neutral **grey dashed "awaiting your judgement" ghost**;
its flyout says *"AI opinion hidden until you judge · blinded"* rather than leaking the AI
value. This mirrors the engine's human-first blinding invariant — the AI never anchors your
call, on the map or in the reviewer.

### Retracted sources — a fact, shown always

A retracted paper (from the retraction scan — `schemas/candidate.py` `retracted`) is
flagged on the map with a **rose ⊘ ring, independent of any rating**. Because retraction is
a *fact*, not a judgement, it shows even on links you haven't judged yet (see *Nodule-Mgmt*:
retracted, rejected for one claim, still-unjudged for another — the ⊘ holds in both).

## The three variants

Pick one (or a primary + a drill-down) to take forward into a panel PR.

### 1 · Constellation — whole-corpus overview
A force-directed node-link map of every claim and paper at once (deterministic layout —
no randomness, stable across reloads). Best for the "how healthy is my evidence base?"
glance: clusters of amber = well-supported, a lonely rose/violet claim jumps out.
Trade-off: gets busy as the corpus grows; layout is the least predictable.

### 2 · Spine — claims ↔ papers, side by side
A bipartite view: claims in a left column (the "spine", matching the product's core
metaphor), papers on the right, edges between. Papers are ordered to minimise crossings.
Best for legibility and scanning — you can read every claim's wording and follow its
edges. Scales more gracefully (add rows) and is the most predictable layout. Trade-off:
less of a "map" feel; long claim text is truncated.

### 3 · Orbit — one claim in focus
An ego-network: the selected claim sits centre, its candidate papers orbit it, grouped
into verdict sectors (accept up top, reject/review below) with distance hinting at
support polarity. A claim picker rail switches focus. Best for **deep review of a single
claim** — the natural companion to the inline reviewer. Trade-off: shows one claim at a
time, so it's a drill-down, not an overview.

**Suggested combination:** Spine or Constellation as the Atlas landing view, with Orbit
as the click-through when you focus a claim.

## Not in scope here (deliberately)

- No editing/rating from the map — read-only by design; decisions stay in the inline
  reviewer where the blinded human-first protocol is enforced.
- No real data wiring — that's the follow-up panel PR (add `GET /api/evidence-map`,
  render into surface `#atlas`, keep the warehouse/contribute flow as a second section
  or its own tab).
- If a real corpus proves too large for plain SVG, a graph lib would need to be
  **vendored** (offline constraint) — but SVG is the starting point per the brief.

## Files
- `index.html` — surface shell + variant switcher
- `styles.css` — design tokens (copied from the panel) + graph styles
- `data.js` — static mock ledger (claims, papers, edges with ratings + decisions)
- `app.js` — the three SVG renderers + shared select/inspect interaction
