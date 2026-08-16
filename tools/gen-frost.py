#!/usr/bin/env python3
"""Bake a wallpaper-aligned frost cache from desktop.png.

Live KWin blur is a dual-kawase downsample. Doing that once at build
time gives every translucent window a spatially correct frosted backdrop
with a single texture sample — no virgl dmabuf, no per-frame kawase.
The sharp desktop.png stays the Plasma wallpaper when live blur works.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "archiso/airootfs/usr/share/backgrounds/synapseos/desktop.png"
DST_FROST = ROOT / "archiso/airootfs/usr/share/backgrounds/synapseos/desktop-frost.jpg"
DST_NOISE = ROOT / "archiso/airootfs/usr/share/synapseos/frost-noise.png"


def bake_frost(src: Path, dst: Path) -> None:
    im = Image.open(src).convert("RGB")
    # Quarter-res + blur + lanczos up = the cheap dual-kawase look.
    small = im.resize((max(1, im.width // 4), max(1, im.height // 4)), Image.Resampling.BOX)
    small = small.filter(ImageFilter.GaussianBlur(radius=7))
    frost = small.resize(im.size, Image.Resampling.LANCZOS)
    frost = ImageEnhance.Brightness(frost).enhance(1.07)
    frost = ImageEnhance.Contrast(frost).enhance(0.90)
    frost = ImageEnhance.Color(frost).enhance(1.06)
    noise = Image.effect_noise(frost.size, 14).convert("RGB")
    frost = Image.blend(frost, noise, 0.035)
    dst.parent.mkdir(parents=True, exist_ok=True)
    frost.save(dst, "JPEG", quality=88, optimize=True)


def bake_noise(dst: Path, size: int = 64) -> None:
    # Tileable grain for GTK/Breeze menus when live blur is missing.
    raw = Image.effect_noise((size, size), 28).convert("L")
    alpha = raw.point(lambda p: int(p * 0.18))
    tile = Image.merge("RGBA", (raw, raw, raw, alpha))
    dst.parent.mkdir(parents=True, exist_ok=True)
    tile.save(dst, "PNG", optimize=True, compress_level=9)


def main() -> int:
    if not SRC.is_file():
        raise SystemExit(f"missing wallpaper: {SRC}")
    bake_frost(SRC, DST_FROST)
    bake_noise(DST_NOISE)
    print(f"wrote {DST_FROST.relative_to(ROOT)} ({DST_FROST.stat().st_size} bytes)")
    print(f"wrote {DST_NOISE.relative_to(ROOT)} ({DST_NOISE.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
