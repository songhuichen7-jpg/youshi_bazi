"""Generate 20 placeholder PNGs using each type's theme color + id/name overlay.
No emoji rendering (Pillow default font can't handle color emoji reliably).
Real AI illustrations replace these files later in the parallel illustration track."""
from __future__ import annotations
import json
from pathlib import Path
from PIL import Image, ImageDraw

DATA_PATH = Path(__file__).parent.parent / "app" / "data" / "cards" / "types.json"
OUT = Path(__file__).parent.parent / "app" / "data" / "cards" / "illustrations"
OUT.mkdir(parents=True, exist_ok=True)

types = json.loads(DATA_PATH.read_text(encoding="utf-8"))

for tid, info in types.items():
    # 360x360 placeholder — same aspect as real illustrations
    img = Image.new("RGBA", (360, 360), info["theme_color"])
    draw = ImageDraw.Draw(img)
    # Bitmap default font is small; draw id big-ish in the center
    draw.text((150, 140), info["id"], fill=(255, 255, 255, 255))
    draw.text((120, 200), info["cosmic_name"], fill=(255, 255, 255, 255))
    img.save(OUT / info["illustration"])

print(f"Generated {len(types)} placeholder illustrations at {OUT}")
