# ADR-0004 — Brand architecture and open-core IP posture

- **Status:** Accepted (2026-06-04) — **§2.3a and §6 superseded in part by
  [ADR-0006](0006-full-rename-retire-zotsynth-alias.md)** (2026-06-05): the
  `zotsynth` import path / CLI / keychain / state-dir aliases were retired in a
  full rename to `citevahti`. The brand and IP decisions below stand.
- **Date:** 2026-06-04
- **Builds on:** [ADR-0003](0003-hosted-layer-and-open-core.md) (the open-core
  boundary).
- **Scope note.** This record keeps the *technical* brand and open-core IP
  decisions. Commercial strategy (buyer segments and sequencing), entity/legal
  structuring, and tax/liability planning are **maintained privately**, not in this
  public repository. The public roadmap is [`../../ROADMAP.md`](../../ROADMAP.md).

## 1. Context

The project shipped as `zotsynth`, a name that leans on **Zotero** (a mark of the
Corporation for Digital Scholarship). For a *free local tool* that association is
tolerable; for infrastructure that may later be offered to organizations (ADR-0003)
it is a trademark risk and it mis-frames the category — it reads as "a Zotero
add-on" rather than citation-integrity infrastructure. The brand and the IP
ownership are decided here because they interlock with the open-core license model
(ADR-0003), which only holds if copyright ownership and contributions are clean.

## 2. Decision

1. **Company: Vahtian.** A **branded house** — one company, a family of products
   bound by the `-vahti` suffix (Finnish *vahti* = sentinel/guard: "the sentinel
   for your citations"). `Vahtian` is a coined, distinctive mark (stronger and
   cheaper to protect than a descriptive name).
2. **Products are named for their users.** The first product is **CiteVahti**.
3. **One domain, products as paths — root is the company.** `vahtian.com` is the
   **Vahtian** (company) layer; each product lives at `vahtian.com/<product>`, so
   CiteVahti's canonical home is **`vahtian.com/citevahti`**. The URL encodes the
   brand hierarchy and SEO authority concentrates on one domain.
3a. **Three naming tiers — company / product / connection layer.** **Vahtian** =
   company. **CiteVahti** = the product (the ledger + review surfaces). **`zotsynth`**
   = the *connection layer*: the Zotero / Better BibTeX / PubMed I/O substrate.
   *Honest gap (as ADR-0001 §4):* today the `zotsynth` package is the **whole**
   product, not only the connection layer; "zotsynth = connection layer" is the
   target. (Superseded in part by ADR-0006 — see §6.)
4. **Design the whole house now; open one door at a time.** Name the family as a
   roadmap, but launch and market **only the live product**. Branding ahead of
   product dilutes focus.
5. **IP posture:** Apache-2.0 core + a separately-licensed hosted layer (ADR-0003); copyright held by
   the founder/entity; **defensive-publication** patent posture (no offensive
   software patents); a **CLA/DCO** gate before external contributions (§5).

## 3. Product family

The product family (which buyers each product serves, and the order they ship) is
**maintained privately**, not in this public repository. The first and only live
product is **CiteVahti** (the researcher/author surface). See
[`../../ROADMAP.md`](../../ROADMAP.md) for the public roadmap.

## 4. Entity & liability

Legal entity structuring, conversion timing, and personal-liability/tax planning
are **maintained privately** with an accountant/jurist — not in this public
repository.

## 5. IP & contribution policy

- **Copyright is the foundation.** The open-core licenses (ADR-0003) work *because*
  the founder/entity holds copyright. Keep `NOTICE`/headers naming the holder.
- **CLA or DCO before the first external contributor.** Without it, merged outside
  contributions cannot be relicensed, which would break the ability to keep the separately-licensed
  hosted module under its own terms. **Action: add `CONTRIBUTING.md` with a DCO
  sign-off (lightweight) or a CLA (stronger) before accepting PRs.**
- **Patents: defensive publication, not offensive filing.** Software-method patents
  are a poor fit (cost, narrowness, and Apache-2.0's own patent grant + retaliation
  clause blunt offensive use). The open ADRs + code already function as dated prior
  art that keeps the method-space free.
- **Trademark** on `Vahtian` (and `CiteVahti` when it is the shipping product).

## 6. The rename (executed 2026-06)

The product is rebranded to **CiteVahti** (a product of **Vahtian**). What changed
and what was (initially) kept as a stable alias:

- **Rebranded (display + distribution):** the PyPI/distribution name (`citevahti`),
  `authors`/`NOTICE` (Vahtian), the CLI `prog` + user-facing strings, the MCP
  server description, the VS Code extension (`name`/`displayName`/`publisher:
  vahtian`/command id `citevahti.verifyClaims`/config namespace `citevahti.*`), and
  the README + forward-facing docs.
- **Originally kept as aliases**, then **retired in [ADR-0006](0006-full-rename-retire-zotsynth-alias.md)**:
  the Python import path `zotsynth`, the `zotsynth` / `zotsynth-mcp` CLI commands,
  the `ZotSynth` keychain service, and the `.zotsynth/` state directory. ADR-0006
  collapsed everything to the single name `citevahti`.
- **Not rewritten:** historical ADRs, release notes, mockups, and internal test
  docstrings keep "ZotSynth" as the genuine historical record; this ADR is the
  pointer.

## 7. Consequences

- **Positive:** one cheap domain + path structure fits the bootstrapping posture;
  the IP model keeps open-core defensible; a coined house brand is cheaper to
  protect than a descriptive or Zotero-derived name.
- **Costs / risks:** the `-vahti` suffix is slightly opaque to non-Finnish ears
  (mitigated by legible prefixes + a pronunciation hint, "site-VAH-tee").
- **Trademark, entity, and legal planning are tracked privately**, not in this
  public repository.
