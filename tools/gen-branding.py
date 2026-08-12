#!/usr/bin/env python3
"""Regenerate SynapseOS branding art (Calamares branding + installer icon).

All text is measured and shrunk to fit its canvas, so nothing is clipped.

Usage:  python3 tools/gen-branding.py
Requires: python-pillow
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BRANDING = ROOT / "archiso/airootfs/etc/calamares/branding/synapseos"
SLIDES = BRANDING / "slideshow"
PIXMAPS = ROOT / "archiso/airootfs/usr/share/pixmaps"

BG_TOP = (11, 16, 24)
BG_BOTTOM = (16, 22, 36)
TEXT = (232, 238, 247)
MUTED = (140, 156, 180)
ACCENT = (41, 182, 246)

FONT_CANDIDATES = {
    "bold": [
        "/usr/share/fonts/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
    ],
    "regular": [
        "/usr/share/fonts/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
    ],
}


def font_path(kind: str) -> str:
    for candidate in FONT_CANDIDATES[kind]:
        if Path(candidate).exists():
            return candidate
    raise SystemExit(f"no {kind} font found; install noto-fonts or ttf-dejavu")


def gradient(size: tuple[int, int]) -> Image.Image:
    width, height = size
    img = Image.new("RGB", size, BG_TOP)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(height - 1, 1)
        draw.line(
            [(0, y), (width, y)],
            fill=tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)),
        )
    return img


def fitted_font(draw, text, kind, start_size, max_width):
    """Largest font size <= start_size whose rendering of *text* fits max_width."""
    path = font_path(kind)
    size = start_size
    while size > 6:
        font = ImageFont.truetype(path, size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 1
    return ImageFont.truetype(path, 6)


def centered(draw, xy, text, font, fill):
    draw.text(xy, text, font=font, fill=fill, anchor="mm")


def welcome(path: Path, size=(400, 400)) -> None:
    img = gradient(size)
    draw = ImageDraw.Draw(img)
    pad = 24
    inner = size[0] - 2 * pad
    title = fitted_font(draw, "SynapseOS", "bold", 62, inner)
    subtitle = fitted_font(draw, "COSMIC desktop", "regular", 20, inner)
    centered(draw, (size[0] / 2, size[1] / 2 - 20), "SynapseOS", title, TEXT)
    centered(draw, (size[0] / 2, size[1] / 2 + 30), "COSMIC desktop", subtitle, MUTED)
    bar = 100
    draw.rectangle(
        [(size[0] - bar) / 2, size[1] - 60, (size[0] + bar) / 2, size[1] - 56],
        fill=ACCENT,
    )
    img.save(path)


def logo(path: Path, size=256) -> None:
    img = gradient((size, size))
    draw = ImageDraw.Draw(img)
    inset = size * 0.13
    draw.ellipse(
        [inset, inset, size - inset, size - inset],
        outline=ACCENT,
        width=max(2, size // 32),
    )
    font = fitted_font(draw, "S", "bold", int(size * 0.42), size * 0.5)
    centered(draw, (size / 2, size / 2), "S", font, TEXT)
    img.save(path)


def banner(path: Path, size=(600, 90)) -> None:
    img = gradient(size)
    draw = ImageDraw.Draw(img)
    font = fitted_font(draw, "SynapseOS", "bold", 40, size[0] - 140)
    draw.text((24, size[1] / 2), "SynapseOS", font=font, fill=TEXT, anchor="lm")
    draw.rectangle([0, size[1] - 3, size[0], size[1]], fill=ACCENT)
    img.save(path)


def wallpaper(path: Path, size=(1920, 1080)) -> None:
    img = gradient(size)
    draw = ImageDraw.Draw(img)
    font = fitted_font(draw, "SynapseOS", "bold", 120, size[0] * 0.6)
    centered(draw, (size[0] / 2, size[1] / 2), "SynapseOS", font, TEXT)
    draw.rectangle(
        [size[0] / 2 - 120, size[1] / 2 + 110, size[0] / 2 + 120, size[1] / 2 + 116],
        fill=ACCENT,
    )
    img.save(path)


def slide(path: Path, heading: str, body: str, size=(520, 320)) -> None:
    img = gradient(size)
    draw = ImageDraw.Draw(img)
    margin = 48
    inner = size[0] - 2 * margin
    head_font = fitted_font(draw, heading, "bold", 34, inner)
    draw.text((margin, 96), heading, font=head_font, fill=TEXT, anchor="ls")

    body_font = ImageFont.truetype(font_path("regular"), 17)
    words, lines, line = body.split(), [], ""
    for word in words:
        probe = f"{line} {word}".strip()
        if draw.textlength(probe, font=body_font) <= inner:
            line = probe
        else:
            lines.append(line)
            line = word
    lines.append(line)
    y = 140
    for text_line in lines[:4]:
        draw.text((margin, y), text_line, font=body_font, fill=MUTED)
        y += 26
    draw.rectangle([margin, 240, size[0] - margin, 244], fill=ACCENT)
    img.save(path)


def main() -> None:
    BRANDING.mkdir(parents=True, exist_ok=True)
    SLIDES.mkdir(parents=True, exist_ok=True)
    PIXMAPS.mkdir(parents=True, exist_ok=True)

    welcome(BRANDING / "welcome.png")
    logo(BRANDING / "logo.png", 256)
    logo(BRANDING / "icon.png", 64)
    logo(PIXMAPS / "synapseos-installer.png", 256)
    banner(BRANDING / "banner.png")
    wallpaper(BRANDING / "wallpaper.png")

    slide(
        SLIDES / "slide1.png",
        "A fresh start",
        "SynapseOS brings the COSMIC desktop to Arch Linux, with sensible "
        "defaults and nothing in your way.",
    )
    slide(
        SLIDES / "slide2.png",
        "Fast and offline",
        "Everything you see in the live session is copied straight to your "
        "disk. No downloads, no waiting on mirrors.",
    )
    slide(
        SLIDES / "slide3.png",
        "Yours to shape",
        "Arch underneath means pacman, the AUR and the whole Arch Wiki are "
        "available from day one.",
    )
    print("branding art written to", BRANDING)


if __name__ == "__main__":
    main()
