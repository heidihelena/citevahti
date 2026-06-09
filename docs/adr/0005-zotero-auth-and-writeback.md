# ADR-0005 — Zotero authentication & write-back strategy

- **Status:** Accepted (2026-06-04)
- **Date:** 2026-06-04
- **Builds on:** [ADR-0001](0001-citation-integrity-architecture.md) (guarded write),
  [ADR-0003](0003-hosted-layer-and-open-core.md) (hosted layer / OAuth),
  [ADR-0004](0004-brand-ip-and-entity.md) (zotsynth = the connection layer).
- **Decides:** how a researcher authorizes CiteVahti to write references back to
  Zotero, without hand-crafting API keys — the biggest adoption blocker for launch.

## 1. Context

Reading from Zotero is already **keyless and local** (Zotero local API on
`localhost:23119` + Better BibTeX). Only the final *write-back* ("Add to Zotero")
needs authorization. The current write path uses the **Zotero Web API**, which
requires the user to manually create a private API key and find their userID —
unacceptable friction for the non-technical researcher audience. The question:
can we make write-back keyless (local), or do we need OAuth?

## 2. Spike evidence (2026-06-04, against a live Zotero)

Tested the local surfaces on `127.0.0.1:23119`:

| Probe | Result |
|---|---|
| `POST /connector/ping` | **200**, keyless — Zotero reachable, connector alive |
| `GET /api/users/0/items` | **200**, keyless — returns the local library + **surfaces the userID** |
| `POST /api/users/0/items` (write) | **400 "Endpoint does not support method"** — the `/api/` mirror is **read-only** |
| `POST /connector/saveItems` (write) | **500** (empty body); `getSelectedCollection` **hung** — reachable but undocumented, UI-coupled, fragile |

Zotero **OAuth** (docs): **OAuth 1.0a**, requires a **registered app + a callback
URL** (i.e. a server), ultimately yields an **API key + userID**, and the new-key
form **accepts pre-set permissions** via `write_access=1` GET params.

**Conclusion:** keyless *read* is solid; keyless *write* is **not reliably
available** (the clean `/api/` path is read-only; the connector path is fragile and
undocumented). OAuth is real but is fundamentally **not local-first** — it needs a
hosted callback.

## 3. Decision

1. **Reads stay keyless + local** (local API + BBT). Unchanged.
2. **Beta write-back = Zotero Web API key, obtained via a guided one-paste flow.**
   CiteVahti opens Zotero's **new-key page pre-filled** (`name=CiteVahti`,
   `library_access=1`, `write_access=1`); the user clicks **Save**, copies the key
   **once**, and pastes it. CiteVahti **auto-detects the userID from the key** (no
   second field). The key lives only in the **OS keychain** (service unchanged for
   compatibility; never logged, exported, or shown to the agent). One click + one
   paste, ~30 s, **no server, no understanding of "API keys" required.**
3. **Keyless connector write is a future investigation, NOT a launch dependency.**
   If the `/connector/saveItems` session handshake can be reverse-engineered *and*
   a non-interactive mode found, it could make desktop write-back fully keyless —
   tracked, but out of scope for the beta (too fragile/undocumented to bet on).
4. **OAuth "Connect Zotero" is a hosted-tier feature** (ADR-0003). Because it
   requires a callback server, it belongs to the Vahtian hosted layer — and is a
   genuine paid differentiator for the cases the local key can't serve well:
   **group libraries**, and using CiteVahti **without the desktop app running**.
5. **The guarded-write invariants are unchanged** regardless of auth method:
   decision-gated, preview→confirm-token→commit, undoable, dedupe fails closed by
   default (an explicit `allow_unverified_dedupe` override is warned and audited).

## 4. The progression (free → paid is the auth ladder)

```
Read (discover/verify)      → keyless, local            [free]
Write-back, desktop user    → one-paste Web API key     [free beta]
Write-back, keyless desktop → connector (if solved)     [free, future]
Connect Zotero (OAuth), groups, no-desktop → hosted     [Pro / org]
```

"We need OAuth" is therefore **not a launch blocker** — it is the first concrete
feature of the hosted layer. The free, local-first, account-free product ships on
keyless reads + a one-paste key for writes.

## 5. Consequences

- **Positive:** removes the worst onboarding friction without a server; keeps the
  free product local-first and account-free; gives the hosted tier a real first
  feature (OAuth); auth becomes a clean free→paid ladder.
- **Costs / risks:** the one-paste key is still one paste (not zero); the connector
  keyless-write path stays an unfunded "maybe"; OAuth 1.0a + a callback server is
  non-trivial to build when the hosted layer starts.
- **Reversible?** Yes — the write backend is already an abstraction (ADR-0001).
  Adding a connector backend or an OAuth/hosted backend later does not change the
  ledger or the guarded-write contract.
