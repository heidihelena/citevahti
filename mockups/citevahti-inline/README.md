# CiteVahti inline review layer (the primary surface)

Open `index.html`. This is the **right** form of CiteVahti: citation integrity
**inside the writing surface**, not a separate dashboard you switch to. Academics
will chat-and-code their manuscripts; the review has to live in the document.

You review a claim **in place**:
- `j` / `k` (or ↑/↓) move between claim spans; click a span to select it.
- Type the fit code: `o``o` = **supported**, `o` = **partly**, `r` = **revise**,
  `d` = **delete candidate**.
- The evidence card (right) updates live; the agent lane (bottom) narrates the
  chat-and-code action.

What each code does (mapped to the ledger):
- `[oo]` **supported** → *Add to Zotero* via the decision-gated, **undoable**
  transaction (never silent).
- `[o ]` **partly** → cite with caution, or ask the agent to revise the wording.
- `[r ]` **revise** → the agent proposes a claim rewrite as an **inline diff**;
  it never edits your text without confirm (try *Accept revision*).
- `[d ]` **delete** → removes the **source candidate** only; your claim and
  sentence stay (the `[n]` marker is struck, not the text).

Colours are four distinct hues so the codes are tellable apart: **amber** = oo ·
**teal** = o · **violet** = r · **rose** = d (lilac stays the brand). The
bracketed code is always shown, so colour is never the only cue.

Dark-first (coder world); toggle light in the top bar. Static mockup — no real
Zotero/PubMed calls; the live behaviour is in the CLI/engine.

> The `citevahti-ui/` four-tab dashboard is the **legacy** frame (it sits outside
> the workflow). At most it's a secondary companion panel — see ADR-0002.
