# Citation tests in CI and pre-commit

CiteVahti's report commands have CI semantics: a stable exit code, JSON output,
and no network or Zotero required for the claim report (it reads only the
`.citevahti/` ledger). The manuscript is the code; this is how you fail the
build on an unsupported claim.

## Exit codes

| Command | Exit 0 | Exit ≠ 0 |
|---|---|---|
| `citevahti claim-report` (alias `report`) | no claim needs attention | ≥ 1 claim is `needs_support` or `review_needed` (`[u] untestable` does **not** fail the build) |
| `citevahti bib-sync --fail-on-orphans` | every citekey resolves | an orphan citekey exists (writes nothing on failure) |
| `citevahti verify-audit` | audit chain intact | chain broken (exit 2) |

Machine-readable output for any of the claim-spine commands: add `--json`
(`claim-add`, `claim-list`, `claim-untestable`, `candidate-list`, the whole
`claim-support-*` chain, `claim-decide`, `decision-list`, `claim-report`,
`literature-search`, `claim-commit`, `txn-undo`). Ids flow end-to-end without
scraping stdout:

```bash
claim_id=$(citevahti claim-add --text "..." --type effectiveness --json | jq -r .claim_id)
```

## Pre-commit hook

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: citevahti-claims
        name: claim tests (CiteVahti)
        entry: citevahti claim-report
        language: system
        pass_filenames: false
        always_run: true
      - id: citevahti-citekeys
        name: citekey orphans (CiteVahti + Better BibTeX)
        entry: citevahti bib-sync --fail-on-orphans
        language: system
        pass_filenames: false
        always_run: true
```

The claim hook is pure ledger — it runs anywhere. The citekey hook needs a
**running Zotero with Better BibTeX** (JSON-RPC) to resolve keys, so it works
as a local pre-commit hook but not on a headless runner — see the limitation
below.

## GitHub Action

```yaml
name: claim-tests
on: [push, pull_request]
jobs:
  claims:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install citevahti
      # The ledger (.citevahti/) must be committed or restored for this to
      # mean anything — the report reads it, not the manuscript.
      - name: Claim tests
        run: citevahti claim-report --format md --output integrity.md
      - name: Audit chain intact
        run: citevahti verify-audit
      - name: Upload integrity report
        if: always()
        uses: actions/upload-artifact@v4
        with: { name: citation-integrity-report, path: integrity.md }
```

`claim-report` exits non-zero when any claim needs attention, failing the job;
the Markdown report is uploaded either way so reviewers can read **why**.

## Known limitation: Better BibTeX is local-only

`bib-sync` resolves citekeys through Better BibTeX's JSON-RPC on the running
Zotero — there is no headless mode. Run the citekey-orphan check as a
**local** pre-commit hook; keep CI to the ledger-only checks (`claim-report`,
`verify-audit`), which need no Zotero, no BBT, and no network.

## What a red build means

A failing claim test means *the ledger records no accepted, supporting
citation for that claim* — not that the claim is false. The fix is the normal
loop: search → link → blind-rate → decide (or mark a non-indexed source
`claim-untestable --reason "…"`). See `docs/QUICKSTART.md` §4–7.
