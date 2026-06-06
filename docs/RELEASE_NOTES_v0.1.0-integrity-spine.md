# Release notes — v0.1.0-integrity-spine

Tag: `v0.1.0-integrity-spine` · `main` @ `5ea4809` · 308 tests passing (offline).
Package metadata version and runtime `zotsynth.__version__` are both **0.1.0**, aligned with the release tag.

This is the **integrity spine** release: the full human → AI → adjudication
workflow with its provenance, audit, and safety machinery in place. It is a
local, single-user tool.

## What ZotSynth is

A citation-integrity and provenance system for research synthesis. Its value is
**not** autonomous reviewing; it is a documented **human → AI → adjudication**
workflow that can be reported transparently in a methods section. The AI is a
**blinded, advisory second rater only**; the **human or panel is always the
decider**, and AI values never become the recorded final value automatically.

## What the integrity spine includes (steps 1–9)

1. **Probe + state layer** — probe-not-proof startup; `.zotsynth/` durable state;
   hash-chained audit log; binding validators.
2. **Read/discover + cite** — read-only Zotero access; exact-match citekeys.
3. **bib_sync + evidence map** — multi-file citekey sync; typed evidence map with
   a citekey-centered reverse index.
4. **Extraction + claim_check** — deterministic passage retrieval; assistive,
   never-guessing extraction; lexical claim support (candidate-only).
5. **PubMed intake + manual import** — PubMed-only provider; pre-decision intake
   with DOI/PMID dedupe.
6. **Snapshot / corpus_diff / surveillance / map_bootstrap** — hashed corpus
   capture; identity-continuity diffs; last-run-baselined surveillance.
7. **Dual-rating + assess + retraction + PRISMA** — blinded advisory AI rating
   with adjudication; human-only assessment and PRISMA decisions; DOI/PMID
   retraction scan.
8. **Evidence export + agreement report** — neutral CSV/Markdown/CSL-JSON;
   agreement metrics with a method-transparency section.
9. **Guarded Zotero write-back** — optional, dry-run-first, token-confirmed,
   never a silent fallback.

## Runtime assumptions

- **Zotero local API is read-only / GET-only** (`http://localhost:23119/api/`).
- **Better BibTeX is the citation engine** (JSON-RPC + CAYW).
- **PubMed (NCBI E-utilities) is the only literature-search provider** (search-only).
- **`.zotsynth/` is the durable state layer**, independent of Zotero.
- Versions are **probed live**, never assumed: Zotero app version
  (`x-zotero-version`), schema version, and Better BibTeX version are kept
  distinct. Probe results are authoritative.
- **Unit tests use fake seams and pass fully offline** — no live Zotero, BBT,
  PubMed, or network writes are required, and none occur during the suite.

## Safety invariants (summary)

No invented citekeys · no unsupported claim asserted as true · no field guessing ·
no AI final value · no discordant acceptance without adjudication · no inclusion
decisions by AI · no search-strategy design · no Zotero write without a dry-run
token confirmation · no silent local→Web-API fallback · no title-only retraction
truth · no title-only dedupe truth · no mutation during reporting exports except
the export audit event. Full list with enforcing code + guard tests:
[`docs/SAFETY_INVARIANTS.md`](SAFETY_INVARIANTS.md).

## Known limitations

- **No distribution artifacts built in this release.** The `build` module is not
  installed in the environment; no wheel/sdist were produced. To build locally:
  `python3 -m pip install build && python3 -m build`.
- **Live AI rating, retraction provider, and Zotero write backend are degraded by
  default.** They run only behind explicitly configured seams; out of the box a
  confirmed write returns `write_layer_unavailable` and the AI rater requires an
  explicit model pin. This is by design, not a defect.
- **Single-user, local only.** No multi-user server, no hosted deployment.
- **Reporting is descriptive.** Agreement metrics do not validate the AI,
  establish ground truth, or substitute for human judgment.

## How to run smoke checks

```bash
cd /path/to/Zotsynth
bash scripts/final_smoke.sh        # pytest + probe + verify-audit; no writes, no live PubMed
```
Reviewer checklist: [`docs/REVIEW_CHECKLIST.md`](REVIEW_CHECKLIST.md).

## Reporting-guideline statement

ZotSynth **records and reports** what was done in the human–AI workflow. It makes
**no claim of compliance with, or endorsement by, PRISMA 2020, PRISMA-trAIce,
RAISE, or any other reporting guideline or organization.** The method-transparency
output is descriptive language only.
