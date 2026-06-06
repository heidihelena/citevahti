# ADR-0003 — Open-core boundary and aggregate-data governance

- **Status:** Accepted (2026-06-04)
- **Date:** 2026-06-04
- **Builds on:** [ADR-0001](0001-citation-integrity-architecture.md) (the ledger is
  the product; the de-identified validation warehouse) and
  [ADR-0002](0002-ui-delivery-and-review-layer.md) (manuscript-native review).
- **Scope note.** This record keeps the *principles* that bound the project: what
  stays free and local, and how any de-identified aggregate data is governed.
  Commercial strategy and the shape of any future hosted offering are **maintained
  privately**, not in this public repository. The public roadmap is
  [`../../ROADMAP.md`](../../ROADMAP.md).

## 1. Context

The tool is a complete, local-first, single-user implementation of the ledger
(ADR-0001). Two principles must be fixed *before* any networked or collaborative
feature is ever considered, so they are decided here rather than emergently:

1. **The open-core boundary** — what is guaranteed to stay free and local.
2. **Governance of any de-identified aggregate data** — the single-user warehouse
   would only ever become a shared resource under strict, consent-first rules. This
   is the highest-risk surface (academic data, consent, possibly
   human-subjects-adjacent) and must be conservative and explicit.

## 2. Decision

1. **Open core, local-first — forever.** The library, CLI, VS Code extension, and
   the constrained MCP/agent surface, plus the **local** de-identified warehouse,
   stay Apache-2.0. A researcher can run the entire claim → decision → audit →
   Zotero-write loop on their own machine with no account and no network beyond
   PubMed/Zotero. **We never paywall a capability a lone researcher needs to verify
   their own manuscript.** This is load-bearing for trust and non-negotiable.
2. **Any collaboration or organizational features, if built, are a separate layer.**
   They would be licensed separately and would not change the local core in any way.
   Their shape and timing are out of scope for this public record.
3. **The local files are the reference.** Any future networked record must
   round-trip to the same de-identified `ValidationRecord` the local warehouse
   emits — no divergent second model of truth.
4. **Only de-identified records could ever aggregate.** Per-user operational data,
   manuscript text, and identity never leave the user's boundary. Cross-user value,
   if it ever exists, comes **exclusively** from de-identified `ValidationRecord`s
   under the §3 governance.

## 3. Aggregate-data governance (conservative by default)

The local warehouse rules (default-off, opt-in, tiered, purgeable, de-identified)
are necessary but not sufficient if records are ever pooled across users. Any such
pooling would additionally require:

1. **Two-step, revocable consent.** Contribution is off by default. A first opt-in
   covers the low-sensitivity tier (claim_type + a one-way claim-text hash + public
   PMID/DOI + ratings + fit); raw claim text is a **separate, second** opt-in.
   Withdrawal purges the contributed records within a stated window.
2. **De-identification enforced at the boundary and re-validated server-side** — any
   record carrying a forbidden field (identity, manuscript text, credentials) is
   rejected. De-id is never trusted from the client alone.
3. **k-anonymity / small-cell suppression on read** — aggregate queries never return
   a cell thin enough to re-identify a contributor.
4. **A data-use agreement + an ethics review** before any data is pooled — treated
   as potentially human-subjects-adjacent; documented basis, no "innovate first,
   ask later."
5. **No undisclosed model training.** If aggregate labels were ever used to train a
   model, the consent text would say so plainly, in advance.
6. **Provenance and schema versioning survive aggregation** so older records stay
   interpretable.

> **Honest flag.** This is the part most likely to cause harm if rushed. If this
> governance can't be made concrete and externally reviewed, aggregate features do
> not ship, and the warehouse stays strictly per-user.

## 4. Consequences

- **Positive:** the free local tool stays whole and trustworthy; any future
  networked layer is gated behind real, reviewable governance; the Apache core is a
  one-way commitment we are keeping.
- **Costs / risks:** the aggregate surface carries ethics and legal weight that must
  be funded properly or deferred; open-core boundary questions are perennial — §2's
  "never paywall solo verification" rule is the tie-breaker.
- **Reversible?** The Apache core is deliberately one-way. Anything about a future
  networked/aggregate layer stays adjustable and, by default, unbuilt.
