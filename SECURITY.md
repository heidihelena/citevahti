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

## Security regression suite

The controls protecting the local trust boundary are guarded by a dedicated, offline
regression group — run it alone with `pytest -m security`:

| Control | Threat it counters | Guarding test |
|---|---|---|
| Loopback panel: reject non-loopback `Host` | DNS-rebinding | `test_panel_csrf.py` |
| Loopback panel: reject cross-origin `Origin`, require `application/json` | CSRF / cross-origin simple-request POST | `test_panel_csrf.py` |
| Loopback panel: per-session CSRF token (`X-CiteVahti-Token`) | forged writes; a header-parser edge case | `test_panel_csrf.py` |
| Deterministic blinding — one rule (`rating/blinding.py`), all surfaces agree | a blinding leak (AI value visible before the human rates) | `test_blinding_deterministic.py`, `test_panel_api.py::test_blinding_is_consistent_across_surfaces` |
| Write path: filename sanitised (`_safe_md_name`) | path traversal out of the manuscripts dir | `test_panel_api.py::test_paste_manuscript_rejects_path_traversal` |
| Constrained agent surface (allow-list + `assert_safe_surface`) | a tool reaching beyond its sanctioned power | `test_agent_surface.py` |
| Decision-file tamper detection | a hand-edited `accept` slipping past the audit | `test_decision_tamper_integrity.py` |
| Read-only views never mutate the ledger | a "report" silently writing/auditing | `test_readonly_tools_dont_mutate.py` |
| Timestamp client: refuse a non-`http(s)` `tsa_url` before opening it | SSRF / local-file read via a `file://` config-supplied TSA URL | `test_timestamp.py::test_rfc3161_rejects_non_http_tsa_url_without_touching_the_filesystem` |
| Sidecars exit when the shell dies (`--parent-pid` watchdog) | an orphaned engine/agent server invisibly outliving the app after a Force Quit or shell crash | `test_parentwatch.py` |
| Supervisor requires the runtime heartbeat's pid to be its own child's | an orphan's heartbeat impersonating a healthy sidecar (masking the real child's death) | `test_supervisor.py::test_probe_distrusts_a_foreign_runtime_heartbeat` |

These complement — they don't replace — the full [safety-invariant](docs/SAFETY_INVARIANTS.md)
table, which the whole offline suite guards. Adding a security control? Mark its test
`@pytest.mark.security` (or `pytestmark = pytest.mark.security` at module level) and add a row here.

## Scope

This is **single-user, local-first** software: it stores state under `.citevahti/` on
your machine, holds the Zotero key only in the OS keychain, and sends **no telemetry**.
Its only outbound calls are: literature lookups to **PubMed (NCBI), OpenAlex, Semantic
Scholar, and Crossref/doi.org** (carrying search queries and the DOIs/PMIDs you look up);
**your Zotero**, if you connect it; — only if you enable opt-in timestamping — the
**audit-head hash** to the RFC 3161 authority you configure; and — only when you ask
(the `check-update` command, the panel's *Check for updates* button, or the `check_update`
agent tool) — a single request to **PyPI** to see if a newer release exists (no data about
you, never auto-installs). Reports about the local trust boundary (keychain handling, the
loopback panel, the constrained MCP agent surface, and what crosses these outbound
boundaries) are in scope.

## Supported versions

The latest published release on PyPI receives fixes. Older versions are best-effort.
