"""Draw the page's favicon (the hex gem in ui.py) as the packages' icons.

kobold.ico for the Windows exe and installer, kobold.icns for the macOS app,
kobold.png for the AppImage. The favicon is an inline SVG of a dozen polygons,
so it is redrawn here with Pillow rather than rasterised through an SVG library
the build would have to carry. Run once, commit the results:

    uv run --with pillow deploy/icon/make_icon.py
"""

from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw

RED = (0x8A, 0x1B, 0x2E, 255)
# (points in the 32-unit viewBox, white opacity) -- verbatim from the SVG.
FACETS = [
    ("16,1.6 7.6,11.9 24.4,11.9", 0.42),
    ("3.4,8.8 16,1.6 7.6,11.9", 0.28),
    ("16,1.6 28.6,8.8 24.4,11.9", 0.34),
    ("3.4,8.8 7.6,11.9 3.4,23.2", 0.20),
    ("28.6,8.8 28.6,23.2 24.4,11.9", 0.26),
    ("3.4,23.2 7.6,11.9 16,26.4", 0.16),
    ("24.4,11.9 28.6,23.2 16,26.4", 0.22),
    ("3.4,23.2 16,26.4 16,30.4", 0.12),
    ("16,26.4 28.6,23.2 16,30.4", 0.18),
    ("7.6,11.9 24.4,11.9 16,26.4", 0.07),
]
OUTLINE = "16,1.6 28.6,8.8 28.6,23.2 16,30.4 3.4,23.2 3.4,8.8"
EDGES = ["16,1.6 7.6,11.9", "16,1.6 24.4,11.9", "7.6,11.9 24.4,11.9", "7.6,11.9 16,26.4",
         "24.4,11.9 16,26.4", "3.4,8.8 7.6,11.9", "28.6,8.8 24.4,11.9", "3.4,23.2 7.6,11.9",
         "28.6,23.2 24.4,11.9", "3.4,23.2 16,26.4", "28.6,23.2 16,26.4", "16,30.4 16,26.4"]


def points(spec: str, scale: float) -> list[tuple[float, float]]:
    return [(float(x) * scale, float(y) * scale) for x, y in (p.split(",") for p in spec.split())]


def draw(size: int) -> Image.Image:
    # Rendered at 4x and shrunk, since ImageDraw does not antialias.
    big = size * 4
    s = big / 32
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, big - 1, big - 1), radius=7 * s, fill=RED)
    for spec, opacity in FACETS:
        layer = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        ImageDraw.Draw(layer).polygon(points(spec, s), fill=(255, 255, 255, round(opacity * 255)))
        img = Image.alpha_composite(img, layer)
    lines = ImageDraw.Draw(img)
    lines.line(points(OUTLINE, s) + points(OUTLINE, s)[:1], fill=(255, 255, 255, 255),
               width=round(1.5 * s), joint="curve")
    for edge in EDGES:
        lines.line(points(edge, s), fill=(255, 255, 255, 255), width=round(1.1 * s))
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    here = pathlib.Path(__file__).parent
    sizes = [16, 24, 32, 48, 64, 128, 256]
    base = draw(256)
    base.save(here / "kobold.ico", format="ICO", sizes=[(n, n) for n in sizes],
              append_images=[draw(n) for n in sizes[:-1]])
    big = draw(512)
    big.save(here / "kobold.icns", format="ICNS",
             append_images=[draw(n) for n in (16, 32, 64, 128, 256)])
    base.save(here / "kobold.png", format="PNG")
    for name in ("kobold.ico", "kobold.icns", "kobold.png"):
        print(f"wrote {name} ({(here / name).stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
