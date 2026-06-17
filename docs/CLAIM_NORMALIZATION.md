# Claim-text normalization (spec v1)

*The shared contract across the -vahti house. Source of truth: this file.*

Every tool that records a claim-test result computes a `claim_text_hash`:

```
claim_text_hash = SHA-256( normalize_claim_text(claim_text) )   # lowercase hex
```

AtlasVahti / CorpusVahti then derive the corpus blind index from that hash
(`HMAC(claim_text_hash, server_secret)`). **If two tools normalize the same claim
differently, they produce different hashes, different blind indexes, and the same
claim never pools into one corpus cell** — the k-anonymity threshold (≥5
contributors) can never be reached across tools. So normalization MUST be
byte-identical everywhere. This document is that one definition.

## The algorithm (fixed order)

1. **NFC** — Unicode normalize to NFC (composed form).
2. **Lowercase** — simple Unicode lowercase.
3. **Collapse whitespace** — replace every run of Unicode whitespace with a single
   space (`U+0020`).
4. **Trim** — strip leading and trailing whitespace.

Then hash the UTF-8 bytes with SHA-256 and render lowercase hex.

Do **not** reorder the steps, add punctuation stripping, accent folding, or
stemming on one side only. Any change is a **v2** that bumps a version tag
everywhere at once.

### Reference implementations

**Python** (`src/citevahti/util.py`, canonical):

```python
def normalize_claim_text(text: str) -> str:
    s = unicodedata.normalize("NFC", text or "")
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s
```

**JavaScript** (MatchVahti `index.html`, must match exactly):

```javascript
function normalizeClaimText(text){
  let s = (text || "").normalize("NFC").toLowerCase();
  s = s.replace(/\s+/g, " ").trim();
  return s;
}
```

## Conformance test vectors

Both implementations MUST map each input to the exact normalized string below
(byte-for-byte). Identical normalized string ⇒ identical SHA-256 ⇒ same corpus
cell. These vectors are asserted in `tests/test_claim_normalization.py` (Python)
and `tests/run.mjs` (MatchVahti).

| # | input | normalized output |
|---|---|---|
| 1 | `LDCT reduces lung-cancer mortality.` | `ldct reduces lung-cancer mortality.` |
| 2 | `  Multiple   spaces \t and \n tabs ` | `multiple spaces and tabs` |
| 3 | `MixedCASE Claim` | `mixedcase claim` |
| 4 | `Café` (composed `U+00E9`) | `café` |
| 5 | `Café` (decomposed `e`+`◌́`) | `café` |
| 6 | `` (empty) | `` (empty) |

Vectors 4 and 5 prove NFC: composed and decomposed forms of "café" must collapse
to the *same* normalized string.

## Known limits (honest scope)

- **Case folding is `lower()`/`toLowerCase()`, not full Unicode casefold.** For
  the scientific-English claim domain these agree across Python and JS. Rare
  language-specific casing (Turkish dotless ı, Greek final sigma, German ß) can
  differ between the two runtimes; claims relying on those are out of scope for
  v1. Don't switch one side to `casefold()` — JS has no equivalent and it would
  diverge.
- **Whitespace class.** Python `re.\s` and JS `\s` agree on all whitespace that
  occurs in real claim text (space, tab, newline, NBSP, the Unicode space block).
  Exotic control separators (`U+001C`–`U+001F`) are not expected in claims and
  are not guaranteed identical; treat them as out of scope.
- **Pseudonymization, not anonymization.** The hash is one-way but a short or
  guessable claim is re-identifiable. The corpus re-hashes client hashes with a
  server-side salted HMAC (the blind index) and enforces k ≥ 5; that is where the
  privacy guarantee lives, not here.

## Changing this spec

Treat the normalized output as a wire format. Any change to the algorithm is a
**v2**: bump a `normalization_version` everywhere, migrate or re-hash existing
records, and update both reference implementations and the vectors in the same
change. Until then, v1 is frozen.

*Consumers: CiteVahti (`normalize_claim_text`), MatchVahti (`normalizeClaimText`),
and the CorpusVahti blind-index derivation. Resolves AtlasVahti DESIGN open
decision #2.*
