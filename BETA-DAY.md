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
below is kept as the record. On Saturday, start at step 0.5 (pre-flight) — but
first run the full suite once on fresh `main`. The gate is **zero failures,
zero errors**. The *collected* count is environment-dependent (tests gate on
installed extras), so compare it to the recorded baseline for the environment
you are in, both measured 2026-07-29 on post-prep main:

- **Local release-prep worktree (macOS):** 1420 passed, 2 skipped.
- **CI (ubuntu, py3.10 and py3.12, `pip install -e ".[dev,mcp,keyring,timestamp,docx]"`):**
  1424 collected (the `-m security` phase reports 92 passed, 1332 deselected).

The two counts differ because CI installs every extra; that is expected, not a
problem. Any failure, or a collected count that matches *neither* baseline —
stop and look before anything else. (The earlier 1432 figure was arithmetic,
not a measurement.)

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

Suite size after all four, as measured, not summed (the earlier 1432 figure
summed 1410 + 10 think tests + 2 mcp-pin tests): **1420 passed, 2 skipped** in
the local release-prep worktree; **1424 collected** in CI with all extras — see
the baselines above.

## 0.5 Pre-flight — one-time prerequisites (check before cutting anything)

- **[G] Zenodo GitHub integration is NOT enabled for this repo.** Checked
  2026-07-30: the Zenodo API has no CiteVahti record (v0.45.0, released
  2026-07-03, minted no DOI). Until Heidi flips the toggle at
  zenodo.org/account/settings/github (enable `heidihelena/citevahti`), **no DOI
  mints for this or any release** — `.zenodo.json` only shapes the metadata once
  the toggle exists. Resolve: Heidi logs into Zenodo, enables the repo, before
  step 3. If it stays off, step 4 has no DOI to confirm — note that in the
  release notes rather than letting it ride silently.
- **[G] MCP Registry publishing needs `mcp-publisher`, authenticated by Heidi.**
  Checked 2026-07-30: registry.modelcontextprotocol.io returns **zero entries**
  for citevahti — the registry does not ingest `server.json` from GitHub on its
  own, and `mcp-publisher` appears nowhere in this repo. Resolve: install the
  CLI (`brew install mcp-publisher`), then Heidi runs `mcp-publisher login
  github` (interactive GitHub auth — only she can) once; the publish itself is
  step 3b.

## 1. Cut the release branch and bump

Off fresh `main`, one branch, e.g. `release/0.46.0`.

**Nine tracked files carry the version** (measured 2026-07-30 by grepping
`0.45.0` across the repo): seven you edit by hand, two lockfiles you regenerate.

Bump **0.45.0 → 0.46.0** by hand in the seven lockstep files (eight slots —
miss none, the registry entry and plugin read them):

1. `pyproject.toml`
2. `src/citevahti/__init__.py`
3. `vscode-extension/package.json`
4. `desktop-extension/manifest.json`
5. `desktop-extension/manifest.binary.json`
6. `.claude-plugin/plugin.json`
7. `server.json` — **two** slots: top-level `version` and `packages[0].version`

Then regenerate the two lockfiles that also record it (tracked — skip them and
the stale 0.45.0 stays in-tree and the next `npm install` / `uv lock` dirties
someone else's checkout):

8. `vscode-extension/package-lock.json` (two slots) —
   `cd vscode-extension && npm install --package-lock-only`
9. `uv.lock` (`[[package]] name = "citevahti"` entry) — `uv lock`; check the
   diff touches only the citevahti version line before staging it.

Then:

- `CHANGELOG.md`: retitle `## [Unreleased]` → `## 0.46.0 — 2026-08-01` (cut the
  section, don't rewrite it), and start a fresh empty `## [Unreleased]` above it.
- `docs/STATUS.md`: bump the `v0.45.0` header line to 0.46.0 with a one-line
  release summary.
- Stage **explicit paths only** — never `git add -A` here.

Quick check before pushing — first line should print 0.46.0 eight times, the
two lockfile checks three more:

```bash
grep -h "0\.46\.0" pyproject.toml src/citevahti/__init__.py \
  vscode-extension/package.json desktop-extension/manifest.json \
  desktop-extension/manifest.binary.json .claude-plugin/plugin.json server.json
grep -m2 '"version": "0\.46\.0"' vscode-extension/package-lock.json
grep -A1 'name = "citevahti"' uv.lock | grep '0\.46\.0'
```

## 2. PR the bump to main

5 required checks (pytest py3.10 / py3.12, VS Code compile, ruff, mypy), signed
commits, enforce_admins. Same `strict=false` rule: **rebase onto main and re-run
the suite + mypy locally immediately before merging.**

## 3. Tag and release — what one event actually triggers, and what it doesn't

```bash
gh release create v0.46.0 --target main --title "CiteVahti 0.46.0" --notes "<from the 0.46.0 changelog section>"
```

### 3a. Automatic — the only two things the release event triggers (both fire on `release: published`; read the workflows, not this list, if in doubt)

- `publish-pypi.yml` → build, `twine check`, PyPI via Trusted Publishing (OIDC,
  env `pypi`) + CycloneDX SBOM attached as a release asset (separate `sbom` job).
- `desktop-extension-build.yml` → 3 signed `.mcpb` (linux-x64 / macos-arm64 /
  win-x64) + signed+notarized `CiteVahti.app` zip, attached to the release.
  Every frozen artifact is smoke-RUN before packing (#221 gate).
- **If the Zenodo toggle from pre-flight is on** (and only then), Zenodo mints a
  DOI off the release, shaped by `.zenodo.json`. Toggle off → nothing mints.

### 3b. Manual — the release event does NOT touch these; each is a step you run

- **[G] MCP Registry:** the registry never reads `server.json` from GitHub.
  From the release checkout, after the tag exists:
  `mcp-publisher login github` (Heidi — interactive) then `mcp-publisher publish`
  (reads `server.json`; the `mcp-name` marker in README is the ownership
  anchor it checks against).
- **VS Code Marketplace:** `cd vscode-extension && npm install && npm run
  package` then `npm run publish` (publisher `vahtian`, `VSCE_PAT` from the
  keychain — never pasted into chat). Full runbook:
  `vscode-extension/PUBLISHING.md`.
- **Open VSX** (VSCodium/Cursor/Gitpod):
  `npx ovsx publish citevahti-*.vsix -p '<token>'` — same `docs/RELEASING.md` §2.

Python package first, extension second — the extension drives the `citevahti` CLI.

## 4. Confirm publication

In this order (PyPI's JSON lags the workflow by minutes):

1. Both workflow runs green in Actions.
2. PyPI shows `latest = 0.46.0`.
3. GitHub release carries 5 assets (3 `.mcpb`, `.app.zip`, SBOM).
4. MCP Registry lists the server after 3b:
   `curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=citevahti"`
   must return a non-empty `servers` list at 0.46.0 (it returned zero entries
   on 2026-07-30 — that is the before-state, not a lag).
5. Marketplace + Open VSX show 0.46.0 after their manual publishes.
6. Zenodo DOI visible — only if the pre-flight toggle was enabled; otherwise
   record "no DOI, toggle pending" in the release notes.

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
