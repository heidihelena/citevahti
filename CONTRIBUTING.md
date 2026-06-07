# Contributing to CiteVahti

CiteVahti (a product of **Vahtian**) is open-core: the library, CLI, and VS Code
extension are Apache-2.0 and local-first, and the hosted layer is separate and
separately licensed (see [ADR-0003](docs/adr/0003-hosted-layer-and-open-core.md)
and [ADR-0004](docs/adr/0004-brand-ip-and-entity.md)). For that model to hold,
contributions have to come in cleanly. This document is the gate.

## Developer Certificate of Origin (DCO)

By contributing, you certify the **[Developer Certificate of Origin 1.1](https://developercertificate.org/)**:
that you wrote the change (or have the right to submit it) and that it may be
provided under the project's license. You certify it by signing off every commit:

```bash
git commit -s -m "your message"      # appends: Signed-off-by: Your Name <you@example.com>
```

Use a real name and a reachable email. Unsigned commits will be asked to amend
(`git commit --amend -s`).

> **Why DCO and not a heavyweight CLA?** The DCO is lightweight and contributor-
> friendly, and it gives the project the provenance it needs. If a future
> separately-licensed module ever requires a stronger Contributor License
> Agreement, that requirement will be stated explicitly on the relevant module —
> never applied retroactively to code you already sent under the DCO.

## What you're agreeing your contribution can be used for

- The **Apache-2.0 core** (this repository's library, CLI, extension): your change
  ships under Apache-2.0.
- Contributions are accepted on the understanding that the maintainer may relicense
  **its own** first-party code into the separately-licensed hosted layer. Your
  Apache-2.0 contribution stays Apache-2.0; the DCO confirms you had the right to
  submit it. (This is the standard open-core arrangement; if that's ever not
  enough for a specific module, that module will carry its own explicit CLA.)

## Ground rules (the non-negotiables)

These are enforced in code and in review. A change that weakens any of them will
be declined regardless of how nice the diff is:

- **The human is the decider.** The AI is a blinded, advisory second rater. No
  change may let an AI value become the recorded `final_value`, set the human
  rating, or make the final accept/reject decision.
- **Blinding is real.** The AI rating stays hidden until the human has rated.
- **No silent writes.** Zotero writes are decision-gated, preview-then-token,
  undoable, and audited. The agent surface never gets a one-call write.
- **Dedupe fails closed.** Uncertainty refuses rather than risks a duplicate.
- **No credentials in logs, configs, prompts, analytics, exports, or the agent
  surface.** Secrets live only in the OS keychain / env.
- **No fabricated citations**, no "AI approved" language, no claim of guideline
  compliance/endorsement.

## Development

The test suite is **fully offline** (no live Zotero/PubMed/network, no API keys)
and runs in a few seconds. From a clean checkout, install into a virtualenv and run
pytest **through the venv's own interpreter**:

```bash
# with uv:
uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"
# …or with stock pip (Python 3.10+):
python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"

python -m pytest               # ~592 tests, a few seconds (httpx is a core dep; pytest is from [dev])
bash scripts/final_smoke.sh    # pytest + probe + verify-audit, no writes
```

> **Use the venv's `python -m pytest`, not a globally-PATHed `python3`.** A
> system/conda `python3` usually has no `pytest`, which reports `No module named
> pytest` — that is the wrong interpreter, not a test failure. `which python`
> should point inside `.venv` after activation.

To verify a specific tagged release exactly as a reviewer would:

```bash
git checkout v0.14.0
python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
python -m pytest -q            # expect: all passing, fully offline
```

- The Python package is imported as `citevahti` (a stable alias across the brand
  rename); the CLI is `citevahti` (with `citevahti` kept as a working alias).
- New behavior needs tests, and the suite must stay **green and offline**.
- Significant architectural changes get an **ADR** under `docs/adr/` rather than a
  large unexplained diff.

## Reporting security or integrity issues

If you find a way to bypass a safety invariant (silent write, blinding leak,
credential exposure, dedupe bypass, fabricated provenance), please report it
privately to the maintainer rather than opening a public issue first.
