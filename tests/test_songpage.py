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


def test_parse_chart_rejects_bare_note_and_image(tmp_path):
    import pytest
    bad = write_chart(tmp_path, "# title: T\n\n@part keys\n@note\n", name="c.txt")
    with pytest.raises(ValueError, match="@note needs text"):
        songpage.parse_chart(str(bad))
    bad = write_chart(tmp_path, "# title: T\n\n@part keys\n@image\n", name="d.txt")
    with pytest.raises(ValueError, match="@image needs text"):
        songpage.parse_chart(str(bad))


def test_part_items_adds_cues_and_hides_chords(tmp_path):
    ch = songpage.parse_chart(str(write_chart(tmp_path, BAND_CHART)))
    drums = songpage.PartSpec("drums", "Drums", chords=False, default_cue="straight time")
    items = songpage.part_items(ch.items, ch.parts["drums"], drums)
    assert items == [
        ("section", "Verse 1", "groove A"),
        ("pair", [], "one two three"),
        ("section", "Chorus ×2", "groove B, crash on 1"),
        ("pair", [], "four"),
    ]
    keys = songpage.PartSpec("keys", "Keys", chords=True)
    items = songpage.part_items(ch.items, ch.parts["keys"], keys)
    assert items[0] == ("section", "Verse 1", "comp")
    assert items[1] == ("pair", [(0, "G"), (9, "D7")], "one two three")
    assert items[2] == ("section", "Chorus ×2", "")
    bass = songpage.PartSpec("bass", "Bass", chords=True, default_cue="roots")
    items = songpage.part_items(ch.items, None, bass)
    assert items[0] == ("section", "Verse 1", "roots")


def test_part_items_drops_chord_only_lines_without_chords():
    items = [("section", "Intro"), ("chords", [(0, "Am")], ""), ("pair", [(0, "Am")], "la")]
    spec = songpage.PartSpec("vocals", "Vocals", chords=False)
    assert songpage.part_items(items, None, spec) == [("section", "Intro", ""), ("pair", [], "la")]


def test_patch_label_numbers_from_bank():
    bank = ["piano", "electric piano", "organ"]
    assert songpage.patch_label("organ; piano for the verses", bank) == "Patch 3 · organ; piano for the verses"
    assert songpage.patch_label("Electric Piano", bank) == "Patch 2 · Electric Piano"
    assert songpage.patch_label("clavinet", bank) == "Patch: clavinet"
    assert songpage.patch_label("", bank) == ""


def test_chord_tokens_in_order_of_appearance():
    items = [("chords", [(0, "Am"), (4, "|"), (8, "G")], ""), ("pair", [(0, "F"), (5, "Am")], "la")]
    assert songpage.chord_tokens(items) == ["Am", "|", "G", "F", "Am"]


def test_layout_and_draw_section_cues(tmp_path):
    st = songpage.Style(12)
    items = [("section", "Verse 1", "groove A, quiet"), ("pair", [], "la la"),
             ("section", "Chorus", "a very long cue that goes on and on about the crash and the ride and the hats"),
             ("pair", [], "la la")]
    cols, fits = songpage.layout(st, items, colw=120, colh=400)
    blocks = cols[0]
    assert blocks[0]["cue"] == "groove A, quiet" and blocks[0]["cue_lines"] is None
    assert blocks[0]["h"] == st.sec_h
    assert len(blocks[2]["cue_lines"]) >= 2
    assert blocks[2]["h"] > st.sec_h
    from reportlab.pdfgen import canvas
    out = tmp_path / "cues.pdf"
    c = canvas.Canvas(str(out))
    songpage.draw_columns(c, st, cols, 28, 700, 120, 18)
    c.showPage()
    c.save()
    text = PdfReader(str(out)).pages[0].extract_text()
    # The long cue wraps onto multiple lines; where exactly it wraps depends on the
    # font (DejaVu on Linux CI vs. Arial Narrow locally), so compare wrap-independently.
    norm = " ".join(text.split())
    assert "VERSE 1" in text and "groove A, quiet" in text and "crash and the ride" in norm


def test_box_layout_corner_and_band():
    W, m = 612, 28
    small = [("mono", "groove A", ["HH|x-x-x-x-|", "BD|o---o---|"])]
    bl = songpage.box_layout(small, W, m, title_w=200)
    assert bl["mode"] == "corner" and bl["header_h"] == songpage.HEADER_H
    assert bl["box_w"] > 0
    wide = [("mono", f"groove {k}", ["HH|x-x-x-x-|x-x-x-x-|x-x-x-x-|x-x-x-|"] * 3) for k in "ABCDEF"]
    bl = songpage.box_layout(wide, W, m, title_w=200)
    assert bl["mode"] == "band" and bl["box_w"] == 0
    assert bl["header_h"] > songpage.HEADER_H
    assert len(bl["rows"]) >= 2
    assert songpage.box_layout([], W, m, 200)["mode"] == "none"


def test_measure_block_kinds(tmp_path):
    from PIL import Image
    png = tmp_path / "riff.png"
    Image.new("RGBA", (200, 50), (0, 0, 0, 255)).save(png)
    w, h, b = songpage.measure_block(("image", str(png)))
    assert h == 52 and w > h and b[0] == "image"
    w, h, b = songpage.measure_block(("note", "a note that is long enough to wrap onto a second line for sure"))
    assert b[0] == "note" and len(b[1]) >= 2 and h > 12
    w, h, b = songpage.measure_block(("diagrams", [("D7", "xx0212"), ("G", "320003")]))
    assert w > 2 * songpage.diagram_width(8)


def test_draw_header_with_blocks(tmp_path):
    from reportlab.pdfgen import canvas
    meta = {"title": "T", "artist": "A", "key": "G", "structure": "verse – chorus"}
    blocks = [("mono", "groove A", ["HH|x-x-x-x-|"]), ("note", "LH roots")]
    hl = songpage.header_layout_blocks(meta, blocks, 612, 28)
    out = tmp_path / "hdr.pdf"
    c = canvas.Canvas(str(out), pagesize=(612, 792))
    songpage.draw_header(c, meta, [], [], 612, 792, 28, hl, guide_prefix="DRUMS", guide_suffix="Patch 1 · kit")
    c.showPage()
    c.save()
    text = PdfReader(str(out)).pages[0].extract_text()
    assert "DRUMS" in text and "Key G" in text and "Patch 1" in text
    assert "groove A" in text and "LH roots" in text


def test_guide_size_shrinks_to_fit():
    from reportlab.pdfbase import pdfmetrics
    guide = " · ".join(["DRUMS", "Key G", "Standard tuning", "No capo",
                         "Patch 2 · a very long patch name for the drum kit that keeps going"])

    # A width computed from the guide's own 9pt rendering always selects 9pt, whichever
    # font resolve_fonts() picked (DejaVu on Linux CI, Arial Narrow locally, or the
    # Helvetica fallback).
    avail = pdfmetrics.stringWidth(guide, songpage.CH_FONT, 9) + 1
    assert songpage.guide_size(guide, avail) == 9

    # Effectively unlimited space keeps the largest size on the ladder.
    assert songpage.guide_size(guide, 100_000) == 10.5

    # Below the 8.5pt floor, guide_size gives up and returns 8.5 anyway.
    assert songpage.guide_size(guide, 1) == 8.5

    # Whatever size comes back, either it fits or it's the documented floor.
    for probe_avail in (1, 50, 200, avail, 100_000):
        size = songpage.guide_size(guide, probe_avail)
        assert size == 8.5 or pdfmetrics.stringWidth(guide, songpage.CH_FONT, size) <= probe_avail


def test_guide_line_fits_beside_corner_box():
    """Regression for the Blister in the Sun drums page: a part prefix plus a long
    # patch: suffix must not push the guide line under a corner-mode box."""
    from reportlab.pdfbase import pdfmetrics
    meta = {"title": "Blister in the Sun", "artist": "Violent Femmes", "key": "G",
            "structure": "verse – chorus"}
    blocks = [("mono", "groove A", ["HH|x-x-x-x-|x-x-x-x-|", "BD|o---o---|o---o---|"])]
    hl = songpage.header_layout_blocks(meta, blocks, 612, 28)
    assert hl["box"]["mode"] == "corner"
    box_w = hl["box_w"]
    bx = 612 - 28 - box_w
    avail = (bx - 8 if box_w else 612 - 28) - 28
    guide = " · ".join(["DRUMS", "Key G", "Standard tuning", "No capo",
                         "Patch 2 · a very long patch name for the drum kit that keeps going"])
    size = songpage.guide_size(guide, avail)
    assert size == 8.5 or pdfmetrics.stringWidth(guide, songpage.CH_FONT, size) <= avail

    # A short guide always keeps the largest size, regardless of the box width.
    short_guide = "DRUMS · Key G"
    assert songpage.guide_size(short_guide, avail) == 10.5


def test_render_part_pages(tmp_path):
    chart = write_chart(tmp_path, BAND_CHART)
    drums = songpage.PartSpec("drums", "Drums", chords=False, patches=["acoustic kit", "808"])
    res = songpage.render(str(chart), str(tmp_path / "drums.pdf"), part=drums)
    assert res.part == "drums" and res.fits
    text = PdfReader(str(tmp_path / "drums.pdf")).pages[0].extract_text()
    assert "DRUMS" in text and "Patch 1" in text
    assert "groove A" in text and "HH|x-x-x-x-|" in text
    assert "crash on 1" in text
    assert "D7" not in text  # chord lines hidden

    keys = songpage.PartSpec("keys", "Keys", chords=True, orchid=True)
    songpage.render(str(chart), str(tmp_path / "keys.pdf"), part=keys)
    text = PdfReader(str(tmp_path / "keys.pdf")).pages[0].extract_text()
    assert "Orchid key: G" in text and "D7" in text and "dominant 7th" in text
    assert "LH roots" in text

    g1 = songpage.PartSpec("guitar1", "Guitar 1", base=True)
    songpage.render(str(chart), str(tmp_path / "g1.pdf"), part=g1)
    text = PdfReader(str(tmp_path / "g1.pdf")).pages[0].extract_text()
    assert "GUITAR 1" in text and "D7" in text and "groove" not in text

    bass = songpage.PartSpec("bass", "Bass", default_cue="roots")
    songpage.render(str(chart), str(tmp_path / "bass.pdf"), part=bass)
    text = PdfReader(str(tmp_path / "bass.pdf")).pages[0].extract_text()
    assert "roots" in text


def test_guide_line_drops_tuning_and_capo_for_non_guitar_part(tmp_path):
    chart = write_chart(tmp_path, """
    # title: T
    # artist: A
    # key: G
    # tuning: Standard tuning
    # capo: No capo

    [Verse 1]
    G        D7
    one two three

    @part keys
    [Verse 1] comp
    """)
    keys = songpage.PartSpec("keys", "Keys", guitar=False)
    songpage.render(str(chart), str(tmp_path / "keys.pdf"), part=keys)
    text = PdfReader(str(tmp_path / "keys.pdf")).pages[0].extract_text()
    assert "KEYS" in text and "Key G" in text
    assert "tuning" not in text.lower() and "capo" not in text.lower()

    guitar1 = songpage.PartSpec("guitar1", "Guitar 1", base=True)
    songpage.render(str(chart), str(tmp_path / "g1.pdf"), part=guitar1)
    text = PdfReader(str(tmp_path / "g1.pdf")).pages[0].extract_text()
    assert "Standard tuning" in text and "No capo" in text


def test_part_orchid_override(tmp_path):
    chart = write_chart(tmp_path, BAND_CHART + "\n# orchid: no\n")
    keys = songpage.PartSpec("keys", "Keys", orchid=True)
    songpage.render(str(chart), str(tmp_path / "keys.pdf"), part=keys)
    assert "Orchid key" not in PdfReader(str(tmp_path / "keys.pdf")).pages[0].extract_text()


def test_render_without_part_is_unchanged(tmp_path):
    res = songpage.render(FIXTURE, str(tmp_path / "classic.pdf"))
    assert res.part is None and res.fits


def test_orchid_override_shows_legend_for_base_part(tmp_path):
    chart = write_chart(tmp_path, """
    # title: T
    # key: G

    [Verse 1]
    G        D7
    one two three

    @part guitar1
    # orchid: yes
    """)
    g1 = songpage.PartSpec("guitar1", "Guitar 1", base=True)
    songpage.render(str(chart), str(tmp_path / "g1.pdf"), part=g1)
    text = PdfReader(str(tmp_path / "g1.pdf")).pages[0].extract_text()
    assert "Orchid key: G" in text


def test_continuation_header_shows_part_title(tmp_path):
    chart = write_chart(tmp_path, """
    # title: T
    # artist: A
    # key: G
    # spread: yes

    [Verse 1]
    G        D7
    one two three

    @part drums
    [*] groove A
    """)
    drums = songpage.PartSpec("drums", "Drums", chords=False)
    songpage.render(str(chart), str(tmp_path / "drums.pdf"), part=drums)
    text = PdfReader(str(tmp_path / "drums.pdf")).pages[1].extract_text()
    assert "Drums" in text and "A" in text
