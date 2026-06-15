# CiteVahti — Claude Code skills

**Citation integrity for manuscripts. Human-first, fully auditable.**

This repo ships as a Claude Code plugin (`.claude-plugin/plugin.json`) with two skills:

| Skill | Use it when |
|---|---|
| [`citevahti-dev`](citevahti-dev/SKILL.md) | Verifying manuscript claims against evidence — claim → PubMed search → blinded rating → human decision → audited Zotero write. |
| [`citevahti-writing`](citevahti-writing/SKILL.md) | Drafting manuscript text from already-verified claims (the MatchVahti → CiteVahti → writing chain). Never invents citations. |

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
