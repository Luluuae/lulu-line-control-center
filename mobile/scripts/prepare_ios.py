#!/usr/bin/env python3
"""Generate an opaque, complete iOS AppIcon set from Lulu Line's existing icon."""
import json
import sys
from pathlib import Path
from PIL import Image

if len(sys.argv) != 3:
    raise SystemExit("usage: prepare_ios.py SOURCE_ICON APPICONSET_DIR")

source = Path(sys.argv[1])
target = Path(sys.argv[2])
if not source.is_file():
    raise SystemExit(f"icon not found: {source}")
target.mkdir(parents=True, exist_ok=True)

specs = [
    ("iphone", "20x20", "2x", 40), ("iphone", "20x20", "3x", 60),
    ("iphone", "29x29", "2x", 58), ("iphone", "29x29", "3x", 87),
    ("iphone", "40x40", "2x", 80), ("iphone", "40x40", "3x", 120),
    ("iphone", "60x60", "2x", 120), ("iphone", "60x60", "3x", 180),
    ("ipad", "20x20", "1x", 20), ("ipad", "20x20", "2x", 40),
    ("ipad", "29x29", "1x", 29), ("ipad", "29x29", "2x", 58),
    ("ipad", "40x40", "1x", 40), ("ipad", "40x40", "2x", 80),
    ("ipad", "76x76", "1x", 76), ("ipad", "76x76", "2x", 152),
    ("ipad", "83.5x83.5", "2x", 167),
    ("ios-marketing", "1024x1024", "1x", 1024),
]

with Image.open(source).convert("RGBA") as src:
    background = Image.new("RGBA", src.size, "white")
    background.alpha_composite(src)
    opaque = background.convert("RGB")
    images = []
    for idiom, size, scale, pixels in specs:
        filename = f"AppIcon-{idiom}-{size.replace('.', '_')}@{scale}.png"
        opaque.resize((pixels, pixels), Image.Resampling.LANCZOS).save(
            target / filename, "PNG", optimize=True
        )
        images.append({"idiom": idiom, "size": size, "scale": scale, "filename": filename})

(target / "Contents.json").write_text(
    json.dumps({"images": images, "info": {"author": "xcode", "version": 1}}, indent=2) + "\n",
    encoding="utf-8",
)
print(f"Generated {len(images)} opaque iOS icons in {target}")
