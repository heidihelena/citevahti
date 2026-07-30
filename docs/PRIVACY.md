# CiteVahti Privacy Policy

*A product of Vahtian. Last updated 2026-07-30.*

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

## When data leaves your machine

CiteVahti makes outbound network requests only when an action needs one — nothing runs on
a timer, and nothing reports back to Vahtian. The table below lists **every outbound path
in CiteVahti 0.45.0, as of 2026-07-30**, with what is sent, what triggers it, and how to
keep it off.

| Path | Destination | What is sent | Trigger | Default / how to keep it off |
| --- | --- | --- | --- | --- |
| Literature search & evidence check | PubMed / NCBI E-utilities (`eutils.ncbi.nlm.nih.gov`) | Your search query, the PMIDs/DOIs you look up, and — if you added them during onboarding — your NCBI API key and contact email | You (or your agent, at your request) search for or check evidence | Only runs when you use those features; offline, they degrade with a plain message |
| Literature search & retraction check | OpenAlex (`api.openalex.org`) | Search terms, DOIs/PMIDs, and your contact email (OpenAlex "polite pool") | Same as above, plus the retraction check | Same as above |
| Literature search | Semantic Scholar (`api.semanticscholar.org`) | Search query; an API key header only if you configured one | Evidence search | Same as above |
| Title → DOI resolution | Crossref (`api.crossref.org`) | Candidate reference titles and your contact email | Importing/linking a reference that has no DOI or PMID | Same as above |
| Zotero, if you connect it | Your Zotero: local API first (localhost), else the Zotero Web API (`api.zotero.org`); `www.zotero.org` for the key/OAuth connect pages | Your Zotero API key (also sent once to check it when you store it), library reads, and — only as the final, previewed, one-click-confirmed step of a citation decision — the citation write | Connecting Zotero; reading your library; confirming a writeback | Only if you connect Zotero; the local-API mode stays on your machine |
| AI second opinion, API mode | The provider endpoint **you** configure (e.g. `api.openai.com`, `api.anthropic.com`; https-only) | **The claim text plus the candidate paper's title and abstract** (claim-support rating), or the question frame — PICO, outcome and study labels — (GRADE rating), with your API key | You enable AI rating and run a rating | **Off by default.** Local mode (Ollama / LM Studio) stays on localhost; see the AI section below |
| Update check | PyPI (`pypi.org`) | The package name only — no data about you | The **Check for updates** button, the `check-update` command, the agent tool, or the **default-off** "check when the panel opens" setting | User-initiated; never installs anything |
| Word (.docx) export — one-time Pandoc fetch | Pandoc's release server on GitHub (via `pypandoc`) | A plain download request for the ~100 MB Pandoc binary — no user data | You ask for a `.docx` export and Pandoc is not already installed | Never downloads otherwise; install Pandoc yourself (or use the `.md` + `.bib` export, which needs no download) |
| Audit timestamping (RFC 3161) | The Time-Stamping Authority URL you configure | The SHA-256 audit-head digest only — never manuscript text, claims, or ratings | An audit timestamp is requested after you configure a TSA | **Off by default** (`timestamp.provider` is `none`) |
| Signed desktop auto-update | The update server, only if a desktop build sets `CITEVAHTI_UPDATE_URL` | Requests for signed update metadata and files — no user data | An update check/apply in a configured desktop build; applying is always an explicit decision | Inert unless an update URL and signing root are configured |

Two things that look like network traffic but never leave your machine: the review panel
and its API run on loopback only (`127.0.0.1`), as do the Zotero local API / Better BibTeX
(`localhost:23119`), local AI (`localhost:11434`), and the app's own health probes. And
links CiteVahti shows you (doi.org, zotero.org, github.com) open in **your own browser**
when you click them — those requests are your browser's, not CiteVahti's.

Outside the optional AI path, CiteVahti sends **no manuscript text, no claims, and no
ratings** to any of these services — only the search terms, reference identifiers, keys,
and digests described above. This table is the complete set of outbound paths we know of
in this version, checked by auditing every network call site in the source; the test
suite runs fully offline against fake HTTP seams in CI, which acts as a regression check
against outbound calls creeping in unnoticed. If you observe a request this table does
not cover, that is a bug — please report it to **<privacy@vahtian.com>**.

## The AI second opinion

CiteVahti's optional AI second rating is **off by default.** When you enable it, you choose
the provider: your MCP assistant (e.g. Claude Desktop), a **fully local** model (Ollama /
LM Studio, no network), or your own API key. In the API-key mode, CiteVahti sends the
provider you configured the material a blinded rating needs: **the claim text plus the
candidate paper's title and abstract** for claim-support ratings, or the question frame
(PICO, outcome and study labels) for GRADE ratings. That is a provider *you* chose and
contract with, under *their* privacy policy. In MCP mode the same claim/paper context goes
to your assistant, whose own provider connection is governed by that assistant's settings —
if your assistant is cloud-backed, that context reaches its provider too. CiteVahti stores
no API key except in your OS keychain, and the AI rating is always blinded until your own
human rating exists.

## Sharing

CiteVahti shares your data with **no one.** The de-identified validation warehouse is a
**local, opt-in, default-off** feature; contributing any of it to the shared research corpus
is a **separate, explicit action** you take, with its own
[contributor privacy notice](CONTRIBUTOR_PRIVACY.md) — never automatic.

## What CiteVahti is not

CiteVahti records whether a cited source *supports* a claim; it does not determine truth, and
it is **not a medical device and gives no clinical advice.** It produces design evidence under
stated assumptions, for you to check — not a guarantee.

## Contact

Privacy questions or requests: **<privacy@vahtian.com>**. For bug reports and general
support you can also use **<https://github.com/heidihelena/citevahti/issues>** or
**<https://vahtian.com/citevahti>**.
