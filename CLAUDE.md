# Songbook

Tools for printing a songbook of chord charts: one song per page, readable in low
light, built into a single PDF with a cover, a grouped table of contents and page
numbers. `README.md` is the user guide; this file is for working on the tool and its
charts. The book being worked on is named in `BOOK.md`, whose own `CLAUDE.md` holds
everything specific to that book (who plays, the song list, decisions, status).

## Layout

```
build.py  songpage.py  fetch_ug.py     the tool
tests/                                 pytest; fixtures under tests/fixtures/book
BOOK.md                                names the active book, imports its CLAUDE.md
books/<name>/book.toml                 title, subtitle, logo, footer mark, group order
books/<name>/songs/*.txt               one chart per song
books/<name>/assets/                   logo and any other artwork
books/<name>/CLAUDE.md                 that book's instructions and status
build/<name>/                          output (gitignored): pages/*.pdf and songbook.pdf
```

The tool never depends on a particular book. Anything about a specific book, its
people or its songs belongs in `books/<name>/`, not here or in the code.

## Page format

Top to bottom:
1. Title and artist
2. Guide line: key, tuning, capo
3. Compact structure line, e.g. `intro – verse 1 – verse 2 – chorus – verse 3 – chorus – bridge – chorus ×2`
4. Chord diagrams for every chord that is not a plain major or minor (in a box
   top-right, with any tab): sevenths, sus, add, slash and power chords.
5. Lyrics with chords above them, two columns
6. A small bit of tab for a signature lick or little instrumental (same top-right box),
   whenever a song has one.

Each song fits on one page; a two-page spread is acceptable when it still avoids a page
turn. The tension is font size vs. fit and bigger is better. Portrait two-column gives
about 11.5pt lyrics on a 36-line song, landscape about 13.5pt; printing repeated
choruses as a one-line marker instead of in full gains about 1pt in portrait. The
default is portrait with full choruses; a song that comes out small gets
`# chorus-markers: yes` or `# landscape: yes` individually.

## Tooling

Python lives in `.venv` (`requirements.txt`: reportlab, pypdf, pillow, pytest). Run
everything with `.venv/bin/python`.

- `build.py [book_dir] [build_dir]` reads `book.toml`, renders every chart in the book's
  `songs/` to `build/<name>/pages/<slug>.pdf`, draws a cover and a table of contents
  grouped by `# group:`, and merges them into `build/<name>/songbook.pdf`. It prints one
  row per song (slug, title, group, start page, lyric size, orientation, fit) and exits
  1 if any song does not fit. With no argument it builds the book named in `BOOK.md`.
- **Band books.** A `[[parts]]` list in `book.toml` (name, title, chords, default_cue,
  orchid, intro, patches) makes `build.py` write one PDF per part with a setup page
  after the cover and identical page numbers in every book; the first part is the base
  and shows the chart's own diagrams and tab. Charts append `@part <name>` blocks with
  `# patch:`, `@tab`/`@grid` (labelled monospace), `@diagram`, `@note`, `@image`, and
  `[Section] cue` lines (`[*]` fallback). `orchid.py` computes the keys legend from
  `# key:` and the chord tokens. `--part <name>` builds one book.
- **Group order** is the `groups` list in `book.toml`; unknown groups go last under
  "Other".
- **Contents order.** Artist first, sorted by artist then title within each group,
  ignoring a leading "The". The contents is always in that order; the physical page
  order within a group can differ because spreads must start on even pages.
- **Logo.** `logo` in `book.toml` (a PNG with transparency; Pillow reads the alpha) is
  drawn on the cover with `cover_word` beneath it, small at the top right of each
  contents page, and centred on a back page. Without a logo the cover shows the title.
  The back page is forced onto an even page (blank inserted if needed) so it is the
  outside back cover.
- **Footer mark.** Every song page gets a small image 22pt tall at 50% alpha in the
  inner bottom corner, opposite the page number. `footer_mark = "auto"` crops the logo
  at the first blank row below 60% of its height, which drops a wordmark under the
  artwork; a path uses that image; `"none"` turns it off. The footer band is the 28pt
  bottom margin, so it never touches lyrics.
- **Page numbers.** Stamped on every page after the cover at the outer bottom corner
  (left edge on even pages, right edge on odd). The contents lists them too.
- **Page planning.** The cover is page 1 (right-hand), so odd pages are right-hand and
  even pages left-hand. A two-page spread must start on an even page so both halves
  face each other. `plan_order()` arranges songs within each group to make that happen:
  on an even page it places a spread next if one remains, on an odd page a single-page
  song; title order otherwise. A blank page is inserted only when a group runs out of
  single-page songs at an odd page, and the build report says so.
- `fetch_ug.py search "<song> <artist>"` lists Ultimate Guitar chord versions with votes
  and URL; `fetch_ug.py get <url> out.txt` saves the chart with a metadata header and
  the Cyrillic watermark removed. Save into a scratch directory, then hand-convert into
  the book's `songs/` (section labels, merged short lines, instrumental bars, structure
  line).
- Header box: diagrams shrink from 9 to 7pt when the box would crowd the title; with a
  tab as well they drop to a second row under the tab and the header grows by 52pt.
  Slash-chord bass walks are better described in the section label than drawn.
- `songpage.py chart.txt out.pdf` renders one page. It auto-shrinks the lyric size from
  13pt down to 9.5pt until the song fits one page (two columns). Fonts: DejaVu Sans
  Condensed → Arial Narrow (macOS Supplemental) → built-in Helvetica.
- `.venv/bin/python -m pytest -q` runs the tests in `tests/` (parsing, chorus markers,
  wrapping, group ordering, book config, an end-to-end build of the fixture book).
  Tests must only use `tests/fixtures/`, never a real book.

### Chart file format (Ultimate Guitar chord-over-lyric style)

```
# title: (Don't Go Back To) Rockville
# artist: R.E.M.
# key: E
# tuning: Standard tuning
# capo: No capo
# group: Special             <- table-of-contents category, one of book.toml's groups
# structure: intro – verse 1 – verse 2 – chorus – verse 3 – chorus – bridge – chorus ×2
# landscape: yes             <- optional per-song overrides, all default off
# spread: yes                <- two facing pages; build.py pads with a blank page so it opens flat
# chorus-markers: yes        <- repeated [Chorus] blocks print as a one-line "(as before)" cue
# min-size: 12               <- floor for the auto-shrink; build warns if it still doesn't fit

@diagram Asus4 x00230        <- frets low string → high, x = mute, 0 = open; shapes above
                                the 4th fret draw from their lowest fret with an "Nfr" label
@tab                         <- tab block for the header box; ends at a blank line.
                                Only the strings the lick uses: drop empty low-E / A lines
e|--0-----0-----0-----0---|
B|--2--h3----p2--h3----p2-|
...
@part drums                  <- overlay for one instrument; see README "Band books"

[Verse 1]                    <- section header
E                               A   Asus4  A  Asus4  A     <- chord line (positions align with lyric below)
lyric line goes here                                       <- lyric line
E   |   E   A  Asus4  A  Asus4  A   |   (x2)              <- chord line with no lyric = chord-only line
```

- A line is a chord line if every token parses as a chord (or `|`, `(x2)`, `N.C.`).
  Parenthesised chords such as a `(D C# F#)` walk-up count too. A non-chord word such
  as `(repeat)` turns the line into a lyric line; use `(x4)` instead.
- Instrumental bars pasted as `| / / / / | ... | x3` must be rewritten as a chord-only
  line: `Em   |   Gmaj7   |   Am   |   Cmaj7   |   (x3)`.
- Ultimate Guitar pastes contain Cyrillic `е` (U+0435) in place of some Latin `e` as a
  scrape watermark. Replace them; check with `grep -nP '[^\x00-\x7F]'`.
- A lyric line of only `~~~~` is a placeholder and renders as a dashed rule sized to the
  character count. Use it only for drafts; a finished book prints full lyrics.
- Chord positions are column offsets into the lyric line below. A chord that lands
  mid-word splits the word and the chord needs horizontal room, so a misaligned paste
  shows up as stretched words. Fix the chart, not the renderer. Long chord names over
  one- and two-letter words stretch them; move the chord to the nearest longer word.
- Chords that fall past the end of the lyric are packed tightly; if they don't fit on
  the chord line they drop to a chord-only line under the lyric.
- Merging short lines in pairs halves the line count, but only works while the merged
  line stays under about 55 characters at 13pt; longer lines wrap and the wrap breaks
  words at chord positions.
- A chord-only line wider than the column overflows; write six bars as `(x3)` of two.
- Section labels: number verses consecutively as they occur. A repeated final chorus is
  one block labelled `[Chorus ×2]`. A repeated verse that differs by a few words can be
  a cue line naming the changes. Keep labels short; a long label overflows the column.

### Workflow

The owner pastes chord charts into the book's `songs/<slug>.txt`, or asks Claude to
fetch one. Show the available Ultimate Guitar versions (key, capo, votes) before
converting; the key is the owner's call. Claude's job is chords, arrangement,
structure, diagrams, tab, layout, and tooling, not writing lyrics. Verify chord
accuracy against the recording where possible. After a change, run the build and the
tests, and rasterise new pages (`sips -s format png`) to check for wrapped lines and
mid-word chords before calling them done.

@BOOK.md
