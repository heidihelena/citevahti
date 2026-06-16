# Publishing the CiteVahti VS Code extension

The extension is a thin client over the `citevahti` CLI. Publishing it is a
packaging + marketplace step; it ships no secrets and stores none.

> **Credentials boundary.** A Marketplace Personal Access Token (PAT) is a
> credential. It is **never** committed, never put in `package.json`, never
> printed to logs, and never pasted into a chat with an assistant. Keep it in an
> environment variable or your OS keychain and pass it only to `vsce`/`ovsx` at
> the moment of publish.

## 0. One-time prerequisites

```bash
cd vscode-extension
npm install            # installs @vscode/vsce (the packaging tool) as a devDependency
npm run compile        # type-checks + emits out/extension.js
```

## 1. Build the VSIX (no account needed)

```bash
npm run package        # -> citevahti-<version>.vsix  (runs `vsce package --no-dependencies`)
```

Install it locally to smoke-test, or hand it to a colleague for private use:

```bash
code --install-extension citevahti-vscode-0.16.0.vsix
```

This is the **private-distribution** path — no Marketplace required. Good for a
lab or a pilot cohort before a public listing.

## 2. Publish to the VS Code Marketplace (public)

The Marketplace is run by Microsoft via Azure DevOps.

1. **Create the publisher.** Go to <https://marketplace.visualstudio.com/manage>
   and create a publisher. Its ID **must equal** the `publisher` field in
   `package.json` (currently `heidihelena`). If that ID is unavailable, change the
   field to the one you registered and rebuild.
2. **Mint a PAT.** In Azure DevOps (<https://dev.azure.com>) →
   *User settings → Personal access tokens → New token*:
   - Organization: **All accessible organizations**
   - Scopes: **Marketplace → Manage**
   - Copy the token once; store it securely.
3. **Publish.**
   ```bash
   export VSCE_PAT='<your-token>'      # not committed, not logged
   npm run publish                     # vsce publish --no-dependencies, reads VSCE_PAT
   # or, to publish a pre-built file:
   #   npx vsce publish --packagePath citevahti-vscode-0.16.0.vsix
   ```

Updating later: bump `version` in `package.json` (keep it in lockstep with the
Python package + the `vX.Y.Z` git tag), `npm run package`, then `npm run publish`.

## 3. (Recommended) Also publish to Open VSX

VSCodium, Cursor, Gitpod, and other non-Microsoft builds pull from
[Open VSX](https://open-vsx.org), not the MS Marketplace. For an open academic
tool this roughly doubles reach.

```bash
npx ovsx create-namespace heidihelena -p '<open-vsx-token>'   # one-time (namespace = publisher)
npx ovsx publish citevahti-vscode-0.16.0.vsix -p '<open-vsx-token>'
```

## What ships in the VSIX

Verify with `npx vsce ls`. It should contain **only**:

```
LICENSE.txt · README.md · icon.png · package.json · out/extension.js
```

No `src/`, no `node_modules/`, no tests, no `.vsix`, no `.DS_Store`
(enforced by `.vscodeignore`). The extension reads no credentials and writes to
Zotero only through the decision-gated, undoable `citevahti` CLI.

## Pre-publish checklist

- [ ] `npm run compile` clean
- [ ] `version` matches `pyproject.toml` and the git tag
- [ ] `CHANGELOG.md` entry for this version
- [ ] `README.md` renders correctly (it is the Marketplace listing page)
- [ ] `npm run package` succeeds and `npx vsce ls` shows only the files above
- [ ] Installed the `.vsix` locally and ran one F5 smoke (verify claims → decide → add → undo)
