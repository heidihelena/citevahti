# Contributor privacy notice — the shared evidence corpus

CiteVahti itself is **local-first**: your manuscript, ratings, and the
de-identified validation warehouse stay on your machine, and nothing in
CiteVahti uploads them. Contributing to the shared Vahtian evidence corpus is
a **separate, active, opt-in step** (today via MatchVahti's "Contribute"
action; never automatic, never a side effect). This notice covers that step.

**Controller:** Vahtian (Heidi Andersén) — contact via
[vahtian.com](https://vahtian.com).

**What a contribution carries** (and only when you actively send it):

- your pseudonymous contributor id and a consent record;
- per judgment: a one-way **hashed** claim index (re-keyed server-side with a
  salted HMAC), the **public** study id (PMID/DOI), study type, your support
  rating, the AI rating, and the agreement status;
- under the separate full-text opt-in only: the claim text and evidence
  snippet.

**Never:** your manuscript, project or claim ids, search history, patient
data, or registry data.

**De-identified, not anonymous.** The contributor id links your contributions
to each other — that linkage is what makes the corpus statistically honest
(distributions count distinct contributors) — and the consent ledger is
personal data. We say "de-identified" because that is what it is; we do not
claim anonymity.

**Where and how long:** an EU database (Frankfurt). Kept until you revoke.

**Your control:** you can preview the exact payload before anything is sent;
every contribution is **revocable** with a secret your tool keeps on your
device. On revocation the data is deleted; a dated tombstone remains as proof
of erasure. Aggregate views expose an edge only at **≥ 5 independent
contributors**.

**Purpose and legal basis:** building the shared claim↔evidence corpus (the
map of where evidence supports, contradicts, and runs out). Legal basis:
your consent.
