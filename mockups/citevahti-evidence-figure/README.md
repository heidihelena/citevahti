# Evidence-map figure — publication system

The Spine layout (chosen in the evidence-map review as the one worth publishing) hardened
into a **directly publishable figure system**. It encodes, as engineering, the acceptance
conditions from the editorial critique:

- **Survives greyscale + colour-vision deficiency.** Verdict is carried by *two* redundant
  non-colour channels — a line **dash pattern** and the bracketed **status code** — both
  tied to colour in the legend. Accept = heavy solid, Caution = light solid, Needs-review =
  dashed, Reject = dotted, Unrated = faint long-dash. Flip **Ink → Greyscale** to proof it.
- **Legend, N and framing live *inside* the figure** (figures travel apart from captions):
  a verdict legend, a retraction key, `N = claims · papers · links`, a ledger-snapshot date,
  and an honest-framing footer — *"displays adjudicated human judgements … does not assert
  that any claim is true."*
- **Retraction is a fact, always shown.** A retracted source gets a ⊘ ring independent of
  any rating (`schemas/candidate.py` `retracted`) — visible even on unjudged links.
- **AI shown only after human judgement.** In **AI view**, edges recolour by the AI rating,
  but only where you've already judged; unjudged links stay grey-dashed "awaiting judgement"
  ghosts and the AI stays blinded. The default **Adjudicated** view is human decisions only.
- **Reproducible.** Deterministic layout; papers ordered to minimise crossings; no randomness.

## Export — vector, journal-sized

- **Download SVG** — a self-contained vector file (literal colours, embedded typography, no
  external refs or CSS variables) sized in **mm** to the chosen column width. This is the
  format journals want; it validated as a clean standalone SVG document.
- **Print / PDF** — a print stylesheet isolates the figure sheet, so "Save as PDF" yields the
  figure alone at its column width.
- **Copy caption** — an auto-generated submission caption: description, mode, retraction note,
  colour/dash accessibility note, honest framing, N, ledger snapshot, and the **claim key**
  (C1…Cn → full claim text, since the plot shows numbered claims + a short gloss).

## Controls
- **Width** — Single 89 mm · 1.5 col 120 mm · Double 183 mm (Lancet column widths).
- **Mapping** — Adjudicated (human decisions, the honest primary) · AI view.
- **Ink** — Colour · Greyscale (print-survival proof).

## Files
- `index.html` — page shell + toolbar + figure sheet + caption panel
- `figure.css` — screen chrome (design tokens) + `@media print` isolation
- `figure.js` — the self-contained SVG figure builder + SVG/print/caption export
- `data.js` — mock ledger (adds a short `gloss` per claim for in-figure labels)

Open `index.html` directly — no server needed. Static mockup; the live panel would build the
same figure from `GET /api/evidence-map`. Not wired into the panel — this is for review first,
per the mockups-first pattern.
