# Security practices — standing checklist

Threat-model-derived practices for CiteVahti as a local-first desktop app that runs a localhost
HTTP panel + an MCP stdio server, calls out to literature APIs (PubMed/NCBI, OpenAlex, Semantic
Scholar, Crossref), optionally to a user's Zotero and an LLM endpoint (local Ollama or a user
API key), and stores a hash-chained ledger of clinical-adjacent research data.

These are framed against STRIDE / OWASP (Desktop App Security Top 10, OWASP Top 10 for LLM
Applications). The auto-update + signing half lives in `secure-updates.md`; this file is
everything else. Items below marked *(plan)* are not necessarily implemented yet — treat them
as the target when you touch the relevant area.

## 1. The loopback panel — localhost is NOT private

Binding to `127.0.0.1` is necessary but **not sufficient**. Any local process can reach the
port, and a malicious *web page* can too via **DNS rebinding** (rebind a hostname to 127.0.0.1
so the browser's same-origin check is satisfied while requests hit your server), and **CSRF**
(a page auto-submits requests to `localhost:PORT` using the user's session).

**Status: implemented and test-guarded.** `panel/server.py` already does all three defenses,
and `tests/test_panel_csrf.py` locks them (5 tests, incl. that the legit client still works).
Before changing the panel, re-read that test — it is the security contract:
- **`Host`-header rejection** (`_reject_bad_host`) — a non-loopback `Host` → 403. Defeats
  DNS-rebinding, since a rebound request carries the attacker's domain in `Host`.
- **Cross-origin `Origin` rejection** on POST (`_reject_unsafe_mutation`) → 403. Defeats CSRF.
- **`Content-Type: application/json` required** on POST → 415 otherwise. Blocks the cross-origin
  "simple request" a browser sends without a CORS preflight (text/plain / form-encoded).
- **Per-session CSRF token required** on POST (`X-CiteVahti-Token`, constant-time compare) → 403
  otherwise — see the dedicated note below.
- Binds `127.0.0.1` explicitly; refuses a non-loopback bind unless `--allow-nonloopback`.

This matters most for the **Zotero-write** and **rating-submit** endpoints — a forged request
there corrupts the provenance trail, which is the product's whole value. Any new mutating
endpoint inherits these checks automatically (they run in `do_POST` before dispatch); don't add
a write path that bypasses them.

- **Per-session CSRF token** (`X-CiteVahti-Token`) — minted per server process, handed to the
  legitimate page at `GET /api/session`, required (constant-time compare) on every POST. This
  is a *positive* secret check, so it stays sound even if the Origin/Host allow-list parser
  ever mishandles an adversarial header value — defense-in-depth for state-changing requests.
  Added before public-beta per the founder's security roadmap (item #2). The client's `api()`
  helper sends it automatically, so it costs the legitimate user nothing.

**Honest limitation:** the token does **not** stop a non-browser local process running as the
user (it can read `/api/session` like any local process) — but such a process is already past
the trust boundary of a single-user local tool. The token's value is against *browser* attacks
(where same-origin policy keeps it secret) and against a future header-parser edge case.

## 2. MCP / LLM surface

- **Indirect prompt injection** is the headline LLM risk here: fetched **literature content**
  (abstracts, full text) flows toward the model. Treat that text as untrusted data, never as
  instructions. The sealed-envelope design already helps (the AI records a blind rating; it
  doesn't take orders to "accept this claim"), but any new feature that pipes fetched text into
  a model prompt must keep that boundary.
- **Tool poisoning / over-broad surface (confused deputy):** the allow-list guard
  (`agent/policy.py` `ALLOWED_AGENT_TOOLS` + `assert_safe_surface`) is the control. Keep the
  surface minimal; a tool that reads is safer than one that writes; one that writes is safer
  than one that reaches the network *and* writes. Justify every addition.
- **Never let an AI value become final** (SAFETY_INVARIANTS #4/#5) — this is also a security
  property: it bounds the damage a manipulated model can do to the ledger.

## 3. Secrets at rest, in transit, in logs

- **Zotero API keys and user LLM API keys:** prefer the **OS keychain** (the `keyring` extra)
  over plaintext config. If a key must sit in a config file, document it and keep the file
  outside any sync/egress path.
- **Never log a secret.** Audit entries, panel logs, and error messages must not echo keys or
  tokens. Scan new logging for this.
- **In transit:** HTTPS only for outbound calls; a local Ollama endpoint stays on loopback.

## 4. Supply chain (CI + dependencies)

- **Pin GitHub Actions to a full commit SHA**, not a floating tag (`@v7`, `@release/v1`). The
  current workflows are unpinned — fix this **before** any signing key lands in CI, because a
  compromised third-party action is the most common secret-exfiltration path. Tools like
  StepSecurity's pinning action, or Dependabot configured for Actions, keep SHAs current.
- **OIDC / Trusted Publishing** for PyPI is already in place (`publish-pypi.yml`, `id-token:
  write` scoped to the publish job, `pypi` environment) — no long-lived PyPI token to leak.
  Keep that pattern; don't regress to an API-token upload.
- **Least-privilege tokens:** `permissions: contents: read` at the top; widen per-job only as
  needed. Gate signing-key jobs behind an Environment with required reviewers.
- **Pin/lock runtime deps** and keep the surface small (the package has only `pydantic` +
  `httpx` as hard runtime deps — a genuine asset; don't grow it casually). An **SBOM** and
  dependency-confusion awareness (the package name `citevahti` is yours on PyPI) are
  proportionate next steps. *(plan)*
- **PyInstaller bundles ship a full Python + deps** — the bundle inherits every dependency's
  vulnerabilities, so dependency hygiene is also *binary* hygiene.

## 5. Audit-ledger integrity — know its limits, state them honestly

The hash-chained ledger is **tamper-evident, not signed** (SAFETY_INVARIANTS documents this).
What it does and does not do:
- ✅ Detects a *partial* retroactive edit/deletion — `verify-audit` catches a snipped or
  altered entry mid-chain.
- ❌ Does **not** stop a determined local attacker who re-hashes the *entire* chain after
  editing — a full re-hash still validates. The chain verifies the **log**, not the
  materialized state files.
- This is an honest beta posture, not a hidden flaw — PRISMA and similar don't require a signed
  trail; the threat model is *honest-researcher provenance*, not defense against a malicious
  local root.

Proportionate upgrades, **as a deliberate scoped decision when pilots grow** (not a silent
default): sign the audit head with the offline `targets`/release key; RFC 3161 trusted
timestamping of the head; an append-only / transparency-log (Merkle) structure. Match the
ambition to the actual provenance requirement of the pilots — don't gold-plate.

## 6. Data governance / privacy-by-design (high level, not legal advice)

Clinical-adjacent research data in the EU → design for GDPR data-minimization:
- **Local-first by default; egress is explicit and opt-in.** The de-identified validation
  warehouse stays local; contributing anything to the shared corpus is a separate, active,
  default-off choice with its own consent — never automatic. Keep that wall.
- Say **"de-identified," not "anonymous."** Disclose exactly what each outbound call sends
  (search queries, titles/DOIs/PMIDs to literature services; whatever the user connects for
  Zotero/LLM).
- Keep the **registry-data controllership wall** in mind given the founder's dual role — that's
  a governance decision to document, not something to encode silently in the tool.

When in doubt on a data-governance call, surface it for a human decision rather than picking a
default that's hard to walk back.
