import shutil
from pathlib import Path

from pypdf import PdfReader

import build


GROUPS = ["Crowd singalongs", "Mellow", "Special"]
FIXTURE_BOOK = Path("tests/fixtures/book")


def song(slug, meta):
    return build.Song(slug, None, meta, GROUPS)


def test_order_songs_by_group_then_title():
    songs = [
        song("z", {"title": "Zed", "group": "Mellow"}),
        song("a", {"title": "Alpha", "group": "Crowd singalongs"}),
        song("m", {"title": "Mid", "group": "Mellow"}),
        song("u", {"title": "Unknown", "group": "Nope"}),
        song("n", {"title": "No group"}),
    ]
    assert [s.slug for s in build.order_songs(songs, GROUPS)] == ["a", "m", "z", "n", "u"]


def test_sort_key_is_artist_then_title_ignoring_the():
    a = song("a", {"title": "Zed", "artist": "The Cure"})
    b = song("b", {"title": "Alpha", "artist": "Oasis"})
    c = song("c", {"title": "Alpha", "artist": "The Cure"})
    assert [s.slug for s in build.order_songs([a, b, c], GROUPS)] == ["c", "a", "b"]
    assert a.label == "The Cure  —  Zed"


def test_group_of_unknown_is_other():
    assert build.group_name({"group": "Nope"}, GROUPS) == build.OTHER
    assert build.group_name({}, GROUPS) == build.OTHER
    assert build.group_name({"group": "Mellow"}, GROUPS) == "Mellow"


def test_paginate_puts_spreads_on_left_hand_pages():
    def r(pages):
        return build.BuildResult(song("s", {}), None, 12, True, False, pages)
    spread, single, spread2 = r(2), r(1), r(2)
    build.paginate([spread, single, spread2], first_page=3)
    assert spread.blank_before and spread.start_page == 4  # page 3 is right-hand, so pad
    assert single.start_page == 6
    assert spread2.blank_before and spread2.start_page == 8


def test_load_book_reads_toml_and_defaults(tmp_path):
    book = build.load_book(FIXTURE_BOOK)
    assert book.title == "Fixture Songbook"
    assert book.groups == ["Mellow", "Special"]
    assert book.logo is None
    bare = tmp_path / "my-book"
    (bare / "songs").mkdir(parents=True)
    assert build.load_book(bare).title == "My Book"


def test_build_end_to_end(tmp_path):
    out_dir = tmp_path / "build"
    results = build.build(FIXTURE_BOOK, out_dir)
    assert [r.song.slug for r in results] == ["short", "parens"]
    assert all(r.fits for r in results)
    assert (out_dir / "pages" / "short.pdf").exists()
    reader = PdfReader(str(out_dir / "songbook.pdf"))
    assert len(reader.pages) == 6  # cover, toc, short, parens, blank, back page (even)
    assert len(reader.pages) % 2 == 0
    assert "Fixture Songbook" in reader.pages[0].extract_text()
    toc = reader.pages[1].extract_text()
    assert toc.index("Johnny Fixture") < toc.index("R.E.M.")
    assert toc.index("MELLOW") < toc.index("SPECIAL")
    assert "Johnny Fixture  —  Short" in toc and "Parens" in toc
    assert "Short" in reader.pages[2].extract_text()
    assert "Parens" in reader.pages[3].extract_text()
    assert [r.start_page for r in results] == [3, 4]
    # page numbers are stamped on every page but the cover
    assert "4" in reader.pages[3].extract_text().split()
    assert "1" not in reader.pages[0].extract_text().split()


def test_build_with_logo_and_footer_mark(tmp_path):
    from PIL import Image
    book_dir = tmp_path / "logo-book"
    (book_dir / "songs").mkdir(parents=True)
    (book_dir / "assets").mkdir()
    shutil.copy(FIXTURE_BOOK / "songs" / "short.txt", book_dir / "songs" / "short.txt")
    # black square "artwork" over a black bar "wordmark", separated by a blank row band
    im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    for x in range(20, 80):
        for y in list(range(10, 60)) + list(range(80, 95)):
            im.putpixel((x, y), (0, 0, 0, 255))
    im.save(book_dir / "assets" / "logo.png")
    (book_dir / "book.toml").write_text(
        'title = "Logo Book"\nlogo = "assets/logo.png"\nfooter_mark = "auto"\n', encoding="utf-8")
    book = build.load_book(book_dir)
    mark = build.footer_mark(book)
    assert mark.getSize() == (60, 50)  # the square, without the bar
    results = build.build(book_dir, tmp_path / "out")
    assert results[0].fits
    assert (tmp_path / "out" / "songbook.pdf").exists()


def test_plan_order_keeps_spreads_on_even_pages_without_blanks():
    def r(slug, group, pages):
        return build.BuildResult(song(slug, {"title": slug, "group": group}), None, 12, True, False, pages)
    # Group A starts on page 3 (odd): a single must go first so the spread opens on 4.
    # Group B then starts on 6 (even): the spread should go first, then the single.
    results = [r("a-spread", "Mellow", 2), r("b-single", "Mellow", 1),
               r("c-single", "Special", 1), r("d-spread", "Special", 2)]
    planned = build.plan_order(results, first_page=3)
    assert [x.song.slug for x in planned] == ["b-single", "a-spread", "d-spread", "c-single"]
    build.paginate(planned, first_page=3)
    assert not any(x.blank_before for x in planned)
    assert [x.start_page for x in planned] == [3, 4, 6, 8]


def test_plan_order_falls_back_to_blank_when_group_has_no_single():
    def r(slug, group, pages):
        return build.BuildResult(song(slug, {"title": slug, "group": group}), None, 12, True, False, pages)
    planned = build.plan_order([r("a-spread", "Mellow", 2)], first_page=3)
    build.paginate(planned, first_page=3)
    assert planned[0].blank_before and planned[0].start_page == 4
