import orchid


def test_parse_key():
    assert orchid.parse_key("G") == ("G", orchid.MAJOR)
    assert orchid.parse_key("Am") == ("A", orchid.MINOR)
    assert orchid.parse_key("F#m") == ("F#", orchid.MINOR)
    assert orchid.parse_key("") is None


def test_parse_chord():
    assert orchid.parse_chord("Em7") == ("E", "minor 7th", "minor", None)
    assert orchid.parse_chord("D7") == ("D", "dominant 7th", "major", None)
    assert orchid.parse_chord("C/G") == ("C", "major", "major", "G")
    assert orchid.parse_chord("Asus4") == ("A", "sus4", "any", None)
    assert orchid.parse_chord("(D") == ("D", "major", "major", None)
    assert orchid.parse_chord("F#m7add11") == ("F#", "m7add11", "major", None)
    assert orchid.parse_chord("|") is None
    assert orchid.parse_chord("(x2)") is None
    assert orchid.parse_chord("N.C.") is None


def test_legend_major_key():
    rows = orchid.legend("G", ["G", "Em7", "D7", "B", "C/G", "G", "|", "F"])
    assert [r[0] for r in rows] == ["G", "Em7", "D7", "B", "C/G", "F"]
    assert rows[0] == ("G", "major", "G", "I", True)
    assert rows[1] == ("Em7", "minor 7th", "E", "vi", True)
    assert rows[2] == ("D7", "dominant 7th", "D", "V", True)
    assert rows[3] == ("B", "major", "B", "III, outside the key", False)
    assert rows[4] == ("C/G", "major", "C", "IV, over G", True)
    assert rows[5] == ("F", "major", "F", "bVII, outside the key", False)


def test_legend_major_key_tritone_is_sharp_iv():
    # The tritone above the tonic is spelled #IV in both major and minor keys.
    rows = {r[0]: r for r in orchid.legend("F", ["F", "Bm"])}
    assert rows["Bm"][3] == "#IV, outside the key"


def test_legend_minor_key():
    rows = {r[0]: r for r in orchid.legend("Am", ["Am", "F", "G", "E7", "Bm", "Bdim", "C"])}
    assert rows["Am"][3] == "i" and rows["Am"][4]
    assert rows["F"][3] == "VI" and rows["G"][3] == "VII" and rows["C"][3] == "III"
    assert rows["E7"][3] == "V, outside the key"
    assert rows["Bm"][3] == "ii, outside the key"
    assert rows["Bdim"][3] == "ii°"


def test_legend_lines_align_and_handle_no_key():
    lines = orchid.legend_lines("G", ["G", "Em7"])
    assert lines == ["G   = major, G (I)", "Em7 = minor 7th, E (vi)"]
    assert orchid.legend_lines("", ["G"]) == []
