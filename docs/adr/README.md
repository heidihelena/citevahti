# Architecture Decision Records

Numbered, append-only records of significant architectural decisions. A new
decision that changes an earlier one gets a new ADR that supersedes it; we do
not rewrite history.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-citation-integrity-architecture.md) | ZotSynth is Citation Integrity Infrastructure | Accepted |
| [0002](0002-ui-delivery-and-review-layer.md) | UI delivery model + the `[oo/o/r/d]` review layer | Accepted |
| [0003](0003-hosted-layer-and-open-core.md) | The hosted layer, open-core boundary, and warehouse governance | Accepted |
| [0004](0004-brand-ip-and-entity.md) | Brand architecture (Vahtian / CiteVahti) and open-core IP posture | Accepted |
| [0005](0005-zotero-auth-and-writeback.md) | Zotero authentication & write-back (keyless reads, one-paste key for beta writes, OAuth → hosted) | Accepted |
| [0006](0006-full-rename-retire-zotsynth-alias.md) | Full rename to `citevahti`; retire the `zotsynth` alias | Accepted (supersedes 0004 §2.3a, §6 in part) |
| [0007](0007-local-web-app-and-http-surface.md) | Two co-primary surfaces — a conversation (MCP prompt) + a localhost side panel for the blind human rating; thin loopback HTTP API; VS Code is one adapter | Accepted (refines 0002; supersedes 0002 §6 in part) |
| [0008](0008-evidence-confidence-tiers.md) | Evidence confidence tiers — the contributor-count ladder (Layer 0 screening → 1 individual → 2 review → 3 guideline); two mechanisms (organized panel vs pooled corpus); ≥5 = the individual→review boundary; a new Layer-0 topic-screening prompt + button | Accepted (builds on 0001, 0003, 0007) |
