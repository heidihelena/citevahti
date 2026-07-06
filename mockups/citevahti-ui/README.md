# CiteVahti UI mockup — DASHBOARD (legacy / secondary)

> **This four-tab dashboard is the legacy frame.** A separate app you switch to
> sits *outside* the writing workflow — and academics will chat-and-code their
> manuscripts, not alt-tab to a citation dashboard. The **primary** surface is the
> inline review layer in `../citevahti-inline/` (ADR-0002). Keep this only as an
> on-palette reference, or as a possible secondary companion panel.

A static, no-build mockup of the four-tab surface (Setup / Check claims /
Evidence / Changes), skinned to **ADR-0002**. Open `index.html` in a browser
(light + dark via `prefers-color-scheme`).

Palette law (see `../../docs/design/tokens.css`):
- Four **distinct status hues** so the codes are tellable apart: **amber** = `oo`
  supported · **teal** = `o` partly · **violet** = `r` revise · **rose** = `d`
  delete-candidate.
- **lilac/violet** = brand + chrome (wordmark, primary buttons, focus, nav).
- **ink + white** = identity & structure (the `[oo]` bracket-eyes mark, text, surfaces).
- No green; delete is rose, not fire-red. The bracketed code is always shown —
  citation support is a research instrument, not an automated judge.

Fit codes (operational, not moral): `[oo]` Supported → Add to Zotero ·
`[o ]` Partly → cite with caution · `[r ]` Revise → human review ·
`[d ]` Delete → remove source candidate (the claim/sentence stay). Labels are
always shown with the code. This is a visual mockup only — no real Zotero/PubMed
calls; the live behaviour lives in the CLI/engine.
