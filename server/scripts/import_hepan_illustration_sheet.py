"""Import a model-generated 3x2 hepan relationship illustration sheet.

The hepan card only needs six relationship archetypes, so this keeps the
source sheet out of the app and saves transparent, card-ready PNGs beside the
hepan copy data.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "app" / "data" / "hepan" / "illustrations"
COLS = 3
ROWS = 2
TARGET = 420
MAX_DRAWN = 330

ASSETS = [
    "tianzuo.png",
    "mirror.png",
    "tongpin.png",
    "ziyang.png",
    "huohua.png",
    "hubu.png",
]


def _line_groups(values: list[int], threshold: float) -> list[tuple[int, int]]:
    groups: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(values):
        if value >= threshold and start is None:
            start = index
        elif value < threshold and start is not None:
            groups.append((start, index - 1))
            start = None
    if start is not None:
        groups.append((start, len(values) - 1))
    return groups


def _detect_grid_lines(source: Image.Image, *, axis: str, expected: int) -> list[float] | None:
    width, height = source.size
    pixels = source.load()
    if axis == "x":
        values = [
            sum(1 for y in range(height) if min(pixels[x, y]) < 248)
            for x in range(width)
        ]
        line_threshold = height * 0.55
    else:
        values = [
            sum(1 for x in range(width) if min(pixels[x, y]) < 248)
            for y in range(height)
        ]
        line_threshold = width * 0.55

    centers = [
        (left + right) / 2
        for left, right in _line_groups(values, line_threshold)
        if right - left <= 5
    ]
    return centers if len(centers) == expected else None


def _cell_boxes(source: Image.Image) -> list[tuple[int, int, int, int]]:
    x_lines = _detect_grid_lines(source, axis="x", expected=COLS * 2)
    y_lines = _detect_grid_lines(source, axis="y", expected=ROWS * 2)
    boxes: list[tuple[int, int, int, int]] = []
    if x_lines is None or y_lines is None:
        inset = 12
        for row in range(ROWS):
            for col in range(COLS):
                left = round(source.width * col / COLS) + inset
                right = round(source.width * (col + 1) / COLS) - inset
                top = round(source.height * row / ROWS) + inset
                bottom = round(source.height * (row + 1) / ROWS) - inset
                boxes.append((left, top, right, bottom))
        return boxes

    for row in range(ROWS):
        for col in range(COLS):
            left = round(x_lines[col * 2]) + 10
            right = round(x_lines[col * 2 + 1]) - 10
            top = round(y_lines[row * 2]) + 10
            bottom = round(y_lines[row * 2 + 1]) - 10
            boxes.append((left, top, right, bottom))
    return boxes


def _white_to_alpha(image: Image.Image) -> Image.Image:
    source = image.convert("RGB")
    out = Image.new("RGBA", source.size)
    source_pixels = source.load()
    pixels = []
    for y in range(source.height):
        for x in range(source.width):
            r, g, b = source_pixels[x, y]
            low = min(r, g, b)
            high = max(r, g, b)
            distance_from_white = 255 - low
            saturation = high - low

            if distance_from_white < 10:
                alpha = 0
            elif distance_from_white < 44 and saturation < 18:
                # The sheet borders are useful for importing, but the card's
                # paper should remain the visual ground once the art is placed.
                alpha = 0
            else:
                alpha = min(255, max(0, int((distance_from_white - 5) * 4.8)))
            pixels.append((r, g, b, alpha))
    out.putdata(pixels)
    return out


def _content_box(image: Image.Image) -> tuple[int, int, int, int]:
    alpha = image.getchannel("A").point(lambda value: 255 if value > 20 else 0)
    box = alpha.getbbox()
    if box is None:
        return (0, 0, image.width, image.height)
    left, top, right, bottom = box
    pad = 12
    return (
        max(0, left - pad),
        max(0, top - pad),
        min(image.width, right + pad),
        min(image.height, bottom + pad),
    )


def _fit_on_canvas(image: Image.Image) -> Image.Image:
    image = image.crop(_content_box(image))
    scale = min(MAX_DRAWN / image.width, MAX_DRAWN / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    image = image.resize(size, Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (TARGET, TARGET), (255, 255, 255, 0))
    canvas.alpha_composite(image, ((TARGET - size[0]) // 2, (TARGET - size[1]) // 2))
    return canvas


def import_sheet(sheet_path: Path) -> None:
    source = Image.open(sheet_path).convert("RGB")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, (left, top, right, bottom) in zip(ASSETS, _cell_boxes(source), strict=True):
        cell = source.crop((left, top, right, bottom))
        illustration = _fit_on_canvas(_white_to_alpha(cell))
        illustration.save(OUT_DIR / filename)

    print(f"Imported {len(ASSETS)} hepan illustrations into {OUT_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sheet", type=Path, help="Path to the generated 3x2 PNG sheet.")
    args = parser.parse_args()
    import_sheet(args.sheet)


if __name__ == "__main__":
    main()
