#!/usr/bin/env python3
"""Invented SynapseOS product mockups for the deck.

These are illustrations, not screenshots: nothing here is a capture of running
software. They exist so the deck can show what the interface would feel like.

Every canvas is 2.6:1 and painted on the deck's own BASE background colour, so
the rounded window corners blend into the slide instead of sitting on a box.

    python3 tools/gen-mockups.py [outdir]

Default outdir: assets/deck/
"""

from __future__ import annotations

import math
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- palette ----
# Catppuccin Macchiato, matching tools/gen-deck.py exactly.
CRUST = (0x18, 0x19, 0x26)
MANTLE = (0x1E, 0x20, 0x30)
BASE = (0x24, 0x27, 0x3A)
SURFACE0 = (0x36, 0x3A, 0x4F)
SURFACE1 = (0x49, 0x4D, 0x64)
OVERLAY = (0x6E, 0x73, 0x8D)
SUBTEXT = (0xA5, 0xAD, 0xCB)
TEXT = (0xCA, 0xD3, 0xF5)
WHITE = (0xFF, 0xFF, 0xFF)

MAUVE = (0xC6, 0xA0, 0xF6)
BLUE = (0x8A, 0xAD, 0xF4)
SAPPHIRE = (0x7D, 0xC4, 0xE4)
TEAL = (0x8B, 0xD5, 0xCA)
GREEN = (0xA6, 0xDA, 0x95)
YELLOW = (0xEE, 0xD4, 0x9F)
PEACH = (0xF5, 0xA9, 0x7F)
RED = (0xED, 0x87, 0x96)

W, H = 3120, 1200          # logical design space
SS = 2                     # supersample factor

FONTS = {
    "bold": [
        Path.home() / ".local/share/fonts/Inter/Inter-Bold.otf",
        Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ],
    "semi": [
        Path.home() / ".local/share/fonts/Inter/Inter-SemiBold.otf",
        Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ],
    "medium": [
        Path.home() / ".local/share/fonts/Inter/Inter-Medium.otf",
        Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    ],
    "regular": [
        Path.home() / ".local/share/fonts/Inter/Inter-Regular.otf",
        Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    ],
    "mono": [
        Path("/usr/share/fonts/TTF/JetBrainsMonoNerdFontMono-Regular.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSansMono.ttf"),
    ],
    "monob": [
        Path("/usr/share/fonts/TTF/JetBrainsMonoNerdFontMono-Bold.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf"),
    ],
}


@lru_cache(maxsize=None)
def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FONTS[kind]:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


# ------------------------------------------------------------- canvas ---------
class C:
    """Draw surface taking logical coordinates, rendering at SS scale."""

    def __init__(self, w=W, h=H, bg=BASE):
        self.w, self.h = w, h
        self.img = Image.new("RGB", (w * SS, h * SS), bg)
        self.d = ImageDraw.Draw(self.img, "RGBA")

    def _s(self, box):
        return [v * SS for v in box]

    def rrect(self, box, r=16, fill=None, outline=None, width=2):
        self.d.rounded_rectangle(self._s(box), radius=r * SS, fill=fill,
                                 outline=outline,
                                 width=max(1, int(width * SS)))

    def rect(self, box, fill=None, outline=None, width=2):
        self.d.rectangle(self._s(box), fill=fill, outline=outline,
                         width=max(1, int(width * SS)))

    def ellipse(self, box, fill=None, outline=None, width=2):
        self.d.ellipse(self._s(box), fill=fill, outline=outline,
                       width=max(1, int(width * SS)))

    def line(self, pts, fill=None, width=2, joint=None):
        self.d.line([v * SS for v in pts], fill=fill,
                    width=max(1, int(width * SS)), joint=joint)

    def arc(self, box, start, end, fill=None, width=2):
        self.d.arc(self._s(box), start, end, fill=fill,
                   width=max(1, int(width * SS)))

    def text(self, xy, s, kind="regular", size=30, fill=TEXT, anchor="la"):
        self.d.text((xy[0] * SS, xy[1] * SS), s, font=font(kind, size * SS),
                    fill=fill, anchor=anchor)

    def tw(self, s, kind="regular", size=30) -> float:
        return self.d.textlength(s, font=font(kind, size * SS)) / SS

    def dim(self, alpha=110, color=CRUST):
        self.d.rectangle([0, 0, self.w * SS, self.h * SS],
                         fill=(*color, alpha))

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.img.resize((self.w, self.h), Image.LANCZOS).save(path, optimize=True)
        return path

    # --------------------------------------------------------- components ----
    def spine(self, x, y, h, color, w=7):
        self.rrect([x, y, x + w, y + h], r=w // 2, fill=color)

    def card(self, box, fill=MANTLE, accent=None, r=18, inset=14):
        self.rrect(box, r=r, fill=fill)
        if accent:
            self.spine(box[0] + inset, box[1] + inset, box[3] - box[1] - inset * 2,
                       accent)

    def pill(self, x, y, label, fg, bg=SURFACE0, size=26, kind="semi", padx=18,
             h=44):
        w = self.tw(label, kind, size) + padx * 2
        self.rrect([x, y, x + w, y + h], r=h // 2, fill=bg)
        self.text((x + w / 2, y + h / 2), label, kind, size, fg, anchor="mm")
        return x + w

    def outline_pill(self, x, y, label, color, size=26, padx=20, h=48):
        w = self.tw(label, "semi", size) + padx * 2
        self.rrect([x, y, x + w, y + h], r=h // 2, fill=None,
                   outline=(*color, 190), width=2)
        self.text((x + w / 2, y + h / 2), label, "semi", size, color, anchor="mm")
        return x + w

    def solid_button(self, x, y, label, bg, fg=CRUST, size=28, padx=26, h=56):
        w = self.tw(label, "bold", size) + padx * 2
        self.rrect([x, y, x + w, y + h], r=h // 2, fill=bg)
        self.text((x + w / 2, y + h / 2), label, "bold", size, fg, anchor="mm")
        return x + w

    def avatar(self, cx, cy, r, initials, color):
        self.ellipse([cx - r, cy - r, cx + r, cy + r], fill=mix(color, CRUST, 0.62))
        self.ellipse([cx - r, cy - r, cx + r, cy + r], fill=None,
                     outline=(*color, 150), width=2)
        self.text((cx, cy + 1), initials, "bold", int(r * 0.95), color, anchor="mm")

    def dot(self, cx, cy, r, color):
        self.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

    def lock(self, x, y, color=OVERLAY, s=22):
        """Small padlock: shackle arc over a body."""
        bw, bh = s, s * 0.72
        self.rrect([x, y + s * 0.42, x + bw, y + s * 0.42 + bh], r=4, fill=color)
        self.arc([x + s * 0.16, y, x + bw - s * 0.16, y + s * 0.72],
                 180, 360, fill=color, width=3)

    def check(self, x, y, color=GREEN, s=22):
        self.line([x, y + s * 0.55, x + s * 0.36, y + s * 0.92,
                   x + s, y + s * 0.08], fill=color, width=4, joint="curve")

    def wrap(self, s, kind, size, maxw):
        words, lines, cur = s.split(), [], ""
        for word in words:
            trial = f"{cur} {word}".strip()
            if self.tw(trial, kind, size) <= maxw or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def para(self, x, y, s, kind, size, fill, maxw, lh=1.4, maxlines=None):
        lines = self.wrap(s, kind, size, maxw)
        if maxlines:
            lines = lines[:maxlines]
        for i, ln in enumerate(lines):
            self.text((x, y + i * size * lh), ln, kind, size, fill)
        return y + len(lines) * size * lh

    def ellipsize(self, s, kind, size, maxw):
        if self.tw(s, kind, size) <= maxw:
            return s
        while s and self.tw(s + "…", kind, size) > maxw:
            s = s[:-1]
        return s.rstrip() + "…"


# ========================================================= 1  timeline =======
APPS = {"Slack": MAUVE, "Telegram": SAPPHIRE, "Gmail": RED, "Discord": BLUE,
        "GitHub": OVERLAY, "Signal": TEAL}


def msg_timeline(out: Path) -> Path:
    c = C()
    c.rrect([0, 0, W, H], r=30, fill=CRUST)

    # ---- top bar
    c.text((48, 48), "Synapse", "bold", 40, WHITE)
    x = 48 + c.tw("Synapse", "bold", 40) + 16
    c.text((x, 52), "· Timeline", "medium", 34, OVERLAY)
    c.rrect([1180, 26, 2010, 92], r=33, fill=MANTLE)
    c.text((1216, 47), "Search people, projects, files", "regular", 28, OVERLAY)
    x = c.pill(2060, 32, "Triage: who is blocked", GREEN, mix(GREEN, CRUST, 0.82),
               size=26, h=54) + 14
    x = c.pill(x, 32, "12 muted", OVERLAY, MANTLE, size=26, h=54) + 14
    c.text((3072, 52), "14:22", "medium", 30, SUBTEXT, anchor="ra")
    c.line([0, 118, W, 118], fill=SURFACE0, width=2)

    # ---- sidebar
    c.rect([0, 118, 560, H], fill=MANTLE)
    c.text((48, 152), "ACCOUNTS", "bold", 24, OVERLAY)
    c.rrect([28, 196, 532, 262], r=16, fill=SURFACE0)
    c.text((48, 214), "All accounts", "semi", 32, WHITE)
    c.text((504, 216), "47", "semi", 30, SUBTEXT, anchor="ra")
    y = 286
    for name, count in [("Slack", 18), ("Telegram", 9), ("Gmail", 14),
                        ("Discord", 4), ("GitHub", 2)]:
        c.dot(56, y + 26, 9, APPS[name])
        c.text((84, y + 8), name, "medium", 30, SUBTEXT)
        c.text((504, y + 10), str(count), "medium", 28, OVERLAY, anchor="ra")
        y += 62
    c.line([28, y + 18, 532, y + 18], fill=SURFACE0, width=2)
    c.text((48, y + 46), "MODE", "bold", 24, OVERLAY)
    c.pill(48, y + 84, "ASSIST", TEAL, mix(TEAL, CRUST, 0.82), size=26, h=50)
    c.para(48, y + 152, "Drafts and proposes. Nothing sends without you.",
           "regular", 25, OVERLAY, 452, lh=1.35)

    def group(x, y, label, color, count):
        c.text((x, y), label, "bold", 25, color)
        c.text((x + c.tw(label, "bold", 25) + 14, y - 1), str(count), "bold", 25,
               OVERLAY)
        return y + 44

    def msg(x, y, w, h, accent, initials, name, app, when, body, tag=None,
            tagc=YELLOW):
        c.card([x, y, x + w, y + h], MANTLE, accent)
        c.avatar(x + 78, y + 56, 30, initials, accent)
        c.text((x + 124, y + 26), name, "semi", 33, WHITE)
        bx = x + 124 + c.tw(name, "semi", 33) + 16
        c.pill(bx, y + 24, app, APPS[app], mix(APPS[app], CRUST, 0.8), size=22,
               padx=13, h=36)
        c.text((x + w - 26, y + 28), when, "medium", 25, OVERLAY, anchor="ra")
        c.para(x + 124, y + 74, body, "regular", 27, SUBTEXT, w - 160, lh=1.32,
               maxlines=2)
        if tag:
            c.text((x + 124, y + h - 44), tag, "semi", 24, tagc)

    def row(x, y, w, h, initials, name, app, when, body, color, done=False):
        c.card([x, y, x + w, y + h], MANTLE, None)
        c.avatar(x + 52, y + h / 2, 24, initials, color)
        c.text((x + 92, y + 18), name, "semi", 29, SUBTEXT if not done else OVERLAY)
        bx = x + 92 + c.tw(name, "semi", 29) + 14
        c.dot(bx + 6, y + 32, 7, APPS[app])
        c.text((x + w - 24, y + 20), when, "medium", 23, OVERLAY, anchor="ra")
        if done:
            c.check(x + 92, y + 56, GREEN, 20)
            c.text((x + 124, y + 54), body, "regular", 25, OVERLAY)
        else:
            c.text((x + 92, y + 54), c.ellipsize(body, "regular", 25, w - 130),
                   "regular", 25, OVERLAY)

    colw = 1180
    ax, bx_ = 600, 1830

    y = group(ax, 152, "NEEDS YOUR REPLY", PEACH, 3)
    msg(ax, y, colw, 154, PEACH, "AM", "Arjun Mehta", "Telegram", "11:04",
        "Are we still on for Friday? Need to book the room today.",
        "waiting 2 days")
    msg(ax, y + 164, colw, 154, PEACH, "PL", "Priya Lal", "Slack", "09:41",
        "Can you sign off the perception schema before the review?",
        "deadline today", RED)
    msg(ax, y + 328, colw, 154, PEACH, "DK", "Dev Kaur", "Gmail", "Wed",
        "Invoice for the Q3 hardware order is attached and unpaid.",
        "3rd follow-up")

    y2 = group(ax, y + 516, "BLOCKING SOMEONE", RED, 1)
    msg(ax, y2, colw, 154, RED, "TS", "Tom Silva", "GitHub", "08:12",
        "PR #212 needs your review — two people are waiting on the merge.",
        "blocks 2 people", RED)

    y = group(bx_, 152, "FYI · NO ACTION NEEDED", SAPPHIRE, 12)
    rows = [("RN", "Rhea Nair", "Slack", "12:02",
             "standup notes posted in #platform", MAUVE),
            ("CI", "CI bot", "GitHub", "11:47",
             "build 4412 passed on main", OVERLAY),
            ("MG", "Maya Gomes", "Discord", "10:30",
             "shared a wallpaper for the theme", BLUE),
            ("NL", "Newsletter", "Gmail", "07:15",
             "Arch weekly — 3 packages you track", RED)]
    for i, (ini, nm, app, when, body, col) in enumerate(rows):
        row(bx_, y + i * 116, colw, 104, ini, nm, app, when, body, col)

    y3 = group(bx_, y + 490, "DRAFTED, AWAITING YOUR OK", GREEN, 2)
    for i, (ini, nm, app, when, body, col) in enumerate(
            [("AM", "Arjun Mehta", "Telegram", "now",
              "reply drafted in your voice", SAPPHIRE),
             ("PL", "Priya Lal", "Slack", "now",
              "sign-off drafted, schema attached", MAUVE)]):
        row(bx_, y3 + i * 116, colw, 104, ini, nm, app, when, body, col, done=True)

    c.text((bx_, y3 + 250), "Grouped by person and project, not by app or "
           "arrival time.", "regular", 25, OVERLAY)
    return c.save(out / "msg-timeline.png")


# ==================================================== 2  voice on desktop ====
def voice_desktop(out: Path) -> Path:
    c = C()
    # wallpaper gradient
    top, bot = (0x1A, 0x1B, 0x28), (0x2C, 0x2F, 0x46)
    for yy in range(H):
        c.d.rectangle([0, yy * SS, W * SS, (yy + 1) * SS],
                      fill=mix(top, bot, yy / H))
    # faint geometry
    for i in range(9):
        r = 300 + i * 165
        c.ellipse([W * 0.74 - r, H * 0.52 - r, W * 0.74 + r, H * 0.52 + r],
                  fill=None, outline=(*SURFACE0, 46), width=2)

    # ---- background windows
    def win(box, title, lines, mono=True):
        c.rrect(box, r=18, fill=CRUST)
        c.rrect([box[0], box[1], box[2], box[1] + 56], r=18, fill=MANTLE)
        c.rect([box[0], box[1] + 38, box[2], box[1] + 56], fill=MANTLE)
        for i, col in enumerate((RED, YELLOW, GREEN)):
            c.dot(box[0] + 30 + i * 26, box[1] + 28, 7, col)
        c.text((box[0] + 118, box[1] + 14), title, "medium", 26, SUBTEXT)
        yy = box[1] + 86
        for txt, col in lines:
            c.text((box[0] + 34, yy), txt, "mono" if mono else "regular", 24, col)
            yy += 38

    win([84, 176, 1180, 900], "Konsole — synapse-core",
        [("$ systemctl --user status synapse-core", SUBTEXT),
         ("● synapse-core.service", GREEN),
         ("   Active: active (running) 3h 12min", SUBTEXT),
         ("   Memory: 412.6M   Tasks: 18", OVERLAY),
         ("   User: ricky  (unprivileged)", OVERLAY),
         ("", TEXT),
         ("$ synapsectl caps list --active", SUBTEXT),
         ("telegram:dm/*      read     7d", TEAL),
         ("slack:channel/*    read     7d", TEAL),
         ("proc:*             throttle 24h", YELLOW),
         ("proc:*             kill     ask", PEACH),
         ("", TEXT),
         ("$ synapsectl why --last", SUBTEXT),
         ("  plan: 2 steps, 1 needs consent", MAUVE)])

    win([1960, 150, 3036, 792], "Kate — perception/schema.rs",
        [("pub struct Event {", MAUVE),
         ("    source:   Source,", SUBTEXT),
         ("    kind:     Kind,", SUBTEXT),
         ("    at:       Instant,", SUBTEXT),
         ("    subject:  EntityId,", SUBTEXT),
         ("    payload:  Sealed<Body>,", GREEN),
         ("    labels:   SensitivitySet,", YELLOW),
         ("}", MAUVE),
         ("", TEXT),
         ("// OTPs and keys never reach", OVERLAY),
         ("// the model context.", OVERLAY),
         ("impl Event {", MAUVE),
         ("    fn redact(&mut self) { .. }", SUBTEXT),
         ("}", MAUVE)])

    c.dim(126)

    # ---- top panel
    c.rect([0, 0, W, 66], fill=(*CRUST, 235))
    c.text((34, 18), "◈", "bold", 30, MAUVE)
    c.text((70, 20), "SynapseOS", "semi", 28, TEXT)
    x = 250
    for app, active in [("Konsole", False), ("Kate", True), ("Firefox", False)]:
        w = c.tw(app, "medium", 26) + 44
        if active:
            c.rrect([x, 12, x + w, 54], r=12, fill=SURFACE0)
        c.text((x + w / 2, 22), app, "medium", 26,
               TEXT if active else OVERLAY, anchor="ma")
        x += w + 12
    c.dot(2210, 33, 8, RED)
    c.text((2232, 20), "listening", "semi", 26, RED)
    c.pill(2360, 12, "ASSIST", TEAL, mix(TEAL, CRUST, 0.78), size=24, h=42)
    c.text((2560, 20), "72%", "medium", 26, SUBTEXT)
    c.text((2660, 20), "Thu 13 Aug   14:22", "medium", 26, SUBTEXT)
    c.text((3086, 20), "⌄", "medium", 26, OVERLAY, anchor="ra")

    # ---- overlay card
    ox, oy, ow, oh = 700, 214, 1720, 800
    c.rrect([ox + 8, oy + 12, ox + ow + 8, oy + oh + 12], r=34,
            fill=(0x10, 0x10, 0x18))
    c.rrect([ox, oy, ox + ow, oy + oh], r=34, fill=MANTLE)
    c.rrect([ox, oy, ox + ow, oy + oh], r=34, fill=None,
            outline=(*MAUVE, 120), width=2)

    # mic + waveform
    c.dot(ox + 74, oy + 66, 26, mix(MAUVE, CRUST, 0.7))
    c.rrect([ox + 68, oy + 52, ox + 80, oy + 74], r=6, fill=MAUVE)
    c.arc([ox + 60, oy + 58, ox + 88, oy + 84], 0, 180, fill=MAUVE, width=3)
    bx = ox + 124
    for i in range(46):
        amp = (math.sin(i * 0.62) * 0.5 + 0.5) * (0.35 + 0.65 * math.sin(i * 0.21) ** 2)
        hh = 8 + amp * 46
        col = mix(MAUVE, SAPPHIRE, i / 46)
        c.rrect([bx + i * 16, oy + 66 - hh / 2, bx + i * 16 + 8, oy + 66 + hh / 2],
                r=4, fill=col)
    c.text((ox + ow - 40, oy + 52), "0:04", "mono", 26, OVERLAY, anchor="ra")

    c.text((ox + 44, oy + 118), "YOU ASKED", "bold", 23, OVERLAY)
    c.text((ox + 44, oy + 152), "why is my laptop hot?", "bold", 52, WHITE)
    c.line([ox + 44, oy + 240, ox + ow - 44, oy + 240], fill=SURFACE0, width=2)

    yy = c.para(ox + 44, oy + 268,
                "chrome_crashpad_handler has held 182% CPU for 41 minutes — about "
                "18% of today's battery. It belongs to Chrome's crash reporter, "
                "not to any tab you have open.",
                "regular", 32, TEXT, ow - 88, lh=1.42)

    # plan box
    py = yy + 26
    c.rrect([ox + 44, py, ox + ow - 44, py + 176], r=20, fill=CRUST)
    c.text((ox + 70, py + 20), "PROPOSED PLAN · 2 STEPS", "bold", 22, MAUVE)
    for i, (num, txt, cap, col) in enumerate(
            [("1", "cgroup-throttle to a 25% ceiling", "proc:throttle · reversible",
              GREEN),
             ("2", "tell you if it climbs again", "notify · 1 hour", BLUE)]):
        ry = py + 58 + i * 54
        c.text((ox + 70, ry), num, "monob", 26, col)
        c.text((ox + 104, ry), txt, "medium", 28, TEXT)
        c.text((ox + ow - 70, ry + 2), cap, "mono", 23, OVERLAY, anchor="ra")

    # buttons
    by = py + 208
    x = c.solid_button(ox + 44, by, "Throttle it", GREEN, CRUST, 28) + 18
    x = c.outline_pill(x, by + 4, "Kill instead", RED, 27, h=48) + 18
    c.outline_pill(x, by + 4, "Not now", OVERLAY, 27, h=48)
    c.text((ox + ow - 44, by + 16), "Ctrl+Alt+S suspends everything",
           "medium", 24, OVERLAY, anchor="ra")
    return c.save(out / "voice-desktop.png")


# ====================================================== 3  process panel =====
def process_panel(out: Path) -> Path:
    c = C()
    c.rrect([0, 0, W, H], r=30, fill=CRUST)
    c.text((48, 40), "Processes", "bold", 42, WHITE)
    c.text((48 + c.tw("Processes", "bold", 42) + 18, 48),
           "· why is my laptop hot?", "medium", 34, OVERLAY)
    x = 2270
    x = c.pill(x, 40, "Live", GREEN, mix(GREEN, CRUST, 0.82), size=25, h=50) + 12
    x = c.pill(x, 40, "Protected set locked", RED, mix(RED, CRUST, 0.85),
               size=25, h=50) + 12
    c.pill(x, 40, "Audit on", MAUVE, mix(MAUVE, CRUST, 0.85), size=25, h=50)
    c.line([0, 118, W, 118], fill=SURFACE0, width=2)

    # ---- hero
    hx, hy, hw, hh = 48, 150, 2020, 244
    c.card([hx, hy, hx + hw, hy + hh], MANTLE, PEACH)
    c.text((hx + 46, hy + 28), "chrome_crashpad_handler", "monob", 40, WHITE)
    c.text((hx + 46 + c.tw("chrome_crashpad_handler", "monob", 40) + 20, hy + 36),
           "· pid 4417 · user ricky", "medium", 27, OVERLAY)
    for i, (val, lab, col) in enumerate([("182%", "CPU, sustained", PEACH),
                                         ("41 min", "held that level", YELLOW),
                                         ("≈18%", "of today's battery", RED),
                                         ("1.2 GB", "resident", SUBTEXT)]):
        cx = hx + 46 + i * 468
        c.text((cx, hy + 92), val, "bold", 46, col)
        c.text((cx, hy + 150), lab, "medium", 25, OVERLAY)
    c.text((hx + 46, hy + 196),
           "Chrome's crash reporter. Not attached to any tab you have open.",
           "regular", 27, SUBTEXT)

    # ---- sparkline
    sx, sy, sw, sh = 2100, 150, 972, 244
    c.card([sx, sy, sx + sw, sy + sh], MANTLE, None)
    c.text((sx + 30, sy + 22), "CPU · LAST 30 MIN", "bold", 22, OVERLAY)
    pts, n = [], 44
    for i in range(n):
        t = i / (n - 1)
        v = 0.12 + 0.1 * math.sin(i * 0.9)
        if t > 0.34:
            v = min(0.95, v + (t - 0.34) * 2.5)
        pts += [sx + 30 + t * (sw - 60), sy + sh - 40 - v * 130]
    c.d.polygon([v * SS for v in
                 pts + [sx + sw - 30, sy + sh - 40, sx + 30, sy + sh - 40]],
                fill=(*PEACH, 42))
    c.line(pts, fill=PEACH, width=4, joint="curve")
    c.line([sx + 30, sy + sh - 40, sx + sw - 30, sy + sh - 40], fill=SURFACE0,
           width=2)
    c.text((sx + 30, sy + sh - 32), "14:52", "mono", 21, OVERLAY)
    c.text((sx + sw - 30, sy + sh - 32), "now", "mono", 21, OVERLAY, anchor="ra")

    # ---- table
    ty = 434
    cols = [48, 1180, 1480, 1790, 2130]
    for label, cx in zip(["PROCESS", "CPU", "RAM", "BATTERY TODAY", "ACTION"],
                         cols):
        c.text((cx, ty), label, "bold", 23, OVERLAY)
    c.line([48, ty + 36, 3072, ty + 36], fill=SURFACE0, width=2)

    procs = [
        ("chrome_crashpad_handler", "pid 4417 · Chrome", "182%", "1.2 GB", "18%",
         PEACH, [("Throttle", GREEN), ("Kill", RED)], None),
        ("node (vite dev)", "pid 3901 · your dev server", "64%", "890 MB", "6%",
         YELLOW, [("Throttle", GREEN), ("Stop", YELLOW)], None),
        ("ollama serve", "pid 2210 · local model host", "41%", "5.4 GB", "4%",
         BLUE, [("Suspend", YELLOW)], None),
        ("kwin_wayland", "pid 1180 · display server", "6%", "320 MB", "1%",
         OVERLAY, None, "protected"),
        ("systemd", "pid 1 · init", "0.2%", "12 MB", "—",
         OVERLAY, None, "protected"),
        ("synapse-core", "pid 2044 · the assistant itself", "3%", "210 MB", "1%",
         OVERLAY, None, "protected (self)"),
    ]
    ry = ty + 50
    for name, sub, cpu, ram, batt, col, buttons, prot in procs:
        c.rrect([48, ry, 3072, ry + 98], r=14,
                fill=MANTLE if prot is None else mix(MANTLE, CRUST, 0.45))
        if prot is None:
            c.spine(62, ry + 16, 66, col)
        nc = WHITE if prot is None else OVERLAY
        c.text((cols[0] + 34, ry + 20), name, "monob", 30, nc)
        c.text((cols[0] + 34, ry + 60), sub, "regular", 24, OVERLAY)
        for val, cx in zip([cpu, ram, batt], cols[1:4]):
            c.text((cx, ry + 34), val, "semi", 30,
                   col if prot is None else OVERLAY)
        if buttons:
            bx = cols[4]
            for label, bc in buttons:
                bx = c.outline_pill(bx, ry + 24, label, bc, 25, padx=18, h=50) + 12
        else:
            c.lock(cols[4], ry + 34, OVERLAY, 24)
            c.text((cols[4] + 40, ry + 34), prot, "medium", 26, OVERLAY)
        ry += 108

    c.text((48, 1128),
           "Every action here spends a capability grant. Killing something with "
           "unsaved work needs an explicit override — throttle and suspend are "
           "offered first because they are reversible.",
           "regular", 25, OVERLAY)
    return c.save(out / "process-panel.png")


# ==================================================== 4  consent + audit =====
def consent_prompt(out: Path) -> Path:
    c = C()
    c.rrect([0, 0, W, H], r=30, fill=BASE)

    # ---------------- dialog
    dx, dy, dw, dh = 48, 48, 1700, 1104
    c.card([dx, dy, dx + dw, dy + dh], MANTLE, MAUVE, r=26, inset=20)
    c.text((dx + 60, dy + 44), "SYNAPSE NEEDS CONSENT", "bold", 24, MAUVE)
    c.text((dx + 60, dy + 84), "One effect, one confirmation", "bold", 44, WHITE)
    c.text((dx + 60, dy + 144), "Requested by you at 14:23 · ASSIST mode",
           "medium", 26, OVERLAY)

    # plain-words statement
    sy = dy + 196
    c.rrect([dx + 60, sy, dx + dw - 60, sy + 128], r=20, fill=CRUST)
    c.para(dx + 92, sy + 30,
           "Send this message to Arjun Mehta on Telegram now.",
           "semi", 36, TEXT, dw - 184, lh=1.3)

    # draft
    fy = sy + 156
    c.rrect([dx + 60, fy, dx + dw - 60, fy + 210], r=20, fill=CRUST)
    c.spine(dx + 84, fy + 22, 166, SAPPHIRE)
    c.text((dx + 116, fy + 24), "THE DRAFT", "bold", 22, SAPPHIRE)
    c.para(dx + 116, fy + 60,
           "“Friday works — 6pm at the usual place. I'll bring the deck so we "
           "can go through it together.”",
           "regular", 29, SUBTEXT, dw - 260, lh=1.38)
    c.text((dx + 116, fy + 164), "written in your voice · editable before sending",
           "medium", 23, OVERLAY)

    # capability tuple
    cy = fy + 244
    c.text((dx + 60, cy), "CAPABILITY REQUESTED", "bold", 23, OVERLAY)
    x = dx + 60
    for chipt in ["resource = telegram:dm/arjun", "verb = send", "ttl = once"]:
        x = c.pill(x, cy + 40, chipt, TEAL, SURFACE0, size=25, kind="mono",
                   padx=20, h=52) + 14
    c.text((dx + 60, cy + 112),
           "Not a category like “messaging access” — the exact effect, the exact "
           "scope, and how long it lasts.", "regular", 25, OVERLAY)

    # buttons
    by = cy + 186
    x = c.solid_button(dx + 60, by, "Allow once", GREEN, CRUST, 29, h=60) + 18
    x = c.outline_pill(x, by + 4, "Always for Arjun", BLUE, 27, h=52) + 18
    c.outline_pill(x, by + 4, "Deny", RED, 27, h=52)
    c.line([dx + 60, by + 96, dx + dw - 60, by + 96], fill=SURFACE0, width=2)
    c.lock(dx + 60, by + 124, OVERLAY, 24)
    c.text((dx + 100, by + 124),
           "The model never held the token. The broker signs and sends.",
           "medium", 25, OVERLAY)

    # ---------------- audit log
    ax, ay, aw, ah = 1796, 48, 1276, 1104
    c.card([ax, ay, ax + aw, ay + ah], MANTLE, None, r=26)
    c.text((ax + 40, ay + 40), "AUDIT LOG", "bold", 26, SUBTEXT)
    c.text((ax + 40 + c.tw("AUDIT LOG", "bold", 26) + 16, ay + 42),
           "· append-only", "medium", 24, OVERLAY)
    c.pill(ax + aw - 190, ay + 32, "exportable", OVERLAY, SURFACE0, size=22, h=44)
    c.line([ax + 40, ay + 92, ax + aw - 40, ay + 92], fill=SURFACE0, width=2)

    entries = [
        ("14:23:06", "consent", "pending → user", MAUVE, "this dialog"),
        ("14:23:05", "draft", "generated · not sent", GREEN, "no side effect"),
        ("14:23:05", "read", "telegram:dm/arjun", TEAL, "cap#7f21 · 7d"),
        ("14:23:04", "ask", "“reply to arjun about friday”", SUBTEXT, "you"),
        ("14:19:41", "throttle", "chrome_crashpad → 25%", YELLOW, "cap#3b90"),
        ("14:19:38", "consent", "allowed once", GREEN, "you"),
        ("14:02:11", "read", "slack:channel/platform", TEAL, "cap#7f0e · 7d"),
        ("13:58:02", "deny", "proc:kill kwin_wayland", RED, "protected set"),
        ("13:41:57", "sync", "perception paused 6 min", OVERLAY, "kill switch"),
    ]
    ry = ay + 112
    for i, (t, verb, detail, col, meta) in enumerate(entries):
        if i % 2 == 0:
            c.rrect([ax + 30, ry - 8, ax + aw - 30, ry + 92], r=12,
                    fill=mix(MANTLE, CRUST, 0.5))
        c.text((ax + 48, ry + 4), t, "mono", 24, OVERLAY)
        c.text((ax + 190, ry + 2), verb, "monob", 26, col)
        c.text((ax + 48, ry + 46),
               c.ellipsize(detail, "mono", 25, aw - 260), "mono", 25, SUBTEXT)
        c.text((ax + aw - 48, ry + 48), meta, "mono", 22, OVERLAY, anchor="ra")
        ry += 108

    c.text((ax + 40, ay + ah - 66),
           "Nothing above was sent. Every line is inspectable\nwithout special "
           "tooling.", "regular", 24, OVERLAY)
    return c.save(out / "consent-prompt.png")


# --------------------------------------------------------------------- main --
def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "assets/deck"
    for fn in (msg_timeline, voice_desktop, process_panel, consent_prompt):
        p = fn(out)
        print(f"wrote {p.relative_to(ROOT)}  "
              f"({p.stat().st_size // 1024} KB, {Image.open(p).size[0]}x"
              f"{Image.open(p).size[1]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
