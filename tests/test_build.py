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


FIXTURE_BAND = Path("tests/fixtures/band")


def test_load_book_reads_parts():
    book = build.load_book(FIXTURE_BAND)
    assert [p.name for p in book.parts] == ["guitar1", "keys", "drums", "vocals"]
    g1, keys, drums = book.parts[0], book.parts[1], book.parts[2]
    assert g1.base and not keys.base
    assert keys.orchid and keys.patches == ["piano", "organ"]
    assert keys.intro == str(FIXTURE_BAND / "parts" / "keys.md")
    assert drums.chords is False and drums.default_cue == "straight time"
    assert build.load_book(FIXTURE_BOOK).parts == []


def test_load_book_rejects_bad_parts(tmp_path):
    import pytest
    book_dir = tmp_path / "b"
    (book_dir / "songs").mkdir(parents=True)
    (book_dir / "book.toml").write_text('[[parts]]\ntitle = "No name"\n', encoding="utf-8")
    with pytest.raises(SystemExit, match="needs a name"):
        build.load_book(book_dir)
    (book_dir / "book.toml").write_text('[[parts]]\nname = "keys"\nintro = "missing.md"\n', encoding="utf-8")
    with pytest.raises(SystemExit, match="intro not found"):
        build.load_book(book_dir)
    for bad in ("toc", "blank", "songbook", "drums/kit", "drums\\kit"):
        # a TOML literal (single-quoted) string keeps a backslash from being an escape
        (book_dir / "book.toml").write_text(f"[[parts]]\nname = '{bad}'\n", encoding="utf-8")
        with pytest.raises(SystemExit, match="reserved or unsafe"):
            build.load_book(book_dir)


def test_discover_rejects_unknown_part(tmp_path):
    import pytest
    book_dir = tmp_path / "band"
    shutil.copytree(FIXTURE_BAND, book_dir)
    (book_dir / "songs" / "odd.txt").write_text(
        "# title: Odd\n# group: Mellow\n\n[Verse 1]\nla\n\n@part trumpet\n[*] blow\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="trumpet"):
        build.discover(build.load_book(book_dir))
    # a book without parts ignores overlays
    (book_dir / "book.toml").write_text('title = "No parts"\n', encoding="utf-8")
    assert "odd" in [s.slug for s in build.discover(build.load_book(book_dir))]


def test_band_build_one_pdf_per_part_with_aligned_pages(tmp_path):
    out = tmp_path / "band"
    results = build.build(FIXTURE_BAND, out)
    names = ["guitar1", "keys", "drums", "vocals"]
    pdfs = {n: PdfReader(str(out / f"{n}.pdf")) for n in names}
    assert not (out / "songbook.pdf").exists()
    assert len({len(r.pages) for r in pdfs.values()}) == 1
    # page 1 cover names the part, page 2 is the gear page, page 3 the shared contents
    assert "Drums" in pdfs["drums"].pages[0].extract_text()
    assert "Keys setup" in pdfs["keys"].pages[1].extract_text()
    assert "1.  piano" in pdfs["keys"].pages[1].extract_text()
    assert "Organ is patch 2" in pdfs["keys"].pages[1].extract_text()
    assert "Drums setup" in pdfs["drums"].pages[1].extract_text()
    assert len({r.pages[2].extract_text() for r in pdfs.values()}) == 1
    full = next(r for r in results if r.song.slug == "full")
    bare = next(r for r in results if r.song.slug == "bare")
    assert full.start_page == 4 and full.pages == 1
    assert bare.pages == 2 and bare.start_page == 6 and bare.blank_before
    for r in pdfs.values():
        assert "Full Band Song" in r.pages[full.start_page - 1].extract_text()
        assert "Bare Song" in r.pages[bare.start_page - 1].extract_text()
    drums = pdfs["drums"].pages[full.start_page - 1].extract_text()
    assert "DRUMS" in drums and "groove B, crash on 1" in drums and "Em7" not in drums
    keys = pdfs["keys"].pages[full.start_page - 1].extract_text()
    assert "Orchid key: G" in keys and "Patch 2" in keys and "Em7" in keys
    # the keys part's header @image (a riff diagram) still renders and the page fits
    assert full.part_fits["keys"]
    bare_drums = pdfs["drums"].pages[bare.start_page - 1].extract_text()
    assert "straight time" in bare_drums
    assert full.part_sizes["vocals"] >= full.part_sizes["guitar1"]
    assert all(full.part_fits.values())


def test_band_build_single_part(tmp_path, capsys):
    out = tmp_path / "band"
    results = build.build(FIXTURE_BAND, out, only_part="drums")
    assert (out / "drums.pdf").exists() and not (out / "keys.pdf").exists()
    assert list(results[0].part_pdfs) == ["drums"]
    book = build.load_book(FIXTURE_BAND)
    assert build.report(results, [p for p in book.parts if p.name == "drums"])
    printed = capsys.readouterr().out
    assert "drums" in printed and "full" in printed


def test_build_unknown_only_part(tmp_path):
    import pytest
    with pytest.raises(SystemExit, match="trumpet"):
        build.build(FIXTURE_BAND, tmp_path / "x", only_part="trumpet")


def test_main_parses_part_flag(tmp_path, monkeypatch):
    rc = build.main(["build.py", str(FIXTURE_BAND), str(tmp_path / "o"), "--part", "vocals"])
    assert rc == 0
    assert (tmp_path / "o" / "vocals.pdf").exists()
