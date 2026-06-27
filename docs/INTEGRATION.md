# Integrating CiteVahti as a citation verifier

CiteVahti's claim-support engine can act as the citation-verification backend for another
tool — e.g. a safety/citation reviewer that asks "does the cited source actually support this
claim?" This documents the **stable seams** for that, and the semantics you must preserve.

## The one rule that makes CiteVahti safe to depend on

CiteVahti **never asserts truth**. A check returns one of four states, never a binary
pass/fail:

| `aggregate_status` / `status` | Meaning |
|---|---|
| `supported_candidate` | the cited text lexically supports the claim (a candidate, not a proof) |
| `contradiction_candidate` | the cited text appears to contradict the claim |
| `no_support_found` | the text was available but didn't support the claim |
| `unverifiable` | could not check (no text, unresolved citekey, etc.) |

**Do not collapse `unverifiable` into a failure**, and do not treat `supported_candidate` as
"true". An integrating reviewer should surface these states, not a thumbs-up/down — that is the
whole point of the workflow.

## Seams, most-stable first

### 1. CLI — `claim-check --json` (recommended for cross-language / process isolation)

```bash
citevahti claim-check --claim "Aspirin reduces cardiovascular events." \
                      --citekey smith2020 --json
```

Emits **only** the `ClaimCheckResult` JSON on stdout (no human lines), so any language can
parse it. Exit code is `0` unless the aggregate is `unverifiable` (then `1`). This is the
**stable contract** — the schema below is what you build against.

```jsonc
{
  "claim_text": "…",
  "aggregate_status": "unverifiable",          // one of the 4 states above
  "require_page": false,
  "per_citekey": [
    {
      "citekey": "smith2020",
      "status": "unverifiable",                // per-citekey, same 4 states
      "zotero_key": null,
      "reason": "citekey_unresolved",
      "score": null,                           // 0..1 lexical support score when computed
      "polarity_cue": null,                    // the negation word that flipped polarity, if any
      "passages": []                           // supporting quotes, when found
    }
  ],
  "warnings": [],
  "provenance": { "tool": "claim_check", "tool_version": "…", "ran_at": "…", "sources": [ … ] }
}
```

Note: this path resolves citekeys against a **Zotero** library for the source text, so it fits
callers that share the user's Zotero. For a caller that already *has* the source text and just
wants a claim-vs-text check, see the in-process primitive below.

### 2. In-process (Python) — the engine functions

```python
from citevahti import tools

# claim vs a specific text blob — fully offline, no Zotero, no ledger:
result = tools.claim_lexical_check(claim_text, source_text)   # -> dict

# claim vs citekeys resolved through Zotero:
result = tools.claim_check(claim_text, citekeys=["smith2020"])  # -> ClaimCheckResult
```

`claim_lexical_check(claim, text)` is the most decoupled primitive for an external safety
reviewer — give it the claim and the cited source's text, get back the structured verdict.
(A `--json` CLI for this offline one-shot can be added on request; it isn't exposed yet.)

### 3. MCP — `verify_claims`

The `citevahti-mcp` server exposes `verify_claims`, a read-only **4-state report over a whole
`.citevahti` ledger**. Use this only if you're already orchestrating via MCP and operating on
a CiteVahti ledger — it's heavier than a one-shot check.

## Recommended integration pattern

Define a verifier seam in your code and keep CiteVahti behind an adapter — exactly the
`CITATION_VERIFIER=local|citevahti` shape:

- `local` → a mock/heuristic (so tests and CI run without CiteVahti installed).
- `citevahti` → calls one of the seams above and maps the 4-state result into your model.
- **Pin the CiteVahti version.** The engine API is not yet frozen; the `claim-check --json`
  schema is the most stable surface, and your adapter is what insulates you from change.

## What NOT to use

- **The loopback HTTP panel (`/api/…`)** is CiteVahti's single-user UI backend — CSRF-token
  gated (`X-CiteVahti-Token`, `GET /api/session`), bound to `127.0.0.1`, and its contract
  shifts with the panel. It is **not** an integration API.
- **FullVahti** is the planned Zotero plugin for fetching open-access PDFs and writing citekeys
  back — it is **not** a verification surface. Verification lives in the claim-check engine.

If you need a frozen, versioned verifier contract (a guaranteed-stable `claim-check --json`
schema, or an offline `claim_lexical_check --json` CLI), open an issue — that seam can be
committed to and held stable across releases.
