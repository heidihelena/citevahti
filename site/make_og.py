#!/usr/bin/env python3
"""Render the CiteVahti Open Graph card (site/og.png), 1200x630.

Reproducible and text-rendered with a real font file — not a hand-pasted bitmap —
so the link-preview wordmark and tagline are crisp and on-brand. Colours, the
bracket mark, the tagline, and the four claim-state chips are kept in lockstep
with site/index.html.

Fonts: by default it picks the first available system sans (Liberation/DejaVu) for
the wordmark + tagline and a system mono for the chips. To pin the brand's exact
font, drop the TTFs in and point at them:

    CITEVAHTI_OG_SANS=/path/Brand-Bold.ttf \
    CITEVAHTI_OG_SANS_REG=/path/Brand-Regular.ttf \
    CITEVAHTI_OG_MONO=/path/Brand-Mono.ttf \
    python3 site/make_og.py

Requires Pillow (`pip install Pillow`). Re-run after editing the hero copy.
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).with_name("og.png")
W, H = 1200, 630

# ---- brand palette (mirrors :root in site/index.html) -----------------------
NAVY = (45, 36, 64)        # #2D2440
VIOLET = (139, 111, 201)   # #8B6FC9
LILAC = (197, 184, 232)    # #C5B8E8
WHITE = (255, 255, 255)
MUTED = (165, 156, 190)    # legible "muted" on navy

# four claim-state chips: (label, fill, border, text) — same colours as the site
CHIPS = [
    ("[oo] verified",        (255, 242, 216), (201, 138, 0),  (90, 67, 0)),
    ("[o] needs support",    (216, 244, 237), (30, 158, 138), (8, 84, 74)),
    ("[r] review needed",    (236, 227, 255), (139, 111, 201), (67, 44, 122)),
    ("[d] decision recorded", (251, 224, 234), (194, 77, 126), (122, 31, 69)),
]

# ---- font resolution --------------------------------------------------------
_SANS_BOLD = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
_SANS_REG = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_MONO = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]


def _font(env: str, candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    paths = [os.environ[env]] if os.environ.get(env) else []
    paths += candidates
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise SystemExit(
        f"no usable font for {env}; set {env}=/path/to/font.ttf "
        f"(tried: {', '.join(paths)})")


def _rounded(draw, box, radius, **kw):
    draw.rounded_rectangle(box, radius=radius, **kw)


def main() -> None:
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)

    sans_bold = _font("CITEVAHTI_OG_SANS", _SANS_BOLD, 76)
    sans_lede = _font("CITEVAHTI_OG_SANS_REG", _SANS_REG, 30)
    sans_brand = _font("CITEVAHTI_OG_SANS", _SANS_BOLD, 34)
    sans_by = _font("CITEVAHTI_OG_SANS_REG", _SANS_REG, 22)
    mono = _font("CITEVAHTI_OG_MONO", _MONO, 21)

    pad = 84

    # ---- header: bracket mark + wordmark ------------------------------------
    # the mark, scaled from the 32px favicon: rounded-rect panel, violet brackets,
    # two lilac dots ("the claim between the brackets").
    m = 64
    mx, my = pad, pad
    _rounded(d, [mx, my, mx + m, my + m], radius=14,
             outline=VIOLET, width=3)
    s = m / 32.0  # scale factor from the 32px source paths

    def px(x, y):
        return (mx + x * s, my + y * s)

    lw = max(3, int(2.4 * s))
    # left bracket  M11 9 H8 V23 H11   /  right bracket  M21 9 H24 V23 H21
    d.line([px(11, 9), px(8, 9), px(8, 23), px(11, 23)], fill=VIOLET, width=lw, joint="curve")
    d.line([px(21, 9), px(24, 9), px(24, 23), px(21, 23)], fill=VIOLET, width=lw, joint="curve")
    r = 1.9 * s
    for cx, cy in ((14, 16), (18, 16)):
        x, y = px(cx, cy)
        d.ellipse([x - r, y - r, x + r, y + r], fill=LILAC)

    tx = mx + m + 24
    d.text((tx, my + 2), "CiteVahti", font=sans_brand, fill=WHITE)
    wm_w = d.textlength("CiteVahti", font=sans_brand)
    d.text((tx + wm_w + 14, my + 14), "· a product of Vahtian", font=sans_by, fill=MUTED)

    # ---- hero: the tagline (two lines, exactly as the site h1) --------------
    d.text((pad, 232), "Verify the claim", font=sans_bold, fill=WHITE)
    d.text((pad, 320), "before you cite it.", font=sans_bold, fill=LILAC)

    # ---- lede ----------------------------------------------------------------
    d.text((pad, 426),
           "Test every manuscript claim against its sources —",
           font=sans_lede, fill=MUTED)
    d.text((pad, 462),
           "a blinded human → AI → adjudication workflow.",
           font=sans_lede, fill=MUTED)

    # ---- the four claim-state chips -----------------------------------------
    cx = pad
    cy = 536
    for label, fill, border, text in CHIPS:
        tw = d.textlength(label, font=mono)
        cw = tw + 30
        _rounded(d, [cx, cy, cx + cw, cy + 40], radius=9, fill=fill, outline=border, width=2)
        d.text((cx + 15, cy + 9), label, font=mono, fill=text)
        cx += cw + 12

    img.save(OUT, "PNG")
    print(f"wrote {OUT} ({W}x{H})")


if __name__ == "__main__":
    main()
