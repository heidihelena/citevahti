# CiteVahti panel — minimal design system

The panel is plain HTML/CSS/JS (no build step). Design decisions live as CSS custom
properties (**tokens**) in `:root` / `.zs-dark`, and a thin **component layer** of `cv-*`
classes. New UI composes tokens + components; it should not introduce new colours,
magic numbers, or one-off `style="…"`.

Files: tokens + components in [`src/citevahti/panel/web/styles.css`](../src/citevahti/panel/web/styles.css);
shared render helpers (`loadingHTML`) in `app.js`.

---

## 1 · Typography scale

Light, document-first. Two display sizes; everything else is body/label/caption.

| Role | Class / element | Size · weight | Token |
|---|---|---|---|
| Title | `.cv-title`, surface/first-run `<h2>` | 20px · 700 | — |
| Subtitle | `.cv-subtitle` | 14px · 600 | `--zs-text-lg` |
| Section label | `.lbl` | 10px · 700, **mono, UPPERCASE** | `--zs-text-2xs` |
| Body | (default) | 13px · 400 | `--zs-text` |
| Caption / help | `.note` (muted) | 12px | `--zs-text-sm` |
| Micro / code | mono | 11px | `--zs-text-xs` |

`.note.ok` = positive (teal), `.note.warn` = caution (rose).

## 2 · Spacing rules

One 2→24px scale; **always a token, never a literal**. Utilities replace inline margins/flex.

`--zs-space-2xs 2` · `-xs 4` · `-sm 6` · `(base) 8` · `-md 10` · `-lg 12` · `-xl 16` · `-2xl 24`

Utilities: `.cv-mt-xs/.cv-mt-sm/.cv-mt/.cv-mt-lg` (top margin), `.cv-m0`, `.cv-wrap`
(flex-wrap), `.cv-col` (stretch column, 8px gap). Card padding = `--zs-space-xl`;
card stack gap = `--zs-space-lg`.

## 3 · Button variants

Two tiers — don't add more.

- **`.btn`** — actions inside cards/surfaces (9×13px, weight 600). Variants:
  `.primary` (filled brand) · `.ghost` (outline brand) · `.danger` (rose). Optional `.hk` hotkey hint.
- **`.chip-btn`** — compact header/toolbar controls (5×9px). `.primary` = the single filled CTA.

Rule: **one** `.primary` per region (the obvious next action). Everything else is ghost/chip.

## 4 · Card patterns

One container: **`.cv-card`** — `1px var(--zs-line)` border, `--zs-radius-lg`, `--zs-space-xl`
padding, `--zs-space-lg` vertical margin, paper background. Modifier `.is-warn` (amber) for
"look here". `.seg` and `.firstrun .panel-box` are **legacy aliases** of the same rule.
`.modal-card` is the elevated variant (shadow) for modals + surface-hosted content.

## 5 · Form patterns

- `.lbl` above the control; `.note` below for help.
- Text: `.revbox` (textarea) and inputs share one field style (full width, `--zs-radius`,
  `1px var(--zs-line)`). Focus ring = brand.
- Actions row: `.actions` (`.cv-wrap` when it can wrap; `.cv-col` when stacked full-width).
- Destructive/irreversible inputs get a `.btn.danger` + a confirm.

## 6 · Status badges

One component, six hues mapped to the four review states + neutral + pending:

`.cv-badge` + `.is-supported` (amber `oo`) · `.is-partial` (teal `o`) · `.is-revise`
(violet `r`) · `.is-reject` (rose `d`) · `.is-pending` (brand) · `.is-muted` (grey).

Colour is **never the only cue** — the bracketed code (`[oo]`, `[r ]`) always shows.
Existing instances on the same hue tokens: `.legchip` (legend), `.qcode` (queue), `.tag`
(candidate metadata).

## 7 · Empty states

**`.cv-empty`** — centered, muted, generous padding. Optional `.cv-empty-title` (one bold
line) + a caption + one primary action. Say what's missing and the single next step
(e.g. the "This folder isn't set up" recovery, the claim-extraction hand-off).

## 8 · Error states

- **Inline**, blocking a region: **`.cv-error`** (rose box) — what failed + how to recover.
- **Transient**, non-blocking: `notify(msg, {kind:"error", retry})` → `.toast.error` with a
  Retry affordance. Prefer a recovery action over raw text. Never surface a shell command.

## 9 · Loading states

One pattern via **`loadingHTML(label, {card})`** → **`.cv-loading`** (spinner `.cv-spin` +
label). Variants: `.is-card` (centered, in a modal-card while data loads), `.is-prominent`
(brand box, for a foregrounded wait like "Waiting for claims…"). Spinner respects
`prefers-reduced-motion`.

---

### Refactor status

Done: typography + card + spinner consolidated to one rule each; all 6 ad-hoc "Loading…"
strings → `loadingHTML`; surface/hand-off/setup screens use `cv-*`. Remaining: a handful of
one-off `style="margin-top:…"` in the evidence card + dead `openExportModal` (tracked
separately) — migrate to the spacing utilities when those areas are next touched.
