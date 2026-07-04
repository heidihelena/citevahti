# CiteVahti Privacy Policy

*A product of Vahtian. Last updated 2026-07-04.*

The canonical, hosted version of this policy is at
**<https://vahtian.com/citevahti/privacy>**; this file is its source of record.

CiteVahti is a **local-first, single-user** citation-integrity tool. It runs on your own
computer, and your manuscript and your ratings stay there. This policy describes exactly
what data CiteVahti handles, where it goes, and what it never does.

## What CiteVahti collects

**Nothing about you, and nothing for us.** CiteVahti has **no telemetry, no analytics, and
no account.** It does not phone home, and it collects no usage data, personal data, or
manuscript content for Vahtian or any third party.

The only data CiteVahti reads is the material **you point it at** on your own machine — the
manuscript file you choose, the claims you write, and the ratings and decisions you record.
It does not read your Claude conversation history, your other uploaded files, or anything
outside the project folder you open.

## Where your data is stored

**On your machine, only.** CiteVahti keeps everything in a local project ledger
(`.citevahti/` inside your project folder): your claims, your evidence, your blinded
ratings, your decisions, and a hash-chained audit log. There is **no cloud storage and no
server** holding your data. Data is retained for as long as you keep those files, and is
deleted when you delete them. Your Zotero API key, if you connect one, is stored in your
operating system's keychain — never in a config file, a log, or anywhere CiteVahti transmits.

## When data leaves your machine — and only then

CiteVahti makes outbound network requests **only** for these purposes, and only when you
take the corresponding action:

- **Literature lookups.** When you search for or check evidence, CiteVahti sends your search
  query and the titles/DOIs/PMIDs of the references you look up to public scholarly services:
  **PubMed (NCBI), OpenAlex, Semantic Scholar, and Crossref/doi.org.** These are the standard
  literature databases; each has its own privacy policy.
- **Your Zotero, if you connect it.** Reading your library, and — only as the final,
  previewed, one-click-confirmed step of a citation decision — writing a citation back to it.
  This talks to your own Zotero account (local API or the Zotero Web API), nowhere else.
- **Update check (optional).** Checking whether a newer CiteVahti release exists sends **one**
  request to the public PyPI API. It is user-initiated (a button, a command, or the
  **default-off** "check when the panel opens" setting), sends **no data about you**, and
  never installs anything.

CiteVahti sends **no manuscript text, no claims, and no ratings** to any of these services
beyond the search terms and reference identifiers described above. There is no other egress.

## The AI second opinion

CiteVahti's optional AI second rating is **off by default.** When you enable it, you choose
the provider: your MCP assistant (e.g. Claude Desktop), a **fully local** model (Ollama /
LM Studio, no network), or your own API key. Only in the API-key mode does the claim text
you are rating go to the provider you configured — and that is a provider *you* chose and
contract with, under *their* privacy policy. CiteVahti stores no such key except in your OS
keychain, and the AI rating is always blinded until your own human rating exists.

## Sharing

CiteVahti shares your data with **no one.** The de-identified validation warehouse is a
**local, opt-in, default-off** feature; contributing any of it to the shared research corpus
is a **separate, explicit action** you take, with its own
[contributor privacy notice](../CONTRIBUTOR_PRIVACY.md) — never automatic.

## What CiteVahti is not

CiteVahti records whether a cited source *supports* a claim; it does not determine truth, and
it is **not a medical device and gives no clinical advice.** It produces design evidence under
stated assumptions, for you to check — not a guarantee.

## Contact

Questions, issues, or a privacy request: **<https://github.com/heidihelena/citevahti/issues>**,
or the contact details at **<https://vahtian.com/citevahti>**.
