# Beta day — Saturday 2026-08-01

CiteVahti 0.46.0 public beta. You run every step below yourself; nothing here is
automated on your behalf. Companion background: [RELEASE-PREP.md](RELEASE-PREP.md)
(where things stood on 2026-07-29 and why). The `secure-release` skill governs the
release itself.

Work from a **clean checkout of fresh `main`** — not `~/Zotsynth` (stale branch,
unrelated dirty state).

## 0. Merge the open prep PRs — DONE 2026-07-29

All four prep PRs (#321, #319, #318, #320) were reviewed and merged on
2026-07-29, in order, each on green CI, with rebases between them. The table
below is kept as the record. On Saturday, start at step 1 — but first run the
full suite once on fresh `main` and check it reports **1432 passed**; if it
does not, stop and look before anything else.

### The order that was used (record)

Branch protection has `strict=false`: a PR that was green can still break `main`
after another merge (it happened 2026-07-28). So for **each** PR, in order:
rebase it onto current `main`, re-run locally
(`PYTHONPATH=src pytest -p no:cacheprovider` and `mypy src`), wait for the 5
checks, merge, then move to the next.

| Order | PR | What | Must-merge? |
|---|---|---|---|
| 1 | [#321](https://github.com/heidihelena/citevahti/pull/321) | mcp dependency capped `<2` — without it a fresh `pip install "citevahti[mcp]"` gets an MCP server that cannot start, and Saturday's `.mcpb` freeze installs the same extra | **Yes — release blocker** |
| 2 | [#319](https://github.com/heidihelena/citevahti/pull/319) | Changelog catch-up: the seven landed PRs (#309–#317) the Unreleased section missed | **Yes** — step 2 cuts the Unreleased section as-is |
| 3 | [#318](https://github.com/heidihelena/citevahti/pull/318) | Opt-in `ai_connection.think` switch + 10 contract tests | Optional — the release is complete without it (RELEASE-PREP: the ceiling half already stops the rating loss) |
| 4 | [#320](https://github.com/heidihelena/citevahti/pull/320) | README says what beta means (no self-update yet, feedback route) | **Yes** — it is the page strangers land on |

#318, #319 and #321 all touch the top of `CHANGELOG.md [Unreleased]`, so each
later one **will** need its rebase — that is expected, not a problem. #320 touches
only README and merges clean in any order.

Expected suite size after all four: **1432** (1410 on main + 10 think tests + 2
mcp-pin tests) passed, 2 skipped.

## 1. Cut the release branch and bump

Off fresh `main`, one branch, e.g. `release/0.46.0`.

Bump **0.45.0 → 0.46.0** in all seven lockstep slots (miss none — the registry
entry and plugin read them):

1. `pyproject.toml`
2. `src/citevahti/__init__.py`
3. `vscode-extension/package.json`
4. `desktop-extension/manifest.json`
5. `desktop-extension/manifest.binary.json`
6. `.claude-plugin/plugin.json`
7. `server.json` — **two** slots: top-level `version` and `packages[0].version`

Then:

- `CHANGELOG.md`: retitle `## [Unreleased]` → `## 0.46.0 — 2026-08-01` (cut the
  section, don't rewrite it), and start a fresh empty `## [Unreleased]` above it.
- `docs/STATUS.md`: bump the `v0.45.0` header line to 0.46.0 with a one-line
  release summary.
- Stage **explicit paths only** — never `git add -A` here.

Quick check before pushing (should print 0.46.0 eight times):

```bash
grep -h "0\.46\.0" pyproject.toml src/citevahti/__init__.py \
  vscode-extension/package.json desktop-extension/manifest.json \
  desktop-extension/manifest.binary.json .claude-plugin/plugin.json server.json
```

## 2. PR the bump to main

5 required checks (pytest py3.10 / py3.12, VS Code compile, ruff, mypy), signed
commits, enforce_admins. Same `strict=false` rule: **rebase onto main and re-run
the suite + mypy locally immediately before merging.**

## 3. Tag and release — one event fans out everything

```bash
gh release create v0.46.0 --target main --title "CiteVahti 0.46.0" --notes "<from the 0.46.0 changelog section>"
```

That single event triggers all of it; nothing else to start by hand:

- `publish-pypi.yml` → build, `twine check`, PyPI via Trusted Publishing (OIDC,
  env `pypi`) + CycloneDX SBOM asset.
- `desktop-extension-build.yml` → 3 signed `.mcpb` (linux-x64 / macos-arm64 /
  win-x64) + signed+notarized `CiteVahti.app` zip. Every frozen artifact is
  smoke-RUN before packing (#221 gate).
- **MCP registry marker rides along** — `mcp-name` in README + `server.json` are
  already in the repo; the version bump in step 1 is all it needs.
- **Zenodo DOI mints automatically** off the GitHub release via `.zenodo.json`.

## 4. Confirm publication

In this order (PyPI's JSON lags the workflow by minutes):

1. Both workflow runs green in Actions.
2. PyPI shows `latest = 0.46.0`.
3. GitHub release carries 5 assets (3 `.mcpb`, `.app.zip`, SBOM).
4. Zenodo DOI visible for the release.

## 5. Smoke-test what a stranger gets

- **pip path:** fresh venv, `pip install "citevahti[mcp]"`, then
  `citevahti demo`. Expect: panel opens, no "MCP server unavailable" line,
  `pip show citevahti` says 0.46.0. (This exact path is what caught the mcp 2.0
  break on 2026-07-29 — keep it in the ritual.)
- **Claude Desktop path:** remove the old CiteVahti extension, fully quit and
  reopen Claude Desktop, install the new macOS `.mcpb`, ask the assistant to run
  the `status` tool — it must report 0.46.0.
- **Desktop app:** replace `CiteVahti.app` in Applications with the new zip's
  app, open it, drag a manuscript in, confirm the panel loads.
- **README from a stranger's seat:** open the repo page logged out; the download
  link ("latest release") must now resolve to 0.46.0 assets.

## 6. Tell the pilots

Remove + reinstall the `.mcpb` (Claude Desktop caches the old one) and replace
the app. The README's *Updating* section says the same in user words — link it.

## 7. If it goes wrong — rollback

- **Bad PyPI release:** yank it on pypi.org → project `citevahti` → Manage →
  release 0.46.0 → Options → **Yank** (with a one-line reason). Yanked releases
  stop being picked by fresh installs but stay reproducible for anyone pinned to
  them. Don't delete.
- **Bad GitHub release:** mark it as pre-release so "latest" stops pointing at it:
  `gh release edit v0.46.0 --prerelease`. The README's download links follow
  `releases/latest`, so this immediately reroutes strangers back to v0.45.0.
- Fix forward on a branch, release 0.46.1 through the same steps.

## Out of scope today (unchanged from RELEASE-PREP)

- **TUF / auto-update activation** — separate founder-only track. Nothing today
  touches `src/citevahti/autoupdate/`, TUF keys, or signing configuration.
- **`think: false` as a default** — stays opt-in (n = 44 could not resolve the
  `unclear` cost).
- Rating vocabulary and blinding — frozen, as always.
