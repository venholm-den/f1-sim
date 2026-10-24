"""Build assets/race_workbench.ico from the Race Workbench logo.

Draws portable_app/web/logo.svg with Pillow so no SVG renderer is needed.
Sizes of 24px and below drop two bars and thicken the strokes to stay legible.

    python scripts/make_app_icon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "race_workbench.ico"
SIZES = (16, 20, 24, 32, 48, 64, 128, 256)
SUPERSAMPLE = 4

PANEL = "#232532"
CORAL = "#e57669"
CORAL_LIGHT = "#f1b8af"
TEXT = "#e9e9ed"


def _bezier(p0, p1, p2, p3, steps=48):
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        yield (
            u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
        )


def draw_icon(size: int) -> Image.Image:
    small = size <= 24
    scale = size * SUPERSAMPLE / 64
    image = Image.new("RGBA", (size * SUPERSAMPLE,) * 2, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def s(*values):
        return [v * scale for v in values]

    border = 5 if small else 3
    inset = border / 2
    draw.rounded_rectangle(s(inset, inset, 64 - inset, 64 - inset), radius=14 * scale,
                           fill=PANEL, outline=CORAL, width=round(border * scale))

    # (x, top, colour) on the 64-unit grid used by logo.svg; bars end at y=52.
    bars = [(13, 40, CORAL), (21.5, 30, CORAL), (30, 20, CORAL_LIGHT), (38.5, 28, CORAL), (47, 38, CORAL)]
    width = 6
    if small:
        bars = [(15, 34, CORAL), (27, 20, CORAL_LIGHT), (39, 30, CORAL)]
        width = 10
    for x, top, colour in bars:
        draw.rounded_rectangle(s(x, top, x + width, 52), radius=1.5 * scale, fill=colour)

    if small:
        points = list(_bezier((10, 30), (20, 12), (44, 6), (54, 18)))
        stroke, dot = 4.5, 4.5
    else:
        points = list(_bezier((10, 34), (20, 14), (44, 8), (56, 22)))
        stroke, dot = 2.4, 3
    draw.line([tuple(s(*p)) for p in points], fill=TEXT, width=round(stroke * scale), joint="curve")
    for x, y, r in ((*points[0], stroke / 2), (*points[-1], dot)):
        draw.ellipse(s(x - r, y - r, x + r, y + r), fill=TEXT)

    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    images = [draw_icon(size) for size in SIZES]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    images[-1].save(OUTPUT, format="ICO", sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({', '.join(map(str, SIZES))} px)")


if __name__ == "__main__":
    main()
