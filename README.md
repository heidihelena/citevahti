# CiteVahti

**Run unit tests on your manuscript citations.**

CiteVahti checks whether each manuscript claim is actually supported by the paper
cited for it. You rate first, AI gives a blinded second opinion, and every decision is
recorded in an auditable local ledger.

![CiteVahti inline review panel — the manuscript on the left, the evidence-and-decision card on the right.](docs/screenshots/01-review-surface.png)

> **Free beta.** CiteVahti is free to use while in beta. Local-first: your manuscript
> never leaves your device unless you choose to use an external AI model.

## Why use it?

- Catch citations that do not support the sentence they are attached to.
- Review claim by claim, inside the manuscript.
- Keep the human decision primary.
- Use optional AI without letting it silently decide.
- Write to Zotero only after preview and confirmation.
- Export a citation-integrity report for methods, review, or audit.

## Build an evidence map you can use again

**Stop losing evidence work after each project.** Most evidence checks disappear after one
manuscript, one review, or one grant deadline. CiteVahti turns them into something reusable.

Every claim you assess is saved to your own evidence map. Next time you work on the same
topic you don't start from zero: pull back earlier judgments, see which evidence you already
checked, and spot where the literature is still thin, contradictory, or overclaimed. You're
not filling someone else's database — you're building a **private research asset** that gets
more useful each time you use it.

**What you get immediately**

- **Less repeated work** — reuse past claim–evidence judgments in later searches, reviews,
  manuscripts, and replies to reviewers.
- **A clearer view of your own coverage** — which claim areas, study types, and evidence gaps
  you have already worked through.
- **A memory layer for evidence work** — assessments stay tied to the public study
  identifiers, ratings, and agreement status instead of being buried in notes, PDFs, or
  spreadsheets.
- **Control before sharing** — your evidence map stays on your machine; contribution is a
  separate opt-in step, and you preview the exact payload before anything is sent.

**What changes when others contribute.** When enough researchers assess overlapping claims,
CiteVahti can show where your judgments align with the field, where they diverge, and where
your expertise is rare. These comparisons appear only when there is enough independent
overlap — thin data stays hidden. The shared corpus is built from **de-identified**
contributions, never from manuscripts, search histories, patient data, registry data, or
private project identifiers.

**Why contribute.** Contributing is not a donation of free labour: it lets your local
evidence work join a larger evidence map while you keep control of what you send. If you opt
in to commercial use, your contributions may also support aggregate evidence products — but
only as de-identified, group-level outputs. Your individual judgments are never sold, shown,
or shared as individual data.

[How your data is handled →](docs/CONTRIBUTOR_PRIVACY.md)

## Start here

**Which one?** Most researchers want the **Claude Desktop extension** — one click, no terminal,
and your AI assistant runs the review through it. Want a **standalone app window** (no Claude
Desktop)? Use the **desktop app**. Comfortable in a terminal, or scripting a pipeline? Use **pip**.
All three drive the same local-first, human-first review.

### No terminal — Claude Desktop

Download the CiteVahti extension **for your computer** from the
[latest release](https://github.com/heidihelena/citevahti/releases/latest), double-click it,
choose a CiteVahti folder, then ask: *"Run claim tests on my manuscript using CiteVahti."*

- **Windows** — `citevahti-<version>-windows-x64.mcpb`
- **Linux** — `citevahti-<version>-linux-x64.mcpb`
- **macOS** (Apple Silicon) — `citevahti-<version>-macos-arm64.mcpb` (signed + notarized)
- **macOS (Intel)** — no separate bundle; install via `pip install citevahti[mcp]`, or run the Apple-Silicon `.mcpb` under Rosetta.

> **First open on macOS** may show a one-time security prompt — the `.mcpb` is a zip, which
> macOS can't pre-stamp even though the app inside is signed and notarized. If it appears:
> **right-click the file → Open**, or **System Settings → Privacy & Security → "Open Anyway"**.
> Once allowed, it installs and runs normally.

### Desktop app — a real window, no browser

A standalone CiteVahti window: the review panel in a native OS window (not a browser tab, and
no Claude Desktop needed). Install once, then launch it:

```bash
pip install "citevahti[app]"
citevahti-app
```

Drag a `.md` or `.docx` onto the window to begin. The AI second opinion is optional — point it
at a local [Ollama](https://ollama.com) model in AI settings (nothing leaves your machine), or
let an MCP chat client provide it. (Installing takes the terminal once; after that it's just the
app window.)

### Terminal

```bash
pip install "citevahti[mcp]"
citevahti run
```

CiteVahti opens the local review panel at `127.0.0.1`. It tells you the one next thing
to do — no command to remember.

![A "what's next" banner above the manuscript names the next action and takes you there.](docs/screenshots/00-next-step.png)

### Update to a new version

For a clean update — uninstall, clear the cached wheel, then reinstall:

```bash
pip uninstall -y citevahti
pip cache remove citevahti
pip install "citevahti[mcp]"
pip show citevahti          # confirm the new version
```

Or in one line: `pip install --no-cache-dir --upgrade "citevahti[mcp]"`.

Your review data in `.citevahti/` is **not** touched by this — updating only replaces the
program. On Claude Desktop, download the newest extension for your platform and double-click
it to replace the old one.

## The workflow

1. Paste or open a manuscript.
2. Extract claim-like statements.
3. Link candidate evidence.
4. Rate support yourself.
5. Reveal the AI second opinion.
6. Decide: accept, caution, review, or reject.
7. Preview Zotero or manuscript changes.
8. Export the report.

The card walks a visible **Rate → Reveal → Decide → Write** stepper, one claim at a time,
so you always know where you are and what comes next.

![The right-hand card showing the Rate → Reveal → Decide → Write stepper.](docs/screenshots/04-rate-reveal-decide-write.png)

Starting from nothing is just as guided: paste a paragraph and CiteVahti takes it from
there — no account, nothing uploaded.

![First-run empty state with a box to paste a manuscript paragraph.](docs/screenshots/03-first-run.png)

## Privacy and safety

CiteVahti is local-first.

- Manuscripts and ratings stay in `.citevahti/` on your machine.
- The panel runs on loopback (`127.0.0.1`) only.
- Zotero writes require preview and confirmation.
- AI is optional and blinded.
- Local AI and bring-your-own API key modes are supported.
- No telemetry.

## What AI does

AI is a **second rater, not the judge.** You always rate first. CiteVahti can then compare
your rating with an optional AI rating from:

- your MCP assistant,
- a local model such as Ollama,
- or your own OpenAI/Anthropic-compatible API key.

The AI rating stays hidden until your rating is in, and the final decision is always
yours. There is no hidden AI subscription — pick the mode you want, or leave AI off.

![AI second-opinion settings: Off · Local AI · My API key.](docs/screenshots/06-ai-settings.png)

### Run AI on your own machine (free, private)

Local mode runs the model on your computer — no API key, nothing leaves your device.

1. Install [Ollama](https://ollama.com/download) (macOS: `brew install ollama`).
2. Pull a model — `qwen2.5` is recommended for claim checking:
   ```bash
   ollama pull qwen2.5
   ```
   (Pick a smaller tag if your machine is tight on memory, e.g. `ollama pull qwen2.5:3b`.)
3. In the panel, open **✦ AI → Local AI**. CiteVahti detects the installed model and
   pins its exact version so the rating stays auditable.

To update later, re-pull the same name (`ollama pull qwen2.5`) for the newest build.

## What gets written

CiteVahti never silently changes Zotero or your manuscript. Every write follows the same
gate:

```
Preview → Confirm → Audit → Undo available
```

## What you can export

Generate a citation-integrity report (Markdown, print-ready HTML, Word, or a review-packet
`.zip`) for a methods section, a co-author, a supervisor, or a journal. The packet even
includes an auto-filled methods paragraph with your review's actual numbers.

![The citation-integrity report export.](docs/screenshots/07-report-export.png)

## What it does and does not check

CiteVahti checks **citation support, not the truth of the underlying claims.** It tests
whether the cited paper supports the sentence — it does not certify that every claim in
the manuscript was entered, and it is not a clinical or scientific oracle. Blinding is a
panel-enforced workflow (the AI value is withheld until you rate), recorded in the ledger
with timestamps and comparison status so the order is auditable, not assumed.

## Responsibility & disclosure

CiteVahti is a **local-first citation-support audit tool for manuscript claims** — it
helps authors test whether the cited evidence supports each claim before submission.

Use of CiteVahti **does not certify** scientific truth, manuscript quality, publication
suitability, or the absence of citation problems. It provides structured decision support
and an audit trail; **final responsibility remains with the human author, reviewer,
editor, or institution.** CiteVahti is developed by the author — any publication, review,
teaching, or evaluation that uses it should **disclose the tool use and the developer
relationship where relevant.** Ready-to-adapt disclosure text and the full statement are in
[docs/DISCLOSURE.md](docs/DISCLOSURE.md).

## Documentation

- [Quickstart](docs/QUICKSTART.md)
- [CLI reference](docs/CLI.md)
- [Safety invariants](docs/SAFETY_INVARIANTS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Reporting in your methods section](docs/REPORTING.md)
- [Status & capabilities](docs/STATUS.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [Writing good (atomic) claims](docs/WRITING_GOOD_CLAIMS.md)
- [Responsibility, disclosure & conflict of interest](docs/DISCLOSURE.md)
- [Contributor privacy](docs/CONTRIBUTOR_PRIVACY.md)
- [Dependencies / SBOM](docs/SBOM.md)

## Feedback & support

CiteVahti is a free beta and your feedback shapes it.

- **Found a bug, or a citation judged wrong?** Open an issue — there are quick forms for
  [a bug](https://github.com/heidihelena/citevahti/issues/new?template=bug_report.yml) and for
  [a wrong support judgment](https://github.com/heidihelena/citevahti/issues/new?template=wrong_support_judgment.yml).
- **Have an idea?** [Request a feature](https://github.com/heidihelena/citevahti/issues/new?template=feature_request.yml).
- **Anything private or security-related?** Email **privacy@vahtian.com** — please don't open a public issue.

New here? Try `citevahti demo` (or the [3-minute path](docs/QUICKSTART.md)) first.

## Companion: FullVahti

[**FullVahti**](https://github.com/heidihelena/fullvahti) is a sibling Zotero plugin that
finds free, legal open-access PDFs for your references and writes CiteVahti's verified
results back as tags — so the citation check and the full text live in one place. See the
[FullVahti README](https://github.com/heidihelena/fullvahti) to install (a two-click Zotero
plugin, no terminal).

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
