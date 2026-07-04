# CiteVahti — worked examples for reviewers

These are runnable, self-contained examples for evaluating the CiteVahti Claude Desktop
extension. **No Zotero account, no API key, and no network are required** — every example
runs against a synthetic demo ledger, so an empty reviewer account still exercises the real
workflow.

## One-time setup (≈1 minute)

The extension bundles the CiteVahti MCP server; no separate install is needed. To create the
synthetic ledger the examples use:

```
citevahti demo          # builds ~/CiteVahti-demo with a sample manuscript + claims
```

(Or point any example at your own project folder instead — the tools take a `--root` /
project path.) Then, in Claude Desktop, confirm the extension is connected: the assistant
should list CiteVahti tools such as `status`, `triage`, and the `run_claim_tests` prompt.

## Example 1 — "What's the status of my review?" (read-only)

**Prompt to Claude:**
> Using CiteVahti, show me the status of my review in `~/CiteVahti-demo` and list the claims
> that still need my attention.

**What happens:** Claude calls `status` (read-only) then `triage` (read-only). No data is
written.

**Expected outcome:** a version + connections summary, then a worst-first list of the demo
claims needing attention, each with a plain reason and next action (e.g. *"raters disagree —
adjudicate"*, *"no accepted supporting citation yet"*). Nothing is rated or decided for you.

## Example 2 — "Run the claim-test review" (the core loop, human-first)

**Prompt to Claude:**
> Run the `run_claim_tests` prompt on my manuscript in `~/CiteVahti-demo`.

**What happens:** the `run_claim_tests` prompt choreographs the blinded loop over the existing
tools — surface a claim and its candidate evidence, then **stop and ask you to rate first.**
The AI's own second opinion stays sealed until your human rating is recorded. Reviewing writes
nothing to Zotero (the demo has no Zotero connected); any write would be previewed and require
your explicit confirmation.

**Expected outcome:** Claude walks one demo claim through *rate → reveal → decide*, never
showing the AI rating before yours, and never auto-accepting. This demonstrates the core
safety property: **the human is the decider; the AI is a blinded advisory second rater.**

## Example 3 — "Check a paragraph I'm drafting" (read-only, everyday loop)

**Prompt to Claude:**
> Use CiteVahti's `check_paragraph` on this text against `~/CiteVahti-demo`:
> *"Structured telephone follow-up reduces avoidable readmissions after day surgery."*

**What happens:** Claude calls the read-only `check_paragraph` tool, which matches each
sentence against the demo ledger and reports, per sentence, whether it is already reviewed,
needs attention, or is new — routing any new work to `run_claim_tests`. It rates and decides
nothing.

**Expected outcome:** a per-sentence verdict (reviewed ✓ / attention ⚠ with a reason / new •)
tying the drafted sentence back to a demo claim, so you can see what still needs evidence
before you cite it.

## Known limitations

- CiteVahti records whether a cited source **supports** a claim; it does not determine truth,
  and it is **not a medical device and gives no clinical advice.**
- The AI second rating is **optional and off by default** (Claude Desktop / local model /
  bring-your-own-key); every mode stays blinded until your human rating exists.
- Zotero write-back and live literature search need you to connect Zotero / provide contact
  details for PubMed; the examples above deliberately avoid them so they run offline.

## Support

Issues and questions: <https://github.com/heidihelena/citevahti/issues> ·
<https://vahtian.com/citevahti>
