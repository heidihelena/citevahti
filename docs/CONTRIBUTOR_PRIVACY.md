# Privacy notice — the shared evidence corpus

CiteVahti itself is **local-first**: your manuscript, ratings, and the
de-identified validation warehouse stay on your machine, and nothing in
CiteVahti uploads them. Contributing to the shared Vahtian evidence corpus is
a **separate, active, opt-in step** (today via MatchVahti's "Contribute"
action; never automatic, never a side effect). This notice covers that step.

**Controller:** Vahtian / Heidi Andersén, Vaasa, Finland. Privacy contact
and all requests: privacy@vahtian.com.

**What a contribution carries** (and only when you actively send it):

- your pseudonymous contributor id and a consent record;
- per judgment: a **keyed pseudonymous claim index** (re-keyed server-side
  with a salted HMAC, designed to prevent direct reconstruction of the claim
  text — not to make it anonymous), the **public** study id (PMID/DOI), study
  type, your support rating, the AI rating, and the agreement status;
- under the separate full-text opt-in only: the claim text and evidence
  snippet.

**What you must not contribute:** patient-identifiable information,
confidential registry data, or unpublished confidential third-party material.
Evidence snippets must be short excerpts necessary for validation — not
substantial portions of copyrighted full text. CiteVahti itself never collects
your manuscript, project or claim ids, search history, patient data, or
registry data.

**Three independent opt-ins.** Each is a separate, **unticked** choice; none
is pre-selected, none is bundled, and declining or revoking any one does not
affect the others or your use of CiteVahti:

1. *"I agree to contribute de-identified judgment metadata."*
2. *"I also agree to include claim text and evidence snippets."*
3. *"I also agree to aggregate commercial use."*

**De-identified, not anonymous.** The contributor id links your contributions
to each other — that linkage is what makes the corpus statistically honest
(distributions count distinct contributors). The contributor id, consent
ledger, revocation records, and keyed claim indexes are **personal data**:
they are designed to reduce re-identification risk, but must not be treated as
anonymous. We say "de-identified" because that is what it is; we do not claim
anonymity.

**Recipients:** Vahtian and its necessary EU-based processors for hosting,
security, backup, and consent management. Commercial customers (under opt-in 3
only) receive **aggregate outputs only — never personal data, never your
individual contribution.** Aggregate views expose an edge only at **≥ 5
independent contributors.**

**Where and how long:** an EU database (Frankfurt). Kept until you revoke, or
until the corpus is retired or the data is no longer needed for the stated
purposes, whichever comes first. We periodically review whether retained
contributions are still needed.

**Your control:**

- You can **preview the exact payload** before anything is sent.
- Every contribution is **revocable** with a secret your tool keeps on your
  device. On revocation the data is deleted and a dated tombstone remains as
  proof of erasure; the tombstone holds only the minimum needed to prove
  deletion and prevent re-import — never your judgments, claim text, or
  evidence snippets.
- **If you lose the device secret,** you can still have your data erased:
  contact privacy@vahtian.com and we will verify your identity by other means
  before acting.
- Revocation stops all future use, including commercial. **Aggregate figures
  already published or delivered before revocation cannot be recalled,** and
  revocation **does not affect the lawfulness of processing carried out before
  it** — but no further use of your data occurs.

**Your rights (GDPR).** You may request **access, rectification, erasure,
restriction of processing, and — where applicable — portability** of your
personal data, and you may **withdraw any consent** at any time, via
privacy@vahtian.com. You also have the right to lodge a complaint with the
supervisory authority: in Finland, the **Office of the Data Protection
Ombudsman (Tietosuojavaltuutetun toimisto).**

**Purpose and legal basis:** building the shared claim↔evidence corpus (the
map of where evidence supports, contradicts, and runs out); and — **only under
the separate commercial-use opt-in (3)** — producing commercial evidence
products from the aggregate corpus. To produce those aggregate outputs,
Vahtian processes your underlying contributed personal data **only if you have
separately consented to commercial use.** Legal basis: **your consent,**
recorded per opt-in.
