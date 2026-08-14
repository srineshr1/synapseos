#!/usr/bin/env python3
"""Regenerate SynapseOS branding art.

Covers Calamares art, the installer icon, the live and installed GRUB
themes, the syslinux splash, Plymouth / SDDM / KSplash assets, and the
desktop wallpaper.

Boot, splash and login stay a solid Macchiato field plus one mark — no
nebula, no credits. Atmosphere is only the desktop-wallpaper fallback.

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
PLYMOUTH = ROOT / "archiso/airootfs/usr/share/plymouth/themes/synapseos"
SDDM = ROOT / "archiso/airootfs/usr/share/sddm/themes/synapseos"
KSPLASH = (
    ROOT
    / "archiso/airootfs/usr/share/plasma/look-and-feel"
    / "Catppuccin-Macchiato-Mauve/contents/splash/images"
)

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
ENTRY_SIZE = (286, 48)
PROGRESS_SIZE = (300, 10)
LOCK_CANVAS = (84, 96)
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


def slide(path: Path, heading: str, body: str, size=(1280, 720)) -> None:
    """Solid field, one mark, one heading. Used as the Calamares slideshow."""
    img = Image.new("RGB", size, VOID)
    mark = geometric_s(72, fg=(MARK_GLOW, MARK))
    img.paste(mark, (88, 88), mark)
    draw = ImageDraw.Draw(img)
    head_font = fitted_font(draw, heading, "display", 48, size[0] * 0.7)
    body_font = load_font("regular", 22)
    draw_tracked(draw, (88, 260), heading, head_font, TEXT, tracking=0.4, anchor="ls")
    words, lines, line = body.split(), [], ""
    inner = int(size[0] * 0.62)
    for word in words:
        probe = f"{line} {word}".strip()
        if draw.textlength(probe, font=body_font) <= inner:
            line = probe
        else:
            lines.append(line)
            line = word
    lines.append(line)
    y = 260 + head_font.size + 24
    for text_line in lines[:4]:
        draw.text((88, y), text_line, font=body_font, fill=MUTED)
        y += 34
    img.save(path)


# --- Boot ---------------------------------------------------------------------

THEME_TXT = f"""\
# SynapseOS live / installed GRUB theme
desktop-image: "splash.png"
desktop-color: "{VOID_HEX}"
title-text: ""
message-color: "#cad3f5"
terminal-font: "DejaVu Sans Regular 24"

+ boot_menu {{
    left = 20%
    top = 48%
    width = 60%
    height = 38%
    item_font = "DejaVu Sans Regular 24"
    item_color = "#a5adcb"
    selected_item_color = "#c6a0f6"
    item_height = 36
    item_padding = 8
    item_spacing = 6
    icon_width = 0
    icon_height = 0
    item_icon_space = 0
}}

+ label {{
    id = "__timeout__"
    left = 20%
    top = 90%
    width = 60%
    align = "center"
    text = "Booting in %d seconds"
    color = "#6e738d"
    font = "DejaVu Sans Regular 24"
}}
"""


def brand_mark(size: int) -> Image.Image:
    return geometric_s(size, fg=(MARK_GLOW, MARK))


def wordmark_logo(mark_size: int = 96, title_size: int = 56) -> Image.Image:
    """Horizontal S + SynapseOS on a transparent field. Shared by Plymouth/SDDM."""
    mark = brand_mark(mark_size)
    probe = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    title = load_font("display", title_size)
    text_w = int(draw.textlength(WORDMARK, font=title))
    gap = max(16, mark_size // 5)
    pad_x, pad_y = 8, 8
    width = pad_x * 2 + mark.width + gap + text_w
    height = pad_y * 2 + max(mark.height, title_size + 8)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    img.paste(mark, (pad_x, (height - mark.height) // 2), mark)
    ImageDraw.Draw(img).text(
        (pad_x + mark.width + gap, height / 2 + title_size * 0.12),
        WORDMARK,
        font=title,
        fill=(*TEXT, 255),
        anchor="ls",
    )
    return img


def boot_splash(path: Path, size: tuple[int, int]) -> Image.Image:
    """Solid crust, small mark and wordmark. Menu lives in the empty lower half."""
    img = Image.new("RGB", size, VOID)
    width, height = size
    scale = width / 1920
    mark_size = max(56, int(88 * scale))
    mark = brand_mark(mark_size)
    draw = ImageDraw.Draw(img)
    title = fitted_font(draw, WORDMARK, "display", max(22, int(36 * scale)), width * 0.6)
    top = max(24, int(height * 0.14))
    paste_center(img, mark, width / 2, top + mark.height / 2)
    # Baseline well below the mark. "ms" is middle + baseline — do not use "mt",
    # which leaves the wordmark sitting on the S.
    baseline = top + mark.height + int(14 * scale) + title.size
    draw_tracked(
        draw,
        (width / 2, baseline),
        WORDMARK,
        title,
        TEXT,
        tracking=1.2 * scale,
        anchor="ms",
    )
    img.save(path)
    return img


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
    for leftover in directory.glob("select_*.png"):
        leftover.unlink()


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


def padlock(size: tuple[int, int], color) -> Image.Image:
    """Shackle-and-body lock on an 84x96 canvas."""
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    body_w, body_h = int(w * 0.70), int(h * 0.42)
    body_x = (w - body_w) // 2
    body_y = int(h * 0.50)
    draw.rounded_rectangle(
        [body_x, body_y, body_x + body_w - 1, body_y + body_h - 1],
        radius=max(5, body_w // 7),
        fill=(*color, 255),
    )
    sw = max(7, w // 9)
    sh_w = int(body_w * 0.62)
    sh_x0 = (w - sh_w) // 2
    sh_x1 = sh_x0 + sh_w
    sh_top = int(h * 0.10)
    # Full upside-down U: arc plus two legs that meet the body.
    draw.arc([sh_x0, sh_top, sh_x1, sh_top + sh_w], 180, 360, fill=(*color, 255), width=sw)
    draw.line(
        [(sh_x0 + sw // 2, sh_top + sh_w // 2), (sh_x0 + sw // 2, body_y + 1)],
        fill=(*color, 255),
        width=sw,
    )
    draw.line(
        [(sh_x1 - sw // 2, sh_top + sh_w // 2), (sh_x1 - sw // 2, body_y + 1)],
        fill=(*color, 255),
        width=sw,
    )
    return img


def entry_field(size: tuple[int, int], border) -> Image.Image:
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=8, fill=(*SURFACE, 255), outline=(*border, 255), width=2)
    return img


def bullet_dot(size: int = 14) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    inset = 3
    draw.ellipse([inset, inset, size - 1 - inset, size - 1 - inset], fill=(*TEXT, 255))
    return img


def progress_bar(size: tuple[int, int], fill) -> Image.Image:
    img = Image.new("RGB", size, fill)
    return img


def write_plymouth_assets(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    wordmark_logo().save(directory / "logo.png")
    padlock(LOCK_CANVAS, MARK).save(directory / "lock.png")
    entry_field(ENTRY_SIZE, MARK).save(directory / "entry.png")
    bullet_dot().save(directory / "bullet.png")
    progress_bar(PROGRESS_SIZE, MARK).save(directory / "progress_bar.png")
    progress_bar(PROGRESS_SIZE, (54, 58, 79)).save(directory / "progress_box.png")


def write_sddm_assets(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    wordmark_logo().save(directory / "logo.png")
    padlock(LOCK_CANVAS, MARK).save(directory / "lock.png")
    padlock(LOCK_CANVAS, (237, 135, 150)).save(directory / "lock-failed.png")
    entry_field(ENTRY_SIZE, MARK).save(directory / "entry.png")
    entry_field(ENTRY_SIZE, (237, 135, 150)).save(directory / "entry-failed.png")
    bullet_dot().save(directory / "bullet.png")


def write_ksplash_mark(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    brand_mark(160).save(directory / "mark.png")


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
            draw.rounded_rectangle([12, y, sidebar_w - 12, y + 36], radius=8, fill=(36, 39, 58))
            draw.rectangle([12, y + 8, 16, y + 28], fill=MARK)
            draw.text((28, y + 18), label, font=nav_font, fill=MARK, anchor="lm")
        else:
            draw.text((28, y + 18), label, font=nav_font, fill=MUTED, anchor="lm")
        y += 44

    mark = brand_mark(72)
    img.paste(mark, (sidebar_w + 48, 56), mark)
    title = load_font("display", 28)
    draw_tracked(draw, (sidebar_w + 48 + mark.width + 16, 56 + mark.height / 2 + 10), WORDMARK, title, TEXT, tracking=0.6, anchor="ls")
    body = load_font("regular", 15)
    intro = "This installer copies the live system to your disk and sets up the bootloader and your account."
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
    ty = 56 + mark.height + 28
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
    plymouth_preview = Image.new("RGB", (640, 360), VOID)
    ply_logo = Image.open(PLYMOUTH / "logo.png").convert("RGBA")
    scale = min(480 / ply_logo.width, 80 / ply_logo.height)
    ply_logo = ply_logo.resize((max(1, int(ply_logo.width * scale)), max(1, int(ply_logo.height * scale))), Image.Resampling.LANCZOS)
    paste_center(plymouth_preview, ply_logo, 320, 150)
    bar = Image.open(PLYMOUTH / "progress_bar.png").resize((240, 8), Image.Resampling.NEAREST)
    plymouth_preview.paste(bar, (200, 230))

    login_preview = Image.new("RGB", (640, 360), VOID)
    paste_center(login_preview, ply_logo, 320, 120)
    entry = Image.open(SDDM / "entry.png").convert("RGBA")
    lock = Image.open(SDDM / "lock.png").convert("RGBA").resize((22, 26), Image.Resampling.LANCZOS)
    login_preview.paste(entry, (177, 200), entry)
    login_preview.paste(lock, (148, 211), lock)

    cells = [
        ("Boot", Image.open(GRUB_THEME / "splash.png").resize((640, 360), Image.Resampling.LANCZOS)),
        ("Plymouth", plymouth_preview),
        ("Installer", Image.open(SOURCE / "installer-mock.png").resize((640, 395), Image.Resampling.LANCZOS)),
        ("Login", login_preview),
        ("Slide 1", Image.open(SLIDES / "slide1.png").resize((640, 360), Image.Resampling.LANCZOS)),
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
    for directory in (
        BRANDING,
        SLIDES,
        PIXMAPS,
        BACKGROUNDS,
        GRUB_THEME,
        INSTALLED_THEME,
        SOURCE,
        PLYMOUTH,
        SDDM,
        KSPLASH,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    logo(BRANDING / "logo.png", 256)
    logo(BRANDING / "icon.png", 64)
    app_icon(PIXMAPS / "synapseos-installer.png", 256)
    desktop_wallpaper(BACKGROUNDS / "desktop.png")
    write_wallpaper_xml(BACKGROUNDS / "synapseos.xml")
    props = ROOT / "archiso/airootfs/usr/share/gnome-background-properties"
    props.mkdir(parents=True, exist_ok=True)
    write_wallpaper_xml(props / "synapseos.xml")

    slide(
        SLIDES / "slide1.png",
        "A fresh start",
        "A compact Catppuccin Plasma desktop, ready the moment the installer finishes.",
    )
    slide(
        SLIDES / "slide2.png",
        "Copied, not downloaded",
        "The live system is written straight to your disk. No extra packages, no waiting on mirrors.",
    )
    slide(
        SLIDES / "slide3.png",
        "Yours to shape",
        "pacman, the AUR and the Arch Wiki are there from the first reboot.",
    )

    geometric_s(1024, fg=(MARK_GLOW, MARK_DEEP), bg=VOID).save(SOURCE / "mark.png")

    live_splash = GRUB_THEME / "splash.png"
    boot_splash(live_splash, (1920, 1080))
    menu_font = GRUB_THEME / MENU_FONT_FILE
    build_menu_font(menu_font)
    write_theme(GRUB_THEME, live_splash, menu_font)
    write_theme(INSTALLED_THEME, live_splash, menu_font)
    syslinux_splash(SYSLINUX / "splash.png")

    write_plymouth_assets(PLYMOUTH)
    write_sddm_assets(SDDM)
    write_ksplash_mark(KSPLASH)

    for leftover in (BRANDING / "welcome.png", BRANDING / "banner.png"):
        if leftover.exists():
            leftover.unlink()

    preview_sheet(SOURCE / "preview.png")

    print("branding art written to", BRANDING)
    print("desktop wallpaper written to", BACKGROUNDS)
    print("GRUB theme written to", GRUB_THEME, "and", INSTALLED_THEME)
    print("plymouth theme written to", PLYMOUTH)
    print("sddm theme assets written to", SDDM)
    print("syslinux splash written to", SYSLINUX / "splash.png")
    print("preview sheet written to", SOURCE / "preview.png")


if __name__ == "__main__":
    main()
