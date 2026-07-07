# CiteVahti — production launch copy (draft v1)

<!-- content-pipeline header -->

- **Audience:** systematic reviewers, PhD supervisors, journal editors, research support offices — anyone accountable for citation accuracy in a manuscript.
- **Decision problem:** "Can I trust that every citation in this document says what the text claims it says — before a reviewer or reader finds out it doesn't?"
- **Funnel stage fed:** Awareness → free tool (web app) → Kit / design-review.
- **Evidence basis:** product architecture facts from CiteVahti development (local-first Zotero MCP, dual-rating adjudication aligned with PRISMA-trAIce and Cochrane/Campbell standards). Items marked [VERIFY] are unconfirmed by me and must be checked against the current repo before publication.
- **CTA (one):** Try the web app on a real reference list. <!-- swap to beta-signup link if prod not live -->
- **Risk flag:** Not clinical content. Low risk. One integrity-claim risk: never let copy imply CiteVahti *guarantees* citation correctness — it surfaces problems for human adjudication.

-----

## Hero

**Every citation, checked. No verdicts, just evidence.**

CiteVahti reads your manuscript's citations and tells you which ones are verified, which are contested, and which don't support the claim they're attached to — so you fix them before a reviewer does.

## The problem (evidence section)

Citation errors are not rare edge cases. Quotation errors — citations that don't support the claim — appear across published biomedical literature at rates consistently reported in the double digits [VERIFY: pick one primary source, e.g. a quotation-error meta-analysis, and cite it precisely; do not publish this paragraph without it]. Retracted papers keep accumulating citations years after retraction. And AI-assisted writing has added a new failure mode: fluent, well-formatted references to papers that don't exist.

Most reference managers check formatting. None of that tells you whether the citation is *true*.

## How it works (product facts)

1. **Connect your library.** CiteVahti runs against your Zotero library, locally. Your manuscript and references stay on your machine — nothing is uploaded to us.
1. **Check every claim–citation pair.** Each citation is assessed on two independent ratings and adjudicated where they disagree, following the same logic as dual screening in systematic reviews (PRISMA-trAIce, Cochrane/Campbell aligned).
1. **Get an evidence-tiered report.** Every citation gets a status — verified / contested / unverifiable / flagged (retraction, mismatch, nonexistent) [VERIFY exact tier labels against current build] — with the reasoning shown, not hidden.

Available as an MCP server (Claude, other MCP clients), a desktop extension, and a web app.

## What CiteVahti will not do (boundary section — keep verbatim)

CiteVahti never issues a verdict on your work. It does not "approve" a manuscript, certify integrity, or replace your judgment as author or reviewer. It surfaces evidence about each citation and shows its reasoning. Adjudication is yours. It also never phones your data home: the architecture is local-first by design.

## Beta honesty block (keep until production criteria met)

CiteVahti is in beta. That means: the checking pipeline works, the failure modes are documented openly, and we publish our evaluation results — precision and recall against a ground-truth citation set — rather than asking you to take accuracy on faith. [VERIFY: link eval results page once citevahti-eval produces them.]

## CTA

**Run it on one reference list.** Ten minutes, your own manuscript, local. → [web app link]

-----

## LinkedIn excerpts (log per content-pipeline)

1. "Your reference manager checks formatting. Nothing checks whether the citation is true." → thread on quotation errors + web app CTA.
1. "We publish CiteVahti's precision and recall instead of asking you to trust it. Evidence tools should be held to evidence standards." → eval-results post, once numbers exist.
1. "CiteVahti never issues a verdict. Here's why that's a feature, not a limitation." → brand-core piece.

-----

# Repo verification notes (appended in-repo — resolve before publication)

Checked against the repo at the time this draft landed. Each note maps to a [VERIFY]
flag above or to a claim the current build contradicts. **Run `citevahti-claims` on the
final copy before it goes anywhere public.**

1. **Tier labels [VERIFY] — DOES NOT MATCH the build.** The copy's
   "verified / contested / unverifiable / flagged" is not what CiteVahti ships. The real
   claim states are **accepted `[oo]` / caution `[o]` / review `[r]` / rejected `[d]` /
   untestable `[u]`** (see `skills/citevahti-dev/SKILL.md` and `docs/GLOSSARY.md`), plus
   retraction flags and the claim-check statuses `supported_candidate` /
   `contradiction_candidate`. Either revise the copy to the shipped labels or treat the
   copy's labels as a product-rename proposal — but don't publish the mismatch.
   Also: "verified" as a status name is exactly the certification-adjacent language the
   risk flag warns about; the shipped vocabulary avoids it deliberately.

2. **"PRISMA-trAIce, Cochrane/Campbell aligned" — soften before publishing.**
   `docs/METHODS.md` §"PRISMA-trAIce / RAISE-style transparency" explicitly states the
   report **does not assert compliance with, or endorsement by, PRISMA 2020,
   PRISMA-trAIce, RAISE, or any other framework**. "Aligned with" in marketing copy reads
   as a compliance claim. Safer phrasing: *"mirrors the dual-screening logic used in
   systematic reviews, with PRISMA-trAIce / RAISE-style transparency reporting."*

3. **"Web app" — it's local, not hosted.** Per ADR-0007 the "web app" is the local
   loopback panel (`citevahti-panel`); there is no hosted try-it-now page. The CTA link
   must go to install/quickstart (`docs/QUICKSTART.md`), not imply a browser-only demo.
   The "nothing is uploaded to us" sentence is true (no telemetry), but literature
   lookups do go out to PubMed / OpenAlex / Semantic Scholar / Crossref — the quickstart
   states this; keep copy consistent with it.

4. **Quotation-error rate [VERIFY] — still open.** Not resolvable from the repo; needs a
   primary literature citation (e.g. a quotation-error meta-analysis) checked through
   CiteVahti itself before the paragraph ships. Do not publish without it.

5. **Eval results link [VERIFY] — no numbers exist yet.** `validation/claimcheck/` has
   the pre-registered measurement ledger and scoring tools, but the human rater columns
   are unfilled — there are **no publishable precision/recall numbers** as of this
   commit, and `docs/KNOWN_LIMITATIONS.md` says so ("No published accuracy benchmark
   yet"). The beta honesty block currently promises published results in the present
   tense ("we publish our evaluation results"); until `citevahti-eval` produces them,
   phrase it as commitment, not fact — e.g. "we will publish…" — or hold the block.

6. **"Fabricated / nonexistent reference" detection — scope-check.** The anti-fabrication
   guarantee in the build is on the *write path* (no citekey without Better BibTeX; no
   Zotero write without DOI/PMID verification). Detecting fabricated references in an
   *incoming* reference list is the `citevahti-screen` sweep keyed on DOI/PMID — items
   with neither identifier can't be machine-checked (`docs/KNOWN_LIMITATIONS.md`). The
   hero copy is fine; just don't let later copy escalate it to "catches hallucinated
   references", which is on the must-not-claim list.
