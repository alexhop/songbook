#!/usr/bin/env python3
"""
build.py — render a book of chord charts to one printable PDF.

Usage:  python3 build.py [book_dir] [build_dir]

A book is a directory holding `book.toml` (title, logo, group order), `songs/*.txt`
charts and any assets. With no argument the book named in BOOK.md is built. Output goes
to build/<book name>/: one PDF per song under pages/, then songbook.pdf with a cover, a
table of contents grouped by `# group:`, every song, and a back page.

Songs are ordered by group, then arranged within each group so a two-page spread always
opens on a left-hand (even) page; a blank page is inserted only when unavoidable.

Exit status is non-zero if any song did not fit on one page at its minimum size.
"""
import io
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

import songpage

OTHER = "Other"
ROOT = Path(__file__).parent
FOOTER_MARK_H = 22  # pt; sits in the 28pt bottom margin, never over lyrics


@dataclass
class Book:
    dir: Path
    title: str
    cover_word: str = "Songbook"
    subtitle: str = ""
    logo: Path | None = None
    footer_mark: str = "auto"   # "auto", "none", or an image path
    groups: list[str] = field(default_factory=list)
    parts: list = field(default_factory=list)   # songpage.PartSpec, in book order

    @property
    def name(self):
        return self.dir.name

    @property
    def songs_dir(self):
        return self.dir / "songs"


def load_parts(cfg, book_dir):
    """The [[parts]] tables of book.toml as PartSpecs; the first one is the base part."""
    parts = []
    for i, p in enumerate(cfg.get("parts", [])):
        if not p.get("name"):
            raise SystemExit(f"{book_dir / 'book.toml'}: every [[parts]] entry needs a name")
        intro = book_dir / p["intro"] if p.get("intro") else None
        if intro is not None and not intro.exists():
            raise SystemExit(f"{book_dir / 'book.toml'}: intro not found: {intro}")
        parts.append(songpage.PartSpec(
            name=p["name"], title=p.get("title", p["name"].title()),
            chords=bool(p.get("chords", True)), default_cue=p.get("default_cue", ""),
            orchid=bool(p.get("orchid", False)), patches=list(p.get("patches", [])),
            intro=str(intro) if intro else None, base=i == 0))
    return parts


def load_book(book_dir):
    """Read book.toml from a book directory; every key is optional."""
    book_dir = Path(book_dir)
    cfg = {}
    toml = book_dir / "book.toml"
    if toml.exists():
        cfg = tomllib.loads(toml.read_text(encoding="utf-8"))
    logo = book_dir / cfg["logo"] if cfg.get("logo") else None
    if logo is not None and not logo.exists():
        raise SystemExit(f"{toml}: logo not found: {logo}")
    mark = cfg.get("footer_mark", "auto")
    if mark not in ("auto", "none"):
        mark = str(book_dir / mark)
    return Book(
        dir=book_dir,
        title=cfg.get("title") or book_dir.name.replace("-", " ").title(),
        cover_word=cfg.get("cover_word", "Songbook"),
        subtitle=cfg.get("subtitle", ""),
        logo=logo,
        footer_mark=mark,
        groups=list(cfg.get("groups", [])),
        parts=load_parts(cfg, book_dir),
    )


def default_book_dir():
    """The book named in BOOK.md next to this script (`books/<name>`)."""
    book_md = ROOT / "BOOK.md"
    if book_md.exists():
        m = re.search(r"books/[\w.-]+", book_md.read_text(encoding="utf-8"))
        if m:
            return ROOT / m.group()
    raise SystemExit("no book given and BOOK.md does not name one; usage: build.py books/<name>")


def draw_logo(c, logo, cx, top, width):
    """Draw `logo` centred on cx with its top edge at `top`; returns its bottom."""
    if logo is None:
        return top
    from reportlab.lib.utils import ImageReader
    img = ImageReader(str(logo))
    iw, ih = img.getSize()
    h = width * ih / iw
    c.drawImage(img, cx - width / 2, top - h, width, h, mask="auto")
    return top - h


@dataclass
class Song:
    slug: str
    path: Path | None
    meta: dict
    groups: list[str] = field(default_factory=list)

    @property
    def title(self):
        return self.meta.get("title") or self.slug

    @property
    def artist(self):
        return self.meta.get("artist", "")

    @property
    def group(self):
        return group_name(self.meta, self.groups)

    @property
    def sort_key(self):
        """Artist then title, ignoring a leading "The"."""
        artist = self.artist.lower()
        if artist.startswith("the "):
            artist = artist[4:]
        return (artist, self.title.lower())

    @property
    def label(self):
        return (self.artist + "  —  " + self.title) if self.artist else self.title


@dataclass
class BuildResult:
    song: Song
    page_pdf: Path
    lyric_size: float
    fits: bool
    landscape: bool
    pages: int
    start_page: int = 0       # book page number, assigned by paginate()
    blank_before: bool = False


def plan_order(results, first_page):
    """Order songs within each group so two-page spreads open on a left-hand (even) page.
    On an even page a spread goes next if one remains; on an odd page a single-page song
    does. Title order is kept within each kind. A blank page is only needed when a group
    runs out of single-page songs at an odd page."""
    planned = []
    page = first_page
    for group in dict.fromkeys(r.song.group for r in results):
        singles = [r for r in results if r.song.group == group and r.pages == 1]
        spreads = [r for r in results if r.song.group == group and r.pages == 2]
        while singles or spreads:
            want_spread = page % 2 == 0
            pick = (spreads if want_spread and spreads else singles) or spreads
            r = pick.pop(0)
            if r.pages == 2 and page % 2 == 1:
                page += 1  # blank page
            planned.append(r)
            page += r.pages
    return planned


def paginate(results, first_page):
    """Assign book page numbers. A two-page spread must open on a left-hand (even) page
    so both halves face each other; a blank page is inserted before it when needed."""
    page = first_page
    for r in results:
        r.blank_before = r.pages == 2 and page % 2 == 1
        if r.blank_before:
            page += 1
        r.start_page = page
        page += r.pages
    return results


def group_name(meta, groups):
    g = meta.get("group", "")
    return g if g in groups else OTHER


def order_songs(items, groups):
    """Sort Songs (or BuildResults) by group order, then artist, then title."""
    order = {g: i for i, g in enumerate(groups)}
    song = lambda x: x.song if isinstance(x, BuildResult) else x
    return sorted(items, key=lambda x: (order.get(song(x).group, len(order)), song(x).sort_key))


def discover(book):
    songs = []
    known = {p.name for p in book.parts}
    for p in sorted(book.songs_dir.glob("*.txt")):
        ch = songpage.parse_chart(str(p))
        unknown = [n for n in ch.parts if n not in known]
        if known and unknown:
            raise SystemExit(f"{p}: @part {', '.join(unknown)} not in book.toml parts "
                             f"({', '.join(sorted(known))})")
        songs.append(Song(slug=p.stem, path=p, meta=ch.meta, groups=book.groups))
    return order_songs(songs, book.groups)


def draw_cover(out, book):
    W, H = letter
    c = canvas.Canvas(str(out), pagesize=letter)
    c.setTitle(book.title)
    c.setFillColorRGB(0, 0, 0)
    if book.logo is not None:
        bottom = draw_logo(c, book.logo, W / 2, H - 120, 400)
        c.setFont(songpage.CH_FONT, 40)
        c.drawCentredString(W / 2, bottom - 60, book.cover_word)
        y = bottom - 86
    else:
        c.setFont(songpage.CH_FONT, 40)
        c.drawCentredString(W / 2, H / 2 + 40, book.title)
        y = H / 2 + 8
    if book.subtitle:
        c.setFont(songpage.LYR_FONT, 14)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        c.drawCentredString(W / 2, y, book.subtitle)
    c.showPage()
    c.save()


def draw_back(out, book):
    W, H = letter
    c = canvas.Canvas(str(out), pagesize=letter)
    draw_logo(c, book.logo, W / 2, H / 2 + 110, 220)
    c.showPage()
    c.save()


def draw_blank(out):
    c = canvas.Canvas(str(out), pagesize=letter)
    c.showPage()
    c.save()


def draw_toc(out, results, book):
    """One or more TOC pages listing songs by group, in artist-then-title order, with
    their book page numbers (the pages themselves may sit in a different order so that
    spreads open flat)."""
    results = order_songs(results, book.groups)
    W, H = letter
    m = 56
    line_h = 17
    c = canvas.Canvas(str(out), pagesize=letter)
    c.setTitle("Contents")

    def new_page():
        c.setFont(songpage.CH_FONT, 22)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(m, H - m - 22, "Contents")
        draw_logo(c, book.logo, W - m - 30, H - m + 8, 60)
        return H - m - 22 - 40

    y = new_page()
    current_group = None
    for r in results:
        s = r.song
        if s.group != current_group:
            if y - 2 * line_h < m:
                c.showPage()
                y = new_page()
            current_group = s.group
            y -= 8
            c.setFont(songpage.CH_FONT, 12)
            c.setFillColorRGB(0.25, 0.25, 0.25)
            c.drawString(m, y, current_group.upper())
            y -= line_h
        if y < m:
            c.showPage()
            y = new_page()
        c.setFont(songpage.LYR_FONT, 12)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(m + 12, y, s.label)
        c.drawRightString(W - m, y, str(r.start_page))
        y -= line_h
    c.showPage()
    c.save()


def footer_mark(book):
    """The small image for song-page footers. "auto" takes the logo's artwork without
    its wordmark, which is unreadable at footer size: the crop is at the first blank row
    below 60% of the image height."""
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    if book.footer_mark == "none":
        return None
    if book.footer_mark != "auto":
        return ImageReader(book.footer_mark)
    if book.logo is None:
        return None
    im = Image.open(book.logo).convert("RGBA")
    alpha, (w, h) = im.getchannel("A"), im.size
    cut = next((y for y in range(int(h * 0.6), h)
                if alpha.crop((0, y, w, y + 1)).getbbox() is None), h)
    art = im.crop((0, 0, w, cut))
    return ImageReader(art.crop(art.getbbox()))


def stamp_page_numbers(writer, first_song_page, book):
    """Number every page after the cover at its outer bottom corner: even pages are
    left-hand pages (number at the left), odd pages right-hand (number at the right).
    Song pages also get the footer mark at the inner (spine) corner; contents pages
    already carry the logo at the top."""
    mark = footer_mark(book)
    for i, page in enumerate(writer.pages):
        number = i + 1
        if number == 1:
            continue
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        c.setFont(songpage.LYR_FONT, 9)
        c.setFillColorRGB(0.35, 0.35, 0.35)
        left_hand = number % 2 == 0
        if left_hand:
            c.drawString(28, 14, str(number))
        else:
            c.drawRightString(w - 28, 14, str(number))
        if number >= first_song_page and mark is not None:
            mw, mh = mark.getSize()
            mark_w = FOOTER_MARK_H * mw / mh
            x = w - 28 - mark_w if left_hand else 28
            c.setFillAlpha(0.5)
            c.drawImage(mark, x, 4, mark_w, FOOTER_MARK_H, mask="auto")
        c.showPage()
        c.save()
        buf.seek(0)
        page.merge_page(PdfReader(buf).pages[0])


def build(book_dir, build_dir=None):
    book = load_book(book_dir)
    build_dir = Path(build_dir) if build_dir else ROOT / "build" / book.name
    pages_dir = build_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for s in discover(book):
        page_pdf = pages_dir / f"{s.slug}.pdf"
        r = songpage.render(str(s.path), str(page_pdf))
        results.append(BuildResult(s, page_pdf, r.lyric_size, r.fits, r.landscape, r.pages))

    cover = build_dir / "cover.pdf"
    toc = build_dir / "toc.pdf"
    blank = build_dir / "blank.pdf"
    draw_cover(cover, book)
    draw_blank(blank)
    # TOC page count is not known until it is drawn; draw once to measure, then redraw
    # with the correct page numbers.
    results = plan_order(results, first_page=3)
    draw_toc(toc, paginate(results, first_page=3), book)
    toc_pages = len(PdfWriter(clone_from=str(toc)).pages)
    if toc_pages > 1:
        results = plan_order(results, first_page=2 + toc_pages)
    draw_toc(toc, paginate(results, first_page=2 + toc_pages), book)

    writer = PdfWriter()
    writer.append(str(cover))
    writer.append(str(toc))
    for r in results:
        if r.blank_before:
            writer.append(str(blank))
        writer.append(str(r.page_pdf))
    stamp_page_numbers(writer, first_song_page=2 + toc_pages, book=book)
    # Back page on an even page so it is the outside back cover when printed.
    if len(writer.pages) % 2 == 0:
        writer.append(str(blank))
    back = build_dir / "back.pdf"
    draw_back(back, book)
    writer.append(str(back))
    writer.add_metadata({"/Title": book.title})
    with open(build_dir / "songbook.pdf", "wb") as f:
        writer.write(f)
    return results


def report(results):
    rows = [(r.song.slug, r.song.title, r.song.group, f"p{r.start_page}",
             f"{r.lyric_size:g}pt",
             ("landscape" if r.landscape else "portrait") + (" spread" if r.pages == 2 else ""),
             "ok" if r.fits else "DOES NOT FIT") for r in results]
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))] if rows else []
    for row in rows:
        print("  ".join(cell.ljust(w) for cell, w in zip(row, widths)))
    blanks = [r.song.slug for r in results if r.blank_before]
    if blanks:
        print(f"\nblank page inserted before: {', '.join(blanks)}")
    bad = [r for r in results if not r.fits]
    if bad:
        print(f"\nWARNING: {len(bad)} song(s) do not fit on one page: "
              + ", ".join(r.song.slug for r in bad), file=sys.stderr)
    return not bad


def main(argv):
    book_dir = Path(argv[1]) if len(argv) > 1 else default_book_dir()
    build_dir = Path(argv[2]) if len(argv) > 2 else ROOT / "build" / book_dir.name
    results = build(book_dir, build_dir)
    ok = report(results)
    print(f"\n{build_dir / 'songbook.pdf'}: {len(results)} song(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
