# ADR-0002 — UI delivery model + the `[oo/o/r/d]` review layer

- **Status:** Accepted (2026-06-03)
- **Relates to:** ADR-0001 (the ledger this UI sits on top of). Refines the
  manifesto's UI section and **supersedes its colour assignments** (see §4).

## 1. Context

The product is the evidence-decision ledger (ADR-0001). It needs a human surface
that fits *coders and researchers writing manuscripts with AI agents* — sparse,
keyboard-native, and non-interrupting. A brand + design brief (the "citation
raccoon" package) supplies a coherent visual language built directly from the
logo.

**The logo is the system.** [`docs/design/logo.svg`](../design/logo.svg) is
*citation brackets* `[ ]` around two angular eye-mask forms — a raccoon "sorting
evidence." So `[oo]` (the two eyes inside brackets) is literally the **Supported**
state; flat-black ink is "identity and structure." The mark depicts the best
outcome.

## 2. Decision

1. **Delivery = an inline review layer in the writing surface — NOT a dashboard.**
   The product must live *inside* where people write and chat-and-code their
   manuscripts. A separate four-tab "citation app" you switch to (Setup / Claims /
   Evidence / Changes — the original skill spec's structure) **sits outside the
   workflow and is the wrong frame**; it is demoted to *at most* a secondary
   companion panel. First target: a **VS Code extension** over Markdown / LaTeX /
   manuscript text + the Zotero API — claim spans highlighted in place, keyboard
   `oo/o/r/d`, a hover/popover evidence card, and the agent proposing edits as
   inline diffs. **Not** Codex Cloud / Claude web as the primary surface — those
   are the *agent that builds/edits*, not the review UI. (Mockups:
   `mockups/zotsynth-inline/` is the primary form; `mockups/zotsynth-ui/` is the
   demoted dashboard. Feasibility in `docs/design/review-layer.md`.)
2. **The review layer is four keyboard fit-codes** over a claim span, operational
   not moral: `oo` supported · `o` partly supported · `r` revise · `d` delete
   candidate. They are **affordances over the ledger**, not a new truth model —
   the full 6-value support vocabulary + adjudication still live underneath and
   are shown in the evidence card (§3).
3. **Palette: four DISTINCT status hues + lilac brand. No green, no fire-red.**
   The four codes get four visually distinct colours so they're tellable apart at
   a glance (an accessibility fix — two yellows / two lilacs were
   indistinguishable): `oo` **amber/gold** (usable evidence), `o` **teal**
   (partial), `r` **violet/lilac** (human action), `d` **rose** (remove
   candidate). Lilac/violet stays the brand + chrome colour. We still avoid
   green's "approved/safe" stamp and fire-red's "error/punitive" feel — delete is
   *rose* ("remove"), not red — keeping ADR-0001's "trust from visible
   uncertainty, not a truth-policing judge". **Colour is never the only cue:** the
   bracketed code (`[oo]`/`[o ]`/`[r ]`/`[d ]`) is always shown. Exact light+dark
   values in [`../design/tokens.css`](../design/tokens.css).
4. **Labels stay visible** (`[d ] Delete`, never a bare `[d]`) and **claim text is
   never silently edited** — a revise/replace shows an inline diff and requires
   confirmation (the no-silent-write principle, extended to the manuscript).
5. **Two distinct deletions — both offered on the `d` card.** "**Delete candidate**"
   removes the *source candidate* from the claim's evidence list (safe, common —
   a `reject` decision; the claim and sentence stay). "**Delete candidate +
   claim**" additionally removes the *claim text* — the more destructive option,
   shown as a **diff (struck), never silent**, and undoable.

## 3. Mapping the fit-codes onto the ledger (ADR-0001)

The codes drive the existing engine; they don't bypass it.

| Code | Label | Palette | Action | Ledger meaning |
|---|---|---|---|---|
| `[oo]` | Supported | yellow (filled) | Add to Zotero | final decision `accept`; support `directly_supports` + strong PICO fit |
| `[o ]` | Partly supported | pale yellow | Cite with caution / revise claim | support `partially_supports` / `indirectly_supports`; decision `accepted_with_caution` |
| `[r ]` | Revise | pale lilac | Review/edit claim or rating | `needs_second_review`, or a diff-gated claim-text revision |
| `[d ]` | Delete | stronger lilac | Remove source candidate | final decision `reject` (drops the candidate; **never** deletes the Zotero item or the sentence) |

The evidence card behind a span carries the complexity: claim, candidate, evidence
excerpt, the AI vs human support ratings (visible disagreement), PICO fit, the
rationale, a suggested revision, and the actions (Add to Zotero / Revise claim /
Change reference / Delete candidate / Send to human review). On the `r` card the
two fixes are explicit — **Revise claim** (reword via the diff) and **Change
reference** (swap a better-fitting paper). "Add to Zotero" runs the
**decision-gated, undoable write transaction** (ADR-0001 step 5) — so even the
prettiest button still obeys every integrity invariant, including undo.

## 4. Supersedes: the manifesto's colour assignments

The original manifesto proposed `green = supported, yellow = review, red =
unsupported, lilac = product`. **This ADR replaces those RGB assignments.** The
first cut used only yellow + lilac, but two yellows (oo/o) and two lilacs (r/d)
proved indistinguishable, so the accepted palette uses **four distinct hues —
amber / teal / violet / rose** — keeping the manifesto's *principle* (no
truth-policing colours): no green ("approved/safe"), and delete is **rose, not
fire-red** (`#FF9999` from the brief's sketch is *not* adopted — too punitive).
Lilac/violet remains the brand. Exact values in
[`docs/design/tokens.css`](../design/tokens.css).

## 5. Consequences

- **Positive:** a keyboard-native review layer that doesn't interrupt writing;
  colours that read as a research *instrument*, not an automated *judge*; every
  "Add to Zotero" inherits the audited, undoable transaction; one coherent palette
  derived from the logo.
- **Cost / scope:** building the VS Code extension (decorations, webview, stable
  span anchoring across edits, inline diffs) is real front-end work — and it is
  **after** the local ledger per ADR-0001 D3. This ADR records the design so it's
  ready; it does not move the build order.
- **Carried forward:** read-only Zotero local API; decision-gated writes; no
  silent edits (now including manuscript text); secrets posture.

## 6. Build target order (design-ready, not yet scheduled)
1. VS Code extension + Markdown/LaTeX + Zotero API (the safe technical target).
2. Then a web editor; Word import/export; Google Docs later.
Do **not** start with Codex Cloud / chat as the primary ZotSynth surface.
