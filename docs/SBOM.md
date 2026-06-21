# Software bill of materials (SBOM) & dependency posture

CiteVahti keeps its dependency graph **deliberately small** — auditability is a
product property, not just an aspiration. This page lists what the package pulls
in and how to verify it yourself.

## Runtime dependencies (always installed)

| Package | Constraint | Why |
|---|---|---|
| `pydantic` | `>=2.13.4` | typed schemas for the ledger (claims, ratings, decisions, audit) |
| `httpx` | `>=0.28.1` | HTTP client for Zotero local API, Better BibTeX, and literature providers |
| `pypandoc` | `>=1.13` | tiny wrapper used for Markdown→Word export; **the Pandoc binary itself is NOT bundled** — it is fetched once, at runtime, only on the first Word export (see [citation_export](../src/citevahti/report/citation_export.py)) |

That's the entire required runtime surface.

## Optional extras (opt-in)

| Extra | Package | Enables |
|---|---|---|
| `mcp` | `mcp>=1.27.2` | the MCP server (chat-client integration) |
| `keyring` | `keyring>=25.7.0` | OS-native secret store for the Zotero key |
| `timestamp` | `asn1crypto>=1.5.1` | RFC-3161 timestamping of the audit head |
| `docx` | `python-docx>=1.1.0` | Word **import** and the integrity-report `.docx` |
| `dev` | `pytest>=9.1.0` | the test suite |

The VS Code extension's dependencies (`@types/*`, `typescript`, `@vscode/vsce`)
are **dev-only** and never ship to end users.

## Generate a full CycloneDX SBOM

```bash
pip install cyclonedx-bom
cyclonedx-py environment > citevahti-sbom.json   # full transitive tree, CycloneDX 1.6
```

## Check for known vulnerabilities

```bash
pip install pip-audit
pip-audit                      # audits the installed environment against OSV/PyPI advisories
```

## Network egress (what leaves the machine, when)

- **Nothing by default.** The panel binds to `127.0.0.1`; there is no telemetry.
- **Literature lookups** (only when you run them) send the search query and
  identifiers to PubMed / OpenAlex / Semantic Scholar / Crossref.
- **External AI** (only if you opt in) sends the claim + evidence to the endpoint
  you configure; the default chat-client (MCP) path keeps this in your assistant.
- **Pandoc fetch** (only on the first Word export) downloads the Pandoc release.
- **Atlas contribution** is a separate, explicit, default-off action — see
  [CONTRIBUTOR_PRIVACY.md](CONTRIBUTOR_PRIVACY.md).

See [SAFETY_INVARIANTS.md](SAFETY_INVARIANTS.md) for the enforced guarantees.
