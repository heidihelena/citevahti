# ADR-0006 — Full rename to `citevahti`; retire the `zotsynth` alias

- **Status:** Accepted (2026-06-05)
- **Date:** 2026-06-05
- **Supersedes (in part):** [ADR-0004](0004-brand-ip-and-entity.md) §2.3a and §6
  — specifically the decision to **keep `zotsynth` permanently** as the import
  path / connection-layer name and to retain the `zotsynth` CLI commands,
  `ZotSynth` keychain service, and `.zotsynth/` state dir as stable aliases.
  ADR-0004's brand, IP, and entity decisions (§2.1–2.6, §3–5) **still stand**.

## 1. Context

ADR-0004 rebranded the product to **CiteVahti** but deliberately preserved
`zotsynth` as a stable alias across three surfaces — the Python import path, the
CLI entry points, and the OS keychain service / `.zotsynth/` state dir. Two
arguments drove that:

1. **Don't break the installed base.** Renaming the import path, keychain
   service, or state dir orphans existing installs (broken imports, stored
   Zotero keys not found, state dir not located) with no auto-migration.
2. **A naming-tier theory (§3a):** `zotsynth` would be repurposed as the name of
   a future *connection layer* (the Zotero / Better BibTeX / PubMed I/O
   substrate) once that layer is factored out of the product.

Both arguments have weakened to the point of inverting:

- **There is no installed base.** The project is pre-1.0 and single-user (the
  maintainer). The compatibility cost ADR-0004 was paying to avoid — orphaned
  keys, broken imports, lost state — **does not exist**. No third party imports
  `zotsynth`, has credentials under the `ZotSynth` keychain service, or has a
  `.zotsynth/` directory to migrate. The alias protects nothing.
- **The connection-layer factor-out hasn't happened and isn't scheduled.**
  ADR-0004 §3a itself flagged the "honest gap": today `zotsynth` is the *whole*
  product, not a connection layer. Keeping the name reserved for a refactor that
  may never land means carrying a second, Zotero-leaning brand name (the exact
  trademark/category-framing risk ADR-0004 §1 set out to remove) indefinitely,
  for a benefit that is purely speculative.

Carrying two names also has a steady tax: every contributor and every doc has to
learn that the thing is called CiteVahti but imports as `zotsynth`, and the
`NOTICE`/`pyproject` comments had to keep explaining the split.

## 2. Decision

**Collapse to a single name. `citevahti` is the brand, the distribution, the
import path, the CLI, and every runtime identifier. The `zotsynth` alias is
retired, not deprecated-with-a-grace-period** — there is no one to give a grace
period to.

Executed in commit `c6efe55` (205 files, 499 tests passing):

- **Package / import:** `src/zotsynth/` → `src/citevahti/`; all `import
  zotsynth` / `zotsynth.*` paths rewritten; `ZotSynthStore` → `CiteVahtiStore`.
- **CLI:** `pyproject` exposes only `citevahti` / `citevahti-mcp`; the
  `zotsynth` / `zotsynth-mcp` entry-point aliases are removed.
- **Runtime identifiers:** keychain service `ZotSynth` → `CiteVahti`; env vars
  `ZOTSYNTH_*` → `CITEVAHTI_*`; state dir `.zotsynth/` → `.citevahti/`.
- **Mockups:** `mockups/zotsynth-*` → `mockups/citevahti-*`.
- **Retired:** the local `.claude/skills/zotsynth/*` skill files.

**History is preserved (ADR convention — we do not rewrite the record):** ADRs
0001–0004, `CHANGELOG.md`, and the dated release notes keep their original
`zotsynth` references as the genuine record of the name at that time. This ADR
is the forward pointer.

## 3. The connection-layer name, revisited

ADR-0004 §3a's architectural insight — that the Zotero/BBT/PubMed I/O substrate
is a distinct component a future Vahtian product could share — **remains valid as
intent.** What changes is that this component will **not** be pre-named
`zotsynth`. If and when the factor-out happens, the layer gets a name *then*,
chosen for what it is (e.g. a `citevahti.connect` submodule, or its own
`*-vahti` package if it becomes a shared library). Reserving a Zotero-derived
brand name years ahead of a refactor that may never ship was the weaker call;
naming on extraction is cheaper and avoids the trademark/category risk in the
interim.

## 4. Consequences

- **Positive:** one name everywhere — no "brand is X, imports as Y" split to
  teach; the Zotero-derived mark is gone from the live surface (ADR-0004 §1's
  original goal, now completed rather than half-done); `NOTICE`/`pyproject` lose
  their "kept as a stable alias" caveats; contributor onboarding is simpler.
- **Costs / risks:** **breaking** for any external consumer — but there are none
  today, which is the whole basis for doing it now. The window to make this
  change for free closes the moment someone else installs the tool or stores a
  key; this ADR records that we spent that window deliberately, while it was
  still free.
- **Reversibility:** low cost to reverse in principle (it's a rename), but there
  is no reason to — the single-name state is the desired end state, not a
  temporary measure.
- **Lesson for next time:** "keep a stable alias to protect the installed base"
  is a real principle, but it only earns its cost *once an installed base
  exists*. Applying it pre-1.0, single-user, bought complexity to protect users
  who weren't there yet. Do the disruptive rename while disruption is free.
</content>
</invoke>
