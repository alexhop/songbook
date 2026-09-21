#!/usr/bin/env python3
"""Draw the example book's placeholder logo: a tent and a campfire as black line art on
a transparent 1024x1024 PNG, with a wordmark underneath. Replace assets/logo.png with
your own artwork; keep the wordmark below the artwork if you use footer_mark = "auto"."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W = 1024
im = Image.new("RGBA", (W, W), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
ink = (0, 0, 0, 255)
lw = 14

# tent
d.line([(150, 640), (400, 250), (650, 640)], fill=ink, width=lw, joint="curve")
d.line([(150, 640), (650, 640)], fill=ink, width=lw)
d.line([(400, 250), (400, 640)], fill=ink, width=lw // 2)
d.line([(400, 250), (330, 640)], fill=ink, width=lw // 2)
d.line([(400, 250), (470, 640)], fill=ink, width=lw // 2)

# campfire: logs and three flames
d.line([(700, 640), (900, 590)], fill=ink, width=lw)
d.line([(700, 590), (900, 640)], fill=ink, width=lw)
for x0, h in ((760, 120), (800, 200), (845, 140)):
    d.line([(x0, 585), (x0 + 20, 585 - h), (x0 + 40, 585)], fill=ink, width=lw // 2, joint="curve")

# ground line
d.line([(120, 680), (920, 680)], fill=ink, width=lw // 2)

# wordmark, separated from the artwork by a blank band so footer_mark = "auto" can crop it
try:
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 120)
except OSError:
    font = ImageFont.load_default(size=120)
text = "EXAMPLE"
tw = d.textlength(text, font=font)
d.text(((W - tw) / 2, 760), text, fill=ink, font=font)

out = Path(__file__).with_name("assets") / "logo.png"
im.save(out)
print(f"wrote {out}")
