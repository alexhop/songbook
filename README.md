# Songbook

Turn a folder of chord charts into a printable songbook: one song per page, chords
above the lyrics in two columns, chord diagrams and a lick of tab in the corner, a
cover, a table of contents by category, page numbers, and a back page. Made for
singalongs where the pages have to be readable by firelight.

## Quick start

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python build.py books/example
open build/example/songbook.pdf
```

`build.py` prints one line per song with its page number and lyric size, and fails if
a song did not fit on its page. Add `--part <name>` to build a single instrument's
book from a `book.toml` with a `[[parts]]` list (see "Band books").

## Make your own book

1. Copy `books/example` to `books/<your-name>`.
2. Edit `book.toml`:

   ```toml
   title = "Our Songbook"
   cover_word = "Songbook"          # printed under the logo on the cover
   subtitle = "Songs for the porch"
   logo = "assets/logo.png"         # PNG with transparency; delete the line for a text cover
   footer_mark = "auto"             # small logo in each page's footer: "auto", "none", or a path
   groups = ["Singalongs", "Ballads"]   # order of the contents sections
   ```

3. Replace `assets/logo.png` with your own artwork, or remove the `logo` line.
4. Replace the charts in `songs/` with yours (format below), one file per song.
5. Put `books/<your-name>` in `BOOK.md` so `build.py` with no arguments builds it.
6. Run `.venv/bin/python build.py`.

The example book's songs are all public domain. The charts you add are yours to
license; this repository's MIT licence covers the tool.

## Chart format

A plain text file, chords on the line above the words they fall on:

```
# title: Oh! Susanna
# artist: Stephen Foster
# key: G
# capo: No capo
# group: Singalongs
# structure: verse 1 – chorus – verse 2 – chorus – verse 3 – chorus

@diagram D7 xx0212

[Verse 1]
G                          D7
I come from Alabama with a banjo on my knee
G                                  D7          G
I'm going to Louisiana, my true love for to see

[Chorus]
C            G              D7
Oh! Susanna, oh don't you cry for me
```

- `# key:`, `# tuning:` and `# capo:` print on the guide line under the title.
- `# group:` puts the song under that heading in the contents. Groups appear in the
  order listed in `book.toml`; anything else goes last under "Other".
- `[Section]` headings print as small labels. `[Chorus ×2]` and cues like
  `[Verse 3 – as verse 1]` are just text.
- A line whose every token is a chord is a chord line. If no lyric follows it, it prints
  on its own, which is how you write intros and instrumentals:
  `G   |   C   |   D7   |   G   |   (x2)`.
- `@diagram NAME frets` adds a chord box to the header. Frets run low string to high,
  `x` mutes and `0` is open: `@diagram D7 xx0212`.
- `@tab` starts a tab block for the header box and ends at a blank line or the next line
  starting with `[`, `@` or `#`. Include only the strings the lick uses.
- Chords align by column, so use spaces, not tabs, and keep chord names above the
  syllable they land on.

Per-song switches, all off by default:

| Line | Effect |
| --- | --- |
| `# landscape: yes` | landscape page, wider columns |
| `# spread: yes` | two facing pages; a blank is inserted so it opens flat |
| `# chorus-markers: yes` | every chorus after the first prints as a one-line "as before" cue |
| `# min-size: 12` | stop shrinking the lyrics at this size and warn instead |

## Band books

A book can print one PDF per instrument from the same charts. List the parts in
`book.toml`; the first one is the base part and shows the chart's own diagrams and tab:

```toml
[[parts]]
name = "guitar1"
title = "Guitar 1"
chords = true

[[parts]]
name = "keys"
title = "Keys"
chords = true          # print the chord lines
orchid = true          # print an Orchid legend: modifier and key per chord
intro = "parts/keys.md"          # setup notes, printed after the cover
patches = ["piano", "organ"]     # numbered patch bank for the setup page
guitar = false                   # drop tuning/capo from the guide line

[[parts]]
name = "drums"
title = "Drums"
chords = false                   # lyrics only, as the roadmap
default_cue = "straight time"
guitar = false
```

`guitar` defaults to true. Set it `false` for a part that isn't a fretted instrument
(keys, bass, drums, vocals) so its guide line skips `# tuning:`/`# capo:`, which don't
mean anything there; it still shows the part title, `Key …` and the patch label.

Each chart then appends one `@part` block per instrument. A part block holds that
instrument's header material and one cue per section:

```
@part drums
# patch: acoustic kit
@grid groove A
HH|x-x-x-x-|x-x-x-x-|
SD|----o---|----o---|
BD|o---o---|o-o-o---|
[*] groove A
[Chorus] groove B, crash on 1

@part keys
# patch: organ
@note LH roots, RH pad
[Chorus] organ, whole notes
```

Blocks: `@tab label` and `@grid label` (monospace, end at a blank line or the next line
starting with `[`, `@` or `#`), `@diagram`, `@note text` and `@image file.png`.
`[Section] cue` matches the body section of that name; `[*]` is the fallback. A part
with no block still gets a page with the lyrics and the book's `default_cue`. A
`[Section]` cue with no text after it (`[Chorus]` with nothing following) suppresses
the default cue for that section rather than falling back to it. `# orchid: no` in a
part turns the legend off for one song.

`build.py books/<name>` writes `build/<name>/<part>.pdf` for every part: a cover naming
the part, a setup page (the intro text and the patch list), the contents, the songs
and a back page. Song order and page numbers are identical in every book. Build one
book with `build.py books/<name> --part drums`.

## How pages are laid out

The lyric size starts at 13pt and shrinks until the song fits one page, down to 9.5pt.
A song that lands small can usually be rescued with chorus markers, a landscape page,
or by merging short lines in pairs in the chart. Spreads are placed so they open on a
left-hand page, and the contents keeps alphabetical order by artist within each group
even when a spread had to move.

## Fetching charts

`fetch_ug.py search "song artist"` lists Ultimate Guitar chord versions with their vote
counts, and `fetch_ug.py get <url> out.txt` saves one as a text file you can convert
into the format above. It is for personal use; the lyrics remain the songwriters'.

## Tests

```
.venv/bin/python -m pytest -q
```
