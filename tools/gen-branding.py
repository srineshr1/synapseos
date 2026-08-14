#!/usr/bin/env python3
"""Regenerate SynapseOS branding art.

Covers Calamares art, the installer icon, the live GRUB theme, the
syslinux (BIOS) splash, the installed GRUB theme, and the desktop
wallpaper.

All lettering is measured and drawn with Pillow so nothing is clipped
or misspelled. Atmosphere is generated procedurally (seeded) so the
script stays reproducible.

Usage:  python3 tools/gen-branding.py
Requires: python-pillow
"""

from __future__ import annotations

import math
import random
import subprocess
from functools import lru_cache
from pathlib import Path
from shutil import copy2

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BRANDING = ROOT / "archiso/airootfs/etc/calamares/branding/synapseos"
SLIDES = BRANDING / "slideshow"
PIXMAPS = ROOT / "archiso/airootfs/usr/share/pixmaps"
BACKGROUNDS = ROOT / "archiso/airootfs/usr/share/backgrounds/synapseos"
GRUB_THEME = ROOT / "archiso/grub/theme"
INSTALLED_THEME = ROOT / "archiso/airootfs/usr/share/grub/themes/synapseos"
SYSLINUX = ROOT / "archiso/syslinux"
SOURCE = ROOT / "archiso/branding"

# Catppuccin Macchiato. Never pure #000.
VOID = (24, 25, 38)          # crust
VOID_HEX = "#181926"
SURFACE = (36, 39, 58)       # base
TEXT = (202, 211, 245)
MUTED = (165, 173, 203)      # subtext0
DIM = (128, 135, 162)        # overlay1
MARK = (198, 160, 246)       # mauve
MARK_DEEP = (138, 105, 196)
MARK_GLOW = (238, 212, 255)
SELECT_BG = (198, 160, 246)
CREDIT_LINE = "Made by Srinesh, Vashista, Vishnu"
BASED_LINE = "Based on Arch"
WORDMARK = "SynapseOS"
MENU_FONT = "DejaVu Sans Regular 24"
MENU_FONT_FILE = "dejavu_24.pf2"
MENU_FONT_SIZE = 24

FONT_CANDIDATES = {
    "display": [
        Path.home() / ".local/share/fonts/Inter/InterDisplay-SemiBold.otf",
        Path("/usr/share/fonts/inter/InterDisplay-SemiBold.otf"),
        Path("/usr/share/fonts/Inter/InterDisplay-SemiBold.otf"),
        Path("/usr/share/fonts/noto/NotoSans-Bold.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ],
    "display-medium": [
        Path.home() / ".local/share/fonts/Inter/InterDisplay-Medium.otf",
        Path("/usr/share/fonts/inter/InterDisplay-Medium.otf"),
        Path("/usr/share/fonts/noto/NotoSans-Medium.ttf"),
        Path("/usr/share/fonts/noto/NotoSans-Bold.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ],
    "bold": [
        Path.home() / ".local/share/fonts/Inter/Inter-SemiBold.otf",
        Path("/usr/share/fonts/inter/Inter-SemiBold.otf"),
        Path("/usr/share/fonts/noto/NotoSans-Bold.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ],
    "regular": [
        Path.home() / ".local/share/fonts/Inter/Inter-Regular.otf",
        Path("/usr/share/fonts/inter/Inter-Regular.otf"),
        Path("/usr/share/fonts/noto/NotoSans-Regular.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    ],
    "medium": [
        Path.home() / ".local/share/fonts/Inter/Inter-Medium.otf",
        Path("/usr/share/fonts/inter/Inter-Medium.otf"),
        Path("/usr/share/fonts/noto/NotoSans-Medium.ttf"),
        Path("/usr/share/fonts/noto/NotoSans-Regular.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    ],
}


def font_path(kind: str) -> str:
    for candidate in FONT_CANDIDATES[kind]:
        if candidate.exists():
            return str(candidate)
    raise SystemExit(f"no {kind} font found; install inter-font or noto-fonts")


def load_font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path(kind), size)


def fitted_font(draw: ImageDraw.ImageDraw, text: str, kind: str, start_size: int, max_width: float):
    size = start_size
    while size > 6:
        font = load_font(kind, size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 1
    return load_font(kind, 6)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix(c0, c1, t: float):
    return tuple(int(round(lerp(a, b, t))) for a, b in zip(c0, c1))


def clamp_byte(v: float) -> int:
    return max(0, min(255, int(round(v))))


def screen_pixel(base, add, amount: float):
    return tuple(
        clamp_byte(b + (255 - (255 - b) * (255 - a) / 255 - b) * amount)
        for b, a in zip(base, add)
    )


def qbezier(p0, p1, p2, steps: int):
    for i in range(steps + 1):
        t = i / steps
        mt = 1.0 - t
        x = mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0]
        y = mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]
        yield x, y


def vertical_gradient(size, top, bottom) -> Image.Image:
    width, height = size
    img = Image.new("RGB", size, top)
    px = img.load()
    for y in range(height):
        color = mix(top, bottom, y / max(height - 1, 1))
        for x in range(width):
            px[x, y] = color
    return img


def geometric_s(size: int, fg=MARK, bg=None) -> Image.Image:
    """Approved block-S: five equal bands, synaptic gap, rounded and AA."""
    scale = 4
    s = max(8, int(size)) * scale
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0) if bg is None else (*bg, 255))
    mask = Image.new("L", (s, s), 0)
    draw = ImageDraw.Draw(mask)
    band = s / 5
    stem = s / 5
    gap = s / 5
    arm = (s - gap) / 2
    radius = max(2, int(band * 0.22))

    def bar(xy):
        draw.rounded_rectangle(xy, radius=radius, fill=255)

    bar([0, 0, s - 1, band - 1])
    bar([0, 0, stem - 1, 3 * band - 1])
    bar([0, 2 * band, arm - 1, 3 * band - 1])
    bar([s - arm, 2 * band, s - 1, 3 * band - 1])
    bar([s - stem, 2 * band, s - 1, s - 1])
    bar([0, 4 * band, s - 1, s - 1])

    if isinstance(fg, tuple) and len(fg) == 2:
        fill = vertical_gradient((s, s), fg[0], fg[1]).convert("RGBA")
    else:
        fill = Image.new("RGBA", (s, s), (*fg, 255))
    fill.putalpha(mask)
    if bg is None:
        canvas = fill
    else:
        canvas.paste(fill, (0, 0), fill)
    return canvas.resize((max(8, int(size)), max(8, int(size))), Image.Resampling.LANCZOS)


def glow_behind(mark: Image.Image, spread: float = 0.42, strength: float = 0.9) -> Image.Image:
    """Soft violet halo around a transparent mark, same canvas size expanded."""
    pad = max(8, int(mark.width * spread))
    w, h = mark.width + pad * 2, mark.height + pad * 2
    halo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    alpha = mark.split()[-1]
    silhouette = Image.new("RGBA", mark.size, (*MARK_GLOW, 255))
    silhouette.putalpha(alpha)
    halo.paste(silhouette, (pad, pad), silhouette)
    radius = max(6, int(mark.width * 0.12))
    halo = halo.filter(ImageFilter.GaussianBlur(radius=radius))
    # Boost the glow without washing the mark.
    boosted = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    boosted = Image.blend(boosted, halo, strength)
    boosted.paste(mark, (pad, pad), mark)
    return boosted


def paste_center(dst: Image.Image, src: Image.Image, cx: float, cy: float) -> None:
    box = (int(cx - src.width / 2), int(cy - src.height / 2))
    if src.mode == "RGBA":
        dst.paste(src, box, src)
    else:
        dst.paste(src, box)


def draw_tracked(draw, xy, text, font, fill, tracking=0.6, anchor="ls"):
    """Draw *text* with extra tracking, characters sharing a baseline.

    Pillow anchors: first letter is l/m/r, second is a/s/m/t. We always
    ink with ``ls`` (left + baseline) so capitals keep their height.
    """
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * max(len(text) - 1, 0)
    x, y = xy
    if anchor[0] == "m":
        x -= total / 2
    elif anchor[0] == "r":
        x -= total
    if len(anchor) > 1 and anchor[1] == "m":
        bbox = font.getbbox(text)
        y += (bbox[3] + bbox[1]) / 2
    elif len(anchor) > 1 and anchor[1] == "t":
        bbox = font.getbbox(text)
        y -= bbox[1]
    cursor = x
    for ch, width in zip(text, widths):
        draw.text((cursor, y), ch, font=font, fill=fill, anchor="ls")
        cursor += width + tracking


def nebula_layer(size, rng: random.Random, blobs) -> Image.Image:
    """Low-res additive glow orbs, then upscale — cheap volumetric haze."""
    lw, lh = max(64, size[0] // 4), max(36, size[1] // 4)
    layer = Image.new("RGB", (lw, lh), (0, 0, 0))
    px = layer.load()
    sx, sy = lw / size[0], lh / size[1]
    for cx, cy, radius, color, peak in blobs:
        cx, cy, radius = cx * sx, cy * sy, radius * sx
        r2 = radius * radius
        x0, x1 = max(0, int(cx - radius)), min(lw, int(cx + radius) + 1)
        y0, y1 = max(0, int(cy - radius)), min(lh, int(cy + radius) + 1)
        for y in range(y0, y1):
            dy = y - cy
            for x in range(x0, x1):
                d2 = (x - cx) * (x - cx) + dy * dy
                if d2 > r2:
                    continue
                fall = (1.0 - d2 / r2) ** 2
                add = tuple(c * peak * fall for c in color)
                base = px[x, y]
                px[x, y] = tuple(clamp_byte(b + a) for b, a in zip(base, add))
    layer = layer.filter(ImageFilter.GaussianBlur(radius=2.4))
    return layer.resize(size, Image.Resampling.LANCZOS)


def filament_layer(size, rng: random.Random, origins, count: int, length: float) -> Image.Image:
    w, h = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for _ in range(count):
        ox, oy = origins[rng.randrange(len(origins))]
        angle = rng.uniform(-math.pi * 0.15, math.pi * 1.15) if oy < h * 0.4 else rng.uniform(0.2, math.pi - 0.2)
        span = length * rng.uniform(0.55, 1.15)
        p0 = (ox + rng.uniform(-18, 18), oy + rng.uniform(-12, 12))
        p2 = (ox + math.cos(angle) * span, oy + math.sin(angle) * span)
        p1 = (
            (p0[0] + p2[0]) / 2 + rng.uniform(-span * 0.28, span * 0.28),
            (p0[1] + p2[1]) / 2 + rng.uniform(-span * 0.22, span * 0.22),
        )
        steps = max(18, int(span / 10))
        pts = list(qbezier(p0, p1, p2, steps))
        alpha = rng.randint(55, 120)
        tint = mix(MARK, MARK_GLOW, rng.random())
        width = rng.choice((1, 1, 1, 2))
        draw.line(pts, fill=(*tint, alpha), width=width, joint="curve")
        # glowing nodes along the filament
        for x, y in pts[:: max(4, steps // 5)]:
            if rng.random() > 0.55:
                continue
            r = rng.uniform(1.1, 2.6)
            node = (*mix(tint, (255, 255, 255), 0.35), rng.randint(140, 220))
            draw.ellipse([x - r, y - r, x + r, y + r], fill=node)
    return layer.filter(ImageFilter.GaussianBlur(radius=0.6))


def grain(size, rng: random.Random, amount: int = 14) -> Image.Image:
    nw, nh = max(1, size[0] // 3), max(1, size[1] // 3)
    data = [rng.randint(0, amount) for _ in range(nw * nh)]
    n = Image.new("L", (nw, nh))
    n.putdata(data)
    return n.resize(size, Image.Resampling.BILINEAR)


def vignette(size, strength: float = 0.55) -> Image.Image:
    w, h = size
    lw, lh = max(64, w // 6), max(36, h // 6)
    img = Image.new("L", (lw, lh), 0)
    px = img.load()
    cx, cy = (lw - 1) / 2, (lh - 1) / 2
    maxd = math.hypot(cx, cy)
    for y in range(lh):
        for x in range(lw):
            d = math.hypot(x - cx, y - cy) / maxd
            px[x, y] = clamp_byte(255 * min(1.0, (d ** 1.65) * strength))
    return img.resize(size, Image.Resampling.LANCZOS)


@lru_cache(maxsize=16)
def atmosphere(size: tuple[int, int], variant: str = "desktop", seed: int = 7) -> Image.Image:
    """Dark void + violet nebula + synaptic filaments. Seeded, no lettering."""
    rng = random.Random(seed + (0 if variant == "desktop" else 41))
    w, h = size
    img = vertical_gradient(size, VOID, mix(VOID, (18, 12, 36), 0.55 if variant == "desktop" else 0.3))

    if variant == "boot":
        blobs = [
            (w * 0.50, -h * 0.02, w * 0.55, MARK_GLOW, 0.55),
            (w * 0.32, h * 0.10, w * 0.38, MARK, 0.38),
            (w * 0.70, h * 0.14, w * 0.34, MARK_DEEP, 0.32),
            (w * 0.50, h * 0.22, w * 0.55, (70, 50, 130), 0.22),
        ]
        origins = [(w * 0.50, h * 0.10), (w * 0.40, h * 0.16), (w * 0.62, h * 0.15)]
        filaments = 16 if w >= 1280 else 8
        length = h * 0.42
    else:
        blobs = [
            (w * 0.62, h * 0.42, w * 0.48, MARK, 0.50),
            (w * 0.55, h * 0.30, w * 0.28, MARK_GLOW, 0.42),
            (w * 0.72, h * 0.52, w * 0.36, MARK_DEEP, 0.36),
            (w * 0.38, h * 0.58, w * 0.30, (60, 40, 120), 0.20),
            (w * 0.18, h * 0.22, w * 0.22, (40, 28, 80), 0.14),
        ]
        origins = [(w * 0.60, h * 0.42), (w * 0.52, h * 0.38), (w * 0.70, h * 0.48)]
        filaments = 46
        length = min(w, h) * 0.62

    # Screen-blend at quarter res; the haze is already soft.
    lw, lh = max(64, w // 4), max(36, h // 4)
    small = img.resize((lw, lh), Image.Resampling.BILINEAR)
    haze = nebula_layer(size, rng, blobs).resize((lw, lh), Image.Resampling.BILINEAR)
    base = small.load()
    add = haze.load()
    for y in range(lh):
        for x in range(lw):
            base[x, y] = screen_pixel(base[x, y], add[x, y], 0.92)
    img = small.resize(size, Image.Resampling.LANCZOS)

    img = img.convert("RGBA")
    img.alpha_composite(filament_layer(size, rng, origins, filaments, length))

    # Fine dust
    dust = Image.new("RGBA", size, (0, 0, 0, 0))
    ddraw = ImageDraw.Draw(dust)
    for _ in range(int((w * h) / 14000)):
        x, y = rng.randrange(w), rng.randrange(h)
        r = rng.choice((0.6, 0.8, 1.1, 1.4))
        ddraw.ellipse([x - r, y - r, x + r, y + r], fill=(230, 220, 255, rng.randint(20, 70)))
    img.alpha_composite(dust)

    rgb = img.convert("RGB")
    g = grain(size, rng, 16)
    rgb = Image.composite(mix_image(rgb, 18), rgb, g)

    vig = vignette(size, 0.62 if variant == "desktop" else 0.48)
    darkened = Image.new("RGB", size, (0, 0, 0))
    rgb = Image.composite(darkened, rgb, vig)

    if variant == "boot":
        # Keep the lower half quiet so the menu reads.
        strip = Image.new("L", (1, h), 0)
        sp = strip.load()
        start = int(h * 0.42)
        for y in range(start, h):
            t = (y - start) / max(h - start, 1)
            sp[0, y] = clamp_byte(210 * (t ** 1.15))
        fade = strip.resize(size, Image.Resampling.BILINEAR)
        rgb = Image.composite(Image.new("RGB", size, VOID), rgb, fade)
    return rgb


def mix_image(img: Image.Image, lift: int) -> Image.Image:
    lifted = Image.new("RGB", img.size, (min(255, VOID[0] + lift), min(255, VOID[1] + lift), min(255, VOID[2] + lift)))
    return Image.blend(img, lifted, 0.35)


# --- Calamares surfaces -------------------------------------------------------

def welcome(path: Path, size=(500, 150)) -> None:
    img = Image.new("RGB", size, VOID)
    mark = glow_behind(geometric_s(92, fg=(MARK_GLOW, MARK)), spread=0.28, strength=0.75)
    paste_center(img, mark, 24 + mark.width / 2, size[1] / 2)
    draw = ImageDraw.Draw(img)
    text_left = 24 + mark.width + 8
    title = fitted_font(draw, WORDMARK, "display", 42, size[0] - text_left - 24)
    sub = fitted_font(draw, BASED_LINE, "regular", 16, size[0] - text_left - 24)
    draw_tracked(draw, (text_left, size[1] / 2 - 4), WORDMARK, title, TEXT, tracking=0.8, anchor="ls")
    draw.text((text_left, size[1] / 2 + 22), BASED_LINE, font=sub, fill=MUTED, anchor="lt")
    img.save(path)


def logo(path: Path, size=256) -> None:
    img = Image.new("RGB", (size, size), VOID)
    inset = max(10, int(size * 0.16))
    mark = geometric_s(size - 2 * inset, fg=(MARK_GLOW, MARK_DEEP))
    img.paste(mark, (inset, inset), mark)
    img.save(path)


def app_icon(path: Path, size=256) -> None:
    """Rounded-tile installer icon — reads at 32px and at 256px."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)
    radius = int(size * 0.22)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=(*VOID, 255))
    # inner rim
    draw.rounded_rectangle(
        [1, 1, size - 2, size - 2],
        radius=radius - 1,
        outline=(*mix(MARK, SURFACE, 0.55), 255),
        width=max(1, size // 64),
    )
    img.alpha_composite(tile)
    mark = glow_behind(geometric_s(int(size * 0.58), fg=(MARK_GLOW, MARK)), spread=0.30, strength=0.8)
    paste_center(img, mark, size / 2, size / 2)
    img.convert("RGB").save(path)


def banner(path: Path, size=(520, 64)) -> None:
    img = Image.new("RGB", size, VOID)
    mark = geometric_s(40, fg=(MARK_GLOW, MARK))
    img.paste(mark, (16, (size[1] - mark.height) // 2), mark)
    draw = ImageDraw.Draw(img)
    font = fitted_font(draw, WORDMARK, "display", 26, size[0] - 80)
    draw_tracked(draw, (68, size[1] / 2 + 8), WORDMARK, font, TEXT, tracking=0.5, anchor="ls")
    img.save(path)


def desktop_wallpaper(path: Path, size=(1920, 1080)) -> None:
    """Prefer the photographic source; fall back to the nebula."""
    src = SOURCE / "desktop.jpg"
    if src.exists():
        img = Image.open(src).convert("RGB")
        img = img.resize(size, Image.Resampling.LANCZOS)
        img.save(path, optimize=True, quality=92)
        return
    img = atmosphere(size, variant="desktop", seed=7).convert("RGBA")
    mark = geometric_s(int(size[1] * 0.28), fg=(MARK_GLOW, MARK_DEEP))
    ghost = mark.copy()
    ghost.putalpha(ghost.split()[-1].point(lambda a: int(a * 0.16)))
    paste_center(img, ghost, size[0] * 0.78, size[1] * 0.62)
    img.convert("RGB").save(path, optimize=True)


def slide(path: Path, number: str, heading: str, body: str, size=(1280, 720)) -> None:
    img = atmosphere(size, variant="desktop", seed=7 + int(number)).convert("RGBA")
    # Dim a readable column on the left without a hard card.
    strip = Image.new("L", (size[0], 1), 0)
    sp = strip.load()
    col = int(size[0] * 0.72)
    for x in range(col):
        t = 1.0 - (x / col) ** 1.6
        sp[x, 0] = clamp_byte(175 * t)
    shade = strip.resize(size, Image.Resampling.BILINEAR)
    img = Image.composite(Image.new("RGBA", size, (*VOID, 255)), img, shade)

    draw = ImageDraw.Draw(img)
    margin = 88
    num_font = load_font("display", 18)
    head_font = fitted_font(draw, heading, "display", 58, size[0] * 0.62)
    draw.text((margin, 168), number, font=num_font, fill=MARK_GLOW)
    draw_tracked(draw, (margin, 210 + head_font.size), heading, head_font, TEXT, tracking=0.3, anchor="ls")

    body_font = load_font("regular", 24)
    words, lines, line = body.split(), [], ""
    inner = int(size[0] * 0.56)
    for word in words:
        probe = f"{line} {word}".strip()
        if draw.textlength(probe, font=body_font) <= inner:
            line = probe
        else:
            lines.append(line)
            line = word
    lines.append(line)
    y = 210 + head_font.size + 28
    for text_line in lines[:5]:
        draw.text((margin, y), text_line, font=body_font, fill=MUTED)
        y += 36

    draw.rounded_rectangle([margin, y + 22, margin + 72, y + 26], radius=2, fill=MARK)

    badge = glow_behind(geometric_s(72, fg=(MARK_GLOW, MARK)), spread=0.30, strength=0.7)
    img.paste(badge, (size[0] - badge.width - 56, 48), badge)
    img.convert("RGB").save(path)


# --- Boot ---------------------------------------------------------------------

THEME_TXT = f"""\
# SynapseOS live / installed GRUB theme
desktop-image: "splash.png"
desktop-color: "{VOID_HEX}"
title-text: ""
message-color: "#d8d2ea"
terminal-box: "select_*.png"
terminal-font: "DejaVu Sans Regular 24"

+ boot_menu {{
    left = 14%
    top = 48%
    width = 72%
    height = 38%
    item_font = "DejaVu Sans Regular 24"
    item_color = "#f4f0fc"
    selected_item_color = "#ffffff"
    selected_item_pixmap_style = "select_*.png"
    item_height = 48
    item_padding = 20
    item_spacing = 8
    icon_width = 0
    icon_height = 0
    item_icon_space = 0
}}

+ label {{
    id = "__timeout__"
    left = 14%
    top = 90%
    width = 72%
    align = "center"
    text = "Booting in %d seconds"
    color = "#a89bc4"
    font = "DejaVu Sans Regular 24"
}}
"""


def boot_splash(path: Path, size: tuple[int, int]) -> Image.Image:
    """Atmosphere, mark, wordmark, credits. Menu lives in the quiet lower half."""
    img = atmosphere(size, variant="boot", seed=3).convert("RGBA")
    width, height = size
    scale = width / 1920

    mark_size = max(72, int(188 * scale))
    mark = glow_behind(geometric_s(mark_size, fg=(MARK_GLOW, MARK)), spread=0.38, strength=0.85)
    mx = (width - mark.width) // 2
    my = max(20, int(56 * scale))
    img.paste(mark, (mx, my), mark)

    draw = ImageDraw.Draw(img)
    title = fitted_font(draw, WORDMARK, "display", max(28, int(54 * scale)), width * 0.78)
    based = fitted_font(draw, BASED_LINE, "medium", max(18, int(22 * scale)), width * 0.78)
    credit = fitted_font(draw, CREDIT_LINE, "regular", max(14, int(17 * scale)), width * 0.90)

    text_y = my + mark.height + int(8 * scale)
    draw_tracked(draw, (width / 2, text_y), WORDMARK, title, TEXT, tracking=1.6 * scale, anchor="mt")
    title_h = title.size
    draw.text(
        (width / 2, text_y + title_h + int(8 * scale)),
        BASED_LINE,
        font=based,
        fill=MUTED,
        anchor="mt",
    )
    draw.text(
        (width / 2, text_y + title_h + based.size + int(20 * scale)),
        CREDIT_LINE,
        font=credit,
        fill=DIM,
        anchor="mt",
    )
    rgb = img.convert("RGB")
    rgb.save(path)
    return rgb


def syslinux_splash(path: Path) -> None:
    """640x480 8-bit PNG. vesamenu.c32 will not initialise graphics without this."""
    hi = boot_splash(path, (1280, 960))
    img = hi.resize((640, 480), Image.Resampling.LANCZOS)
    img.convert("P", palette=Image.Palette.ADAPTIVE, colors=240).save(path)


def write_select_slices(directory: Path) -> None:
    """Rounded purple pill. Corner pixels match the void so they disappear."""
    tile = 20
    canvas = 60
    img = Image.new("RGB", (canvas, canvas), VOID)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, canvas - 1, canvas - 1], radius=14, fill=SELECT_BG)
    # hairline highlight along the top of the pill
    highlight = Image.new("RGB", (canvas, canvas), VOID)
    hd = ImageDraw.Draw(highlight)
    hd.rounded_rectangle([0, 0, canvas - 1, canvas - 1], radius=14, fill=mix(SELECT_BG, (255, 255, 255), 0.18))
    mask = Image.new("L", (canvas, canvas), 0)
    md = ImageDraw.Draw(mask)
    md.rectangle([0, 0, canvas - 1, 3], fill=255)
    img = Image.composite(highlight, img, mask)

    names = {
        "nw": (0, 0),
        "n": (tile, 0),
        "ne": (canvas - tile, 0),
        "w": (0, tile),
        "c": (tile, tile),
        "e": (canvas - tile, tile),
        "sw": (0, canvas - tile),
        "s": (tile, canvas - tile),
        "se": (canvas - tile, canvas - tile),
    }
    for name, (x, y) in names.items():
        img.crop((x, y, x + tile, y + tile)).save(directory / f"select_{name}.png")


def build_menu_font(dest: Path) -> None:
    """Ship a 24px DejaVu face with the theme. Unifont 16 disappears in a
    scaled VM window, and GRUB only uses fonts sitting in the theme dir.
    """
    ttf = Path("/usr/share/fonts/TTF/DejaVuSans.ttf")
    if not ttf.exists():
        ttf = Path(font_path("regular"))
    subprocess.run(
        ["grub-mkfont", "-n", "DejaVu Sans", "-s", str(MENU_FONT_SIZE), "-o", str(dest), str(ttf)],
        check=True,
    )


def write_theme(directory: Path, splash: Path, font: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / "splash.png"
    if splash.resolve() != dest.resolve():
        copy2(splash, dest)
    font_dest = directory / MENU_FONT_FILE
    if font.resolve() != font_dest.resolve():
        copy2(font, font_dest)
    (directory / "theme.txt").write_text(THEME_TXT)
    write_select_slices(directory)


def write_cosmic_bg_config(skel: Path) -> None:
    dest = skel / "com.system76.CosmicBackground/v1"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "same-on-all").write_text("true\n")
    (dest / "all").write_text(
        """(
    output: "all",
    source: Path("/usr/share/backgrounds/synapseos/desktop.png"),
    filter_by_theme: false,
    rotation_frequency: 900,
    filter_method: Lanczos,
    scaling_mode: Zoom,
    sampling_method: Alphanumeric,
)
"""
    )


def write_wallpaper_xml(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE wallpapers SYSTEM "gnome-wp-list.dtd">
<wallpapers>
  <wallpaper deleted="false">
    <name>SynapseOS</name>
    <filename>/usr/share/backgrounds/synapseos/desktop.png</filename>
    <options>zoom</options>
    <pcolor>#08070d</pcolor>
    <scolor>#08070d</scolor>
    <shade_type>solid</shade_type>
  </wallpaper>
</wallpapers>
"""
    )


def installer_mockup(path: Path) -> None:
    """Static chrome preview of the Calamares window using brand colours."""
    w, h = 1100, 680
    sidebar_w = 230
    img = Image.new("RGB", (w, h), VOID)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, sidebar_w, h], fill=(12, 11, 18))
    logo_img = Image.open(BRANDING / "logo.png").convert("RGBA").resize((72, 72), Image.Resampling.LANCZOS)
    img.paste(logo_img, (24, 28), logo_img)
    nav_font = load_font("medium", 14)
    steps = [
        (True, "Welcome"),
        (False, "Location"),
        (False, "Keyboard"),
        (False, "Partitions"),
        (False, "Users"),
        (False, "Summary"),
    ]
    y = 124
    for current, label in steps:
        if current:
            draw.rounded_rectangle([12, y, sidebar_w - 12, y + 36], radius=8, fill=MARK)
            draw.text((28, y + 18), label, font=nav_font, fill=(255, 255, 255), anchor="lm")
        else:
            draw.text((28, y + 18), label, font=nav_font, fill=MUTED, anchor="lm")
        y += 44

    welcome_img = Image.open(BRANDING / "welcome.png")
    img.paste(welcome_img, (sidebar_w + 48, 48))
    body = load_font("regular", 15)
    intro = (
        "Welcome to the SynapseOS installer. SynapseOS is an Arch Linux based "
        "distribution with a compact Catppuccin Macchiato Plasma desktop."
    )
    # wrap
    words, lines, line = intro.split(), [], ""
    max_w = w - sidebar_w - 96
    for word in words:
        probe = f"{line} {word}".strip()
        if draw.textlength(probe, font=body) <= max_w:
            line = probe
        else:
            lines.append(line)
            line = word
    lines.append(line)
    ty = 48 + welcome_img.height + 20
    for text_line in lines:
        draw.text((sidebar_w + 48, ty), text_line, font=body, fill=MUTED)
        ty += 22

    # fake language combo
    draw.rounded_rectangle([sidebar_w + 48, ty + 24, sidebar_w + 360, ty + 58], radius=6, outline=(44, 38, 64), width=1)
    draw.rectangle([sidebar_w + 48, ty + 24, sidebar_w + 360, ty + 58], fill=(18, 16, 26))
    draw.rounded_rectangle([sidebar_w + 48, ty + 24, sidebar_w + 360, ty + 58], radius=6, outline=(44, 38, 64), width=1)
    draw.text((sidebar_w + 62, ty + 41), "American English", font=body, fill=TEXT, anchor="lm")

    # nav buttons
    def button(x, y, label, primary=False):
        bw, bh = 108, 36
        fill = MARK if primary else (22, 20, 31)
        outline = MARK if primary else (44, 38, 64)
        draw.rounded_rectangle([x, y, x + bw, y + bh], radius=8, fill=fill, outline=outline)
        color = (255, 255, 255) if primary else TEXT
        draw.text((x + bw / 2, y + bh / 2), label, font=nav_font, fill=color, anchor="mm")

    button(w - 48 - 108, h - 28 - 36, "Next", primary=True)
    button(w - 48 - 108 - 16 - 108, h - 28 - 36, "Cancel")
    img.save(path)


def preview_sheet(path: Path) -> None:
    """Contact sheet so a human can judge the system at a glance."""
    installer_mockup(SOURCE / "installer-mock.png")
    cells = [
        ("Boot", Image.open(GRUB_THEME / "splash.png").resize((640, 360), Image.Resampling.LANCZOS)),
        ("Desktop", Image.open(BACKGROUNDS / "desktop.png").resize((640, 360), Image.Resampling.LANCZOS)),
        ("Installer", Image.open(SOURCE / "installer-mock.png").resize((640, 395), Image.Resampling.LANCZOS)),
        ("Slide 1", Image.open(SLIDES / "slide1.png").resize((640, 360), Image.Resampling.LANCZOS)),
        ("Welcome", Image.open(BRANDING / "welcome.png")),
        ("Icon", Image.open(PIXMAPS / "synapseos-installer.png").resize((180, 180), Image.Resampling.LANCZOS)),
    ]
    pad, label_h, gap = 28, 28, 20
    col_w = 640
    rows = [
        [cells[0], cells[1]],
        [cells[3], cells[2]],
        [cells[4], cells[5]],
    ]
    heights = []
    for row in rows:
        heights.append(max(im.height for _, im in row) + label_h)
    sheet = Image.new(
        "RGB",
        (pad * 2 + col_w * 2 + gap, pad * 2 + sum(heights) + gap * (len(rows) - 1)),
        mix(VOID, (20, 18, 30), 0.4),
    )
    draw = ImageDraw.Draw(sheet)
    font = load_font("medium", 14)
    y = pad
    for row, h in zip(rows, heights):
        x = pad
        for label, im in row:
            draw.text((x, y), label, font=font, fill=MUTED)
            sheet.paste(im.convert("RGB"), (x, y + label_h))
            x += col_w + gap
        y += h + gap
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def main() -> None:
    for directory in (BRANDING, SLIDES, PIXMAPS, BACKGROUNDS, GRUB_THEME, INSTALLED_THEME, SOURCE):
        directory.mkdir(parents=True, exist_ok=True)

    welcome(BRANDING / "welcome.png")
    logo(BRANDING / "logo.png", 256)
    logo(BRANDING / "icon.png", 64)
    app_icon(PIXMAPS / "synapseos-installer.png", 256)
    banner(BRANDING / "banner.png")
    desktop_wallpaper(BACKGROUNDS / "desktop.png")
    write_wallpaper_xml(BACKGROUNDS / "synapseos.xml")
    props = ROOT / "archiso/airootfs/usr/share/gnome-background-properties"
    props.mkdir(parents=True, exist_ok=True)
    write_wallpaper_xml(props / "synapseos.xml")
    # Plasma wallpaper is set from appletsrc, not COSMIC config.

    slide(
        SLIDES / "slide1.png",
        "01",
        "A fresh start",
        "SynapseOS brings a compact Catppuccin Plasma desktop to Arch Linux, "
        "with sensible defaults and nothing in your way.",
    )
    slide(
        SLIDES / "slide2.png",
        "02",
        "Fast and offline",
        "Everything you see in the live session is copied straight to your "
        "disk. No downloads, no waiting on mirrors.",
    )
    slide(
        SLIDES / "slide3.png",
        "03",
        "Yours to shape",
        "Arch underneath means pacman, the AUR and the whole Arch Wiki are "
        "available from day one.",
    )

    geometric_s(1024, fg=(MARK_GLOW, MARK_DEEP), bg=VOID).save(SOURCE / "mark.png")

    live_splash = GRUB_THEME / "splash.png"
    boot_splash(live_splash, (1920, 1080))
    menu_font = GRUB_THEME / MENU_FONT_FILE
    build_menu_font(menu_font)
    write_theme(GRUB_THEME, live_splash, menu_font)
    write_theme(INSTALLED_THEME, live_splash, menu_font)
    syslinux_splash(SYSLINUX / "splash.png")

    preview_sheet(SOURCE / "preview.png")

    print("branding art written to", BRANDING)
    print("desktop wallpaper written to", BACKGROUNDS)
    print("GRUB theme written to", GRUB_THEME, "and", INSTALLED_THEME)
    print("syslinux splash written to", SYSLINUX / "splash.png")
    print("preview sheet written to", SOURCE / "preview.png")


if __name__ == "__main__":
    main()
