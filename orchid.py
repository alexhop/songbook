"""
orchid.py — the keys-page legend for a Telepathic Instruments Orchid.

The Orchid is set to the song's key; the player presses a modifier for the chord
quality, then the key for the root. legend() maps every chord in a chart to that pair
and its scale degree, and says when a chord lies outside the key.
"""
import re

PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
MAJOR, MINOR = (0, 2, 4, 5, 7, 9, 11), (0, 2, 3, 5, 7, 8, 10)
QUALITY = {
    MAJOR: ("major", "minor", "minor", "major", "major", "minor", "diminished"),
    MINOR: ("minor", "diminished", "major", "minor", "minor", "major", "major"),
}
NUMERAL = ("I", "II", "III", "IV", "V", "VI", "VII")
CHROMATIC = {
    MAJOR: {1: "bII", 3: "bIII", 6: "#IV", 8: "bVI", 10: "bVII"},
    MINOR: {1: "bII", 4: "#III", 6: "#IV", 9: "#VI", 11: "#VII"},
}
# suffix -> (modifier to press, triad class for the in-key test). The modifier names
# are placeholders until they are checked against the Orchid's own labels.
SUFFIXES = {
    "": ("major", "major"), "m": ("minor", "minor"), "min": ("minor", "minor"),
    "7": ("dominant 7th", "major"), "9": ("dominant 7th", "major"),
    "maj7": ("major 7th", "major"), "M7": ("major 7th", "major"),
    "m7": ("minor 7th", "minor"), "m6": ("minor", "minor"), "6": ("major", "major"),
    "dim": ("diminished", "diminished"), "m7b5": ("diminished", "diminished"),
    "aug": ("augmented", "major"), "+": ("augmented", "major"),
    "sus2": ("sus2", "any"), "sus4": ("sus4", "any"), "sus": ("sus4", "any"),
    "add9": ("add9", "major"), "2": ("add9", "major"), "5": ("power chord", "any"),
}
CHORD = re.compile(r"^([A-G][#b]?)(.*?)(?:/([A-G][#b]?))?$")


def pitch(note):
    return (PITCH[note[0]] + {"#": 1, "b": -1}.get(note[1:], 0)) % 12


def parse_key(key):
    m = CHORD.match((key or "").strip())
    if not m:
        return None
    return m.group(1), (MINOR if m.group(2) in ("m", "min", "minor") else MAJOR)


def parse_chord(name):
    """(root, modifier, triad_class, bass), or None for |, (x2), N.C. and the like.
    An unknown suffix is printed as written and treated as a major triad."""
    m = CHORD.match(name.strip("()"))
    if not m:
        return None
    root, suffix, bass = m.groups()
    suffix = suffix.replace("(no3)", "")
    if suffix not in SUFFIXES:
        return root, suffix, "major", bass
    modifier, triad = SUFFIXES[suffix]
    return root, modifier, triad, bass


def legend(key, chords):
    """Rows (chord, modifier, root, degree text, in_key) in order of first appearance."""
    parsed = parse_key(key)
    if parsed is None:
        return []
    tonic, scale = parsed
    rows, seen = [], set()
    for token in chords:
        ch = parse_chord(token)
        if ch is None or token in seen:
            continue
        seen.add(token)
        root, modifier, triad, bass = ch
        semis = (pitch(root) - pitch(tonic)) % 12
        if semis in scale:
            idx = scale.index(semis)
            expected = QUALITY[scale][idx]
            in_key = triad == "any" or triad == expected
            numeral = NUMERAL[idx]
            shown = expected if triad == "any" else triad
            if shown != "major":
                numeral = numeral.lower()
            if shown == "diminished":
                numeral += "°"
        else:
            numeral, in_key = CHROMATIC[scale][semis], False
        text = numeral + ("" if in_key else ", outside the key") + (f", over {bass}" if bass else "")
        rows.append((token, modifier, root, text, in_key))
    return rows


def legend_lines(key, chords):
    rows = legend(key, chords)
    if not rows:
        return []
    w = max(len(r[0]) for r in rows)
    return [f"{ch.ljust(w)} = {mod}, {root} ({text})" for ch, mod, root, text, _ in rows]
