# Example book

Eight public-domain songs (lyrics and tunes published before 1930) that together use
every feature of the chart format: chord diagrams, a header tab, chorus markers, a
two-page spread, cue lines and repeat markers. It exists so the tool can be tried and
tested without any copyrighted material. Keep it that way: only public-domain songs
here, with the source of the text in each chart's `# source:` line.

To start your own book, copy this directory to `books/<name>`, replace `book.toml`,
`assets/logo.png` (`make_logo.py` draws this placeholder) and `songs/`, and point
`BOOK.md` at it.

Oh! Susanna carries a `@part drums` block as the README's band-book example; the
example book has no `parts` list, so the block is ignored in its build.
