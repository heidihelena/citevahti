---
name: citevahti-support
description: Use when handling a CiteVahti user report — triaging a bug report or pilot-user email, updating the known-issues register, drafting a support reply, or deciding whether a report needs immediate escalation. Data-loss and false-verified reports escalate immediately. Maintainer-facing; mandatory from the first paying customer onward.
---

# CiteVahti support — triage, known issues, escalation

CiteVahti runs in live pilots with real researchers; a support failure isn't an annoyed
user — it's a damaged audit trail, or a manuscript submitted on bad information.
This skill makes support responses consistent, honest, and correctly escalated.

**Activation gate (from `docs/BETA_TO_PRODUCTION.md`):** this workflow is mandatory
*before the first paying customer* — during free beta, apply it lightly rather than
building process for its own sake.

## Triggers

**Use when:** a bug report, pilot feedback, support email, or GitHub issue arrives;
drafting a reply; updating the known-issues register; deciding severity/escalation.

**Do NOT use for:** fixing the bug itself (normal development, gated by
`secure-release` when it ships), or feature requests (route to `ROADMAP.md` triage).

## Escalation criteria — check these FIRST, before anything else

Two report classes are **immediate, drop-everything escalations**:

1. **Data loss** — a user's ledger, audit log, ratings, manuscript edits, or Zotero
   library damaged or destroyed by CiteVahti. The audit chain is the product's promise.
2. **False-verified** — CiteVahti recorded, displayed, or exported a support/decision
   value the human did not make: an AI rating that leaked into `final_value`, a decision
   shown as accepted that wasn't, an audit entry that misstates what happened. This is
   an invariant breach (`docs/SAFETY_INVARIANTS.md`), not a bug like the others.

For either: acknowledge within hours, not days; reproduce against the invariant tests
(`test_dual_rating.py`, `test_readonly_tools_dont_mutate.py`, the `security` marker
group); if confirmed, treat per `SECURITY.md` (a bypassed safety control is a security
issue even with no traditional vulnerability) — fix, add the regression test to the
`security` group, disclose honestly in `CHANGELOG.md` and to affected pilot users, and
consider whether shipped releases need a warning note. Never quietly patch an
invariant breach.

**Security reports** follow `SECURITY.md` disclosure handling — don't discuss details
in a public issue thread.

## Triage template

Record for every report (a GitHub issue with these as the body, or the register row):

```
- Report date / channel / user (pilot? paying?):
- Version + surface (pip / .mcpb / desktop app / panel / VS Code) + OS:
- Expected vs actual, verbatim where possible:
- Reproduction: steps / not-yet-reproduced / can't-share-data
- Data sensitivity: does reproducing need their manuscript? (prefer synthetic — `citevahti demo`)
- Severity: escalation (data-loss / false-verified) · blocks-workflow · degraded · cosmetic
- Known issue? (check the register) · Invariant-adjacent? (which one)
- Next action + owner + promised follow-up date:
```

## Known-issues register

Keep one register (`docs/KNOWN_ISSUES.md`; create on first entry) so the same bug is
never rediscovered at full triage cost: symptom, affected versions/surfaces,
workaround, status, fixed-in version. On each release (`citevahti-release`), sweep the
register — fixed entries move to the changelog, stale entries get re-verified.
`docs/KNOWN_LIMITATIONS.md` stays for *by-design* limits; the register is for *defects*.
A limitation users keep hitting is a UX bug — consider promoting it.

## Response snippets — tone rules

Honesty over reassurance, specifics over apology-boilerplate:

- **Acknowledge:** what you understood the problem to be, severity you assigned, when
  they'll hear back. Never "works for me" as a first reply.
- **Known issue:** link the register entry, give the workaround, state the fix status.
- **By-design (safety gate ate their action):** explain *which safeguard* the gate
  protects (e.g. dedupe fails closed; writes need DOI/PMID) before pointing at the
  escape hatch (`--allow-duplicate` etc.) — the gate is the product, don't apologize
  for it.
- **Can't reproduce:** say what you tried, ask for the exact version/surface and a
  synthetic reproduction; never ask a user to send manuscript content if a synthetic
  case can work.
- **Escalation:** confirm receipt fast, no speculation about cause until reproduced,
  commit to a follow-up time and keep it.

The existing troubleshooting table in `skills/citevahti-dev/SKILL.md` and
`docs/QUICKSTART.md` covers the common setup snags — link, don't retype.

## Hard rules

- **NEVER downgrade a data-loss or false-verified report** to normal queue, even if it
  looks like user error — disprove it first.
- **NEVER ask for a user's manuscript** when a synthetic reproduction could work.
- **NEVER promise a fix date you haven't scoped**, and never promise auto-delivery of a
  fix (no auto-updater — users must update manually; tell them how per surface).
- **NEVER let a workaround that weakens a safety gate become the documented answer.**
