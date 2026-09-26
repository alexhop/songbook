import textwrap

from pypdf import PdfReader

import songpage

FIXTURE = "tests/fixtures/book/songs/parens.txt"


def write_chart(tmp_path, text, name="song.txt"):
    p = tmp_path / name
    p.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return p


def test_fonts_registered():
    assert songpage.LYR_FONT
    assert songpage.CH_FONT
    assert songpage.MONO


def test_chord_line_detection():
    assert songpage.is_chord_line("E   |   E   A   Asus4   A   Asus4   A   |   (x2)")
    assert songpage.is_chord_line("C#m                   Bm          A   Asus4")
    assert songpage.is_chord_line("N.C.  E/G#  Bsus4")
    assert songpage.is_chord_line("A         D    (D C# F#) D        E")
    assert not songpage.is_chord_line("(fade out)")
    assert not songpage.is_chord_line("Looking at your watch a third time")
    assert not songpage.is_chord_line("")


def test_parse_fixture():
    meta, diagrams, tab, items = songpage.parse(FIXTURE)
    assert meta["title"] == "(Don't Go Back To) Parens"
    assert meta["group"] == "Special"
    assert diagrams == [("Asus4", "x00230")]
    assert len(tab) == 7
    assert items[0] == ("section", "Intro")
    assert items[1][0] == "chords"
    assert items[2] == ("section", "Verse 1")
    assert [i[1] for i in items if i[0] == "section"] == [
        "Intro", "Verse 1", "Verse 2", "Chorus", "Verse 3", "Chorus", "Bridge", "Chorus ×2",
    ]


CHART_WITH_CHORUSES = """
    # title: T
    # artist: A

    [Verse 1]
    E
    one
    [Chorus]
    A
    two
    B
    three
    [Verse 2]
    E
    four
    [Chorus]
    A
    two
    B
    three
    [Chorus ×2]
    A
    two
    B
    three
"""


def test_collapse_repeated_choruses_keeps_first_full():
    items = [
        ("section", "Chorus"), ("pair", [(0, "A")], "two"),
        ("section", "Verse 2"), ("pair", [(0, "E")], "four"),
        ("section", "Chorus"), ("pair", [(0, "A")], "two"),
        ("section", "Chorus ×2"), ("pair", [(0, "A")], "two"),
    ]
    out = songpage.collapse_repeated_choruses(items)
    assert out == [
        ("section", "Chorus"), ("pair", [(0, "A")], "two"),
        ("section", "Verse 2"), ("pair", [(0, "E")], "four"),
        ("marker", "Chorus"),
        ("marker", "Chorus ×2"),
    ]


def test_truthy():
    assert songpage.truthy("yes")
    assert songpage.truthy("True")
    assert songpage.truthy("1")
    assert not songpage.truthy("no")
    assert not songpage.truthy("")
    assert not songpage.truthy(None)


def test_render_fixture_returns_result(tmp_path):
    out = tmp_path / "parens.pdf"
    res = songpage.render(FIXTURE, str(out))
    assert res.fits
    assert res.lyric_size >= 10
    assert not res.landscape
    reader = PdfReader(str(out))
    assert len(reader.pages) == 1
    w, h = reader.pages[0].mediabox.width, reader.pages[0].mediabox.height
    assert h > w


def test_render_landscape_and_markers(tmp_path):
    chart = write_chart(tmp_path, "# landscape: yes\n# chorus-markers: yes\n" + CHART_WITH_CHORUSES)
    out = tmp_path / "out.pdf"
    res = songpage.render(str(chart), str(out))
    assert res.landscape
    page = PdfReader(str(out)).pages[0]
    assert page.mediabox.width > page.mediabox.height
    text = page.extract_text()
    assert "AS BEFORE" in text.upper()


def test_min_size_stops_shrinking(tmp_path):
    long_chart = "# title: Long\n# min-size: 13\n" + "\n".join(
        f"[Verse {n}]\nE        A        B        E\n" + "la " * 30 for n in range(1, 30)
    )
    chart = write_chart(tmp_path, long_chart)
    res = songpage.render(str(chart), str(tmp_path / "long.pdf"))
    assert res.lyric_size == 13
    assert not res.fits


def test_chordless_atoms_are_not_padded():
    st = songpage.Style(12)
    # "A" lands mid-word on "long": the chord-less "l" atom must keep its own width.
    lyric = "before too long"
    chords = [(0, "Bm"), (12, "A")]
    (vis, chord_only), = songpage.wrap_line(st, chords, lyric, colw=400, placeholder=False)
    assert not chord_only
    for chord, text, adv in vis:
        if chord is None:
            assert adv == st.tw(text, False)


def test_spread_renders_two_pages(tmp_path):
    long_chart = "# title: Long\n# spread: yes\n" + "\n".join(
        f"[Verse {n}]\nE        A        B        E\n" + "la " * 20 for n in range(1, 25)
    )
    chart = write_chart(tmp_path, long_chart)
    out = tmp_path / "long.pdf"
    res = songpage.render(str(chart), str(out))
    assert res.pages == 2
    assert res.fits
    reader = PdfReader(str(out))
    assert len(reader.pages) == 2
    assert "continued" in reader.pages[1].extract_text().lower()


def test_form_line_shrinks_beside_a_wide_header_box(tmp_path):
    chart = write_chart(tmp_path, "# title: Wide\n# structure: " + "section – " * 20 + "end\n"
                        + "".join(f"@diagram X{n} x0{n}23x\n" for n in range(6)).replace("X", "C")
                        + "\n[Verse 1]\nC\nla la\n")
    out = tmp_path / "wide.pdf"
    songpage.render(str(chart), str(out))
    assert PdfReader(str(out)).pages[0].extract_text().count("section") == 20


BAND_CHART = """
    # title: T
    # artist: A
    # key: G

    @diagram D7 xx0212

    [Verse 1]
    G        D7
    one two three
    [Chorus ×2]
    C
    four

    @part drums
    # patch: acoustic kit
    @grid groove A
    HH|x-x-x-x-|
    BD|o---o---|

    @grid groove B
    HH|o-o-o-o-|
    [*] groove A
    [Chorus] groove B, crash on 1

    @part keys
    @note LH roots, RH pad
    @diagram Gmaj7 320002
    [Verse 1] comp
    """


def test_parse_chart_collects_parts(tmp_path):
    ch = songpage.parse_chart(str(write_chart(tmp_path, BAND_CHART)))
    assert ch.meta["key"] == "G"
    assert ch.diagrams == [("D7", "xx0212")]
    assert [i[1] for i in ch.items if i[0] == "section"] == ["Verse 1", "Chorus ×2"]
    assert list(ch.parts) == ["drums", "keys"]
    drums = ch.parts["drums"]
    assert drums.meta == {"patch": "acoustic kit"}
    assert drums.blocks == [
        ("mono", "groove A", ["HH|x-x-x-x-|", "BD|o---o---|"]),
        ("mono", "groove B", ["HH|o-o-o-o-|"]),
    ]
    assert drums.cues == {"*": "groove A", "chorus": "groove B, crash on 1"}
    keys = ch.parts["keys"]
    assert keys.blocks == [("note", "LH roots, RH pad")]
    assert keys.diagrams == [("Gmaj7", "320002")]
    assert keys.cues == {"verse 1": "comp"}


def test_parse_keeps_four_tuple_and_ignores_parts(tmp_path):
    meta, diagrams, tab, items = songpage.parse(str(write_chart(tmp_path, BAND_CHART)))
    assert meta["title"] == "T"
    assert diagrams == [("D7", "xx0212")]
    assert tab == []
    assert items[-1] == ("pair", [(0, "C")], "four")


def test_cue_key_strips_notes_and_repeats():
    assert songpage.cue_key("Verse 3 – quiet, palm-muted") == "verse 3"
    assert songpage.cue_key("Chorus ×2") == "chorus"
    assert songpage.cue_key("Outro (x4)") == "outro"
    assert songpage.cue_key("*") == "*"


def test_parse_chart_rejects_stray_lines_and_nameless_parts(tmp_path):
    import pytest
    bad = write_chart(tmp_path, "# title: T\n\n@part drums\nsome stray words\n")
    with pytest.raises(ValueError, match="stray words"):
        songpage.parse_chart(str(bad))
    bad = write_chart(tmp_path, "# title: T\n\n@part\n", name="b.txt")
    with pytest.raises(ValueError, match="needs a name"):
        songpage.parse_chart(str(bad))
