# CiteVahti — Claude Code skills

**Citation integrity for manuscripts. Human-first, fully auditable.**

This repo ships as a Claude Code plugin (`.claude-plugin/plugin.json`) with these skills.

**For researchers:**

| Skill | Use it when |
|---|---|
| [`citevahti-dev`](citevahti-dev/SKILL.md) | Verifying manuscript claims against evidence — claim → PubMed search → blinded rating → human decision → audited Zotero write. |
| [`citevahti-writing`](citevahti-writing/SKILL.md) | Drafting manuscript text from already-verified claims (the MatchVahti → CiteVahti → writing chain). Never invents citations. |
| [`citevahti-screen`](citevahti-screen/SKILL.md) | Sweeping an existing reference list for retractions and claim–source mismatches before submission. |
| [`citevahti-review`](citevahti-review/SKILL.md) | A read-only peer-review/editor pass over someone else's manuscript. |
| [`citevahti-report`](citevahti-report/SKILL.md) | Packaging a finished audit: methods paragraph, integrity summary, evidence appendix. |

**For the maintainer** (the beta → production set — see [`docs/BETA_TO_PRODUCTION.md`](../docs/BETA_TO_PRODUCTION.md)):

| Skill | Use it when |
|---|---|
| [`citevahti-eval`](citevahti-eval/SKILL.md) | Measuring CiteVahti's own accuracy against the pre-registered ground-truth ledger. **The production gate: no threshold pass, no release.** |
| [`citevahti-release`](citevahti-release/SKILL.md) | Shipping a release — eval gate, surface parity, version lockstep, DOI, rollback notes. Defers mechanics to the `secure-release` skill. |
| [`citevahti-claims`](citevahti-claims/SKILL.md) | Auditing any public artifact against the must-not-claim list before publication. |
| [`citevahti-support`](citevahti-support/SKILL.md) | Triaging user reports; data-loss and false-verified reports escalate immediately. |
| [`citevahti-onboarding`](citevahti-onboarding/SKILL.md) | Regenerating per-channel install/quickstart docs from the shipped truth. |

The human is always the decider. The AI is a blinded advisory second rater.

## Install

```
/plugin install https://github.com/heidihelena/citevahti
```

Or, with no terminal, download `citevahti.mcpb` from the
[latest release](https://github.com/heidihelena/citevahti/releases/latest) and double-click.

## Safety guarantees

- No silent Zotero writes — always preview → confirm → undoable
- AI never sets the final value — human/panel adjudication only
- Hash-chained audit log — every mutation recorded
- Dedupe fails closed — write refused if the check cannot run
- 631 offline tests

[vahtian.com](https://vahtian.com) · Apache-2.0 · [heidihelena/citevahti](https://github.com/heidihelena/citevahti)
