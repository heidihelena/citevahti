# Auto-updates for the CiteVahti desktop app

Signed auto-updates for the **frozen desktop app** (the PyInstaller bundle), built on
[`tufup`](https://github.com/dennisvang/tufup) → [The Update Framework](https://theupdateframework.io)
(`python-tuf`). Updates are delivered as **signed metadata + hashes**, so a client accepts a new
version only if it was signed by CiteVahti's offline keys — authenticity and integrity **even if
the update server is compromised**.

> This is separate from `citevahti.update_check` (the "newer version on PyPI?" nudge for the pip
> install). A `pip` install updates with `pip`; this updates the *frozen app* in place.

## Status: scaffold, inert until you generate keys

The code is in place (`src/citevahti/autoupdate/`, the `update` extra, the launch-time check),
but it is a **safe no-op** until two founder-only steps are done: generating the offline keys and
standing up the update server. Until then the app launches and behaves exactly as before.

The check is **never silent**: `check_for_update()` is read-only; an update is only ever
downloaded and applied after an explicit decision (`apply_update()` is the post-consent step).

## The security model — the key split (do not skip)

TUF divides signing into **offline trust anchors** and **online freshness roles**. Respecting
this split is the entire reason to use TUF over a "download a file and run it" updater.

| Role | Authorizes | Where it lives |
|---|---|---|
| `root` | the trust anchor — signs the other roles | **Offline. Never in CI.** |
| `targets` | "this bundle is a legitimate CiteVahti release" | **Offline. Sign locally at release.** |
| `snapshot` | which metadata versions are current | online role — may later move to CI |
| `timestamp` | freshness; re-signed often | online role — may later move to CI |

A `targets`-signed update is an automatic push to every installed client with **no central
revocation** — far higher blast radius than a code-signing cert (which Apple/Microsoft can
revoke). So `root`/`targets` stay offline even in beta. **A leaked `root` key is the painful
one** — recovering trust with already-installed clients is hard; guard it like a signing HSM.

## One-time setup (founder, offline)

```bash
pip install 'citevahti[update]'      # tufup
```

1. **Generate the keys + initial metadata** into an offline keystore:
   ```python
   from citevahti.autoupdate.maintainer import init_repository
   init_repository(repo_dir="~/citevahti-updates", keys_dir="~/.citevahti-keys")
   ```
2. **Back up `~/.citevahti-keys`** securely (encrypted; the same way as the going-public backup
   bundle). Losing `root`/`targets` means you cannot publish trusted updates again.
3. **Bundle the trust anchor with the app**: copy the generated `root.json` to
   `src/citevahti/autoupdate/root.json` so it ships inside the PyInstaller build. (Its presence
   is part of what flips the updater from inert to active.)
4. **Stand up a static file server** (any HTTPS host / object store) serving `metadata/` and
   `targets/`, and set `CITEVAHTI_UPDATE_URL` to its base URL in the app's environment.

## Per release (founder, offline)

```bash
./desktop-extension/build-app.sh <version>     # build the frozen bundle (and code-sign it)
```
```python
from citevahti.autoupdate.maintainer import add_release
add_release(repo_dir="~/citevahti-updates", keys_dir="~/.citevahti-keys",
            bundle_dir="desktop-extension/build/app/dist/CiteVahti", version="0.41.0")
```
Then upload `~/citevahti-updates/{metadata,targets}/` to the update server. Clients pick it up on
their next launch check.

> **Two distinct signatures.** tufup signs the *update metadata* (these offline keys). Apple/
> Windows code-signing signs the *bundle* so the OS trusts it on first launch — a separate
> concern handled in `desktop-extension/BUILD.md` / the secure-release skill. You need both for a
> no-scare, auto-updating product.

## Key-management runbook

- **Custody:** `root`/`targets` private keys live only in the encrypted offline keystore + its
  backup. Never commit them; never put them in CI. `snapshot`/`timestamp` may move to a
  reviewer-gated CI environment later (a GA optimization), but not `root`/`targets`.
- **Rotation:** rotate `targets` periodically per TUF guidance; rotate `root` rarely and
  carefully (it re-establishes trust). Both are offline operations.
- **Compromise:** if a key leaks, rotate it offline and publish new metadata. A `root`
  compromise is the worst case — plan to communicate a re-install out of band if it happens.
- **Get help here:** this is the part of "production-grade" worth a second pair of eyes before
  the pilot population grows — it is flagged as a maintenance burden in the secure-release skill.

## Follow-ups (not in this scaffold)

- The **prompted download/apply UX** in the desktop app (a "Update now / Later" dialog with
  release notes). Today an available update is surfaced at launch and via the panel's *Check for
  updates* affordance; `apply_update()` exists but isn't yet wired to a UI button.
- Moving `snapshot`/`timestamp` signing into a reviewer-gated CI environment.
- A delta-update path (tufup supports patches) once bundles are large enough to warrant it.
