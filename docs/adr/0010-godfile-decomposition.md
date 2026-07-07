# ADR-0010 — God-file decomposition: staged, characterization-first, write-boundary-led

- **Status:** Accepted (2026-07-07)
- **Date:** 2026-07-07
- **Builds on:** [ADR-0001](0001-citation-integrity-architecture.md) (the write/security
  boundary — capability without power, the token-confirmed Zotero write path) and
  [ADR-0007](0007-local-web-app-and-http-surface.md) (the thin loopback HTTP panel surface).
- **Scope note.** This record fixes *how* we decompose three large files, and — as much —
  *what we will not do*. It is a plan to be reviewed **before** any code moves, per the
  maintainer's "plan before split". It changes no runtime behaviour by itself.

## 1. Context

Three files are large enough to be called "god-files":

| File | LOC | Units | Test coverage | What it actually is |
|---|---|---|---|---|
| `tools.py` | ~1,650 | 117 top-level fns | **66%** | A **thin facade** — 77 of 117 fns are `from .service import X; return X(...)`. |
| `cli.py` | ~2,170 | 76 `_cmd_*` + argparse | **39%** | argparse dispatch + 76 command handlers. The **least-tested** file in the repo. |
| `panel/server.py` | ~1,480 | one `http.server` handler | **84%** | One **~600-line `dispatch()` if/elif** (the real god-*function*). Not FastAPI. |

The prompting question came with a generic "best practices for god-files" essay written
**without knowledge of these files**. Most of its advice is sound in the abstract but either
**already done** or **inverted** for this repo, and acting on it verbatim would be cosmetic
at best and destabilising at worst. This ADR records the reconciliation so the plan is
grounded in what we have.

### 1a. What is already true (so we do not redo it)

- **The registry/implementation split already exists.** The essay's headline "best first
  move" — separate the agent-callable allow-list from the implementations — is **done**:
  `agent/` is the audited surface (`agent.TOOLS` registry + `policy.py` allow-list +
  `annotations.py` read-only/destructive hints, cross-checked by
  `test_readonly_tools_dont_mutate.py` and `test_mcp_tool_annotations.py`). We do **not**
  build a `tools/registry.py`.
- **The service layer already exists.** Two dozen-plus service packages (`export`,
  `writeback`, `rating`, `claims`, `claimcheck`, `prisma`, `report`, `pubmed`, `zotero`,
  `evidence`, `retraction`, `risk`, `intake`, `extract`, `corpus`, …) already hold the logic. The
  target shape the essay argues *toward* — "core services, used by CLI/panel/MCP tools" —
  is largely the shape we are **already in**. `tools.py` is a facade over it, not a tangle.

## 2. The governing idea — module boundaries should track runtime responsibilities, and the decomposition must be behaviour-preserving

Good decomposition here is **not** "the files are big, split them". It is: (a) preserve the
public surface exactly, (b) make each new module a real runtime responsibility, and (c)
move code only **behind characterization checks**. Size is a symptom; the boundary we
actually care about is the **write/security surface** (ADR-0001) — the code that can mutate
a Zotero library, the filesystem, config, or the audited ledger. Isolating *that* is worth
more than any line-count reduction.

### 2a. Where the generic essay is wrong for us (recorded so we don't regress to it)

1. **"tools.py holds business logic to untangle."** It does not — it is a facade. There are
   **no import cycles to break**; splitting is mechanically low-risk but also **lower-value**
   than the essay implies. It buys navigability and one safety boundary, not decoupling.
2. **"Never hide imports inside functions."** In this facade the **77 lazy in-body imports
   are load-bearing** — they stop the facade from importing all 27 services at module load
   and are what keep it cycle-free. Any `tools/` package split **must preserve the lazy
   pattern**; a re-export `__init__` that eagerly imports every submodule reintroduces
   exactly the cost the pattern avoids.
3. **"Split the panel into FastAPI routers."** We are on `http.server`, not FastAPI. The
   real target is the ~600-line `dispatch()` function → a **route table**, not routers.
4. **"Best first move: separate the MCP allow-list."** Already done (§1a).

### 2b. The real risk gradient is coverage, not size

`cli.py` at **39%** is the *dangerous* file to move — not the largest, but the least
characterized. `panel/server.py` (84%) is well-tested yet concentrates the write + OAuth +
blinded-rating surface in one function. `tools.py` (66%) is a facade. **Characterization
tests precede every move, heaviest where coverage is lowest.**

## 3. Decision — a staged plan, safety-net first, write-surface last

**PR 0 — characterization net, zero code moves.** Lock the public behaviour that every later
PR must preserve:

- `citevahti.tools` exposes the same set of public names (snapshot of `dir(tools)`).
- `agent.TOOLS` name-set is unchanged (extend the existing surface tests with an explicit
  frozen name set).
- The CLI command list (argparse subparsers) is unchanged.
- The panel route list (the `dispatch()` method+path table) is unchanged.

PR 0 has standalone value and ships **regardless** of whether we split anything further.

**PR 1+ — `tools.py` → `tools/` package, behaviour-identical.** A re-export `__init__`
keeps every `from citevahti.tools import X` working; the **lazy-import discipline is
preserved** inside each submodule. Group by responsibility, read-only first, **write last**:

| New module | Holds | Privilege |
|---|---|---|
| `tools/zotero_read.py` | `zot_search`, `zot_item`, `zot_collections`, `zot_attachments`, `zotero_locate`, `zotero_evidence`, `cite` | read |
| `tools/search.py` | `literature_search`, `resolve_dois*`, `openalex_search`, `semanticscholar_search`, `scan_retractions`, `scan_licenses`, `check_update` | read (external) |
| `tools/claims.py` | `add_claim`, `list_claims`, `propose_revision`, `accept/reject_revision`, `claim_bond_status`, `extract`, `claim_check`, `claim_lexical_check` | ledger |
| `tools/rating.py` + `tools/support.py` | frame ratings + claim↔candidate support ratings, `decide`, `assess` | ledger |
| `tools/reports.py` | `evidence_export`, `agreement_report`, `model_advisor`, `methods_statement`, `export_*`, `claim_report`, `evidence_map`, `cite_export*`, `warehouse_*`, `atlas_*` | read / fs-export |
| `tools/onboarding.py` | `onboard`, `ai_config_get/set`, `ai_local_models`, `getting_started` | config |
| `tools/manuscript.py` | `run_manuscript_tests`, `triage`, `check_paragraph`, `draft_context`, `chat`, `*_prompt` | read |
| **`tools/writeback.py`** | `note_add`, `annotation_add`, `item_add`, `tag_add/remove`, `collection_add_item`, `intake_push`, `assessment_tag_mirror`, `commit_decision`, transactions, `connect_zotero`, OAuth, `zotero_new_key_url` | **PRIVILEGED — the one file that can mutate an external library** |

Move 2–3 groups per PR; `writeback` is its own PR, reviewed hardest. This is the essay's one
directly-applicable point (isolate write functions) and the **only strong reason** to split
the facade at all.

**PR N — `panel/server.py` `dispatch()` → route table.** Behind PR 0's route
characterization. `dispatch` becomes `ROUTES[(method, path)] → handler`; handlers move to
`panel/routes/*.py`. The rating / OAuth / edit routes move **last**, reviewed hardest. This
is the **highest value/risk target** — a 600-line function is what actually impedes the
security review the MCP surface needs.

**PR last — `cli.py` handlers → `cli/commands/*.py`.** Only **after** characterization tests
lift it off 39% coverage. `cli.py` remains an entry-point shim (`from citevahti.cli.main
import main`).

## 4. Consequences

- **Behaviour is frozen by construction.** Every PR after PR 0 is gated by the stability
  tests; a rename or a dropped route fails CI immediately. The refactor cannot become a
  silent functional migration.
- **The write surface gets a physical boundary.** `tools/writeback.py` and the last-moved
  panel routes make "what can mutate" a small, separately-reviewed set — a security win that
  compounds the existing `agent/policy.py` allow-list.
- **This is internal hygiene with zero formative value.** It does nothing for the
  PhD-student user and carries real regression risk on the write/security path. It is
  therefore **opt-in and incremental** — done one concern per PR, safety-net first, or **not
  at all**. It must never be a drive-by cleanup bundled with feature work.
- **If only part is done, do the high-value part.** PR 0 (characterization net) + the panel
  `dispatch()` split is the best value/risk slice. Splitting the `tools.py` facade is
  nice-to-have; skip it unless the `writeback` isolation is wanted as a review boundary.
- **The lazy-import pattern is now documented as intentional**, not a smell — future work
  will not "clean it up" into eager imports and reintroduce load-time coupling.

## 5. Security invariants to pin before each move (the perimeter addendum)

The decomposition is safe **because the security perimeter is not in the code being moved**.
Each invariant is enforced above or beside the target files, not inside them:

| Invariant | Enforced in | Moved by this plan? |
|---|---|---|
| Agent can't call a dangerous verb | `agent/policy.py` allow-list + `assert_safe_surface()` (runs at import) | **No** — `agent/` untouched |
| CSRF / Host / loopback / Origin | the HTTP handler `do_GET`/`do_POST` (`_reject_bad_host()` + `_reject_unsafe_mutation()`), **above** `dispatch()` | **No** — the choke point stays in the handler |
| Mutations only via CSRF-gated POST | `do_GET` → `dispatch(…, "GET", …)` is read-only; every state change goes through the POST guard | **No** |
| Blinding order (AI value hidden until the human commits) | rating **services** + `blinded_rating_view()` | **No** — services already separate |
| Tamper-evident ledger | audit log in `state/` | **No** |
| Read tools don't mutate | `test_readonly_tools_dont_mutate.py` (name-based; survives re-export) | **No** |

`dispatch(root, method, path, body)` is **pure post-authorization routing** — the request has
already cleared Host + CSRF by the time it runs. Splitting it into a route table is therefore
security-neutral *by construction*, provided the four rules below hold.

### 5a. Rules every move must obey (perimeter cannot regress)

1. **The mutation choke point stays above the route table.** `_reject_unsafe_mutation` stays in
   the HTTP handler; route handlers receive already-authorized `(root, method, path, body)`.
   Never push the CSRF check down into per-route modules — one forgotten route becomes a hole.
2. **No route reachable via GET may mutate.** The perimeter assumes GET is read-only; a
   state-changing GET bypasses CSRF entirely.
3. **The CSRF token stays a per-handler closure** (it is minted per server process in the
   handler scope today). A refactor that makes routes "standalone importable" must not hoist
   the token to module/global scope — that is a downgrade.
4. **Assert the whole set, not members.** The perimeter tests are name/path-based; the
   characterization net must freeze the *entire* mutating-route list and the *entire*
   `agent.TOOLS` name-set, so a relocated route or tool cannot silently fall out of coverage
   while CI stays green.

### 5b. The one new test that converts "trust the refactor" into "CI enforces the perimeter"

Before the panel split, add a **CSRF-rejection test parametrized over the full mutating-route
list**: for every state-changing `(method, path)`, a request with a missing/wrong
`X-CiteVahti-Token` (or cross-origin `Origin`) must be rejected **before** any handler runs.
Because it is parametrized over the enumerated route set (rule 4), a newly-split route
physically cannot skip the guard without failing this test. Pair it with a "no mutating GET"
assertion (rule 2) and the frozen `agent.TOOLS` name-set (§3 PR 0).

### 5c. Net security judgement

Security **neutral-to-positive** if §5a is pinned as tests before any code moves — and a clear
**win** for the write surface: `tools/writeback.py` turns "everything that can mutate an
external library / the ledger / config" from scattered-across-1,650-lines into one small,
separately-reviewed file, so a newly-added write capability shows up in a diff a reviewer is
watching (strengthening ADR-0001). Security **negative only** if done as a blind "move code,
keep the existing tests green" exercise — because today's tests prove *behaviour shape* (does
the route exist? does the read tool mutate?) more than they prove *every* perimeter property
per route. The addendum closes that gap.

## 6. Not in scope

- No new features, no behaviour changes, no dependency changes.
- No `tools/registry.py` (the agent registry already exists in `agent/`).
- No framework swap for the panel (stays `http.server` per ADR-0007).
- The god-file split is **not** an ADR-0001 boundary change — it relocates code within the
  existing capability surface without widening it.
