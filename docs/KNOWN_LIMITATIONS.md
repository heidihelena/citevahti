# Known limitations

CiteVahti is honest about what it does *not* do. Read this before relying on it
for anything high-stakes (a thesis defense, a submission, a reviewer response).

## Scope & maturity
- **Beta, single-developer, single-user, local-first.** No multi-user sync, no
  server, no account. Your manuscript and ratings stay on your machine.
- **No published accuracy benchmark yet.** The engineering is well-tested
  (hundreds of offline tests), but claim-extraction accuracy, human inter-rater
  reliability, and AI–human agreement have not yet been measured and published.
  Treat CiteVahti as a disciplined *workflow*, not a validated *oracle*.

## What it checks — and what it doesn't
- It records whether a cited source **supports a specific claim**. It does **not**
  judge whether the claim is **true** or **clinically valid**. A well-supported
  claim can still be wrong; an unsupported claim can still be true.
- The system **never asserts** that a paper supports a claim — it records *your*
  judgment (AI is a blinded second opinion you may ignore).

## Evidence coverage
- Literature lookups use **PubMed, OpenAlex, Semantic Scholar, and Crossref** —
  strongest for **biomedical/indexed journal** literature. **Books, clinical
  guidelines, grey literature, institutional reports, and non-indexed sources**
  may not be found, and a claim cited to one of those can't be machine-checked.
- **Full text vs abstract.** CiteVahti stages candidate papers and shows each
  paper's own **abstract** (blinding-safe) for you to read before rating. It does
  **not** fetch or parse the **full text** for you — your support judgment is only
  as good as what you actually read.

## Identifiers
- **Retraction** and **duplicate** checks key on **DOI/PMID only**. An item with
  no DOI or PMID is **not** retraction-checked or deduped, and can't be written to
  Zotero (anti-fabrication: no unverifiable citations).

## Claim granularity
- A sentence with **multiple claims** makes the support judgment ambiguous. Keep
  claims **atomic** — see [WRITING_GOOD_CLAIMS.md](WRITING_GOOD_CLAIMS.md).

## AI second opinion
- The AI rating is **optional** and its quality depends entirely on the model you
  choose (your chat assistant via MCP, a local model, or your own API key) — or
  none at all. CiteVahti adds no AI of its own and never lets AI decide.

## Writing environment
- Review happens on **Markdown** in the local panel. If you write in **Word /
  Google Docs**, you import to Markdown (or paste), review, then **cite-stable
  export** bridges back to a `.docx` with live citations (Pandoc). There is no
  in-Word plugin yet.

## Integrations required for some features
- **Citekey injection** and **Zotero write-back** need **Zotero** running with the
  **Better BibTeX** add-on. Without them, you still get claim review, the report,
  and a minted-key bibliography — just not your library's own citekeys or writes.
- **Group-library** targeting is supported but newer than personal-library use.

## Audit trail
- The hash-chained audit log is **tamper-evident, not tamper-proof** — it detects
  edits to the recorded history; it is not a cryptographic signature or notarized
  attestation (optional RFC-3161 timestamping of the audit head is available).
