# CiteVahti review layer — design reference

Companion to [ADR-0002](../adr/0002-ui-delivery-and-review-layer.md). Colours and
status classes live in [`tokens.css`](tokens.css). The brand mark
([`logo.svg`](logo.svg)) is flat-black citation brackets around two eye-masks —
`[oo]` is the Supported state itself.

## The fit-codes (keyboard-native)
A claim span carries one code. Type it to act; the popup carries the detail.

```
[oo] Supported        amber/gold    Add to Zotero
[o ] Partly supported teal          Cite with caution / revise claim
[r ] Revise           violet/lilac  Review/edit (claim or rating)
[d ] Delete           rose          Remove source candidate
```
Four distinct hues so the codes are tellable apart (accessibility); lilac/violet
stays the brand. No green; delete is rose, not fire-red. The bracketed code is
always shown — colour is never the only cue.

Operational, not moral. `oo`=complete fit, `o`=partial fit, `r`=work remains,
`d`=remove candidate. Always render the **label with the code** (`[d ] Delete`,
not `[d]`): keyboard users type `d`; visual users need the word.

## The evidence card (behind a highlighted span)
Compact, coder-first. Shows visible AI–human disagreement (trust comes from that,
not from a single score).

```
[ r ] Revise
Claim:    "Vitamin D improves diagnostic accuracy."
Issue:    Source discusses association, not diagnostic improvement.
Evidence: "...higher 25(OH)D was associated with ..."   (excerpt + locator)
Fit:      Population ✓  Intervention ~  Outcome ✗  Claim ~
AI:       partially_supports (conf 0.6)
Human:    —  (your turn; AI hidden until you rate, in blinded mode)
Suggested revision: "Higher vitamin D levels were associated with better
                     diagnostic performance in some models."
Actions:  Revise claim · Change reference · Delete candidate · Send to human review · Open paper
```

For `[oo]` the card shows the PICO checks (Population/Outcome/Direction/Study-type
match) and a single action: **Add verified citation to Zotero** — which runs the
decision-gated, undoable write transaction (ADR-0001 step 5).

## The user flow
1. User writes normally.
2. CiteVahti marks claim spans (claim extraction is AI-*proposed*, human-confirmed).
3. User reviews line by line: `oo` accept · `o` partly · `r` revise · `d` delete candidate.
4. `[r ]` → the agent proposes a rewritten claim **as an inline diff** (never silent).
5. `[d ]` → removes the *candidate citation link*, not the sentence.
6. The popup shows the evidence basis before any Zotero hand-off.

## Two deletions (the `d` card offers both)
- **Delete candidate** — safe, common: the claim stays; the paper leaves the
  claim's evidence list. This is a `reject` decision in the ledger.
- **Delete candidate + claim** — also removes the claim text. Separate, more
  destructive, **diff-gated**, explicit confirm, undoable. The agent must never
  silently delete or rewrite a claim. Example:
  *"Coffee causes dehydration."* → *"Coffee intake was not associated with
  increased dehydration markers in the cited study."* — shown as a diff.

## Architecture (four layers)
- **Editor layer** — decorations, keyboard shortcuts, click handlers, hovers.
- **CiteVahti analysis layer** — claim extraction, source matching, evidence
  excerpting, fit classification (`oo/o/r/d`), revision proposal. (= the ledger.)
- **Agent layer** — applies edits, removes source candidates, generates the claim
  rewrite (diff), opens the Zotero hand-off.
- **Zotero layer** — item lookup, citation insertion, note creation, audit trail.

## Feasibility by environment (why VS Code first)
| Environment | Inline colours | Click span | Agent edits | CiteVahti popup | Difficulty |
|---|---|---|---|---|---|
| Custom CiteVahti web editor | yes | yes | yes | yes | easy |
| **VS Code extension** | **yes** | **yes** | **yes** | **yes** | **moderate** ← target |
| Cursor / Windsurf | likely | likely | likely | likely | moderate |
| Codex IDE extension | depends on API | partial | yes | partial | moderate-hard |
| Codex Cloud web | limited | limited | via repo edits | not ideal | hard |
| Claude Code in VS Code | yes (extension layer) | yes | yes | yes | moderate |
| Claude web/chat | limited | limited | no native doc editing | limited | hard |

VS Code is the safest target: its extension API exposes editor decorations,
webviews, commands, diagnostics, hovers, and quick-fix actions. Use Codex / Claude
Code as the **agent that builds and edits CiteVahti**, not as the primary user
surface.

## Effort
- **Easy:** highlight spans, badges, keyboard codes, popup/card, audit status,
  simple edits, remove candidate source, export to Zotero.
- **Moderate:** high-quality claim extraction; mapping claim spans to source
  evidence; keeping highlights stable across edits; clean inline diffs;
  multi-citation claims.
- **Hard / avoid:** doing this inside Codex Cloud or Claude chat; editing Word
  docs directly with perfect citation preservation; silently resolving
  contradictory evidence; making support judgments without a human-visible
  rationale.
