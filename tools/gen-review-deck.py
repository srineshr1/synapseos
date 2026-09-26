#!/usr/bin/env python3
"""Build "SynapseOS - Project Review-1.pptx" on the MVSREC Project Review-1 template.

The template is a fully rasterised design: every card, rule, panel and arrow is a
picture-filled freeform exported at exactly 96 DPI. So instead of drawing
look-alike shapes, this script *clones the template's own primitives at their
native size* and lays new text over them. The result is pixel-identical chrome
with real project content.

Facts in this deck are taken from the working tree, not from memory:
  archiso/airootfs/usr/lib/synapseos/synapseos/   (19 tools, policy, planner)
  tests/test_synapseos.py                          (32 tests / 7 suites)
  archiso/packages.x86_64                          (293 packages)
  docs/GOAL.md                                     (v1 definition of done)

Usage:
    /tmp/pptx-venv/bin/python tools/gen-review-deck.py [-o OUT.pptx]
"""

from __future__ import annotations

import argparse
import copy
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls, qn
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "Project Review-1 Template.pptx"
DEFAULT_OUT = ROOT / "SynapseOS - Project Review-1.pptx"
FIG = ROOT / "docs" / "diagrams"

# ----------------------------------------------------------------------------
# palette + type, sampled from the template's own runs
# ----------------------------------------------------------------------------
NAVY = RGBColor(0x00, 0x1D, 0x54)      # body + titles
NAVY_D = RGBColor(0x00, 0x14, 0x3C)    # display headings
INK = RGBColor(0x1B, 0x33, 0x5C)       # long-form body copy
MUTED = RGBColor(0x53, 0x6E, 0x96)     # captions, secondary
ACCENT = RGBColor(0x75, 0xA9, 0xD6)    # eyebrow / numerals
ACCENT_L = RGBColor(0xA1, 0xC9, 0xEB)
ACCENT_B = RGBColor(0x2E, 0x6F, 0xB0)  # emphasis
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GOOD = RGBColor(0x1E, 0x7A, 0x55)      # DONE pills
WARN = RGBColor(0xA8, 0x6A, 0x14)      # PLANNED pills

HEAD = "DM Sans Bold"
BODY = "DM Sans"

# grid, in inches (matches the template exactly)
EYEBROW_Y = 1.88
TITLE_Y = 2.28
RULE_Y = 3.46
CONTENT_Y = 3.98
FOOT_Y = 10.58

COL_X = (1.19, 7.14, 12.85)            # 6-card grid columns
CARD_W = (5.72, 5.73, 5.96)
ROW_Y = (3.98, 7.26)
NUM_X = (1.19, 10.23)                  # numbered-row grid
NUM_Y = (3.98, 6.09, 8.20)
TABLE_X, TABLE_W = 0.95, 18.10
TABLE_H = 5.86

# template assets: name -> (1-based donor slide, shape name). Cloned at native size.
ASSETS = {
    # chrome
    "bg2": (2, "Freeform 2"), "bg3": (3, "Freeform 2"), "bg4": (4, "Freeform 2"),
    "bg5": (5, "Freeform 2"), "bg6": (6, "Freeform 2"), "bg7": (7, "Freeform 2"),
    "bg8": (8, "Freeform 2"),
    "band": (3, "Freeform 3"), "band_full": (4, "Freeform 3"),
    "leftbar": (3, "Freeform 6"), "leftbar8": (8, "Freeform 6"),
    "rule": (3, "Freeform 8"), "rule_thin": (2, "Freeform 8"),
    "rule_wide": (5, "Freeform 8"),
    "corner_bl": (3, "Freeform 22"), "corner_bl2": (5, "Freeform 11"),
    "corner_bl3": (7, "Freeform 34"), "corner_bl4": (2, "Freeform 13"),
    "corner_br": (3, "Freeform 19"), "corner_br2": (6, "Freeform 32"),
    # 6-card grid (row 1 then row 2, left to right)
    "card_a": (3, "Freeform 9"), "card_b": (3, "Freeform 11"), "card_c": (3, "Freeform 13"),
    "card_d": (3, "Freeform 15"), "card_e": (3, "Freeform 17"), "card_f": (3, "Freeform 20"),
    # numbered rows 8.58 x ~1.89
    "row_a": (4, "Freeform 8"), "row_b": (4, "Freeform 12"), "row_c": (4, "Freeform 16"),
    "row_d": (4, "Freeform 20"), "row_e": (4, "Freeform 24"), "row_f": (4, "Freeform 28"),
    # 5-row badge list
    "badge_s": (6, "Freeform 8"), "badge_l": (6, "Freeform 12"),
    "badge_l2": (6, "Freeform 17"), "badge_l3": (6, "Freeform 22"),
    "badge_s2": (6, "Freeform 27"),
    "list_s": (6, "Freeform 10"), "list_l": (6, "Freeform 14"),
    "list_l2": (6, "Freeform 19"), "list_l3": (6, "Freeform 24"),
    "list_s2": (6, "Freeform 29"),
    # panels + art
    "panel_abs": (2, "Freeform 9"), "art_tall": (2, "Freeform 11"),
    "art_blue": (6, "Freeform 31"),
    "ref_left": (8, "Freeform 9"), "ref_right": (8, "Freeform 10"),
    "div1": (8, "Freeform 11"), "div2": (8, "Freeform 14"), "div3": (8, "Freeform 17"),
    "div4": (8, "Freeform 20"), "div5": (8, "Freeform 23"), "div6": (8, "Freeform 26"),
    "div7": (8, "Freeform 29"),
    # architecture composition (slide 7)
    "arch_frame": (7, "Freeform 8"),
    "arch_n1": (7, "Freeform 9"), "arch_n2": (7, "Freeform 12"),
    "arch_n3": (7, "Freeform 14"), "arch_n4": (7, "Freeform 20"),
    "arch_n5": (7, "Freeform 23"), "arch_n6": (7, "Freeform 17"),
    "arch_n7": (7, "Freeform 28"),
    "arch_a1": (7, "Freeform 11"), "arch_a2": (7, "Freeform 13"),
    "arch_a3": (7, "Freeform 19"), "arch_a4": (7, "Freeform 22"),
    "arch_a5": (7, "Freeform 25"), "arch_a6": (7, "Freeform 16"),
    "arch_a7": (7, "Freeform 26"), "arch_a8": (7, "Freeform 27"),
    "arch_a9": (7, "Freeform 30"),
    "arch_legend": (7, "Freeform 31"), "arch_lrule": (7, "Freeform 33"),
}

REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# ----------------------------------------------------------------------------
# type metrics: measured from the installed DM Sans so layout can be checked
# ----------------------------------------------------------------------------
FONT_FILES = {
    False: Path.home() / ".local/share/fonts/dm-sans/DMSans-Regular.ttf",
    True: Path.home() / ".local/share/fonts/dm-sans/DMSansBold-Regular.ttf",
}
LINE_FACTOR = 1.34          # DM Sans win ascent+descent / upem, with slack
_FONT_CACHE: dict = {}


def _face(bold: bool):
    if bold in _FONT_CACHE:
        return _FONT_CACHE[bold]
    face = None
    try:
        from fontTools.ttLib import TTFont
        path = FONT_FILES[bold]
        if path.exists():
            tt = TTFont(str(path))
            upem = tt["head"].unitsPerEm
            cmap = tt.getBestCmap()
            hmtx = tt["hmtx"]
            widths = {}
            for code, name in cmap.items():
                try:
                    widths[chr(code)] = hmtx[name][0] / upem
                except KeyError:
                    pass
            face = (widths, hmtx[".notdef"][0] / upem if ".notdef" in hmtx else 0.55)
    except Exception:
        face = None
    _FONT_CACHE[bold] = face
    return face


def text_width(text: str, size: float, bold: bool) -> float:
    """Advance width of a single line, in inches."""
    face = _face(bold)
    if face is None:                                    # heuristic fallback
        return len(text) * size * 0.0072
    widths, fallback = face
    em = sum(widths.get(ch, fallback) for ch in text)
    return em * size / 72.0


def wrapped_lines(text: str, size: float, bold: bool, box_w: float) -> int:
    """Greedy word wrap count for a paragraph inside box_w inches.

    Uses 97% of the nominal width: kerning, hinting and the renderer's own
    rounding make borderline lines flip, and it is always safer to predict the
    extra line than to lay out on top of something.
    """
    if not text:
        return 1
    limit = box_w * 0.97
    lines, cur = 1, ""
    for word in text.split(" "):
        trial = word if not cur else f"{cur} {word}"
        if text_width(trial, size, bold) <= limit or not cur:
            cur = trial
        else:
            lines += 1
            cur = word
    return lines


def fit_size(text: str, box_w: float, start: float, *, bold=True,
             min_size=28.0, step=1.0, max_lines=2) -> tuple[float, int]:
    """Largest size <= start whose wrapped height stays within max_lines."""
    size = start
    while size > min_size:
        if wrapped_lines(text, size, bold, box_w) <= max_lines:
            break
        size -= step
    return size, wrapped_lines(text, size, bold, box_w)


# ----------------------------------------------------------------------------
# low-level pptx helpers
# ----------------------------------------------------------------------------
def remap_rels(src_part, dst_part, element) -> None:
    """Re-point every r:id/r:embed in a copied element at dst_part's own rels."""
    for el in element.iter():
        for attr, val in list(el.attrib.items()):
            if not attr.startswith("{%s}" % REL_NS):
                continue
            try:
                rel = src_part.rels[val]
            except KeyError:
                continue
            if rel.is_external:
                new = dst_part.relate_to(rel.target_ref, rel.reltype, is_external=True)
            else:
                new = dst_part.relate_to(rel.target_part, rel.reltype)
            el.set(attr, new)


def blank_slide(prs):
    """A slide on the template's Blank layout with no inherited placeholders."""
    slide = prs.slides.add_slide(prs.slide_masters[0].slide_layouts[6])
    for shape in list(slide.shapes):
        shape._element.getparent().remove(shape._element)
    return slide


def delete_slide(prs, slide) -> None:
    lst = prs.slides._sldIdLst
    idx = list(prs.slides).index(slide)
    sldId = list(lst)[idx]
    prs.part.drop_rel(sldId.get(qn("r:id")))
    lst.remove(sldId)


def reorder(prs, order) -> None:
    """order: list of slide objects in the desired sequence."""
    lst = prs.slides._sldIdLst
    current = list(prs.slides)
    ids = list(lst)
    by_slide = {id(s): ids[i] for i, s in enumerate(current)}
    for sldId in ids:
        lst.remove(sldId)
    for s in order:
        lst.append(by_slide[id(s)])


def set_borders(cell, color="C9DDF0", pt=0.75, edges="LRTB") -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    tags = ["a:lnL", "a:lnR", "a:lnT", "a:lnB"]
    for tag in tags:
        for el in tcPr.findall(qn(tag)):
            tcPr.remove(el)
    emu = int(Pt(pt))
    for tag in reversed(tags):
        if tag[-1] not in edges:
            continue
        tcPr.insert(0, parse_xml(
            f'<{tag} {nsdecls("a")} w="{emu}" cap="flat" cmpd="sng" algn="ctr">'
            f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
            f'<a:prstDash val="solid"/></{tag}>'))


# ----------------------------------------------------------------------------
# deck builder
# ----------------------------------------------------------------------------
class Deck:
    def __init__(self, template: Path):
        self.prs = Presentation(str(template))
        self.tpl_slides = list(self.prs.slides)
        self.built: list = []
        self.checks: list = []
        self._assets = {}
        for key, (si, name) in ASSETS.items():
            src = self.tpl_slides[si - 1]
            match = [sh for sh in src.shapes if sh.name == name]
            if not match:
                raise KeyError(f"template asset {key} ({name} on slide {si}) not found")
            self._assets[key] = (src, match[0])

    # -- asset cloning -------------------------------------------------------
    def place(self, slide, key, x=None, y=None, w=None, h=None):
        src_slide, shape = self._assets[key]
        el = copy.deepcopy(shape._element)
        slide.shapes._spTree.append(el)
        remap_rels(src_slide.part, slide.part, el)
        new = slide.shapes[-1]
        new.name = f"{key}-{len(slide.shapes)}"
        if x is not None:
            new.left = Inches(x)
        if y is not None:
            new.top = Inches(y)
        if w is not None:
            new.width = Inches(w)
        if h is not None:
            new.height = Inches(h)
        return new

    # -- text ----------------------------------------------------------------
    def text(self, slide, x, y, w, h, lines, *, size=17, bold=False, color=INK,
             font=None, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=1.16,
             space_after=0, space_before=0, wrap=True, tag=""):
        """lines: str | list[str] | list[dict(text=..., size=..., bold=..., ...)]"""
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = wrap
        tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        items = [lines] if isinstance(lines, (str, dict)) else list(lines)
        est = 0.0
        for i, item in enumerate(items):
            spec = {"text": item} if isinstance(item, str) else dict(item)
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            para.alignment = spec.get("align", align)
            sp = spec.get("spacing", spacing)
            para.line_spacing = sp
            before = spec.get("space_before", space_before if i else 0)
            after = spec.get("space_after", space_after) if i < len(items) - 1 else 0
            if before:
                para.space_before = Pt(before)
            if after:
                para.space_after = Pt(after)
            run = para.add_run()
            run.text = spec["text"]
            f = run.font
            psize = spec.get("size", size)
            pbold = spec.get("bold", bold)
            f.size = Pt(psize)
            f.bold = pbold
            f.name = spec.get("font", font) or (HEAD if pbold else BODY)
            f.color.rgb = spec.get("color", color)
            nlines = wrapped_lines(spec["text"], psize, pbold, w) if wrap else 1
            est += nlines * psize * LINE_FACTOR * sp / 72.0
            est += (before + after) / 72.0
        self.checks.append((len(self.built) + 1, tag or spec["text"][:34], est, h))
        return box

    # -- reusable slide furniture -------------------------------------------
    def chrome(self, *, bg="bg3", band="band", leftbar=False,
               corner_bl="corner_bl", corner_br="corner_br"):
        slide = blank_slide(self.prs)
        self.place(slide, bg, 0, 0)
        self.place(slide, band)
        if leftbar:
            self.place(slide, "leftbar")
        if corner_bl:
            self.place(slide, corner_bl)
        if corner_br:
            self.place(slide, corner_br)
        # letterhead
        self.text(slide, 6.20, 0.30, 7.60, 0.62, "MVSR ENGINEERING COLLEGE",
                  size=31.5, bold=True, color=NAVY, align=PP_ALIGN.CENTER,
                  spacing=1.0, tag="letterhead")
        self.text(slide, 6.20, 0.92, 7.60, 0.40,
                  "Department of Computer Science & Engineering",
                  size=18.8, color=NAVY, align=PP_ALIGN.CENTER, spacing=1.0,
                  tag="letterhead-sub")
        self.built.append(slide)
        return slide

    def head(self, slide, eyebrow, title, *, lead=None, title_size=56,
             rule="rule", title_w=None):
        """Auto-fits the title so it never collides with the lead column."""
        if title_w is None:
            title_w = 10.10 if lead else 13.60
        self.text(slide, 1.19, EYEBROW_Y, 12.0, 0.34, eyebrow,
                  size=13, bold=True, color=ACCENT, tag="eyebrow")
        forced = title.split("\n")
        budget = CONTENT_Y - TITLE_Y - 0.06          # 1.64in of title space
        size = title_size
        while size > 26:
            nlines = sum(wrapped_lines(seg, size, True, title_w) for seg in forced)
            if nlines * size * LINE_FACTOR / 72.0 <= budget:
                break
            size -= 1
        line_h = size * LINE_FACTOR / 72.0
        self.text(slide, 1.19, TITLE_Y, title_w, max(nlines * line_h, 1.05),
                  title, size=size, bold=True, color=NAVY_D, spacing=1.0,
                  tag="title")
        if nlines >= 2:
            # a two-line title fills the rule's row, so use a vertical accent
            # bar instead — the same treatment the template uses on slide 1
            self.rect(slide, 0.95, TITLE_Y + 0.05, 0.055,
                      nlines * line_h - 0.12, fill="75A9D6")
        elif rule:
            self.place(slide, rule, 1.19, RULE_Y)
        if lead:
            self.text(slide, 11.50, 2.40, 7.31, 1.42, lead, size=18.5,
                      color=MUTED, spacing=1.20, tag="lead")

    def foot(self, slide, n, total):
        self.text(slide, 1.19, FOOT_Y, 12.0, 0.30,
                  "SynapseOS  ·  Capstone Project Work-1  ·  Batch 15  ·  MVSREC",
                  size=12, bold=True, color=MUTED)
        self.text(slide, 16.31, FOOT_Y, 2.50, 0.30, f"{n:02d} / {total:02d}",
                  size=12, bold=True, color=ACCENT, align=PP_ALIGN.RIGHT)

    # -- composite layouts ---------------------------------------------------
    def cards6(self, slide, cards):
        """cards: 6 x (title, [bullet, ...])"""
        keys = ("card_a", "card_b", "card_c", "card_d", "card_e", "card_f")
        for i, (title, bullets) in enumerate(cards):
            r, c = divmod(i, 3)
            x, y, w = COL_X[c], ROW_Y[r], CARD_W[c]
            self.place(slide, keys[i], x, y)
            self.text(slide, x + 0.30, y + 0.28, w - 0.56, 0.44, title,
                      size=19, bold=True, color=NAVY, spacing=1.0,
                      tag="card-title")
            self.text(slide, x + 0.30, y + 0.86, w - 0.58, 2.00,
                      [{"text": b, "space_after": 5} for b in bullets],
                      size=14.5, color=INK, spacing=1.12, tag="card-body")

    def rows6(self, slide, rows, *, num_color=NAVY):
        """rows: 6 x (num, title, body). Column-major like the template."""
        keys = ("row_a", "row_c", "row_e", "row_b", "row_d", "row_f")
        for i, (num, title, body) in enumerate(rows):
            c, r = divmod(i, 3)
            x, y = NUM_X[c], NUM_Y[r]
            self.place(slide, keys[i], x, y)
            self.text(slide, x + 0.40, y + 0.42, 1.20, 1.00, num,
                      size=44, bold=True, color=num_color, align=PP_ALIGN.CENTER,
                      anchor=MSO_ANCHOR.MIDDLE, spacing=1.0)
            self.text(slide, x + 2.42, y + 0.30, 5.70, 0.44, title,
                      size=21, bold=True, color=NAVY, spacing=1.0, tag="row-title")
            self.text(slide, x + 2.42, y + 0.80, 5.86, 0.98, body,
                      size=14.5, color=INK, spacing=1.12, tag="row-body")

    def list5(self, slide, items, *, width=9.77, x=1.19, text_w=None):
        """items: 5 x (num, headline, detail). Uses the template's badge rows."""
        geom = [("badge_s", "list_s", 3.98, 1.18),
                ("badge_l", "list_l", 5.16, 1.41),
                ("badge_l2", "list_l2", 6.32, 1.42),
                ("badge_l3", "list_l3", 7.50, 1.41),
                ("badge_s2", "list_s2", 8.91, 1.18)]
        tw = text_w if text_w is not None else width - 0.85
        for (bk, lk, y, h), (num, headline, detail) in zip(geom, items):
            self.place(slide, bk, x, y)
            self.place(slide, lk, x + 1.19, y)
            self.text(slide, x + 0.19, y, 1.06, h, num, size=32, bold=True,
                      color=NAVY, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
                      tag="badge")
            body = [{"text": headline, "size": 18, "bold": True, "color": NAVY,
                     "space_after": 3}]
            if detail:
                body.append({"text": detail, "size": 14, "color": INK})
            self.text(slide, x + 1.62, y + 0.08, tw, h - 0.16, body,
                      anchor=MSO_ANCHOR.MIDDLE, spacing=1.10, tag="listrow")

    def table(self, slide, cols, rows, *, x=TABLE_X, y=CONTENT_Y, w=TABLE_W,
              h=TABLE_H, head_size=15, body_size=14, head_h=0.62,
              zebra=("FFFFFF", "F5F9FD")):
        """cols: [(label, width_in), ...]  rows: [[cell, ...], ...]"""
        shape = slide.shapes.add_table(len(rows) + 1, len(cols),
                                       Inches(x), Inches(y), Inches(w), Inches(h))
        tbl = shape.table
        tbl.first_row = False
        tbl.horz_banding = False
        for i, (_, cw) in enumerate(cols):
            tbl.columns[i].width = Inches(cw)
        tbl.rows[0].height = Inches(head_h)
        body_h = (h - head_h) / max(len(rows), 1)
        for r in range(1, len(rows) + 1):
            tbl.rows[r].height = Inches(body_h)

        def fill(cell, hexcolor):
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string(hexcolor)

        def put(cell, text, *, size, bold, color, align=PP_ALIGN.LEFT):
            cell.margin_left = cell.margin_right = Inches(0.14)
            cell.margin_top = cell.margin_bottom = Inches(0.07)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            para = tf.paragraphs[0]
            para.alignment = align
            para.line_spacing = 1.10
            run = para.add_run()
            run.text = text
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.name = HEAD if bold else BODY
            run.font.color.rgb = color

        for i, (label, _) in enumerate(cols):
            cell = tbl.cell(0, i)
            fill(cell, "DCE9F7")
            put(cell, label, size=head_size, bold=True, color=NAVY,
                align=PP_ALIGN.CENTER if i == 0 else PP_ALIGN.LEFT)
            set_borders(cell, "B7D2EC", 0.9)
        for r, row in enumerate(rows, start=1):
            for c, val in enumerate(row):
                cell = tbl.cell(r, c)
                fill(cell, zebra[(r - 1) % len(zebra)])
                bold = c == 0
                put(cell, str(val), size=body_size, bold=bold,
                    color=ACCENT_B if bold else INK,
                    align=PP_ALIGN.CENTER if c == 0 else PP_ALIGN.LEFT)
                set_borders(cell, "C9DDF0", 0.75)
        return tbl

    def figure(self, slide, png, *, x, y, h, notes=None, notes_x=None,
               notes_w=5.6, caption=None):
        from PIL import Image
        with Image.open(png) as im:
            ratio = im.width / im.height
        w = h * ratio
        slide.shapes.add_picture(str(png), Inches(x), Inches(y),
                                 Inches(w), Inches(h))
        if caption:
            self.text(slide, x, y + h + 0.14, w + 2.0, 0.28, caption,
                      size=13, bold=True, color=MUTED, tag="fig-caption")
        if notes:
            nx = notes_x if notes_x is not None else x + w + 0.70
            body = [{"text": "HOW TO READ IT", "size": 13, "bold": True,
                     "color": ACCENT, "space_after": 12}]
            for headline, detail in notes:
                body.append({"text": headline, "size": 16.5, "bold": True,
                             "color": NAVY, "space_after": 3})
                body.append({"text": detail, "size": 14, "color": INK,
                             "space_after": 13})
            self.text(slide, nx, y + 0.04, notes_w, h, body, spacing=1.12,
                      tag="fig-notes")
        return w

    def pill(self, slide, x, y, text, *, fill="E4F1E8", color=GOOD, w=1.30,
             h=0.30, size=12.5):
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x),
                                       Inches(y), Inches(w), Inches(h))
        shape.adjustments[0] = 0.5
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(fill)
        shape.line.fill.background()
        shape.shadow.inherit = False
        tf = shape.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.word_wrap = False
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        para = tf.paragraphs[0]
        para.alignment = PP_ALIGN.CENTER
        run = para.add_run()
        run.text = text
        run.font.size = Pt(size)
        run.font.bold = True
        run.font.name = HEAD
        run.font.color.rgb = color
        return shape

    def rect(self, slide, x, y, w, h, *, fill=None, line=None, lw=0.75,
             radius=None, shape_type=MSO_SHAPE.RECTANGLE):
        shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y),
                                       Inches(w), Inches(h))
        if radius is not None and shape_type == MSO_SHAPE.ROUNDED_RECTANGLE:
            shape.adjustments[0] = radius
        if fill:
            shape.fill.solid()
            shape.fill.fore_color.rgb = RGBColor.from_string(fill)
        else:
            shape.fill.background()
        if line:
            shape.line.color.rgb = RGBColor.from_string(line)
            shape.line.width = Pt(lw)
        else:
            shape.line.fill.background()
        shape.shadow.inherit = False
        shape.text_frame.text = ""
        return shape


# ============================================================================
# content
# ============================================================================
TEAM = [("Siluveru Vashishta", "2451-23-751-010"),
        ("Rudraksha Srinesh", "2451-23-751-020"),
        ("Beernelli Vishnu", "2451-23-751-021")]

ABSTRACT = (
    "SynapseOS is an Arch Linux desktop distribution in which the assistant is a "
    "first-class operating-system service rather than an application. One "
    "unprivileged user-space daemon, synapse-core, perceives the live session — "
    "windows, application groups, the process table, battery, load and thermals — "
    "and acts on it through nineteen typed tools gated by a policy the user owns.\n"
    "The governing rule is that the language model never touches the machine. It "
    "receives a compact snapshot of the session and may only name a tool and its "
    "arguments; every effect is produced by local code after the policy engine has "
    "approved it. sudo, su, pkexec and doas are refused outright, PID 1 and the "
    "compositor are structurally unkillable, and every ask, tool call and consent "
    "decision is appended to a readable JSON-lines audit log.\n"
    "Three modes bound behaviour. Observe is read-only. Assist, the default, runs "
    "safe verbs at once but demands a plain-language confirmation before closing, "
    "throttling or killing anything. Act is opt-in per capability and still "
    "confirms shell execution.\n"
    "The deliverable is a bootable, fully offline ISO with an installer, the "
    "Caelestia desktop and the assistant bound to Super+S. The ISO is the vehicle; "
    "the assistant is the product."
)

AGENDA = [
    ("01", "Problem and objectives",
     "Why a tab-bound assistant is blind, and the six things v1 must let a "
     "stranger do in ten minutes."),
    ("02", "Scope and boundaries",
     "What is in the image, what the daemon may touch, and the three things this "
     "project deliberately is not."),
    ("03", "Literature survey",
     "Ten works across agent operating systems, computer-use agents and prompt-"
     "injection defence, with the gap each leaves open."),
    ("04", "Proposed system and architecture",
     "Session service, typed tools, policy gate and audit log — plus Figures 4.1 "
     "and 4.2 from the running code."),
    ("05", "Design models",
     "Use case, class and sequence diagrams generated from the synapseos package, "
     "not drawn by hand."),
    ("06", "Status, validation and plan",
     "What works today, 32 unit tests across 7 suites, project metrics, milestones "
     "and risks."),
]

PROBLEM = [
    ("The assistant lives in a tab", [
        "·  It runs in a browser or an editor, so its",
        "    world ends at the tab boundary.",
        "·  It cannot enumerate windows or read /proc.",
        "·  Every session starts with no memory of",
        "    the machine it is running on."]),
    ("The human is the integration layer", [
        "·  Copy, paste, screenshot, re-explain, repeat.",
        "·  Every task begins by rebuilding state the",
        "    OS already tracks.",
        "·  That cost is paid per question, forever."]),
    ("Perception exists and is unused", [
        "·  CPU, RSS, elapsed time, focus, battery and",
        "    thermals are readable by any process.",
        "·  No reasoning layer consumes them as input.",
        "·  \"Why is my laptop hot?\" is answerable —",
        "    and still unanswered."]),
    ("Advice, never action", [
        "·  An assistant can describe how to throttle",
        "    a runaway build. It cannot do it.",
        "·  There is no typed, auditable path from an",
        "    intent to a session effect.",
        "·  The user is still the one who acts."]),
    ("The unsafe shortcut is a shell", [
        "·  A root shell makes a model capable and",
        "    unaccountable in one step.",
        "·  Prompt injection then becomes privilege",
        "    escalation.",
        "·  Window titles are attacker-controlled."]),
    ("Nothing is inspectable", [
        "·  When an agent does act, there is rarely a",
        "    record of what it proposed.",
        "·  No append-only trail of what was allowed",
        "    and what actually ran.",
        "·  Without a log, trust is a feeling."]),
]

OBJECTIVES = [
    ("01", "Perceive the live session",
     "Read windows, application groups, the process table, battery, load and "
     "thermals from OS sources and expose one compact snapshot, refreshed every 2 s."),
    ("02", "Act only through typed tools",
     "Nineteen typed OS tools across apps, windows, browser, process, system, "
     "files, shell and policy. The model names a tool; local code performs the effect."),
    ("03", "Gate every effect with policy",
     "Modes observe, assist and act. Confirm close, throttle, kill and shell_run in "
     "plain language. Protect PID 1, the compositor and the core itself."),
    ("04", "Keep the assistant unprivileged",
     "No root shell, ever. Refuse sudo, su, pkexec, doas and the password "
     "utilities. System verbs go through named methods, never run_as_root."),
    ("05", "Make every action auditable",
     "Append an immutable JSON-lines record of each ask, tool call, consent "
     "decision and mode change. Readable with one command and no special tooling."),
    ("06", "Ship an installable ISO",
     "One offline, self-contained Arch image: Caelestia desktop, Calamares "
     "installer, assistant enabled with the graphical session, Super+S out of the box."),
]

SCOPE = [
    ("Problem / Domain Covered", [
        "·  OS-level assistance on a Linux desktop",
        "·  Session perception: windows, apps, processes",
        "·  Capability-gated action with human consent",
        "·  Distribution engineering: ISO and installer"]),
    ("System Boundaries", [
        "·  One unprivileged daemon per graphical session",
        "·  UNIX-socket JSON-RPC; no network listener",
        "·  Session verbs only; no kernel changes",
        "·  The model holds no state about the machine"]),
    ("Target Users", [
        "·  Desktop users who want a session copilot",
        "·  Developers running heavy toolchains",
        "·  Reviewers who need an auditable trail",
        "·  Coding agents attaching over MCP"]),
    ("Major Functionalities", [
        "·  Ask what is running, and for how long",
        "·  Launch, focus and close apps by name",
        "·  Explain, throttle or kill a process",
        "·  Open files and URLs; notify the desktop",
        "·  Read status, switch mode, pause at once"]),
    ("In-Scope Components", [
        "·  archiso profile, 293 packages, Calamares",
        "·  core, overlay, synapsectl, MCP server",
        "·  Planner, Policy, ToolBroker, Sampler, audit",
        "·  32 unit tests across 7 suites"]),
    ("Out-of-Scope Components", [
        "·  A Linux kernel or scheduler fork",
        "·  A GPU-multiplexing agent runtime (AIOS)",
        "·  Messaging connectors (Product B)",
        "·  Root-privileged administration",
        "·  Screen-pixel GUI automation"]),
]

LIT_COLS = [("#", 0.70), ("Work  (author, year, arXiv)", 4.45), ("Focus", 2.55),
            ("Key contribution", 5.20), ("Gap this project addresses", 5.20)]

LIT_A = [
    ["1", "Mei et al., 2024 — AIOS: LLM Agent Operating System (arXiv:2403.16971)",
     "Agent runtime as an OS kernel",
     "Isolates LLM services — scheduling, context, memory, storage and access "
     "control — into an AIOS kernel that serves many concurrent agents.",
     "Schedules agents, not a desktop session. It does not enumerate windows or "
     "stop a runaway process on a real machine."],
    ["2", "Ge et al., 2023 — LLM as OS, Agents as Apps (arXiv:2312.03815)",
     "Vision and ecosystem",
     "Frames the LLM as an operating system and agents as its applications; sets "
     "the AIOS-Agent research agenda.",
     "Conceptual. No policy engine, no consent surface and no bootable image to "
     "hand to a stranger."],
    ["3", "Hu et al., 2025 — OS Agents: a survey of agents for computing devices "
     "(arXiv:2508.04482)",
     "Survey of OS and GUI agents",
     "Taxonomy of construction, evaluation and benchmarks for agents that operate "
     "computers; names safety and privacy as open problems.",
     "Surveyed systems drive pixels and GUIs. Safety is future work rather than a "
     "property of the architecture."],
    ["4", "Zhang et al., 2024 — LLM-Brained GUI Agents: a survey (arXiv:2411.18279)",
     "GUI automation",
     "Reviews perception-to-action pipelines that interpret screenshots and "
     "synthesise clicks and keystrokes.",
     "Screen scraping is brittle and unauditable; there is no typed contract "
     "between an intent and its effect."],
    ["5", "Sager et al., 2025 — A comprehensive survey of agents for computer use "
     "(arXiv:2501.16150)",
     "Computer-use agents",
     "Foundations, challenges and future directions for computer-use agents "
     "across desktop, mobile and web.",
     "Identifies reliability and safety gaps but offers no OS-level capability "
     "gate or protected process set."],
]

LIT_B = [
    ["6", "Beurer-Kellner et al., 2025 — Design patterns for securing LLM agents "
     "against prompt injections (arXiv:2506.08837)",
     "Agent security patterns",
     "Six patterns — action-selector, plan-then-execute, dual LLM and others — "
     "that constrain an agent so injected text cannot escalate.",
     "Adopted directly: plan-then-execute plus a typed action selector, with the "
     "gate outside the model."],
    ["7", "Ferrag et al., 2025 — From prompt injections to protocol exploits "
     "(arXiv:2506.23260)",
     "Function-calling and MCP threats",
     "Threat taxonomy for tool-calling and Model Context Protocol workflows, "
     "including tool poisoning and protocol abuse.",
     "Motivates treating window titles, file contents and page text as data and "
     "never as instructions."],
    ["8", "Zheng et al., 2025 — Towards Agentic OS: an LLM agent framework for "
     "Linux schedulers (arXiv:2509.01245)",
     "Agents inside the OS",
     "SchedCP lets an agent tune kernel schedulers behind a verification "
     "boundary that validates every change.",
     "Confirms the pattern at kernel level; this work applies it to session "
     "verbs a desktop user actually asks for."],
    ["9", "Yao et al., 2022 — ReAct: synergizing reasoning and acting in language "
     "models (arXiv:2210.03629)",
     "Reason-act loops",
     "Interleaves reasoning traces with actions so a model can plan, observe a "
     "result and revise.",
     "Basis of the bounded plan/act loop in planner.py, capped at MAX_STEPS = 8 "
     "with a refreshable snapshot."],
    ["10", "Schick et al., 2023 — Toolformer: language models can teach "
     "themselves to use tools (arXiv:2302.04761)",
     "Learned tool use",
     "Shows that models can learn when and how to call external APIs from "
     "self-supervised data.",
     "Establishes typed tool calls as the interface; this work supplies the "
     "OS-side contract and the gate."],
]

GAP_COLS = [("Criterion", 4.00), ("Assistant in a browser tab", 3.45),
            ("Computer-use / GUI agent", 3.55), ("AIOS-class agent runtime", 3.50),
            ("SynapseOS (this work)", 3.60)]
GAP_ROWS = [
    ["Sees the live session", "No — tab scope only",
     "Partly — screenshots and accessibility trees",
     "No — sees agents, not the desktop",
     "Yes — /proc, app groups, windows, sensors every 2 s"],
    ["How it acts", "It does not act; it advises",
     "Synthesises clicks and keystrokes",
     "Schedules agent calls and tool invocations",
     "19 typed tools; local code performs every effect"],
    ["Privilege held by the model", "None, and no reach",
     "Whatever the desktop session has",
     "Framework-defined access control",
     "None — sudo, su, pkexec and doas are refused"],
    ["Destructive action control", "Not applicable",
     "Usually none; clicks are irreversible",
     "Kernel-style access control per agent",
     "Plain-language consent; throttle preferred over kill"],
    ["Protected from itself", "Not applicable", "No protected set",
     "Resource isolation between agents",
     "PID 1, compositor, shell and core are unkillable"],
    ["Auditability", "Chat history only", "Screen recordings at best",
     "Framework logs, agent-facing",
     "Append-only JSON-lines log of ask, tool, consent, mode"],
    ["Delivered as", "A web page", "A Python package or extension",
     "A research framework",
     "A bootable offline ISO with an installer"],
]

PROPOSED = [
    ("01", "One core, many clients",
     "synapse-core is a systemd --user unit. The overlay, synapsectl and the MCP "
     "server are clients of one UNIX socket. Apps do not each ship an "
     "assistant."),
    ("02", "Perception is first-class",
     "Sampler.tick() reads /proc every 2 s, rolls PIDs into application groups, "
     "lists windows via hyprctl and keeps first-seen timestamps in SQLite."),
    ("03", "The model only names a tool",
     "The planner sends the snapshot plus 19 tool specifications to grok-4.6 and "
     "runs a function-calling loop capped at MAX_STEPS = 8. It never gets a shell."),
    ("04", "Policy is the gate, not the prompt",
     "Every call passes Policy.check before ToolBroker dispatches it. Refusals are "
     "structural — mode, protected set, grants — not a matter of phrasing."),
    ("05", "Consent names one concrete effect",
     "The prompt states the effect — \"send SIGTERM to pid 4417, "
     "chrome_crashpad_handler\" — not a category. Pending consent expires "
     "in 300 s."),
    ("06", "The ISO is the vehicle",
     "One offline image carries the desktop, toolchains, three coding agents, the "
     "assistant and an installer that copies the live rootfs to disk."),
]

ARCH_NODES = [
    ("arch_n1", 0.71, 4.69, 1.92, 1.88, "Desktop\nUser", "Super+S · voice · CLI"),
    ("arch_n2", 3.09, 4.69, 2.39, 1.88, "Interaction\nClients", "overlay · synapsectl · MCP"),
    ("arch_n3", 5.71, 4.69, 2.40, 1.88, "synapse-core", "user unit · UNIX socket"),
    ("arch_n4", 8.80, 4.69, 2.40, 1.88, "Planner", "function-calling loop"),
    ("arch_n5", 11.67, 4.69, 2.15, 1.88, "SpaceXAI", "grok-4.6 · external"),
    ("arch_n6", 5.71, 7.73, 2.40, 1.65, "Perception", "/proc · hyprctl · SQLite"),
    ("arch_n7", 9.52, 7.73, 2.39, 1.65, "Policy ·\nToolBroker", "gate · 19 typed tools"),
]

TRUST = [
    ("OBSERVE  —  read-only", [
        "·  Only the 8 read tools resolve.",
        "·  Every mutating tool is denied outright.",
        "·  Safe to hand to a machine you do not own.",
        "·  policy_set_mode is the one way out."]),
    ("ASSIST  —  the everyday mode", [
        "·  The default on first boot.",
        "·  6 auto tools run at once: launch, focus,",
        "    open URL, navigate, notify, open file.",
        "·  5 confirm tools ask first: close, throttle,",
        "    kill, shell_run, set mode."]),
    ("ACT  —  opt-in, per capability", [
        "·  Approved patterns run inside their grant.",
        "·  shell_run is in ALWAYS_CONFIRM, so it",
        "    still asks in act mode.",
        "·  Grants are session-scoped; a pending",
        "    consent expires after 300 s."]),
    ("No root, ever", [
        "·  tools.py refuses sudo, su, pkexec, doas,",
        "    passwd, chpasswd, visudo, newgrp and sg.",
        "·  shell_run takes argv, never a shell string.",
        "·  System verbs will use named polkit methods,",
        "    not run_as_root."]),
    ("A structural protected set", [
        "·  PID 1 and the core's own PID can never be",
        "    signalled.",
        "·  Hyprland, Quickshell, greetd, PipeWire,",
        "    dbus and the keyring are protected.",
        "·  Enforced in Policy, not by prompt wording."]),
    ("External text is data", [
        "·  Window titles, files, notifications and",
        "    page text are quoted as data.",
        "·  No tool call may originate from that text.",
        "·  Ctrl+Alt+S pauses everything, and the",
        "    overlay shows that it is paused."]),
]

TOOL_COLS = [("#", 0.70), ("Group", 2.55), ("Typed tools", 7.35),
            ("Effect", 3.75), ("Gate in assist mode", 3.75)]
TOOL_ROWS = [
    ["5", "Applications",
     "apps_list · apps_running · apps_launch · apps_focus · apps_close",
     "Enumerate .desktop entries, group running PIDs, launch, focus, close",
     "Read, launch and focus are free; apps_close confirms"],
    ["1", "Windows", "windows_list",
     "Window titles and the focused window via hyprctl",
     "Read-only — always free"],
    ["3", "Browser", "browser_open · browser_navigate · browser_tabs",
     "Open a URL, navigate the active window, list open tabs",
     "Free; URLs are normalised before dispatch"],
    ["4", "Process", "proc_list · proc_explain · proc_throttle · proc_kill",
     "Rank by CPU or RSS, explain a PID, cgroup cpu.max, SIGTERM",
     "Throttle and kill always confirm; protected set denied"],
    ["1", "System", "sys_status",
     "Load, memory, battery, thermals and the current mode",
     "Read-only — always free"],
    ["2", "Notify and files", "notify_send · files_open",
     "Desktop notification; open a path with its registered handler",
     "Free; paths are resolved and confined"],
    ["1", "Shell", "shell_run",
     "Run argv with no shell, refusing the privilege binaries",
     "In ALWAYS_CONFIRM — asks in every mode, act included"],
    ["2", "Policy", "policy_status · policy_set_mode",
     "Report mode, pending consents and grants; change the mode",
     "Status is free; changing the mode confirms"],
]

STACK = [
    ("Base and image", [
        "·  Arch Linux · archiso 88 · squashfs + xz",
        "·  293 requested packages, resolved offline",
        "·  Calamares, vendored, offline unpack",
        "·  BIOS syslinux + UEFI GRUB boot paths"]),
    ("Desktop session", [
        "·  Caelestia — Hyprland + Quickshell",
        "·  greetd / tuigreet, PipeWire audio",
        "·  Super+S binds the assistant overlay",
        "·  Ctrl+Alt+S is the kill switch"]),
    ("Core service", [
        "·  Python package, ~4,050 lines",
        "·  systemd --user unit, unprivileged",
        "·  JSON-RPC over a UNIX socket",
        "·  Clients: overlay, synapsectl, MCP"]),
    ("Planner", [
        "·  SpaceXAI grok-4.6, Responses API",
        "·  Function calling over 19 tool specs",
        "·  MAX_STEPS = 8, refreshable snapshot",
        "·  No key means no cloud call, and no",
        "    pretending one succeeded"]),
    ("Perception", [
        "·  /proc and /sys sampled every 2 s",
        "·  cgroup v2 cpu.max for throttling",
        "·  hyprctl for windows, xdg for handlers",
        "·  SQLite keeps first-seen timestamps"]),
    ("Tooling and quality", [
        "·  32 unit tests, 7 suites, unittest",
        "·  check-packages.py pre-flights the list",
        "·  18 AUR packages staged in a local repo",
        "·  5 UML figures from the source tree"]),
]

STATUS = [
    ("01", "Ask what is running, and for how long",
     "Sampler groups /proc into AppGroup objects with elapsed time from btime. "
     "synapsectl apps and the overlay both read it. DONE."),
    ("02", "Launch, focus and close applications by name",
     "gtk-launch and xdg-open for launch, hyprctl dispatch for focus and close. "
     "Launch and focus run without a prompt in assist. DONE."),
    ("03", "Explain, throttle or kill a runaway process",
     "proc_explain names the owner; proc_throttle writes cgroup v2 cpu.max; "
     "proc_kill sends SIGTERM after a confirm. Protected set denied. DONE."),
    ("04", "Pause the assistant and see that it is paused",
     "Ctrl+Alt+S sets the paused flag; Policy then denies every mutating tool and "
     "the overlay renders the paused state. DONE."),
    ("05", "Toggle Wi-Fi, volume, brightness and sleep",
     "sys_status reads this state but cannot change it. The named polkit helper is "
     "the next milestone. PLANNED — not in this build."),
]

DONE_V1 = [
    ("01", "Truthful session state",
     "Ask what is running and for how long, and get the answer from /proc rather "
     "than from a guess.  Status: done."),
    ("02", "Consent before damage",
     "Kill or throttle a runaway app after a plain-language confirmation naming the "
     "exact PID.  Status: done."),
    ("03", "Apps by name",
     "Launch, focus and close applications without knowing a desktop id.  "
     "Status: done."),
    ("04", "System toggles",
     "Wi-Fi, volume, brightness and sleep. sys_status reads them; a polkit helper "
     "with named methods will set them.  Status: planned."),
    ("05", "An instant kill switch",
     "Ctrl+Alt+S pauses the assistant and the overlay shows the paused state.  "
     "Status: done."),
    ("06", "A readable audit log",
     "Append-only JSON lines covering ask, tool, consent and mode. One command, no "
     "special tooling.  Status: done."),
]

TEST_COLS = [("#", 0.70), ("Suite", 3.60), ("What it locks down", 8.00),
             ("Why it matters to the review", 5.80)]
TEST_ROWS = [
    ["6", "ProcTests",
     "/proc/stat parsing with spaces in comm, btime-derived elapsed time, cmdline "
     "decoding, cgroup-derived desktop id, duration formatting",
     "\"For how long\" must be true; a mis-parsed comm would mislabel a process"],
    ["1", "AppTests", "Desktop-entry parsing into launchable application records",
     "Launch by name only works if .desktop files resolve correctly"],
    ["4", "PolicyTests",
     "observe blocks launch, assist demands consent for kill, the protected set "
     "is rejected, and the protected predicate matches by comm and prefix",
     "This is the security claim of the project, asserted as executable tests"],
    ["2", "SamplerTests",
     "Elapsed time for a running group, and that a shared cgroup does not merge "
     "unrelated binaries into one app",
     "Children inherit the terminal's scope; merging them would report nonsense"],
    ["6", "McpTests",
     "Tool listing and dispatch over the stdio MCP server, string-argv rejection, "
     "and that sudo is blocked at the MCP boundary too",
     "Coding agents attach here, so the same gate must hold on that path"],
    ["1", "ConfigTests", "Defaults, mode validation and 0600 key-file handling",
     "An invalid mode must fall back to assist, never to act"],
    ["12", "DesktopConfigTests",
     "Caelestia and Hyprland defaults in /etc/skel: keybinds, autostart, the "
     "Super+S bind and the Ctrl+Alt+S pause bind",
     "The assistant is only \"in the OS\" if the session actually binds it"],
]

METRICS = [
    ("4,050", [
        "lines of Python in the package",
        "",
        "·  tools.py 556 · overlay.py 516 · server.py 431",
        "·  policy.py 317 · perception/ 1,246"]),
    ("19 / 3", [
        "typed OS tools, three gate classes",
        "",
        "·  8 read tools, free in every mode",
        "·  6 auto tools, free in assist",
        "·  5 confirm tools, one always confirming"]),
    ("32 / 7", [
        "unit tests, seven suites, all pass",
        "",
        "·  python3 -m unittest discover -s tests",
        "·  Policy, MCP and desktop config covered"]),
    ("293", [
        "packages in the live image",
        "",
        "·  C/C++, Rust, Go, Java, Python, Node",
        "·  three coding agents, Docker, editors",
        "·  18 AUR packages staged locally"]),
    ("5", [
        "UML figures from the source tree",
        "",
        "·  system architecture, assistant runtime",
        "·  use case, class and sequence",
        "·  SVG plus 2x PNG, one command"]),
    ("1", [
        "offline ISO, installable end to end",
        "",
        "·  Calamares copies the live rootfs",
        "·  BIOS and UEFI boot paths validated",
        "·  assistant enabled with the session"]),
]

PLAN = [
    ("Requirement study and problem framing", 0.0, 1.5, "done"),
    ("Base ISO, installer and boot paths", 1.0, 1.0, "done"),
    ("Desktop migration to Caelestia", 1.35, 0.6, "done"),
    ("Perception layer and typed tool broker", 1.30, 0.95, "done"),
    ("Policy, consent surface and audit log", 1.60, 0.80, "done"),
    ("Overlay, synapsectl and MCP server", 1.70, 0.85, "done"),
    ("Unit tests and UML documentation", 2.00, 0.80, "now"),
    ("Named polkit helper for system verbs", 2.90, 1.40, "plan"),
    ("Scheduler: time and event routines", 4.00, 1.50, "plan"),
    ("Hardening, signed image, evaluation", 5.20, 2.00, "plan"),
]
PLAN_MONTHS = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar",
               "Apr", "May"]
PLAN_TODAY = 2.33          # 10 Sep 2026

RISK_COLS = [("Risk", 4.60), ("Why it is credible", 5.40),
             ("Mitigation in this build", 5.60), ("Residual", 2.50)]
RISK_ROWS = [
    ["Prompt injection through session text",
     "Window titles, page text and file contents are attacker-controlled and land "
     "in the planner's context.",
     "External text is quoted as data; no tool call may originate from it; "
     "destructive verbs need consent.",
     "Medium — needs an evaluation harness"],
    ["A hallucinated destructive call",
     "The model can name proc_kill with a plausible but wrong PID.",
     "Policy checks the protected set, consent names the exact PID and comm, and "
     "throttle is offered before kill.",
     "Low"],
    ["Privilege escalation via the shell tool",
     "shell_run is the widest surface in the tool set.",
     "argv only, never a shell string; nine privilege binaries refused; "
     "ALWAYS_CONFIRM even in act mode.",
     "Low"],
    ["Cloud dependency and key handling",
     "The planner calls an external LLM; a leaked XAI_API_KEY is a real cost and "
     "privacy problem.",
     "Key file is 0600, environment preferred, and with no key the overlay still "
     "reports local state instead of faking a call.",
     "Medium — local model routing is future work"],
    ["Live image exhausts RAM or stalls on SATA",
     "A ~5 GB squashfs copied to RAM on an 8 GB laptop invites the OOM killer.",
     "copytoram=n by default, cow_spacesize=1G, libata.force=noncq and "
     "systemd.gpt_auto=no on the live entry.",
     "Low"],
    ["Known-credentials rescue account",
     "postinstall.sh creates rescue/rescue with sudo so a forgotten password does "
     "not mean reinstalling.",
     "Documented as an intentional backdoor, printed in /etc/motd at every login, "
     "with removal commands.",
     "High until removed by the user"],
]

FUTURE = [
    ("01", "Named system verbs over polkit",
     "Wi-Fi, packages, power and brightness as named polkit methods with their own "
     "consent text — never run_as_root. This closes objective 4."),
    ("02", "Scheduler for routines",
     "\"At 17:30 close the work apps.\" A systemd timer per routine, with the same "
     "policy gate. Drawn as PLANNED in Figure 4.1, not claimed as working."),
    ("03", "Local model routing",
     "Triage and classification on-device, escalating to the cloud per task. "
     "Removes the network from the common path."),
    ("04", "Evaluation harness for injection",
     "A corpus of hostile window titles and pages, scored on whether any tool call "
     "escapes the gate. Turns a security claim into a measurement."),
    ("05", "Product B — connectors",
     "Messaging and mail connectors behind an identity broker the model never "
     "reads. Starts only after Product A is a daily driver."),
    ("06", "Reproducible, signed images",
     "Pinned package sets, a signed local repo and published checksums, so an ISO "
     "can be rebuilt and verified rather than trusted."),
]

REFS_A = [
    ("Mei, K., Zhu, X., Xu, W., et al.",
     "AIOS: LLM Agent Operating System. arXiv:2403.16971, 2024."),
    ("Ge, Y., Ren, Y., Hua, W., et al.",
     "LLM as OS, Agents as Apps: Envisioning AIOS, Agents and the AIOS-Agent "
     "Ecosystem. arXiv:2312.03815, 2023."),
    ("Hu, X., Xiong, T., Yi, B., et al.",
     "OS Agents: A Survey on MLLM-based Agents for General Computing Devices Use. "
     "arXiv:2508.04482, 2025."),
    ("Zhang, C., He, S., Qian, J., et al.",
     "Large Language Model-Brained GUI Agents: A Survey. arXiv:2411.18279, 2024."),
    ("Sager, P. J., Meyer, B., Yan, C., et al.",
     "A Comprehensive Survey of Agents for Computer Use. arXiv:2501.16150, 2025."),
    ("Beurer-Kellner, L., Debenedetti, E., Dobos, D., et al.",
     "Design Patterns for Securing LLM Agents against Prompt Injections. "
     "arXiv:2506.08837, 2025."),
    ("Ferrag, M. A., Tihanyi, N., Debbah, M., et al.",
     "From Prompt Injections to Protocol Exploits: Threats in LLM-Powered AI "
     "Agent Workflows. arXiv:2506.23260, 2025."),
    ("Zheng, Y., Yu, T., Wei, Y., et al.",
     "Towards Agentic OS: An LLM Agent Framework for Linux Schedulers. "
     "arXiv:2509.01245, 2025."),
]

REFS_B = [
    ("Yao, S., Zhao, J., Yu, D., et al.",
     "ReAct: Synergizing Reasoning and Acting in Language Models. "
     "arXiv:2210.03629, 2022 (ICLR 2023)."),
    ("Schick, T., Dwivedi-Yu, J., Dessì, R., et al.",
     "Toolformer: Language Models Can Teach Themselves to Use Tools. "
     "arXiv:2302.04761, 2023."),
    ("Saltzer, J. H., and Schroeder, M. D.",
     "The Protection of Information in Computer Systems. Proc. IEEE 63(9), 1975."),
    ("Anthropic",
     "Model Context Protocol specification. modelcontextprotocol.io, 2024 — the "
     "stdio transport used by synapseos-mcp."),
    ("Arch Linux and freedesktop.org",
     "archiso, systemd user units, cgroups v2, the Desktop Entry Specification "
     "and the XDG Base Directory Specification."),
    ("Caelestia, Hyprland and Calamares projects",
     "Quickshell desktop dotfiles, the Wayland compositor and the "
     "distribution-independent installer framework."),
]


# ============================================================================
# slide construction
# ============================================================================
def build_title(deck: Deck):
    slide = deck.tpl_slides[0]
    by = {sh.name: sh for sh in slide.shapes}

    def retext(name, lines, *, size=None, bold=None, color=None):
        sh = by[name]
        tf = sh.text_frame
        first = tf.paragraphs[0]
        proto = first.runs[0] if first.runs else None
        base_size = proto.font.size if proto is not None else Pt(20)
        base_bold = proto.font.bold if proto is not None else False
        base_font = proto.font.name if proto is not None else BODY
        base_color = NAVY
        try:
            if proto is not None and proto.font.color.type is not None:
                base_color = proto.font.color.rgb
        except Exception:
            pass
        tf.clear()
        for i, line in enumerate(lines):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            para.line_spacing = 1.06
            run = para.add_run()
            run.text = line
            run.font.size = Pt(size) if size else base_size
            run.font.bold = base_bold if bold is None else bold
            run.font.name = base_font
            run.font.color.rgb = color or base_color

    by["TextBox 7"].top = Inches(2.62)
    by["TextBox 7"].height = Inches(1.62)
    retext("TextBox 7", ["SynapseOS"], size=86)

    deck.text(slide, 1.82, 4.32, 11.60, 0.46,
              "An Arch Linux desktop with the assistant as a first-class OS service",
              size=21, bold=True, color=ACCENT_B, tag="s1-tagline")

    by["TextBox 10"].width = Inches(7.60)
    retext("TextBox 10", ["2026-27   ·   Batch 15   ·   B.E. CSE"], size=27)

    by["TextBox 12"].width = Inches(6.40)
    retext("TextBox 12", [f"{name}  —  {roll}" for name, roll in TEAM])

    guide = by["TextBox 15"]
    guide.left = Inches(14.20)
    guide.top = Inches(6.56)
    guide.width = Inches(5.00)
    guide.height = Inches(1.30)
    retext("TextBox 15", ["Guide", "T. Lakshmi",
                          "Assistant Professor, Dept. of CSE"])
    tf = guide.text_frame
    tf.word_wrap = True
    for para, (size, bold, color, before) in zip(
            tf.paragraphs, [(13.5, True, ACCENT, 0), (25.0, True, NAVY_D, 4),
                            (15.5, False, MUTED, 3)]):
        para.alignment = PP_ALIGN.RIGHT
        para.line_spacing = 1.06
        if before:
            para.space_before = Pt(before)
        run = para.runs[0]
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        run.font.name = HEAD if bold else BODY

    by["TextBox 5"].left = Inches(6.20)
    by["TextBox 5"].width = Inches(7.60)
    retext("TextBox 5", ["Department of Computer Science & Engineering"])
    by["TextBox 5"].text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    return slide


def build_thanks(deck: Deck, total: int):
    slide = deck.tpl_slides[8]
    by = {sh.name: sh for sh in slide.shapes}

    lead = by["TextBox 12"]
    lead.top = Inches(5.92)
    lead.width = Inches(7.00)
    lead.height = Inches(1.10)
    tf = lead.text_frame
    tf.word_wrap = True
    tf.clear()
    para = tf.paragraphs[0]
    para.line_spacing = 1.10
    run = para.add_run()
    run.text = "The assistant should live in the OS, not in a tab."
    run.font.size = Pt(30.5)
    run.font.bold = True
    run.font.name = HEAD
    run.font.color.rgb = NAVY_D

    deck.text(slide, 1.62, 7.14, 7.44, 0.76, [
        {"text": "Siluveru Vashishta   ·   Rudraksha Srinesh   ·   "
                 "Beernelli Vishnu", "space_after": 4},
        {"text": "Guide  ·  T. Lakshmi, Assistant Professor, Dept. of CSE"},
    ], size=15, color=MUTED, spacing=1.10, tag="thanks-team")

    by["TextBox 13"].top = Inches(8.20)
    by["TextBox 14"].top = Inches(8.82)
    deck.text(slide, 1.62, 9.56, 7.20, 0.34,
              "github.com/srineshr1/synapseos   ·   synapseaios.web.app",
              size=15.5, bold=True, color=ACCENT_B, tag="thanks-links")

    letter = by["TextBox 5"]
    letter.left = Inches(6.20)
    letter.width = Inches(7.60)
    ltf = letter.text_frame
    ltf.clear()
    lp = ltf.paragraphs[0]
    lp.alignment = PP_ALIGN.CENTER
    lrun = lp.add_run()
    lrun.text = "Department of Computer Science & Engineering"
    lrun.font.size = Pt(18.8)
    lrun.font.name = BODY
    lrun.font.color.rgb = NAVY

    deck.text(slide, 1.62, 10.30, 7.60, 0.30, f"{total:02d} / {total:02d}",
              size=12, bold=True, color=ACCENT, tag="thanks-page")
    return slide


def build(out: Path) -> Path:
    deck = Deck(TEMPLATE)
    total = 29

    title = build_title(deck)

    # 02 — agenda ------------------------------------------------------------
    s = deck.chrome(bg="bg4", band="band_full", corner_bl="corner_bl",
                    corner_br="corner_br")
    deck.head(s, "02  —  CONTENTS", "What this review covers",
              lead="Six blocks. Problem and objectives first, then the design "
                   "models generated from the code, then an honest status report.")
    deck.rows6(s, AGENDA)

    # 03 — abstract ----------------------------------------------------------
    s = deck.chrome(bg="bg2", leftbar=True, corner_bl="corner_bl4",
                    corner_br=None)
    deck.head(s, "03  —  ABSTRACT", "Project Abstract", rule="rule_thin")
    deck.place(s, "art_tall", 12.38, 2.57)
    deck.place(s, "panel_abs", 1.19, 4.22)
    paras = ABSTRACT.split("\n")
    deck.text(s, 1.62, 4.52, 10.32, 5.12,
              [{"text": p, "space_after": 7} for p in paras],
              size=15, color=INK, spacing=1.04, tag="abstract")
    deck.text(s, 12.90, 9.98, 5.40, 0.30, "approx. 215 words",
              size=13, bold=True, color=MUTED, align=PP_ALIGN.RIGHT)

    # 04 — problem -----------------------------------------------------------
    s = deck.chrome(bg="bg3", leftbar=True)
    deck.head(s, "04  —  PROBLEM STATEMENT",
              "The smartest thing on the machine is also the most blind",
              title_size=44, title_w=12.20)
    deck.cards6(s, PROBLEM)

    # 05 — objectives --------------------------------------------------------
    s = deck.chrome(bg="bg4", band="band_full")
    deck.head(s, "05  —  OBJECTIVES", "Project Objectives",
              lead="Objectives 1, 2, 3, 5 and 6 are implemented and tested. "
                   "Objective 4 is the one open milestone, and it is marked as "
                   "such throughout this deck.")
    deck.rows6(s, OBJECTIVES)

    # 06 — scope -------------------------------------------------------------
    s = deck.chrome(bg="bg3", leftbar=True)
    deck.head(s, "06  —  SCOPE", "Project Scope",
              lead="What the image contains, what the daemon may touch, and the "
                   "four things this project deliberately is not.")
    deck.cards6(s, SCOPE)

    # 07 / 08 — literature survey -------------------------------------------
    s = deck.chrome(bg="bg5", leftbar=True, corner_bl="corner_bl2")
    deck.head(s, "07  —  LITERATURE SURVEY", "Literature Survey",
              rule="rule_wide",
              lead="Ten works, grouped by what they solve. The last column is the "
                   "gap that motivates this project.")
    deck.table(s, LIT_COLS, LIT_A, head_size=15, body_size=13.5)
    deck.text(s, TABLE_X, 9.98, 12.0, 0.30,
              "Papers 1–5 of 10  ·  agent operating systems and computer-use agents",
              size=13, bold=True, color=MUTED)

    s = deck.chrome(bg="bg5", leftbar=True, corner_bl="corner_bl2")
    deck.head(s, "08  —  LITERATURE SURVEY", "Literature Survey — Continued",
              title_size=46, rule="rule_wide",
              lead="Security patterns and tool-use foundations. These five rows "
                   "are the ones the implementation follows most directly.")
    deck.table(s, LIT_COLS, LIT_B, head_size=15, body_size=13.5)
    deck.text(s, TABLE_X, 9.98, 12.0, 0.30,
              "Papers 6–10 of 10  ·  prompt-injection defence, agentic OS, tool use",
              size=13, bold=True, color=MUTED)

    # 09 — research gap ------------------------------------------------------
    s = deck.chrome(bg="bg8", leftbar="leftbar", corner_bl="corner_bl2")
    deck.head(s, "09  —  RESEARCH GAP", "Existing approaches vs this work",
              title_size=46, rule="rule_wide",
              lead="The gap is not intelligence. It is a typed, gated, auditable "
                   "path from an intent to a session effect.")
    deck.table(s, GAP_COLS, GAP_ROWS, head_size=14.5, body_size=13.5)

    # 10 — proposed system ---------------------------------------------------
    s = deck.chrome(bg="bg4", band="band_full")
    deck.head(s, "10  —  PROPOSED SYSTEM",
              "Put the assistant inside the OS",
              title_size=56)
    deck.rows6(s, PROPOSED)

    # 11 — proposed architecture (template diagram, relabelled) -------------
    s = deck.chrome(bg="bg7", corner_bl="corner_bl3", corner_br=None)
    deck.head(s, "11  —  PROPOSED ARCHITECTURE", "Proposed Architecture",
              lead="One request, end to end. The model occupies exactly one "
                   "segment of this diagram.")
    deck.place(s, "arch_frame", 2.85, 3.51)
    for key in ("arch_a1", "arch_a2", "arch_a3", "arch_a4", "arch_a5", "arch_a6",
                "arch_a7", "arch_a8", "arch_a9"):
        deck.place(s, key)
    for key, x, y, w, h, label, sub in ARCH_NODES:
        deck.place(s, key, x, y)
        lines = [{"text": line, "size": 18.5, "bold": True, "color": NAVY,
                  "align": PP_ALIGN.CENTER, "spacing": 1.06}
                 for line in label.split("\n")]
        lines.append({"text": sub, "size": 11.5, "color": MUTED,
                      "align": PP_ALIGN.CENTER, "space_before": 6})
        deck.text(s, x + 0.10, y, w - 0.20, h, lines,
                  anchor=MSO_ANCHOR.MIDDLE)
    deck.place(s, "arch_legend", 14.76, 3.75)
    deck.place(s, "arch_lrule", 15.23, 4.69)
    deck.text(s, 15.23, 4.12, 3.90, 0.46, "Diagram Legend",
              size=20, bold=True, color=NAVY, spacing=1.0, tag="legend-title")
    deck.text(s, 15.23, 5.14, 3.86, 4.66, [
        {"text": "Solid arrows are the request path: user to client to core to "
                 "planner to model.", "space_after": 13},
        {"text": "The dashed return is the proposed tool call, arriving as a "
                 "function_call.", "space_after": 13},
        {"text": "Everything below the core is local. SpaceXAI never reads /proc "
                 "and never gets a shell.", "space_after": 13},
        {"text": "Policy sits between proposal and effect, so a refusal costs "
                 "nothing.", "space_after": 13},
        {"text": "Figure 4.1 gives the full layered view.", "color": MUTED},
    ], size=14, color=INK, spacing=1.10, tag="legend-body")

    # 12–16 — the five generated figures ------------------------------------
    figures = [
        ("12  —  SYSTEM ARCHITECTURE", "System Architecture",
         "Figure 4.1  ·  system-architecture.svg  ·  generated from the source tree",
         "system-architecture.png", 5.86, 1.19, [
             ("Five bands, one direction",
              "Interaction clients sit on synapse-core; the core sits on the "
              "desktop session, userspace and the kernel. Nothing reaches past "
              "its own band."),
             ("The core is one process",
              "synapse-core.service is a systemd --user unit: one instance per "
              "graphical session, no root, one UNIX socket."),
             ("Planner, Policy, ToolBroker, Sampler",
              "Four collaborators inside the core. Only ToolBroker produces "
              "effects, and only after Policy has agreed."),
             ("Amber dashes are not shipped",
              "The scheduler and the polkit helper are drawn PLANNED. They are "
              "not in this build and are not claimed as working software."),
         ]),
        ("13  —  ASSISTANT RUNTIME", "Assistant Runtime",
         "Figure 4.2  ·  the model proposes, policy decides, local code acts",
         "assistant-architecture.png", 5.86, 1.19, [
             ("Numbered path, left to right",
              "Client, transport, Core.handle, planner, model. The request is a "
              "line, not a mesh."),
             ("The local execution path",
              "Everything under the band runs on the machine: ToolBroker, "
              "Policy, perception and the session effects."),
             ("One audit line per step",
              "Ask, tool call, consent decision and mode change are each appended "
              "to JSONL under $XDG_DATA_HOME."),
             ("The pause is real",
              "Ctrl+Alt+S sets a flag Policy reads; while it holds, every mutating "
              "tool is denied regardless of mode."),
         ]),
        ("14  —  USE CASE DIAGRAM", "Use Case Diagram",
         "Figure 4.3  ·  actors, «include» behaviour and the consent «extend»",
         "use-case.png", 5.86, 1.19, [
             ("Four actors, one boundary",
              "Desktop user and installer user outside the system; SpaceXAI, the "
              "Caelestia session and coding agents as external systems."),
             ("«include» is what always runs",
              "Plan tool calls, read session state, apply session effects and "
              "enforce policy are unconditional steps."),
             ("«extend» is the consent prompt",
              "It fires on kill, throttle, close and shell_run in assist mode. In "
              "act mode shell_run still asks."),
             ("Read-only cases skip the gate",
              "Inspect, audit and status never reach enforce policy, which is why "
              "observe mode is safe to hand to a stranger."),
         ]),
        ("15  —  CLASS DIAGRAM", "Class Diagram",
         "Figure 4.4  ·  usr/lib/synapseos/synapseos  ·  drawn from the running code",
         "class-diagram.png", 5.86, 1.19, [
             ("Core composes five collaborators",
              "Planner, Policy, ToolBroker, Sampler and Config are owned by Core "
              "for its lifetime — composition, multiplicity one."),
             ("The overlay never imports Core",
              "It reaches the daemon only through CoreClient over the socket, so "
              "the GUI cannot bypass the gate."),
             ("AppGroup.windows is list[str]",
              "It holds window titles, not Window objects. AppGroup.pids is what "
              "groups Process, so there is no association to Window."),
             ("Five exceptions, all named",
              "ConsentNeeded, ToolError, PlannerError, ClientError and RpcError "
              "are the only ones the package raises."),
         ]),
        ("16  —  SEQUENCE DIAGRAM", "Sequence Diagram",
         "Figure 4.5  ·  a destructive request in assist mode, end to end",
         "sequence.png", 5.86, 1.19, [
             ("\"Close the runaway build.\"",
              "Super+S opens the overlay, Core.handle records the ask and "
              "snapshots the session before anything is planned."),
             ("The model only names a tool",
              "The planner posts the snapshot and 19 tool specifications; the "
              "model returns function_call proc_kill with a PID."),
             ("Policy demands consent",
              "In assist mode proc_kill is a confirm tool. Deny drops the Pending "
              "record and no tool runs at all."),
             ("Only local code acts",
              "On allow, ToolBroker sends SIGTERM and appends the audit line. The "
              "model is not on that segment."),
         ]),
    ]
    for i, (eyebrow, heading, caption, png, h, x, notes) in enumerate(figures):
        s = deck.chrome(bg="bg6" if i % 2 else "bg7",
                        corner_bl="corner_bl2" if i % 2 else "corner_bl3",
                        corner_br=None)
        deck.head(s, eyebrow, heading)
        w = deck.figure(s, FIG / png, x=x, y=CONTENT_Y, h=h, caption=caption,
                        notes=notes, notes_w=min(18.81 - (x + w + 0.70), 6.40))

    # 17 — trust model -------------------------------------------------------
    s = deck.chrome(bg="bg3", leftbar=True)
    deck.head(s, "17  —  TRUST MODEL", "The user holds the leash",
              lead="Three modes, one protected set and nine refused binaries. "
                   "Every claim on this slide is asserted by a unit test.")
    deck.cards6(s, TRUST)

    # 18 — tool catalogue ----------------------------------------------------
    s = deck.chrome(bg="bg5", leftbar=True, corner_bl="corner_bl2")
    deck.head(s, "18  —  TOOL CATALOGUE", "Nineteen typed OS tools",
              rule="rule_wide",
              lead="The whole action surface, and the gate each group meets in "
                   "assist mode. Nothing outside this table can happen.")
    deck.table(s, TOOL_COLS, TOOL_ROWS, head_size=14.5, body_size=13.5,
               head_h=0.56, h=5.60)
    deck.text(s, TABLE_X, 9.86, 15.0, 0.30,
              "8 read tools  ·  6 auto tools  ·  5 confirm tools  ·  shell_run is in "
              "ALWAYS_CONFIRM, so act mode does not exempt it",
              size=13, bold=True, color=MUTED)

    # 19 — technology stack --------------------------------------------------
    s = deck.chrome(bg="bg3", leftbar=True)
    deck.head(s, "19  —  TECHNOLOGY STACK", "Built on things that already work",
              title_size=50,
              lead="No new kernel, no new desktop, no new package manager. The "
                   "novelty is the service in the middle.")
    deck.cards6(s, STACK)

    # 20 — implementation status --------------------------------------------
    s = deck.chrome(bg="bg6", corner_bl=None, corner_br="corner_br2")
    deck.head(s, "20  —  IMPLEMENTATION STATUS",
              "What a stranger can do today", title_w=11.0)
    deck.place(s, "art_blue", 13.09, 3.04)
    deck.list5(s, STATUS, text_w=7.20)
    for y, label, fill, colour in [(3.98, "DONE", "E4F1E8", GOOD),
                                   (5.16, "DONE", "E4F1E8", GOOD),
                                   (6.32, "DONE", "E4F1E8", GOOD),
                                   (7.50, "DONE", "E4F1E8", GOOD),
                                   (8.91, "PLANNED", "FBF0DC", WARN)]:
        h = 1.18 if y in (3.98, 8.91) else 1.41
        deck.pill(s, 10.30, y + h / 2 - 0.16, label, fill=fill, color=colour,
                  w=1.44, h=0.32)

    # 21 — v1 definition of done --------------------------------------------
    s = deck.chrome(bg="bg4", band="band_full")
    deck.head(s, "21  —  DEFINITION OF DONE",
              "v1 is done when a stranger can, in ten minutes…",
              title_size=42, title_w=12.8)
    deck.rows6(s, DONE_V1)
    for i in range(6):
        c, r = divmod(i, 3)
        x, y = NUM_X[c], NUM_Y[r]
        planned = i == 3
        deck.pill(s, x + 7.00, y + 0.30, "PLANNED" if planned else "DONE",
                  fill="FBF0DC" if planned else "E4F1E8",
                  color=WARN if planned else GOOD, w=1.34, h=0.30)

    # 22 — testing -----------------------------------------------------------
    s = deck.chrome(bg="bg8", leftbar=True, corner_bl="corner_bl2")
    deck.head(s, "22  —  VALIDATION", "Testing and validation",
              rule="rule_wide",
              lead="python3 -m unittest discover -s tests  gives  Ran 32 tests, OK. "
                   "The security claims are the ones under test.")
    deck.table(s, TEST_COLS, TEST_ROWS, head_size=15, body_size=13.5,
               head_h=0.58)
    deck.text(s, TABLE_X, 9.98, 15.0, 0.30,
              "32 tests  ·  7 suites  ·  all passing  ·  plus tools/check-packages.py, "
              "which resolves all 293 packages before an hour-long ISO build",
              size=13, bold=True, color=MUTED)

    # 23 — metrics -----------------------------------------------------------
    s = deck.chrome(bg="bg3", leftbar=True)
    deck.head(s, "23  —  METRICS", "Project metrics and deliverables",
              title_size=50,
              lead="Counted from the working tree at the time of this review, not "
                   "estimated.")
    keys = ("card_a", "card_b", "card_c", "card_d", "card_e", "card_f")
    for i, (number, body) in enumerate(METRICS):
        r, c = divmod(i, 3)
        x, y, w = COL_X[c], ROW_Y[r], CARD_W[c]
        deck.place(s, keys[i], x, y)
        deck.text(s, x + 0.30, y + 0.22, w - 0.60, 1.00, number,
                  size=52, bold=True, color=ACCENT_B, spacing=1.0, tag="metric")
        deck.text(s, x + 0.30, y + 1.22, w - 0.58, 0.44, body[0],
                  size=17, bold=True, color=NAVY, spacing=1.0, tag="metric-label")
        deck.text(s, x + 0.30, y + 1.74, w - 0.58, 1.20,
                  [{"text": b, "space_after": 4} for b in body[2:]],
                  size=13.5, color=INK, spacing=1.10, tag="metric-body")

    # 24 — plan / milestones -------------------------------------------------
    s = deck.chrome(bg="bg4", band="band_full", corner_bl=None, corner_br=None)
    deck.head(s, "24  —  PROJECT PLAN", "Milestones and schedule",
              lead="Phases through Review-1 are complete and dated from the "
                   "repository history. Everything after it is planned work.")
    gx, gy, gw = 6.60, 4.14, 11.60
    lane_h, gap = 0.44, 0.09
    col_w = gw / len(PLAN_MONTHS)
    deck.rect(s, gx, gy - 0.46, gw, 0.42, fill="DCE9F7")
    for i, month in enumerate(PLAN_MONTHS):
        deck.text(s, gx + i * col_w, gy - 0.37, col_w, 0.28, month, size=13,
                  bold=True, color=NAVY, align=PP_ALIGN.CENTER)
        if i:
            deck.rect(s, gx + i * col_w, gy - 0.04, 0.011,
                      len(PLAN) * (lane_h + gap), fill="E3EBF4")
    for i, (label, start, span, state) in enumerate(PLAN):
        y = gy + i * (lane_h + gap)
        deck.rect(s, 1.19, y, 5.20, lane_h, fill="F5F9FD" if i % 2 else "FFFFFF")
        deck.text(s, 1.34, y + 0.02, 4.95, lane_h - 0.04, label, size=13.5,
                  bold=state == "now", color=NAVY if state != "plan" else MUTED,
                  anchor=MSO_ANCHOR.MIDDLE)
        fill, line, _txt = {
            "done": ("75A9D6", None, WHITE),
            "now": ("2E6FB0", None, WHITE),
            "plan": ("EDF4FB", "A1C9EB", RGBColor(0x3C, 0x5E, 0x8A)),
        }[state]
        bar = deck.rect(s, gx + start * col_w + 0.03, y + 0.05,
                        span * col_w - 0.06, lane_h - 0.10, fill=fill, line=line,
                        radius=0.28, shape_type=MSO_SHAPE.ROUNDED_RECTANGLE)
        note = {"done": "complete", "now": "Review-1", "plan": "planned"}[state]
        deck.text(s, gx + (start + span) * col_w + 0.10, y + 0.03, 1.60,
                  lane_h - 0.06, note, size=11,
                  bold=state == "now",
                  color=RGBColor(0x2E, 0x6F, 0xB0) if state == "now" else MUTED,
                  anchor=MSO_ANCHOR.MIDDLE, spacing=1.0, tag="gantt-note")
    marker_x = gx + PLAN_TODAY * col_w
    bottom = gy + len(PLAN) * (lane_h + gap)
    deck.rect(s, marker_x, gy - 0.04, 0.022, bottom - gy + 0.04, fill="C2453C")
    deck.text(s, marker_x - 1.05, bottom + 0.06, 2.10, 0.28, "Review-1  ·  today",
              size=12, bold=True, color=RGBColor(0xC2, 0x45, 0x3C),
              align=PP_ALIGN.CENTER)
    for i, (label, colour) in enumerate([("complete", "75A9D6"),
                                         ("current phase", "2E6FB0"),
                                         ("planned", "EDF4FB")]):
        lx = 1.19 + i * 2.30
        deck.rect(s, lx, bottom + 0.30, 0.44, 0.22, fill=colour,
                  line="A1C9EB" if colour == "EDF4FB" else None, radius=0.4,
                  shape_type=MSO_SHAPE.ROUNDED_RECTANGLE)
        deck.text(s, lx + 0.58, bottom + 0.28, 1.70, 0.26, label, size=12.5,
                  color=MUTED)

    # 25 — risks -------------------------------------------------------------
    s = deck.chrome(bg="bg8", leftbar=True, corner_bl="corner_bl2")
    deck.head(s, "25  —  RISKS", "Risks and mitigations", rule="rule_wide",
              lead="Including the two the project chose to accept, and says so in "
                   "the README and in /etc/motd.")
    deck.table(s, RISK_COLS, RISK_ROWS, head_size=15, body_size=13.5)

    # 26 — future scope ------------------------------------------------------
    s = deck.chrome(bg="bg4", band="band_full")
    deck.head(s, "26  —  FUTURE SCOPE", "What comes after Review-1",
              lead="Objective 4 first. Product B does not start until Product A "
                   "is a daily driver.")
    deck.rows6(s, FUTURE)

    # 27 / 28 — references ---------------------------------------------------
    for idx, (eyebrow, heading, refs) in enumerate([
            ("27  —  REFERENCES", "References", REFS_A),
            ("28  —  REFERENCES", "References — Continued", REFS_B)]):
        s = deck.chrome(bg="bg8", leftbar="leftbar8", corner_bl=None,
                        corner_br="corner_br2")
        deck.head(s, eyebrow, heading, title_size=52 if idx else 58,
                  rule="rule_thin")
        deck.place(s, "ref_left", 0.95, 3.28)
        deck.place(s, "ref_right", 5.23, 3.28)
        deck.text(s, 1.36, 3.72, 3.50, 4.30, [
            {"text": "How to read the list", "size": 17, "bold": True,
             "color": NAVY, "space_after": 12},
            {"text": "Entries 1–10 are the surveyed literature, in the order they "
                     "appear on slides 07 and 08.", "space_after": 12},
            {"text": "Entries 11–14 are the standards, specifications and projects "
                     "this build depends on.", "space_after": 12},
            {"text": "arXiv identifiers are given so every claim can be checked "
                     "against the source."},
        ], size=14, color=INK, spacing=1.16)
        divs = ("div1", "div2", "div3", "div4", "div5", "div6", "div7")
        base = 1 if idx == 0 else 9
        top, pitch = 3.74, 0.82
        for i, (authors, rest) in enumerate(refs):
            y = top + i * pitch
            deck.text(s, 6.06, y + 0.04, 0.90, 0.52, f"{base + i:02d}",
                      size=29, bold=True, color=ACCENT_L, spacing=1.0,
                      tag="ref-num")
            deck.text(s, 7.30, y, 11.55, 0.72,
                      [{"text": authors, "size": 15.5, "bold": True,
                        "color": NAVY, "space_after": 2},
                       {"text": rest, "size": 13.5, "color": INK}],
                      spacing=1.10, tag="ref-body")
            if i < len(refs) - 1 and i < len(divs):
                deck.place(s, divs[i], 5.71, y + pitch - 0.14)

    thanks = build_thanks(deck, total)

    # footers ---------------------------------------------------------------
    for i, slide in enumerate(deck.built, start=2):
        deck.foot(slide, i, total)

    # drop the untouched template slides and put the deck in order ----------
    keep = {id(title), id(thanks)}
    for slide in list(deck.prs.slides):
        if id(slide) not in keep and slide not in deck.built:
            delete_slide(deck.prs, slide)
    reorder(deck.prs, [title] + deck.built + [thanks])

    deck.prs.save(str(out))
    over = [(n, tag, est, h) for n, tag, est, h in deck.checks if est > h + 0.02]
    if over:
        print(f"\n  {len(over)} text box(es) estimated to overflow their frame:")
        for n, tag, est, h in over:
            print(f"    slide {n + 1:>2}  {tag[:40]:<42} est {est:.2f}in "
                  f"> frame {h:.2f}in")
    else:
        print("  layout check: no estimated text overflow")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    out = build(Path(args.out))
    prs = Presentation(str(out))
    print(f"wrote {out}  ({len(prs.slides)} slides, "
          f"{out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
