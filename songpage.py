#!/usr/bin/env python3
"""
songpage.py — render one campfire-songbook page from a chord-over-lyric text chart.

Usage:  python3 songpage.py chart.txt out.pdf

Chart format (Ultimate-Guitar style):
    # key: value            metadata lines (title, artist, key, tuning, capo, structure)
    [Section name]          section header
    E        A  Asus4       chord line — positions align with the lyric line below
    lyric text here         lyric line (a line of only ~~~~ is a placeholder, drawn as a rule)
    E   A   B               chord line with no lyric below = chord-only line (intros etc.)

    @diagram Asus4 x00230   chord diagram for the header box (frets low→high, x=mute, 0=open)
    @tab                    start of a tab block for the header box; ends at a blank line

Optional metadata: # group: <toc category>, # landscape: yes, # spread: yes (two facing
pages), # chorus-markers: yes (repeated choruses print as a one-line cue),
# min-size: 12 (floor for the auto-shrink).

Layout: letter, header block, two columns, auto-shrinks lyric size to fit one page.
"""
import os
import re
import sys
import orchid
from dataclasses import dataclass, field
from reportlab.lib.pagesizes import letter, landscape as _landscape
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ---------- fonts ----------
# Preference order: DejaVu Sans Condensed (Linux), Arial Narrow (macOS Supplemental),
# then reportlab's built-in Helvetica. Each entry: (regular, bold, mono) file paths.
FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial Narrow.ttf",
     "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf",
     None),
]


def resolve_fonts():
    """Register the first available font family; return (lyric, chord, mono) font names."""
    for regular, bold, mono in FONT_CANDIDATES:
        if not (os.path.exists(regular) and os.path.exists(bold)):
            continue
        pdfmetrics.registerFont(TTFont("Lyr", regular))
        pdfmetrics.registerFont(TTFont("LyrB", bold))
        if mono and os.path.exists(mono):
            pdfmetrics.registerFont(TTFont("Mono", mono))
            return "Lyr", "LyrB", "Mono"
        return "Lyr", "LyrB", "Courier"
    return "Helvetica", "Helvetica-Bold", "Courier"


LYR_FONT, CH_FONT, MONO = resolve_fonts()


def truthy(v):
    return str(v or "").strip().lower() in {"yes", "true", "1", "on"}

# ---------- parsing ----------
# A chord token may be wrapped in parentheses, so a walk-up like "(D C# F#)" splits into
# the tokens "(D", "C#", "F#)" and still reads as a chord line.
CHORD_TOK = re.compile(
    r"^\(?(?:[A-G][#b]?(?:m|maj|min|dim|aug|sus|add|M|\d|\+|-|/[A-G][#b]?|\(no3\))*"
    r"|[x×]\d+|\||N\.?C\.?)\)?$"
)


def is_chord_line(s):
    toks = s.split()
    return bool(toks) and all(CHORD_TOK.match(t) for t in toks)


def chord_positions(s):
    return [(m.start(), m.group()) for m in re.finditer(r"\S+", s)]


def is_placeholder(s):
    t = s.strip()
    return bool(t) and set(t) <= {"~"}


@dataclass
class Part:
    """One instrument's overlay on a chart: its metadata, header blocks and cues."""
    name: str
    meta: dict = field(default_factory=dict)
    blocks: list = field(default_factory=list)   # ("mono", label, lines) | ("note", text) | ("image", path)
    diagrams: list = field(default_factory=list)
    cues: dict = field(default_factory=dict)      # cue_key(section) -> text; "*" is the default


@dataclass
class Chart:
    meta: dict
    diagrams: list
    tab: list
    items: list
    parts: dict = field(default_factory=dict)   # name -> Part, in file order


SECTION_RE = re.compile(r"^\[(.+?)\](.*)$")


def cue_key(name):
    """Sections match cues by their label alone: 'Verse 3 – quiet' and 'Chorus ×2' match
    the cues [Verse 3] and [Chorus]."""
    label = re.split(r"\s+[–—-]\s+", name.strip(), maxsplit=1)[0]
    label = re.sub(r"\s*(×\d+|\(x\d+\))$", "", label)
    return label.lower()


def parse_chart(path):
    meta, diagrams, tab, items, parts = {}, [], [], [], {}
    part = None
    lines = open(path, encoding="utf-8").read().splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i].rstrip("\n")
        s = raw.strip()
        if s.startswith("@part"):
            name = s[len("@part"):].strip()
            if not name:
                raise ValueError(f"{path}:{i + 1}: @part needs a name")
            part = parts.setdefault(name, Part(name))
        elif s.startswith("#"):
            k, _, v = s[1:].partition(":")
            (part.meta if part else meta)[k.strip().lower()] = v.strip()
        elif s.startswith("@diagram"):
            _, name, frets = s.split(None, 2)
            (part.diagrams if part else diagrams).append((name, frets))
        elif s.startswith(("@tab", "@grid")):
            label = s.split(None, 1)[1].strip() if " " in s else ""
            block = []
            i += 1
            while i < len(lines) and lines[i].strip() \
                    and not lines[i].lstrip().startswith(("[", "@", "#")):
                block.append(lines[i].rstrip())
                i += 1
            if part:
                part.blocks.append(("mono", label, block))
            else:
                tab.extend(block)
            # If block ended at a special line, don't increment i again; continue to process it
            if i < len(lines) and lines[i].lstrip().startswith(("[", "@", "#")):
                continue
            # If block ended at blank line, skip it
            if i < len(lines) and not lines[i].strip():
                i += 1
            continue
        elif s.startswith(("@note", "@image")):
            if not part:
                raise ValueError(f"{path}:{i + 1}: {s.split()[0]} is only valid inside @part")
            kind, _, text = s.partition(" ")
            if kind == "@image":
                text = os.path.join(os.path.dirname(os.path.abspath(path)), text.strip())
            part.blocks.append((kind[1:], text.strip()))
        elif part:
            if m := SECTION_RE.match(s):
                part.cues[cue_key(m.group(1))] = m.group(2).strip()
            elif s:
                raise ValueError(f"{path}:{i + 1}: unexpected line in @part {part.name}: {s}")
        elif re.match(r"^\[.+\]$", s):
            items.append(("section", s[1:-1]))
        elif not s:
            pass
        elif is_chord_line(raw):
            nxt = lines[i + 1].rstrip("\n") if i + 1 < len(lines) else ""
            if nxt.strip() and not is_chord_line(nxt) and not re.match(r"^\[.+\]$", nxt.strip()) \
                    and not nxt.strip().startswith(("#", "@")):
                items.append(("pair", chord_positions(raw), nxt))
                i += 1
            else:
                items.append(("chords", chord_positions(raw), ""))
        else:
            items.append(("pair", [], raw))
        i += 1
    return Chart(meta, diagrams, tab, items, parts)


def parse(path):
    """The chart's own part as a four-tuple (meta, diagrams, tab, items)."""
    ch = parse_chart(path)
    return ch.meta, ch.diagrams, ch.tab, ch.items


CHORUS_RE = re.compile(r"^chorus\b", re.IGNORECASE)


def collapse_repeated_choruses(items):
    """Keep the first [Chorus] block in full; later chorus sections become one-line markers."""
    out, seen, skipping = [], False, False
    for it in items:
        if it[0] == "section":
            is_chorus = bool(CHORUS_RE.match(it[1]))
            skipping = is_chorus and seen
            if is_chorus and not seen:
                seen = True
            out.append(("marker", it[1]) if skipping else it)
        elif not skipping:
            out.append(it)
    return out


@dataclass
class PartSpec:
    """How a book renders one instrument's part (from book.toml's [[parts]])."""
    name: str
    title: str
    chords: bool = True
    default_cue: str = ""
    orchid: bool = False
    patches: list = field(default_factory=list)
    intro: str | None = None
    base: bool = False   # the book's first part: it also shows the chart's own diagrams and tab


def part_items(items, part, spec):
    """The shared body seen through one part: sections carry that part's cue, chord
    lines are kept or dropped per the part."""
    cues = part.cues if part else {}
    out = []
    for it in items:
        if it[0] == "section":
            cue = cues.get(cue_key(it[1]), cues.get("*", spec.default_cue))
            out.append(("section", it[1], cue))
        elif it[0] == "pair":
            out.append(it if spec.chords else ("pair", [], it[2]))
        elif spec.chords:
            out.append(it)
    return out


def chord_tokens(items):
    return [name for it in items if it[0] in ("pair", "chords") for _, name in it[1]]


def patch_label(patch, bank):
    """'organ' with bank [piano, organ] -> 'Patch 2 · organ'; a name not in the bank
    prints as written. Only the text before a semicolon is matched."""
    if not patch:
        return ""
    first = patch.split(";")[0].strip().lower()
    for n, name in enumerate(bank, 1):
        if first == name.lower():
            return f"Patch {n} · {patch}"
    return "Patch: " + patch


# ---------- layout ----------
class Style:
    def __init__(self, lyr):
        self.lyr = lyr
        self.ch = round(lyr * 0.86, 1)
        self.ch_h = self.ch * 1.15
        self.lyr_h = lyr * 1.22
        self.pair_gap = lyr * 0.36
        self.trail_gap = self.ch * 0.28
        self.sec_h = 13
        self.sec_gap = 7
        self.chord_gap = self.ch * 0.4
        self.indent = lyr * 1.2
        alphabet = "the quick brown fox jumps over the lazy dog and it's not far away "
        self.avgw = pdfmetrics.stringWidth(alphabet, LYR_FONT, lyr) / len(alphabet)

    def tw(self, text, placeholder):
        if placeholder:
            return len(text) * self.avgw
        return pdfmetrics.stringWidth(text, LYR_FONT, self.lyr)

    def cw(self, chord):
        return pdfmetrics.stringWidth(chord, CH_FONT, self.ch) if chord else 0


def segments(chords, lyric):
    """Split lyric at chord positions -> [(chord|None, text)]"""
    if not chords:
        return [(None, lyric)]
    segs = []
    if chords[0][0] > 0:
        segs.append((None, lyric[:chords[0][0]]))
    for k, (pos, name) in enumerate(chords):
        end = chords[k + 1][0] if k + 1 < len(chords) else max(len(lyric), pos)
        segs.append((name, lyric[pos:end] if pos < len(lyric) else ""))
    return segs


def atoms(segs, placeholder):
    """Break segments into wrap-able atoms; chord rides on the first atom of its segment."""
    out = []
    for chord, text in segs:
        if placeholder or not text:
            out.append((chord, text))
            continue
        words = re.findall(r"\S+\s*", text) or [text]
        if text and text[0].isspace():  # leading space stays attached to previous atom visually
            lead = re.match(r"\s+", text).group()
            words = [lead + words[0]] + words[1:] if words else [lead]
        for w_i, w in enumerate(words):
            out.append((chord if w_i == 0 else None, w))
    return out


def wrap_line(st, chords, lyric, colw, placeholder, overflow=0):
    """Return list of (atoms, chord_only) visual lines; atoms = [(chord, text, adv)].
    Chords that fall past the end of the lyric ("trailing", e.g. a sus hang) are packed
    tightly; if the run doesn't fit it drops to a chord-only line below the lyric."""
    ats = atoms(segments(chords, lyric), placeholder)
    body = [(c, t) for c, t in ats if t != ""]
    trail = [c for c, t in ats if t == "" and c]
    lines, cur, x = [], [], 0.0
    for idx, (chord, text) in enumerate(body):
        tw = st.tw(text, placeholder)
        cw = st.cw(chord)
        last = idx == len(body) - 1 and not trail
        need = (cw + (0 if last else st.chord_gap)) if chord else 0  # chord-less atoms take only their text width
        adv = max(tw, need)
        limit = colw - (st.indent if lines else 0)
        if cur and x + adv > limit:
            lines.append((cur, False))
            cur, x = [], 0.0
            if not placeholder:
                text = text.lstrip()
                tw = st.tw(text, placeholder)
                adv = max(tw, need)
        if placeholder and not cur and adv > limit and len(text) > 8:
            n = int(len(text) * limit / adv) - 1
            cur.append((chord, text[:n], st.tw(text[:n], True)))
            lines.append((cur, False))
            rest = text[n:]
            cur, x = [(None, rest, st.tw(rest, True))], st.tw(rest, True)
            continue
        cur.append((chord, text, adv))
        x += adv
    if trail:
        run = [(c, "", st.cw(c) + (st.trail_gap if k < len(trail) - 1 else 0)) for k, c in enumerate(trail)]
        run_w = sum(a for _, _, a in run)
        limit = colw + overflow - (st.indent if lines else 0)
        if cur and x + st.chord_gap + run_w <= limit:
            cur[-1] = (cur[-1][0], cur[-1][1], max(cur[-1][2], st.tw(cur[-1][1], placeholder) + st.chord_gap))
            cur.extend(run)
        else:
            if cur:
                lines.append((cur, False))
            cur = run
            lines.append((cur, True))
            cur = []
    if cur:
        lines.append((cur, False))
    return lines


def line_height(st, vis, chord_only, has_lyric):
    """Height of one visual line. A wrapped continuation with no chords on it needs no
    chord row, so it takes only the lyric height."""
    if chord_only or not has_lyric:
        return st.ch_h * 1.05
    if not any(ch for ch, _, _ in vis):
        return st.lyr_h
    return st.ch_h + st.lyr_h


def layout(st, items, colw, colh, gutter=18, max_cols=2):
    """Assign items to columns of height colh. Returns (columns, fits); fits is False
    when the items need more than max_cols columns (two per page)."""
    cols, col, y = [], [], colh
    blocks = []
    for it in items:
        if it[0] in ("section", "marker"):
            cue = it[2] if len(it) > 2 else ""
            cue_lines = None
            if cue:
                label_w = pdfmetrics.stringWidth(it[1].upper() + "  ", CH_FONT, 8.5)
                if label_w + pdfmetrics.stringWidth("· " + cue, LYR_FONT, 8.5) > colw:
                    cue_lines = wrap_words(cue, LYR_FONT, 8.5, colw)
            h = st.sec_h + (len(cue_lines) * 10 if cue_lines else 0)
            blocks.append({"kind": it[0], "name": it[1], "cue": cue, "cue_lines": cue_lines, "h": h})
        else:
            placeholder = is_placeholder(it[2])
            vis = wrap_line(st, it[1], it[2], colw, placeholder, overflow=gutter - 6)
            has_lyric = it[0] == "pair"
            h = sum(line_height(st, v, co, has_lyric) for v, co in vis)
            blocks.append({"kind": it[0], "lines": vis, "placeholder": placeholder,
                           "h": h + st.pair_gap})
    k = 0
    while k < len(blocks):
        b = blocks[k]
        need = b["h"]
        gap = st.sec_gap if (b["kind"] in ("section", "marker") and col) else 0
        if b["kind"] == "section" and k + 1 < len(blocks):
            need += blocks[k + 1]["h"]  # keep header with its first line
        if y - gap - need < 0 and col:
            cols.append(col)
            col, y, gap = [], colh, 0
            if len(cols) == max_cols:
                return cols, False
        y -= gap
        b["y"] = y
        col.append(b)
        y -= b["h"]
        k += 1
    cols.append(col)
    return cols, len(cols) <= max_cols


# ---------- drawing ----------
def diagram_width(size):
    return 4.4 * size + 6


def draw_diagram(c, x, y, name, frets, size=9):
    """x,y = top-left. frets string low→high, e.g. x00230. Shapes above the 4th fret
    are drawn from their lowest fretted position with a "Nfr" label instead of a nut."""
    sw, fh, nstr, nfr = size * 0.8, size * 0.95, 6, 4
    gx, gy = x + size * 0.6, y - size * 1.7
    fretted = [int(ch) for ch in frets if ch.isdigit() and ch != "0"]
    base = min(fretted) if fretted and max(fretted) > nfr else 1
    c.setFont(CH_FONT, size * 1.05)
    c.drawCentredString(gx + sw * (nstr - 1) / 2, y - size * 0.4, name)
    c.setStrokeColorRGB(0.15, 0.15, 0.15)
    c.setLineWidth(1.6 if base == 1 else 0.6)
    c.line(gx, gy, gx + sw * (nstr - 1), gy)  # nut, or just the top line when shifted
    c.setLineWidth(0.6)
    for s in range(nstr):
        c.line(gx + s * sw, gy, gx + s * sw, gy - fh * nfr)
    for f in range(1, nfr + 1):
        c.line(gx, gy - f * fh, gx + sw * (nstr - 1), gy - f * fh)
    c.setFont(LYR_FONT, size * 0.85)
    if base > 1:
        c.setFont(LYR_FONT, size * 0.7)
        c.drawRightString(gx - size * 0.15, gy - 0.75 * fh, f"{base}fr")
        c.setFont(LYR_FONT, size * 0.85)
    for s, ch in enumerate(frets):
        sx = gx + s * sw
        if ch == "x":
            c.drawCentredString(sx, gy + size * 0.35, "x")
        elif ch == "0":
            c.circle(sx, gy + size * 0.55, size * 0.22, stroke=1, fill=0)
        else:
            f = int(ch) - base + 1
            c.circle(sx, gy - (f - 0.5) * fh, size * 0.3, stroke=0, fill=1)
    return x + diagram_width(size)  # right edge


HEADER_H = 72
DIAGRAM_ROW_H = 52
MONO_SIZE, MONO_LEAD = 7.2, 8.4
NOTE_SIZE, NOTE_W = 8, 150
BOX_PAD = 6
CORNER_H = 62


def measure_block(block):
    """(width, height, drawable) for one header-box block. Notes are wrapped and images
    opened here so drawing needs no further measuring."""
    kind = block[0]
    if kind == "mono":
        _, label, lines = block
        widths = [pdfmetrics.stringWidth(t, MONO, MONO_SIZE) for t in lines]
        widths.append(pdfmetrics.stringWidth(label, CH_FONT, 8) if label else 0)
        return max(widths) + 8, MONO_LEAD * len(lines) + (11 if label else 0) + 6, block
    if kind == "note":
        lines = wrap_words(block[1], LYR_FONT, NOTE_SIZE, NOTE_W)
        w = max(pdfmetrics.stringWidth(t, LYR_FONT, NOTE_SIZE) for t in lines) + 8
        return w, (NOTE_SIZE + 2) * len(lines) + 6, ("note", lines)
    if kind == "image":
        from reportlab.lib.utils import ImageReader
        img = ImageReader(block[1])
        iw, ih = img.getSize()
        return 52 * iw / ih + 8, 52, ("image", img)
    if kind == "diagrams":
        return diagram_width(8) * len(block[1]) + 6, 56, block
    raise ValueError(f"unknown header block {kind}")


def box_layout(blocks, W, m, title_w):
    """Place header blocks in one row beside the title when they fit there, otherwise
    in rows across a full-width band under the header."""
    measured = [measure_block(b) for b in blocks]
    if not measured:
        return {"mode": "none", "rows": [], "box_w": 0, "box_h": 0, "header_h": HEADER_H}
    row_w = sum(w for w, _, _ in measured) + BOX_PAD * (len(measured) + 1)
    row_h = max(h for _, h, _ in measured) + BOX_PAD
    if row_h <= CORNER_H and W - m - row_w >= m + title_w + 10:
        return {"mode": "corner", "rows": [measured], "box_w": row_w, "box_h": CORNER_H,
                "header_h": HEADER_H}
    rows, cur, x = [], [], BOX_PAD
    for w, h, b in measured:
        if cur and x + w > W - 2 * m - BOX_PAD:
            rows.append(cur)
            cur, x = [], BOX_PAD
        cur.append((w, h, b))
        x += w + BOX_PAD
    rows.append(cur)
    box_h = sum(max(h for _, h, _ in r) for r in rows) + BOX_PAD * (len(rows) + 1)
    return {"mode": "band", "rows": rows, "box_w": 0, "box_h": box_h,
            "header_h": HEADER_H + box_h + 4}


def draw_block(c, x, y, h, block):
    """Draw one measured block with its top-left corner at (x, y)."""
    kind = block[0]
    c.setFillColorRGB(0.1, 0.1, 0.1)
    if kind == "mono":
        _, label, lines = block
        ty = y - 9
        if label:
            c.setFont(CH_FONT, 8)
            c.drawString(x + 4, ty, label)
            ty -= 11
        c.setFont(MONO, MONO_SIZE)
        for t in lines:
            c.drawString(x + 4, ty, t)
            ty -= MONO_LEAD
    elif kind == "note":
        c.setFont(LYR_FONT, NOTE_SIZE)
        for k, t in enumerate(block[1]):
            c.drawString(x + 4, y - 9 - k * (NOTE_SIZE + 2), t)
    elif kind == "image":
        iw, ih = block[1].getSize()
        c.drawImage(block[1], x + 4, y - h + 2, (h - 4) * iw / ih, h - 4, mask="auto")
    elif kind == "diagrams":
        dx = x + 2
        for name, frets in block[1]:
            dx = draw_diagram(c, dx, y - 2, name, frets, size=8)


def draw_box(c, bl, W, H, m):
    top = H - m
    if bl["mode"] == "corner":
        bx, by, bw, bh = W - m - bl["box_w"], top, bl["box_w"], bl["box_h"]
    else:
        bx, by, bw, bh = m, top - HEADER_H, W - 2 * m, bl["box_h"]
    c.setStrokeColorRGB(0.75, 0.75, 0.75)
    c.setLineWidth(0.5)
    c.roundRect(bx - 2, by - bh, bw + 2, bh, 4, stroke=1, fill=0)
    y = by - BOX_PAD
    for row in bl["rows"]:
        x = bx + BOX_PAD
        for w, h, b in row:
            draw_block(c, x, y, h, b)
            x += w + BOX_PAD
        y -= max(h for _, h, _ in row) + BOX_PAD


def title_width(meta, ts):
    return (pdfmetrics.stringWidth(meta.get("title", ""), CH_FONT, ts) + 8
            + pdfmetrics.stringWidth("— " + meta.get("artist", ""), LYR_FONT, 12))


def header_layout_blocks(meta, blocks, W, m):
    """Header layout for a part page: the block box beside the title, or a band below."""
    bl = box_layout(blocks, W, m, title_width(meta, 19))
    return {"size": 8, "box_w": bl["box_w"], "two_rows": False, "header_h": bl["header_h"],
            "title_size": 19, "box": bl}


def header_layout(meta, diagrams, tab, W, m):
    """Decide how the header box fits beside the title: diagram size 9 down to 7, and
    if a tab plus diagrams still would not fit, put the diagrams on a second row under
    the tab (which makes the header taller). Returns a dict for draw_header/render."""
    tab_w = (max(pdfmetrics.stringWidth(t, MONO, 7.2) for t in tab) + 10) if tab else 0
    fits = lambda box_w, ts: not box_w or W - m - box_w >= m + title_width(meta, ts) + 10
    # One row: shrink the diagrams first, then the title a step, before using two rows.
    for ts in (19, 18, 17):
        for size in (9, 8, 7):
            dia_w = (diagram_width(size) * len(diagrams) + 6) if diagrams else 0
            if fits(tab_w + dia_w, ts):
                return {"size": size, "box_w": tab_w + dia_w, "two_rows": False,
                        "header_h": HEADER_H, "title_size": ts}
    if tab and diagrams:
        for size in (9, 8, 7):
            dia_w = diagram_width(size) * len(diagrams) + 6
            if fits(max(tab_w, dia_w), 19):
                return {"size": size, "box_w": max(tab_w, dia_w), "two_rows": True,
                        "header_h": HEADER_H + DIAGRAM_ROW_H, "title_size": 19}
    print(f"WARNING: header box overlaps the title in {meta.get('title')}", file=sys.stderr)
    dia_w = (diagram_width(7) * len(diagrams) + 6) if diagrams else 0
    return {"size": 7, "box_w": tab_w + dia_w, "two_rows": False, "header_h": HEADER_H,
            "title_size": 17}


def draw_header(c, meta, diagrams, tab, W, H, m, hl=None, guide_prefix="", guide_suffix=""):
    hl = hl or header_layout(meta, diagrams, tab, W, m)
    top = H - m
    title = meta.get("title", "")
    artist = meta.get("artist", "")
    ts = hl.get("title_size", 19)
    c.setFillColorRGB(0, 0, 0)
    c.setFont(CH_FONT, ts)
    c.drawString(m, top - 19, title)
    tw = pdfmetrics.stringWidth(title, CH_FONT, ts)
    c.setFont(LYR_FONT, 12)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawString(m + tw + 8, top - 19, "— " + artist)
    guide = " · ".join(v for v in [
        guide_prefix,
        ("Key " + meta["key"]) if "key" in meta else "",
        meta.get("tuning", ""), meta.get("capo", ""), guide_suffix] if v)
    c.setFillColorRGB(0, 0, 0)
    c.setFont(CH_FONT, 10.5)
    c.drawString(m, top - 37, guide)
    box_w = hl["box_w"]
    bx, by = W - m - box_w, top

    # The form line shrinks (down to 8pt) and then wraps onto a second line rather than
    # run under the header box.
    form = "Form:  " + meta.get("structure", "")
    avail = (bx - 8 if box_w else W - m) - m
    for size in (9.5, 9, 8.5, 8):
        lines = wrap_words(form, LYR_FONT, size, avail)
        if len(lines) <= 2:
            break
    else:
        size = 7
        lines = wrap_words(form, LYR_FONT, size, avail)[:3]  # three lines still clear the columns
    c.setFont(LYR_FONT, size)
    c.setFillColorRGB(0.25, 0.25, 0.25)
    for i, line in enumerate(lines):
        c.drawString(m, top - 52 - i * (size + 1), line)

    if hl.get("box"):
        if hl["box"]["mode"] != "none":
            draw_box(c, hl["box"], W, H, m)
        return

    # right-hand box: diagrams + tab (diagrams drop to a second row when needed)
    if not diagrams and not tab:
        return
    size = hl["size"]
    box_h = 62 + (DIAGRAM_ROW_H if hl["two_rows"] else 0)
    x = bx + 4
    if not hl["two_rows"]:
        for name, frets in diagrams:
            x = draw_diagram(c, x, by - 2, name, frets, size=size)
    if tab:
        c.setFont(MONO, 7.2)
        c.setFillColorRGB(0.1, 0.1, 0.1)
        ty = by - 9
        for t in tab:
            c.drawString(x + 4, ty, t)
            ty -= 8.4
    if hl["two_rows"]:
        x = bx + 4
        for name, frets in diagrams:
            x = draw_diagram(c, x, by - 64, name, frets, size=size)
    c.setStrokeColorRGB(0.75, 0.75, 0.75)
    c.setLineWidth(0.5)
    c.roundRect(bx - 2, top - box_h, box_w + 2, box_h, 4, stroke=1, fill=0)


def wrap_words(text, font, size, width):
    """Greedy word wrap by measured width; a word wider than the line stands alone."""
    lines, cur = [], ""
    for word in text.split():
        cand = (cur + " " + word) if cur else word
        if cur and pdfmetrics.stringWidth(cand, font, size) > width:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def draw_continuation_header(c, meta, W, H, m, part_title=""):
    """Slim header for the second page of a spread."""
    top = H - m
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.setFont(CH_FONT, 12)
    c.drawString(m, top - 14, meta.get("title", "") + "  (continued)")
    c.setFont(LYR_FONT, 9.5)
    right = " · ".join(v for v in [part_title, meta.get("artist", "")] if v)
    c.drawRightString(W - m, top - 14, right)
    c.setStrokeColorRGB(0.8, 0.8, 0.8)
    c.setLineWidth(0.5)
    c.line(m, top - 20, W - m, top - 20)


def draw_columns(c, st, cols, x0, y0, colw, gutter):
    for ci, col in enumerate(cols):
        cx = x0 + ci * (colw + gutter)
        for b in col:
            y = y0 + b["y"]  # y is offset from column top measured downward
            if b["kind"] in ("section", "marker"):
                c.setFont(CH_FONT, 8.5)
                c.setFillColorRGB(0.35, 0.35, 0.35)
                name = b["name"].upper()
                if b["kind"] == "marker":
                    name += "  (AS BEFORE)"
                c.drawString(cx, y - 9, name)
                nw = pdfmetrics.stringWidth(name, CH_FONT, 8.5)
                if b.get("cue"):
                    c.setFont(LYR_FONT, 8.5)
                    c.setFillColorRGB(0.45, 0.45, 0.45)
                    if b["cue_lines"] is None:
                        c.drawString(cx + nw + 6, y - 9, "· " + b["cue"])
                        nw += 6 + pdfmetrics.stringWidth("· " + b["cue"], LYR_FONT, 8.5)
                    else:
                        for k, line in enumerate(b["cue_lines"]):
                            c.drawString(cx, y - 9 - 10 * (k + 1), line)
                c.setStrokeColorRGB(0.8, 0.8, 0.8)
                c.setLineWidth(0.5)
                c.line(cx + nw + 6, y - 6, cx + colw, y - 6)
                continue
            has_lyric = b["kind"] == "pair"
            for li, (vis, chord_only) in enumerate(b["lines"]):
                x = cx + (st.indent if li else 0)
                lh = line_height(st, vis, chord_only, has_lyric)
                ych = y - st.ch
                ylyr = y - lh + (st.lyr_h - st.lyr)
                for chord, text, adv in vis:
                    if chord:
                        c.setFont(CH_FONT, st.ch)
                        c.setFillColorRGB(0, 0, 0)
                        c.drawString(x, ych, chord)
                    if has_lyric and text and not chord_only:
                        if b["placeholder"]:
                            c.setStrokeColorRGB(0.6, 0.6, 0.6)
                            c.setLineWidth(0.7)
                            c.setDash(1.2, 2.2)
                            c.line(x, ylyr - 1, x + st.tw(text, True) - 2, ylyr - 1)
                            c.setDash()
                        else:
                            c.setFont(LYR_FONT, st.lyr)
                            c.setFillColorRGB(0, 0, 0)
                            c.drawString(x, ylyr, text)
                    x += adv
                y -= lh


@dataclass
class RenderResult:
    out: str
    lyric_size: float
    chord_size: float
    fits: bool
    landscape: bool
    pages: int
    meta: dict
    part: str | None = None


SIZES = (13, 12.5, 12, 11.5, 11, 10.5, 10, 9.5)


def want_orchid(overlay, spec):
    """Whether the Orchid legend should show: the book's PartSpec default, overridable
    per-song by the part's own `# orchid:` line."""
    if overlay and "orchid" in overlay.meta:
        return truthy(overlay.meta["orchid"])
    return spec.orchid


def part_blocks(chart, overlay, spec):
    """Header-box blocks for one part: the Orchid legend for keys, the chart's own
    diagrams and tab for the base part, then the overlay's diagrams and blocks."""
    blocks = []
    if want_orchid(overlay, spec):
        key = chart.meta.get("key", "")
        lines = orchid.legend_lines(key, chord_tokens(chart.items))
        if lines:
            blocks.append(("mono", "Orchid key: " + key, lines))
    if spec.base:
        if chart.diagrams:
            blocks.append(("diagrams", chart.diagrams))
        if chart.tab:
            blocks.append(("mono", "", chart.tab))
    if overlay:
        if overlay.diagrams:
            blocks.append(("diagrams", overlay.diagrams))
        blocks.extend(overlay.blocks)
    return blocks


def render(chart, out, sizes=SIZES, part=None):
    """Render one chart to a PDF of one page, or two facing pages with `# spread: yes`.
    With `part` (a PartSpec) the page shows the body through that part: its cues, its
    header blocks, chord lines only if the part wants them."""
    ch = parse_chart(chart)
    meta = ch.meta
    overlay = ch.parts.get(part.name) if part else None
    items = ch.items if part is None else part_items(ch.items, overlay, part)
    use_landscape = truthy(meta.get("landscape"))
    pages = 2 if truthy(meta.get("spread")) else 1
    if truthy(meta.get("chorus-markers")):
        items = collapse_repeated_choruses(items)
    min_size = float(meta["min-size"]) if meta.get("min-size") else min(sizes)
    sizes = [s for s in sizes if s >= min_size] or [min_size]

    pagesize = _landscape(letter) if use_landscape else letter
    W, H = pagesize
    m = 28
    diagrams, tab, prefix, suffix = ch.diagrams, ch.tab, "", ""
    if part is None:
        hl = header_layout(meta, diagrams, tab, W, m)
    else:
        prefix = part.title.upper()
        suffix = patch_label(overlay.meta.get("patch", "") if overlay else "", part.patches)
        classic = part.base and not want_orchid(overlay, part) \
            and not (overlay and (overlay.blocks or overlay.diagrams))
        if classic:
            hl = header_layout(meta, diagrams, tab, W, m)
        else:
            diagrams, tab = [], []
            hl = header_layout_blocks(meta, part_blocks(ch, overlay, part), W, m)
    header_h = hl["header_h"]
    gutter = 18
    colw = (W - 2 * m - gutter) / 2
    col_top = H - m - header_h
    colh = col_top - m
    max_cols = 2 * pages
    chosen = None
    for s in sizes:
        st = Style(s)
        cols, fits = layout(st, items, colw, colh, gutter, max_cols)
        if fits:
            chosen = (st, cols, True)
            break
    if chosen is None:
        st = Style(sizes[-1])
        cols, _ = layout(st, items, colw, colh, gutter, max_cols)
        chosen = (st, cols, False)
    st, cols, fits = chosen
    c = canvas.Canvas(out, pagesize=pagesize)
    c.setTitle(meta.get("title", "Song") + (f" ({part.title})" if part else ""))
    for p in range(pages):
        if p == 0:
            draw_header(c, meta, diagrams, tab, W, H, m, hl, prefix, suffix)
        else:
            draw_continuation_header(c, meta, W, H, m, part.title if part else "")
        draw_columns(c, st, cols[2 * p:2 * p + 2], m, col_top - colh, colw, gutter)
        c.showPage()
    c.save()
    return RenderResult(out, st.lyr, st.ch, fits, use_landscape, pages, meta,
                        part.name if part else None)


def main(argv):
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    res = render(argv[1], argv[2])
    print(f"{res.out}: lyric {res.lyric_size}pt / chords {res.chord_size}pt"
          + ("" if res.fits else "  WARNING: does not fit on one page"))
    return 0 if res.fits else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
