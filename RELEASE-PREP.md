# Release prep — CiteVahti, Saturday 2026-08-01

Prepared 2026-07-29 against `origin/main` @ `93b1bf0` (#317). Fan-out and
version-file claims corrected 2026-07-30 against measured state (Zenodo API, MCP
registry API, branch protection, repo grep) — [BETA-DAY.md](BETA-DAY.md) is the
runbook; this file is the background. Working copy for all
checks: clean worktree `~/Zotsynth-release-prep` (this checkout, `~/Zotsynth`, sits on a
stale branch with unrelated dirty state — do not cut the release from it).

## Where things stand

| Item | Status |
|---|---|
| P0 — manuscript switching (PR #277, `fb8cffa`) | Fixed on main. Regression tests: `tests/test_rootcfg.py` (recents dedupe/order/cap, temp-root guards), `tests/test_panel_api.py::test_context_lists_recent_manuscripts_and_open_records_them` |
| P0 — window-close kills app + stale cache (PR #278, `8d905fa`) | Fixed on main. Regression tests: `tests/test_desktop_app.py` (close hides, never stops sidecars; 5 tests) + `tests/test_panel_api.py` (no-store on JSON/HTML/static) |
| Rater bug (a) — AI never returns `unclear` | Fixed on main: #296 (rater may return `unclear` as an honest verdict), #299 (every copy of the scale held to `SUPPORT_VALUES`), #302 (failed call ≠ abstention). Tests: `test_support_ai_rater.py`, `test_vocabulary_sync.py` |
| Rater bug (b) — qwen3 loses 27% of ratings on the /v1 path | Ceiling half fixed on main: #298 + #305 (local ceiling 4096, sized from the whole corpus; truncation is a typed *configuration* failure, never an abstention; transient failures retried, #304). `think` half fixed on branch `fix/rater-vocabulary-and-v1-path` (below) — **not merged, not pushed** |
| Full offline suite (worktree, branch tip) | **1420 passed, 2 skipped** (41.8 s). `ruff check src` clean, `mypy` clean (190 files) |

## The fix branch (needs a PR before it can ship)

`fix/rater-vocabulary-and-v1-path`, 4 signed commits on top of `origin/main`, in the
worktree `~/Zotsynth-release-prep`. Not pushed (per instruction).

- `646a7db` feat(config): `ai_connection.think` — operator-visible chain-of-thought control
- `b62f78c` fix(rating): honor `think=false` over Ollama's native `/api/chat`
- `695d80f` test(rating): lock the think-switch contract (`tests/test_think_control.py`, 10 tests)
- `66c1dee` docs(changelog): record the switch and its measured trade

Design honours the 2026-07-27 measurement (memory: *think-false-tradeoff*): `think:
false` never truncates and runs ~4.4x faster, **but** loses agreement exactly on
`unclear`-anchor items (40/44 vs 35/44; McNemar p = 0.227 — not resolvable at n = 44).
So the default stays thinking-on; the switch is opt-in, local-Ollama-only, and `api`
mode rejects it rather than silently ignoring it. Latency control, not a correctness fix.

To include it Saturday: push the branch (`git push -u origin
fix/rater-vocabulary-and-v1-path` from the worktree), open the PR (`--head`!), 5 checks
green, **rebase onto main and re-run the suite before merging** (branch protection has
`strict=false` — two individually green PRs have already made main red once, 2026-07-28).
The release is complete without it; the ceiling half on main already stops the rating loss.

## Version

- Current: **0.45.0** everywhere (checked in lockstep at `origin/main`). Nine
  tracked files carry it (measured by grep, 2026-07-30): seven hand-edited —
  `pyproject.toml`, `src/citevahti/__init__.py`, `vscode-extension/package.json`, both
  `desktop-extension/manifest*.json`, `.claude-plugin/plugin.json`, and `server.json`
  (two slots: top-level + `packages[0]`) — plus two regenerated lockfiles,
  `vscode-extension/package-lock.json` (two slots) and `uv.lock`. Last release:
  tag `v0.45.0`, 2026-07-03.
- Proposed next: **0.46.0** — 96 commits since v0.45.0 with real Added entries, so a
  minor bump, not a patch.

## Changelog since v0.45.0 (already written in `CHANGELOG.md [Unreleased]` — cut the section, don't rewrite it)

- **Rating integrity (the heart of this release):** blind AI rater can answer `unclear`
  (#296); one support scale everywhere (#299); failed call ≠ abstention, typed failure
  kinds (#302); corpus-sized local reply ceiling + truncation named as configuration
  (#298/#305); transient failures retried, judgements never re-asked (#304); a
  multi-source claim is not decided by one accept (#307); duplicate pair records fixed
  (#309/#310); agreement report reads the claim-support ledger (#303); import-results
  reads abstracts and says when one is missing (#308).
- **Panel/desktop:** recent manuscripts (#277); close hides the window, nothing is
  cacheable (#278); filename decode fix (#301); declined ≠ never-asked in the panel (#300).
- **Evaluation/skills:** prescreen benchmark report + held-out suite export with
  leaderboard contract (#293–#295, #306); `getting_started`, `model_advisor`; published
  evaluation page; PICO/certainty flags; coverage visibility.
- **Metadata/registry:** MCP registry marker (`mcp-name` in README + `server.json`, #285);
  `CITATION.cff` + `.zenodo.json` + ORCID creator credit (#284); secret redaction in
  onboarding output (#287); copy says *check*, not *verify* (#317).
- If the fix branch merges: `ai_connection.think` (Added entry already in the section).

## Release steps (Saturday — Heidi runs these; secure-release skill governs)

1. Cut a release branch off fresh `main`. Bump the **seven hand-edited files above** in
   lockstep (don't miss `server.json` x2 and `.claude-plugin/plugin.json` — the registry
   entry and plugin read them), then regenerate the two lockfiles
   (`npm install --package-lock-only` in `vscode-extension/`; `uv lock`). Retitle
   `## [Unreleased]` → `## 0.46.0 — 2026-08-01`; bump
   `docs/STATUS.md` header. Stage explicit paths — never `git add -A` here.
2. PR to `main` (protected: 5 required checks — pytest py3.10/py3.12, VS Code compile,
   ruff, mypy — signed commits, enforce_admins). Before merging: rebase onto main, re-run
   `PYTHONPATH=src pytest -p no:cacheprovider` + mypy locally (`strict=false` gotcha).
3. `gh release create v0.46.0 --target main --title "CiteVahti 0.46.0" --notes ...`
   The release event triggers exactly two workflows (both on `release: published`);
   everything else is manual:
   - `publish-pypi.yml` → build, `twine check`, **PyPI via Trusted Publishing** (OIDC,
     env `pypi`) + CycloneDX SBOM asset.
   - `desktop-extension-build.yml` → 3 signed `.mcpb` (linux-x64 / macos-arm64 /
     win-x64) + signed+notarized `CiteVahti.app` zip. Every frozen artifact is
     smoke-run before packing (#221 gate).
   - **MCP registry does NOT ingest `server.json` on its own** (live registry showed
     zero citevahti entries 2026-07-30). Manual: `mcp-publisher login github` (Heidi)
     + `mcp-publisher publish`. The `mcp-name` marker in README is the ownership
     anchor, not a trigger.
   - **Zenodo DOI mints only if the repo toggle at zenodo.org/account/settings/github
     is enabled** — it was not as of 2026-07-30 (no CiteVahti record exists; v0.45.0
     minted nothing). Heidi-gate, see BETA-DAY pre-flight.
   - **Marketplace + Open VSX** stay manual per `docs/RELEASING.md` §2.
4. Confirm: workflow logs first (PyPI JSON lags minutes), then PyPI `latest=0.46.0`, 5
   release assets, MCP registry lists the server post-publish, Marketplace/Open VSX at
   0.46.0, Zenodo DOI only if the toggle was flipped. `status` MCP tool reports the
   running version.
5. Tell pilots: remove + reinstall the `.mcpb` (Claude Desktop caches the old one) and
   replace the app.

## NOT in this release

- **TUF / auto-update activation.** Separate founder-only track (Friday 2026-07-31).
  Nothing in this release touches autoupdate, TUF keys, or signing configuration; the
  tuf CVE pin (GHSA-qp9x-wp8f-qgjj, Windows-only, updater inert) stays as is and must be
  resolved before auto-update ever goes live.
- **`think: false` as a default.** Stays opt-in; a default swap needs a corpus large
  enough to resolve the `unclear` cost (n = 44 could not).
- Anything that changes the rating vocabulary or blinding — frozen, as always.
