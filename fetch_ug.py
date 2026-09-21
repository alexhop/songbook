#!/usr/bin/env python3
"""
fetch_ug.py — pull chord charts from Ultimate Guitar for conversion into songs/.

Usage:
    fetch_ug.py search "<song> <artist>"        list chord versions: id, votes, rating, key, capo
    fetch_ug.py get <url> [out.txt]             print (or save) the chart with [ch]/[tab] tags stripped

The chart is embedded in each page as JSON in a data-content attribute.
"""
import html
import json
import re
import sys
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def page_data(url):
    m = re.search(r'data-content="([^"]+)"', fetch(url))
    if not m:
        raise SystemExit(f"no data-content on {url}")
    return json.loads(html.unescape(m.group(1)))["store"]["page"]["data"]


def search(query):
    url = "https://www.ultimate-guitar.com/search.php?" + urllib.parse.urlencode(
        {"search_type": "title", "value": query})
    data = page_data(url)
    results = [r for r in data.get("results", []) if r.get("type") == "Chords"]
    results.sort(key=lambda r: -(r.get("votes") or 0))
    print(f"{'votes':>5}  {'rating':>6}  {'key':>4}  song — artist  url")
    for r in results:
        print(f"{r.get('votes') or 0:>5}  {r.get('rating') or 0:>6.2f}  {r.get('tonality_name') or '?':>4}  "
              f"{r['song_name']} — {r['artist_name']}  {r.get('tab_url', '')}")
    return results


def get(id_or_url):
    url = id_or_url if id_or_url.startswith("http") else f"https://tabs.ultimate-guitar.com/tab/{id_or_url}"
    if not id_or_url.startswith("http"):
        raise SystemExit("pass the tab URL printed by `search` (bare ids do not resolve)")
    data = page_data(url)
    view = data["tab_view"]
    tab = data["tab"]
    meta = view.get("meta") or {}
    content = view["wiki_tab"]["content"].replace("\r\n", "\n")
    content = re.sub(r"\[/?(ch|tab)\]", "", content).replace("е", "e")
    header = (f"# title: {tab['song_name']}\n# artist: {tab['artist_name']}\n"
              f"# key: {tab.get('tonality_name') or ''}\n# tuning: {meta.get('tuning', {}).get('name', 'Standard tuning') if isinstance(meta.get('tuning'), dict) else 'Standard tuning'}\n"
              f"# capo: {('Capo ' + str(meta['capo'])) if meta.get('capo') else 'No capo'}\n"
              f"# source: {tab.get('tab_url', url)}\n\n")
    return header + content.strip() + "\n"


def main(argv):
    if len(argv) >= 3 and argv[1] == "search":
        search(" ".join(argv[2:]))
    elif len(argv) >= 3 and argv[1] == "get":
        text = get(argv[2])
        if len(argv) > 3:
            open(argv[3], "w", encoding="utf-8").write(text)
            print(f"wrote {argv[3]} ({text.count(chr(10))} lines)")
        else:
            print(text)
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
