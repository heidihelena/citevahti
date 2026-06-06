# Security & integrity policy

CiteVahti's value rests on a small set of **safety invariants** (see
[`docs/SAFETY_INVARIANTS.md`](docs/SAFETY_INVARIANTS.md)). A bug that lets any of
them be bypassed is a security issue, even if no traditional vulnerability is
involved. In particular:

- a **silent or unconfirmed Zotero write**, or a write that isn't undoable;
- a **blinding leak** — the AI's support rating becoming visible before the human
  commits theirs;
- **credential exposure** (a Zotero key written outside the OS keychain, logged, or
  echoed);
- a **dedupe / guard bypass**, or **fabricated provenance** in the audit log.

## Reporting

Please report privately — **do not open a public issue first**.

- Preferred: GitHub **"Report a vulnerability"** (Security → Advisories → private
  vulnerability reporting) on this repository.
- We aim to acknowledge within a few days and to credit reporters who want it.

When you can, include: the invariant you think is affected, a minimal repro (the
project is fully offline-testable with fake seams — no live Zotero/PubMed needed),
and the version (`citevahti --version` / the extension version).

## Scope

This is **single-user, local-first, PubMed-only** software: it stores state under
`.citevahti/` on your machine, holds the Zotero key only in the OS keychain, and
makes no telemetry or cloud calls. Reports about the local trust boundary (keychain
handling, the loopback panel, the constrained MCP agent surface) are in scope.

## Supported versions

The latest published release on PyPI receives fixes. Older versions are best-effort.
