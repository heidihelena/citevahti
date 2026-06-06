# Reviewer checklist

Work top to bottom. Everything here is safe (read-only / offline / dry-run); no
step performs a live PubMed call or a real Zotero write.

## 1. Run the full test suite
```bash
cd /path/to/Citevahti
pytest            # expect: 308 passed, fully offline
```
- [ ] All tests pass with no network access.

## 2. Verify the startup probe
```bash
citevahti probe
```
- [ ] Capabilities are reported only after a successful probe (probe-not-proof).
- [ ] Honest degradation + remediation strings when a backend is absent.

## 3. Verify version separation (BBT vs Zotero)
- [ ] Zotero **app** version comes from `x-zotero-version` (e.g. `9.0.4`).
- [ ] The schema version (`zotero-schema-version`, e.g. `42`) and the local-API
      version are **never** reported as the app version.
- [ ] The **Better BibTeX** version (e.g. `9.0.27`) is read live from BBT's
      `api.ready` (`betterbibtex` field), is distinct from the app version, and
      is **not hardcoded**. See `tests/test_probe_version.py`.

## 4. Verify no `$HOME` repo changes
```bash
git -C "$HOME" log --oneline | head        # should be unchanged
git -C "$HOME" status --short              # CiteVahti nested repo only
```
- [ ] The accidental `$HOME` git repo is untouched; CiteVahti is its own repo at
      `/path/to/Citevahti`.

## 5. Inspect `.citevahti/` audit behavior
```bash
SMOKE=$(mktemp -d); citevahti --root "$SMOKE" init; citevahti --root "$SMOKE" verify-audit
```
- [ ] Every state mutation appends a hash-chained audit entry.
- [ ] `verify-audit` reports the chain intact; a tampered line breaks it
      (`tests/test_audit_chain.py`).

## 6. Run dry-run write-back only
- [ ] `note-add` / `tag-add` / `assessment-tag-mirror` etc. default to dry-run,
      return a diff preview + one-use confirmation token, and write nothing.
- [ ] A confirmed write requires `--confirm-token` matching the exact pending
      payload; a changed payload invalidates the token.
- [ ] With the default (unavailable) backend, a confirmed write fails cleanly
      with `write_layer_unavailable` and **never** falls back to the Web API.

## 7. Inspect the agreement-report Markdown
- [ ] The method-transparency section states AI role, blinding, abstention
      handling, comparison rule, adjudication rule, human/panel final authority,
      model provenance, agreement metrics, and limitations.
- [ ] It explicitly **disclaims** any compliance/endorsement claim.
- [ ] `human_only` / `ai_abstained` are excluded from the agreement denominator;
      adjudicated records counted by their original comparison.

## 8. Inspect the evidence-export output
- [ ] Neutral tables only (no GRADEpro/RevMan/MAGICapp shape, no recommendations).
- [ ] AI values excluded by default; clearly labelled + separated when requested.
- [ ] Stale/retraction flags preserved; unknown selection IDs reported as warnings.
- [ ] Export mutates nothing except writing an `export.evidence` audit event.

## 9. Verify no real PubMed calls in tests
```bash
grep -rn "eutils.ncbi" tests/    # expect: no matches
```
- [ ] All PubMed paths use `FakeProvider`; `NCBI_EMAIL` absent → graceful
      degradation, never a live call.

## 10. Verify no real Zotero writes in tests
```bash
grep -rn "FakeWriteBackend\|UnavailableBackend" tests/   # write tests use fakes
```
- [ ] All write-back tests use fake backends; no test issues a live Zotero write.

## 11. Cross-check the hard invariants
- [ ] Walk `docs/SAFETY_INVARIANTS.md` and confirm each invariant maps to passing
      guard tests.

## Final smoke
```bash
bash scripts/final_smoke.sh      # pytest + probe + verify-audit; no writes
```
