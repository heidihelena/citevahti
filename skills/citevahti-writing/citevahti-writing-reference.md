# CiteVahti Writing — Step Reference

## Step 2 — Map citation slots

Common forms researchers use:
```
"[REF: low-dose CT mortality]"   "<!-- cite: NLST -->"
"[needs citation]"               "(XXX et al.)"
```

For each slot:
1. Check `.citevahti/` for matching accepted claim
2. Found → use it, do not search further
3. Not found → flag it, offer `citevahti-dev` workflow first
4. Never fill with unverified paper

## Step 3 — Drafting rules

Write from the ledger, not from memory:
- `directly_supports` → "X demonstrates..." / "Studies show..."
- `partially_supports` → "Evidence suggests..." / "X has been associated with..."
- Attach citekey: `[@citekey]` (Pandoc/Markdown) or `[ZOTERO: citekey]` (Word)
- Never strengthen claim beyond support rating
- Multiple converging claims: synthesise, cite each separately

Draft format per claim:
```
[Claim text in manuscript voice]. [@citekey] — [oo] accepted

[Second claim]. [@citekey2] — [o] caution
(Reviewer: confirm interpretation against full text.)
```

## Step 4 — Human review checklist

Present with draft:
- Each citation with state `[oo]` / `[o]`
- `[o]` caution claims flagged explicitly
- Slots that could not be filled

Ask:
- "Does the language match the strength of the evidence?"
- "Unfilled slots — check now or mark as [u] untestable?"

Do NOT move to next section until researcher confirms.

## Step 5 — Write citekeys

After confirmation:
- Insert in agreed format
- Remaining `[o]` caution: remind at session end

## MatchVahti Lite vs MatchVahti

| | Lite (browser) | MatchVahti (app) |
|---|---|---|
| Input | PubMed abstract | Full text |
| Output | .ris → Zotero | .citevahti/ ledger |
| Claim granularity | Sentence, abstract only | Claim×paper blinded rating |
| Zotero tags | cite:abstract-only, cite:closer-look | Synced via CiteVahti |
| Writing readiness | After import + human review | After [oo] / [o] decision |
| Strength | Weaker — abstract only | Stronger — full-text checked |

Prefer MatchVahti-sourced claims for writing. Lite captures always flag `cite:abstract-only`.

## cite:abstract-only + closer-look workflow

1. Tag present → flag in draft: `[@citekey] ⚠ abstract-only — check before submission`
2. `cite:closer-look` also present → run `vahtian_fulltext.py` to fetch PDF → then CiteVahti claim check
3. Never silently drop the flag
