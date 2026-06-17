# Releasing CiteVahti

Two artifacts ship per release: the **Python package** (`citevahti` on PyPI — the
CLI + library the extension drives) and the **VS Code extension** (Marketplace +
Open VSX). Publish the **Python package first** — the extension calls the
`citevahti` CLI.

> **Credentials boundary.** PyPI / Marketplace / Open VSX tokens are credentials:
> never committed, never logged, never pasted into a chat. Use env vars or the
> keychain; pass them only to `twine` / `vsce` / `ovsx` at publish time.

## 0. Pre-flight
- [ ] `pytest -p no:cacheprovider -q` green (offline).
- [ ] `cd vscode-extension && npm run compile` clean.
- [ ] Versions in lockstep: `pyproject.toml`, `src/citevahti/__init__.py` `__version__`,
      `vscode-extension/package.json`, and the git tag.
- [ ] `CHANGELOG.md` has the release section; README status/test-count current.

## 1. Python package → PyPI

### Recommended: one-click via GitHub Release (Trusted Publishing, no token)

`.github/workflows/publish-pypi.yml` builds, `twine check`s, and publishes on a published
GitHub Release — no PyPI token stored anywhere.

- **One-time setup:** on PyPI → the `citevahti` project → *Publishing* → add a **Trusted
  Publisher**: owner `heidihelena`, repo `citevahti`, workflow `publish-pypi.yml`,
  environment `pypi`. (For the very first upload, use the manual `twine` path below once,
  or configure a "pending" trusted publisher.)
- **To release:** make sure `pyproject.toml`/`__init__.py`/`vscode-extension/package.json`
  and the tag agree, then create a GitHub Release with tag `vX.Y.Z`. The workflow publishes.
- **Verify** `twine check` locally with current tooling first (`pip install -U twine
  'packaging>=24.2'`) — an old `packaging` (<24.2) falsely rejects Metadata-2.4 license
  fields.

### Manual fallback (`twine`)

```bash
python -m venv .venv && source .venv/bin/activate
pip install --upgrade build hatchling twine    # the build toolchain (not runtime deps)

python -m build                                 # → dist/citevahti-X.Y.Z{.tar.gz,-py3-none-any.whl}
twine check dist/*                              # metadata + README render must PASS

# the panel ships its UI as package data — confirm the assets are inside the wheel
python -c "import zipfile,glob; z=zipfile.ZipFile(glob.glob('dist/*.whl')[0]); print('\n'.join(n for n in z.namelist() if 'panel/web' in n))"
# expect: citevahti/panel/web/{index.html,app.js,styles.css}

# verify a clean install in a throwaway venv before publishing
python -m venv /tmp/cvcheck
/tmp/cvcheck/bin/pip install dist/citevahti-*.whl
/tmp/cvcheck/bin/citevahti --help && /tmp/cvcheck/bin/python -c "import citevahti; print(citevahti.__version__)"

# publish (token in env, never on the command line history)
export TWINE_USERNAME=__token__
export TWINE_PASSWORD='pypi-<your-token>'
twine upload dist/*                             # or: twine upload --repository testpypi dist/*  (dry run on TestPyPI)
```

The wheel must expose the entry points **`citevahti` / `citevahti-mcp`** (plus the
`citevahti` / `citevahti-mcp` aliases) and import as `citevahti`. `dist/` and `build/`
are git-ignored — never commit build artifacts.

## 2. VS Code extension → Marketplace + Open VSX

See [`vscode-extension/PUBLISHING.md`](../vscode-extension/PUBLISHING.md) for the
full runbook. In short:

```bash
cd vscode-extension
npm install && npm run package                  # → citevahti-X.Y.Z.vsix
# Marketplace (publisher `vahtian`, Azure PAT):
export VSCE_PAT='<token>'; npm run publish
# Open VSX (for VSCodium/Cursor/Gitpod):
npx ovsx publish citevahti-*.vsix -p '<open-vsx-token>'
```

## 3. Tag + push

```bash
git tag -a vX.Y.Z -m "CiteVahti X.Y.Z — <summary>"
git push origin main --tags
```

## Build-environment notes
- A real build needs `build` + `hatchling` available (PyPI). In a locked-down
  environment these may be absent — install them into the build venv first
  (`pip install build hatchling`); `python -m build` then provisions an **isolated**
  env for the wheel automatically.
- The Python package has only two runtime deps (`pydantic`, `httpx`); the `keyring`,
  `mcp`, and `dev` extras are optional.
