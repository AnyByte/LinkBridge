#!/usr/bin/env python3
"""Regenerate assets/LinkBridge.icns from assets/icon.png.

Pipeline:
  1. Load assets/icon.png (1024x1024 with a white margin around the artwork)
  2. Flood-fill the four corners to transparent — also writes
     assets/icon-transparent.png so a transparent PNG is available standalone
  3. Detect the bounding box of non-transparent pixels and crop to it
  4. Center in a square canvas (longer side wins) and resize back to 1024x1024
     so the artwork fills the canvas — saved as assets/icon-1024.png
  5. Generate assets/LinkBridge.iconset/ with 10 PNG sizes (16, 32, 64, 128,
     256, 512, 1024, plus the @2x retina variants required by macOS)
  6. Run `iconutil -c icns assets/LinkBridge.iconset -o assets/LinkBridge.icns`

Requires Pillow:
    python3 -m pip install Pillow

Usage (from the repo root):
    python3 scripts/build_icon.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit(
        "error: Pillow is required for icon regeneration.\n"
        "  install it with:  python3 -m pip install Pillow"
    )

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "assets" / "icon.png"
TRANSPARENT = REPO / "assets" / "icon-transparent.png"
CROPPED_1024 = REPO / "assets" / "icon-1024.png"
ICONSET = REPO / "assets" / "LinkBridge.iconset"
ICNS = REPO / "assets" / "LinkBridge.icns"

TRANSPARENT_RGBA = (0, 0, 0, 0)
FLOOD_THRESHOLD = 35

ICONSET_SIZES = [
    (16, ""),
    (16, "@2x"),
    (32, ""),
    (32, "@2x"),
    (128, ""),
    (128, "@2x"),
    (256, ""),
    (256, "@2x"),
    (512, ""),
    (512, "@2x"),
]


def main() -> int:
    if not SOURCE.exists():
        sys.exit(f"error: source icon not found at {SOURCE}")

    img = Image.open(SOURCE).convert("RGBA")
    w, h = img.size
    print(f"loaded {SOURCE.name} ({w}x{h})")

    for corner in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        ImageDraw.floodfill(img, corner, TRANSPARENT_RGBA, thresh=FLOOD_THRESHOLD)

    img.save(TRANSPARENT)
    print(f"  wrote {TRANSPARENT.name}")

    bbox = img.getbbox()
    if bbox is None:
        sys.exit("error: no opaque pixels remain after flood fill")
    print(f"  bbox: {bbox}  ({bbox[2] - bbox[0]} x {bbox[3] - bbox[1]})")

    cropped = img.crop(bbox)
    cw, ch = cropped.size
    square_size = max(cw, ch)
    square = Image.new("RGBA", (square_size, square_size), TRANSPARENT_RGBA)
    square.paste(cropped, ((square_size - cw) // 2, (square_size - ch) // 2))

    final_1024 = square.resize((1024, 1024), Image.LANCZOS)
    final_1024.save(CROPPED_1024)
    print(f"  wrote {CROPPED_1024.name}")

    if ICONSET.exists():
        shutil.rmtree(ICONSET)
    ICONSET.mkdir(parents=True)

    for logical, suffix in ICONSET_SIZES:
        pixel_size = logical * 2 if suffix == "@2x" else logical
        out = ICONSET / f"icon_{logical}x{logical}{suffix}.png"
        final_1024.resize((pixel_size, pixel_size), Image.LANCZOS).save(out)
    print(f"  wrote {len(ICONSET_SIZES)} sizes to {ICONSET.name}/")

    subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICNS)],
        check=True,
    )
    print(f"  wrote {ICNS.name} ({ICNS.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
