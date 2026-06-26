# Secure auto-updates & code signing for the desktop app

The desktop app (`CiteVahti.app` / `.exe` / Linux bundle) is the **primary product** and
currently has **no auto-update mechanism**. This is the canonical plan for adding one safely.
It is forward-looking — most of this isn't built yet — so when you implement a piece, move the
"how it actually works in this repo" detail into `desktop-extension/BUILD.md` and leave the
*reasoning* here.

Sourcing: the recommendations below come from a verified deep-research pass (primary vendor
docs: Apple, Microsoft Learn, tufup/TUF). Three items rest on vendor behavior that changes —
they're dated **June 2026**; re-verify before relying on them.

## The mechanism: tufup (not PyUpdater, not a hand-rolled checker)

Use **tufup** (`pip install tufup`). It is built on `python-tuf`, the CNCF-graduated reference
implementation of The Update Framework, and automates the full cycle for a stand-alone Python
app: build a signed archive + patch, check for updates, download, install. It is
packaging-agnostic and works with PyInstaller bundles.

- **Why tufup over a "check a version endpoint + download installer" script:** TUF's signed
  metadata gives you authenticity + integrity **even if the update server is compromised**. A
  plain HTTPS-download checker trusts whoever controls the download URL; if that server (or its
  DNS, or a CDN account) is taken over, it can push a backdoored "update" to every pilot user
  silently. TUF is specifically designed to stop that.
- **Why NOT PyUpdater:** effectively abandoned — last release April 2021, repo archived
  September 2022. Its EdDSA dual-key design is a good *reference* for what good update security
  looks like, but don't depend on dead code. tufup exists precisely as its maintained successor.
- **Why NOT pywinsparkle / Sparkle:** viable but Windows-only (or platform-specific), so you'd
  maintain a separate updater per OS. tufup is one cross-platform path — the right call for a
  solo maintainer.

## The key split — the one rule that makes tufup worth using

TUF divides signing into **offline** trust anchors and **online** freshness roles. This split
is the entire security benefit. Respect it even during beta:

| Role | Authorizes | Where it may live |
|---|---|---|
| `root` | the trust anchor — signs the other roles | **Offline.** Never in CI. |
| `targets` | "this bundle is a legitimate CiteVahti release" | **Offline.** Sign locally at release time. |
| `snapshot` | which metadata versions are current | OK in CI (online role) |
| `timestamp` | freshness; re-signed frequently | OK in CI (online role) |

**Why `targets`/`root` stay offline even though the Apple cert is already in CI:** the two
signatures protect different things and have different blast radii.
- An Apple-signed `.app` signs a *fresh download the user fetches*; Apple can **revoke** the
  cert and Gatekeeper enforces it.
- A `targets`-signed update is an *automatic, silent push* to every already-installed client,
  with **no central revocation authority**. Higher stealth, bigger blast radius — and it lands
  on the exact clinical-adjacent pilot population you most need to protect.

So defense-in-depth keeps `targets`/`root` out of CI. The practical workflow for a solo dev:
CI builds (and Apple/Windows code-signs) the bundle; you run the ~30-second `tufup` publish
step **locally** with the offline keys to sign the new target; CI uploads the signed metadata +
target to the static update server. An encrypted keystore dir on your machine (backed up the
same way as the going-public bundle) is sufficient key custody for beta — a hardware token is a
GA-era upgrade.

**Beta shortcut, if you must put everything in CI for velocity:** it's defensible only with all
three of (1) every Action pinned to a SHA, (2) the signing job gated behind a GitHub
Environment with required reviewers, and (3) a written note that it's a beta-only posture with
a trigger to move `root`/`targets` offline (e.g. before the curated-directory listing, or
before pilot users exceed N). Temporary CI keys quietly become permanent; don't let them.

## Code signing & notarization — the prerequisite

Signing isn't optional polish: it's the precondition for a trustworthy update channel **and**
for a no-scare first launch (a non-technical researcher who hits "unidentified developer" will
quit). The repo already has `desktop-extension/sign-notarize.sh` and `entitlements.plist` for
the `.mcpb` binary — the desktop `.app` uses the same Apple flow.

### macOS — effectively mandatory, fully scriptable
Notarization is an automated Apple **scan** (not human App Review) of Developer ID-signed
software; it's been required for Developer ID distribution since June 2019 (macOS 10.15+).
`notarytool` + `stapler` (bundled with Xcode) script cleanly in CI (`--wait`,
`--output-format json`, `store-credentials`). Needs a paid **Apple Developer ID ($99/yr)**. The
existing `sign-notarize.sh` already does: codesign with hardened runtime + entitlements +
secure timestamp → verify → **smoke-test the signed binary still runs** → notarize with
`--wait`. Keep that smoke test; a hardened-runtime + onefile freeze can sign cleanly yet fail
to launch. *(Apple requirements only tighten; dated June 2026.)*

> Note: a `.mcpb` (a zip) **cannot be stapled** — its notarization ticket lives on Apple's
> servers and Gatekeeper checks it online on first launch. For an offline-proof ticket, ship
> the binary inside a signed + notarized `.pkg`/`.dmg` and staple that. The `.app` *can* be
> stapled.

### Windows — sign under the Vahtian org, do NOT buy EV
- **EV certificates no longer bypass SmartScreen** (Microsoft removed that in 2024) — EV-signed
  files build reputation the same as OV, so the $400+/yr EV premium buys nothing here.
- **Azure Artifact Signing** (formerly Trusted Signing) is Microsoft's recommended path:
  ~$9.99/mo, no hardware token, native to GitHub Actions. **But it is geo-restricted** —
  *individual* developers are limited to USA/Canada; *organizations* also get EU/UK.
- **Consequence for this founder (EU/Finland):** as an individual she can't use the cheap path
  → she'd need a traditional OV certificate with hardware-token/cloud-HSM storage (real CI
  friction). **The fix: sign Windows builds under the Vahtian organization**, which unlocks the
  token-free Azure path in the EU. Confirm Vahtian's org verification satisfies Azure before
  depending on it. *(Geo-limits say "currently"; dated June 2026.)*

### Linux
AppImage + zsync (delta updates) or a Flatpak/Snap with the store's own auto-update. Lower
priority than mac/Windows for this user base; tufup also covers Linux bundles directly.

## Update UX (ties to SKILL.md §3)
Prompted-with-release-notes beats silent for a tool handling research provenance — the user
should know *what changed* before their analysis environment shifts. Keep a rollback path
(tufup retains prior archives). Never auto-update a review mid-session.

## First implementation order
1. macOS signing + notarization wired into CI (unblocks trust + updates; the script exists).
2. Windows signing under Vahtian (Azure Artifact Signing).
3. tufup repo init + the release flow with the key split baked in (CI builds & notarizes; you
   sign `targets` locally; CI publishes).
4. In-app update check + prompted-update UX.
Defer: delta updates, Linux store packaging, a fully-CI-side signing setup.
