#!/usr/bin/env python3
"""Render the CiteVahti Sentinel mark to PNG app icons.

Matches brand/marks/citevahti.svg (vahtian repo): navy rounded square, two violet
brackets, two lilac dots. Drawn supersampled (32x) then downsampled for clean edges.
Run from anywhere: python3 make-icon.py — writes both
  * desktop-extension/icon.png            (512x512, the .mcpb / bundle icon)
  * src/citevahti/panel/web/apple-touch-icon.png  (180x180, the panel home-screen icon)
so every surface shows the same mark.
"""
from pathlib import Path

from PIL import Image, ImageDraw

S = 32                      # px per SVG unit -> 1024px canvas, downsampled per output
W = 32 * S
NAVY   = (0x2D, 0x24, 0x40, 255)
VIOLET = (0x8B, 0x6F, 0xC9, 255)
LILAC  = (0xC5, 0xB8, 0xE8, 255)


def render() -> Image.Image:
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, W - 1], radius=7 * S, fill=NAVY)

    sw = 2.3 * S
    def bracket(points):
        pts = [(x * S, y * S) for x, y in points]
        d.line(pts, fill=VIOLET, width=int(round(sw)), joint="curve")
        r = sw / 2
        for x, y in (pts[0], pts[-1]):          # round caps on the open ends
            d.ellipse([x - r, y - r, x + r, y + r], fill=VIOLET)

    bracket([(12, 9), (9, 9), (9, 23), (12, 23)])    # [
    bracket([(20, 9), (23, 9), (23, 23), (20, 23)])  # ]

    def dot(cx, cy, r=1.7):
        d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], fill=LILAC)
    dot(13.9, 16); dot(18.1, 16)
    return img


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    repo = here.parent
    mark = render()
    mark.resize((512, 512), Image.LANCZOS).save(here / "icon.png")
    print("wrote desktop-extension/icon.png (512x512)")
    panel_icon = repo / "src" / "citevahti" / "panel" / "web" / "apple-touch-icon.png"
    mark.resize((180, 180), Image.LANCZOS).save(panel_icon)
    print(f"wrote {panel_icon.relative_to(repo)} (180x180)")
