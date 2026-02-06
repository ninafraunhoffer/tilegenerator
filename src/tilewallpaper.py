#!/usr/bin/env python3
"""
tilewallpaper.py

Create a wallpaper/background from a seamless square tile by repeating it
X-by-Y times and cropping to a target size.

Key idea to avoid huge intermediates:
- Instead of tiling at the original tile resolution (which can be massive)
  and then downscaling, we compute an "effective tile size" that will cover
  the target output when repeated X-by-Y, then resize the tile once and tile
  at that scale.

Requires: pillow
    pip install pillow
"""

from __future__ import annotations

import argparse
import math
import os
from dataclasses import dataclass
from typing import Tuple, Optional

from PIL import Image


DPI = 300


@dataclass(frozen=True)
class TargetSpec:
    width_px: int
    height_px: int
    dpi: int = DPI


PRESETS = {
    # Common phone wallpaper (portrait)
    "phone": TargetSpec(1080, 1920, DPI),

    # 4K UHD desktop (landscape)
    "4k": TargetSpec(3840, 2160, DPI),

    # A4 at 300 PPI: 8.27 × 11.69 inches -> 2480 × 3508 px (rounded)
    "a4-portrait": TargetSpec(2480, 3508, DPI),
    "a4-landscape": TargetSpec(3508, 2480, DPI),
}


def parse_tiles(s: str) -> Tuple[int, int]:
    """
    Parse tiles like "2x4" or "2*4" into (2, 4).
    """
    s = s.lower().replace("*", "x").strip()
    if "x" not in s:
        raise argparse.ArgumentTypeError("Tiles must look like 2x4 or 2*4")
    a, b = s.split("x", 1)
    try:
        tx = int(a)
        ty = int(b)
    except ValueError:
        raise argparse.ArgumentTypeError("Tiles must be integers, like 2x4")
    if tx <= 0 or ty <= 0:
        raise argparse.ArgumentTypeError("Tiles must be positive integers")
    return tx, ty


def parse_size(s: str) -> Tuple[int, int]:
    """
    Parse size like "3840x2160" into (3840, 2160).
    """
    s = s.lower().strip()
    if "x" not in s:
        raise argparse.ArgumentTypeError("Size must look like 3840x2160")
    a, b = s.split("x", 1)
    try:
        w = int(a)
        h = int(b)
    except ValueError:
        raise argparse.ArgumentTypeError("Size must be integers, like 3840x2160")
    if w <= 0 or h <= 0:
        raise argparse.ArgumentTypeError("Size must be positive integers")
    return w, h


def load_tile(path: str) -> Image.Image:
    img = Image.open(path)
    # Work in RGBA to preserve transparency if present.
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    elif img.mode == "RGB":
        img = img.convert("RGBA")
    return img


def compute_effective_tile_size(
    target_w: int,
    target_h: int,
    tiles_x: int,
    tiles_y: int,
) -> int:
    """
    Choose a tile pixel size so that tiling X-by-Y covers the target output size.

    We want:
      tiles_x * tile_size >= target_w
      tiles_y * tile_size >= target_h

    So:
      tile_size >= target_w / tiles_x
      tile_size >= target_h / tiles_y

    Pick the max and ceil.
    """
    return int(math.ceil(max(target_w / tiles_x, target_h / tiles_y)))


def tile_image(tile: Image.Image, tiles_x: int, tiles_y: int) -> Image.Image:
    tw, th = tile.size
    canvas = Image.new("RGBA", (tw * tiles_x, th * tiles_y), (0, 0, 0, 0))
    for y in range(tiles_y):
        for x in range(tiles_x):
            canvas.paste(tile, (x * tw, y * th))
    return canvas


def crop_to_target(
    img: Image.Image,
    target_w: int,
    target_h: int,
    anchor: str = "center",
) -> Image.Image:
    """
    Crop img to exactly (target_w, target_h). Assumes img is at least that large.
    anchor: center | topleft | topright | bottomleft | bottomright
    """
    w, h = img.size
    if w < target_w or h < target_h:
        raise ValueError(
            f"Internal error: image too small to crop. Have {w}x{h}, need {target_w}x{target_h}"
        )

    if anchor == "center":
        left = (w - target_w) // 2
        top = (h - target_h) // 2
    elif anchor == "topleft":
        left, top = 0, 0
    elif anchor == "topright":
        left, top = w - target_w, 0
    elif anchor == "bottomleft":
        left, top = 0, h - target_h
    elif anchor == "bottomright":
        left, top = w - target_w, h - target_h
    else:
        raise ValueError(f"Unknown anchor: {anchor}")

    return img.crop((left, top, left + target_w, top + target_h))


def make_pattern_wallpaper(
    input_path: str,
    output_path: str,
    tiles_x: int,
    tiles_y: int,
    target: TargetSpec,
    anchor: str = "center",
    resample: int = Image.Resampling.LANCZOS,
    force_square_check: bool = True,
) -> None:
    tile = load_tile(input_path)

    # Optional check: tile should be square for the assumptions here.
    if force_square_check:
        if tile.size[0] != tile.size[1]:
            raise ValueError(f"Input tile must be square. Got {tile.size[0]}x{tile.size[1]}")

    target_w, target_h = target.width_px, target.height_px

    # Compute effective tile size to avoid a huge intermediate.
    eff = compute_effective_tile_size(target_w, target_h, tiles_x, tiles_y)

    # Resize tile to effective size.
    if tile.size != (eff, eff):
        tile = tile.resize((eff, eff), resample=resample)

    # Tile just enough to cover target. This intermediate is only slightly larger than final.
    tiled = tile_image(tile, tiles_x, tiles_y)

    # Crop to exact output size.
    out = crop_to_target(tiled, target_w, target_h, anchor=anchor)

    # If saving to JPG, we must drop alpha. For PNG/WebP alpha is fine.
    ext = os.path.splitext(output_path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        out = out.convert("RGB")

    out.save(output_path, dpi=(target.dpi, target.dpi))


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Create wallpaper/background from a seamless square tile by repeating it and cropping to a target size."
    )
    p.add_argument("input", help="Input tile image (square). PNG/JPG/WebP/etc.")
    p.add_argument("output", help="Output image path, extension decides format (e.g. out.png, out.jpg, out.webp)")

    p.add_argument("--tiles", type=parse_tiles, default=(2, 2),
                   help='Tile count like "2x4" (default: 2x2)')

    group = p.add_mutually_exclusive_group(required=False)
    group.add_argument("--preset", choices=sorted(PRESETS.keys()),
                       help=f"Target preset ({', '.join(sorted(PRESETS.keys()))}). Default: 4k")
    group.add_argument("--size", type=parse_size,
                       help='Custom target size in pixels like "3000x2000"')

    p.add_argument("--anchor", choices=["center", "topleft", "topright", "bottomleft", "bottomright"],
                   default="center",
                   help="Where to anchor the crop (default: center)")

    p.add_argument("--no-square-check", action="store_true",
                   help="Disable square-tile validation")

    return p


def main() -> None:
    args = build_argparser().parse_args()

    tiles_x, tiles_y = args.tiles

    if args.size:
        target = TargetSpec(args.size[0], args.size[1], DPI)
    else:
        preset = args.preset or "4k"
        target = PRESETS[preset]

    # Ensure the output directory exists
    os.makedirs("out", exist_ok=True)

    # Prepend the 'out' directory to the output path
    output_path = os.path.join("out", args.output)

    make_pattern_wallpaper(
        input_path=args.input,
        output_path=output_path,
        tiles_x=tiles_x,
        tiles_y=tiles_y,
        target=target,
        anchor=args.anchor,
        force_square_check=not args.no_square_check,
    )


if __name__ == "__main__":
    main()

# example usage:
# python src/tilewallpaper.py img/tile.png phone.png --tiles 3x6 --preset phone
# python src/tilewallpaper.py img/frog.png a4_landscape.png --tiles 2x1 --preset a4-landscape
# python src/tilewallpaper.py img/frog.png desktop.png --tiles 6x4 --preset 4k
# python src/tilewallpaper.py img/tile.png custom.png --tiles 3x3 --size 3000x2000
