# Key-management runbook — CiteVahti signed auto-updates

The **operational** companion to [`AUTO_UPDATE.md`](AUTO_UPDATE.md) (which explains *why*
the update channel is built on TUF/tufup). This is the *how*: the exact steps — with
copy-pasteable commands — to generate the signing keys **offline**, back them up to a USB
drive, sign a release, rotate keys, and recover from a leak.

Do this **before the first signed update ships**. Until it's done, the auto-updater is a
safe no-op (it reports `not_configured` and never touches the network).

> **Read this once, end to end, before running anything.** These commands mint real signing
> keys. Losing the `root`/`targets` keys means you can never publish a trusted update again;
> leaking them means someone else can. Both are recoverable only with pain — see §6.

---

## 0. The keys, at a glance

TUF splits signing into **offline trust anchors** and **online freshness roles**. Respect the
split even in beta — it is the entire reason to use TUF over a "download a file and run it"
updater.

| Key | Role | Secret? | Where it lives |
|---|---|---|---|
| `root` | trust anchor — signs the other roles | **YES** | **Offline only.** Keystore + USB backup. Never CI. |
| `targets` | "this bundle is a legitimate CiteVahti release" | **YES** | **Offline only.** Sign releases locally. Never CI. |
| `snapshot` | which metadata versions are current | yes | Offline for now; *may* move to a reviewer-gated CI env later |
| `timestamp` | freshness; re-signed often | yes | Offline for now; *may* move to a reviewer-gated CI env later |
| `root.json` | the **public** trust anchor clients verify against | **NO** | Committed to the repo + bundled in the app. Public. |

**Blast radius (why `root`/`targets` never go in CI):** a `targets`-signed update is an
automatic, silent push to *every installed client*, with **no central revocation** — unlike
the Apple/Windows code-signing cert, which the OS vendor can revoke. Higher stealth, bigger
blast radius, landing on your clinical-adjacent pilot users. Keep the anchors offline.

---

## 1. Prerequisites

- A machine **you control** (your laptop is fine for beta — a hardware token / air-gapped box
  is a GA-era upgrade, not a beta blocker).
- A **USB drive** for the encrypted backup (any size; the keystore is tiny).
- A **password manager** entry for the key passphrases — stored **separately from the USB**
  (a passphrase written on the same USB protects nothing).
- The CiteVahti venv with the update extra:

```bash
cd /path/to/citevahti
pip install 'citevahti[update]'          # installs tufup (The Update Framework)
```

Pick two directories and export them once per shell session — every command below reuses them:

```bash
export CV_KEYS="$HOME/.citevahti-keys"     # PRIVATE signing keys — never commit, never CI
export CV_REPO="$HOME/citevahti-updates"   # the TUF repo (metadata/ + targets/) you publish
```

---

## 2. One-time: generate the keys (OFFLINE)

Disconnect from the network first (Wi-Fi off) — key generation needs nothing online, and
staying offline keeps the private keys off any wire.

```bash
python - <<'PY'
import os
from citevahti.autoupdate.maintainer import init_repository
init_repository(repo_dir=os.environ["CV_REPO"], keys_dir=os.environ["CV_KEYS"])
print("OK: four role keys + initial signed metadata created")
print("  private keys :", os.environ["CV_KEYS"])
print("  metadata     :", os.environ["CV_REPO"], "(root.json is the public anchor)")
PY
```

tufup encrypts each **private** key on disk with a passphrase it asks you to set. Use a
**strong, unique** passphrase and save it in your password manager **now** — there is no
recovery if you lose it. (Exact prompts follow your installed tufup version; if anything
differs from the above, trust `tufup`'s own docs over this file and tell the maintainer to
update it.)

Verify the outputs exist:

```bash
ls -1 "$CV_KEYS"                      # the private role keys (encrypted)
ls -1 "$CV_REPO/metadata/root.json"  # the PUBLIC trust anchor
```

---

## 3. Back up the keystore to a USB drive (encrypted at rest)

The private keys are already passphrase-encrypted by tufup; the container below is a **second
layer** so a lost or stolen USB is inert on its own. Set `USB` to your mounted drive.

```bash
export USB="/Volumes/YOUR_USB"        # macOS; on Linux e.g. /media/$USER/YOUR_USB
```

**Option A — `age` (simple, cross-platform; `brew install age`):**

```bash
# encrypt a tarball of the whole keystore to the USB (prompts for a backup passphrase)
tar -czf - -C "$CV_KEYS" . | age -p > "$USB/citevahti-keys.tar.gz.age"

# restore later (onto a machine you control):
#   age -d "$USB/citevahti-keys.tar.gz.age" | tar -xzf - -C "$CV_KEYS"
```

**Option B — macOS encrypted disk image (native, no extra install):**

```bash
hdiutil create -encryption AES-256 -stdinpass -size 25m \
  -volname CiteVahtiKeys -fs APFS "$USB/citevahti-keys.dmg"      # prompts for image password
hdiutil attach "$USB/citevahti-keys.dmg"                          # prompts again to mount
cp -R "$CV_KEYS"/. "/Volumes/CiteVahtiKeys/"
hdiutil detach "/Volumes/CiteVahtiKeys"
```

**Custody rules (the whole point):**

- Keep **two** copies on **two** USB drives, stored in **two** locations. One dies, you still
  publish; the site burns down, you still publish.
- The backup passphrase lives in your **password manager**, never on the USB.
- Label the drives; note the date. Re-verify a restore works **once a quarter** (a backup you
  never test is a hope, not a backup).
- The USB is for the **private keys only**. `root.json` is public — it goes in the repo (§4).

---

## 4. Ship the public trust anchor with the app

`root.json` is **not secret** — it holds only public keys, and it is what every client uses to
bootstrap trust. Copy it into the package and commit it (this is part of what flips the updater
from inert to active):

```bash
cp "$CV_REPO/metadata/root.json" src/citevahti/autoupdate/root.json
git add src/citevahti/autoupdate/root.json
git commit -m "Add bundled TUF trust anchor (root.json) for signed auto-update"
```

Then stand up a static HTTPS host serving `metadata/` and `targets/`, and point the app at it:

```bash
# in the app's environment (the frozen desktop app reads this):
export CITEVAHTI_UPDATE_URL="https://updates.citevahti.example"
```

With a frozen build that bundles `root.json` **and** `CITEVAHTI_UPDATE_URL` set, the updater
goes live; the panel's *Desktop app auto-update* → **Update now / Later** flow then works.

---

## 5. Per release (OFFLINE, with the USB keystore available)

CI builds and **code-signs** (Apple/Windows) the bundle; you sign the *update metadata*
locally with the offline keys — the ~30-second step that no server ever sees.

```bash
export CV_VERSION="0.46.0"
export CV_BUNDLE="desktop-extension/build/app/dist/CiteVahti"   # the frozen, code-signed bundle

python - <<'PY'
import os
from citevahti.autoupdate.maintainer import add_release
add_release(repo_dir=os.environ["CV_REPO"], keys_dir=os.environ["CV_KEYS"],
            bundle_dir=os.environ["CV_BUNDLE"], version=os.environ["CV_VERSION"])
print("OK: signed target for", os.environ["CV_VERSION"])
PY
```

`add_release` signs with the `targets` (and freshness) keys — tufup will ask for the
passphrase(s) you set in §2. Then publish the updated metadata + target to the update server:

```bash
rsync -av "$CV_REPO/metadata/" updates-host:/srv/citevahti/metadata/
rsync -av "$CV_REPO/targets/"  updates-host:/srv/citevahti/targets/
```

Clients pick it up on their next launch check and are prompted — never auto-applied,
never mid-review.

---

## 6. Rotation & compromise recovery

- **`targets` rotation (routine):** rotate periodically per TUF guidance. An offline operation
  with the `root` key; re-sign and publish new metadata. Clients follow the `root`-signed
  delegation automatically — no client action needed.
- **`root` rotation (rare, careful):** `root` re-establishes trust for the whole chain. tufup
  supports a signed root-version bump; **re-copy the new `root.json` into the app (§4) and ship
  a build with it**, because clients pinned to the old root need the new one delivered through
  the signed chain. Do this deliberately, not casually.
- **Leaked `snapshot`/`timestamp`:** contained — rotate them and publish. These are the
  online-ish roles precisely because their blast radius is small.
- **Leaked `targets`:** rotate `targets` (signed by `root`) and publish immediately; anyone
  holding the old key can no longer mint accepted updates once the delegation moves.
- **Leaked `root` — the worst case:** there is **no central revocation**. Rotate `root`
  offline, ship a new build carrying the new `root.json`, **and communicate a manual
  re-install out of band** to pilot users (email/Signal), because a client that already trusts
  the leaked root can be fed a malicious chain until it sees the new root. Treat this as an
  incident, not a chore.

**This is the part to get a second pair of eyes on before pilot users grow.** It is flagged as
a maintenance burden in the `secure-release` skill for a reason — key custody and `root`
recovery are where solo maintainers get hurt.

---

## 7. Checklist

- [ ] `pip install 'citevahti[update]'`, `CV_KEYS` / `CV_REPO` exported.
- [ ] Keys generated **offline** (§2); passphrases saved in a password manager.
- [ ] Keystore backed up to **two** encrypted USB drives in **two** locations (§3).
- [ ] Quarterly restore-test scheduled.
- [ ] `root.json` copied into `src/citevahti/autoupdate/root.json` and committed (§4).
- [ ] Update server up; `CITEVAHTI_UPDATE_URL` set in the app environment (§4).
- [ ] Per-release signing step (§5) added to the release runbook next to the version bump.
- [ ] `root`/`targets` are **never** in git or CI — verify before every push.
