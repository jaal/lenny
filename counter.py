"""Core logic: GitHub commit-day counting + Lenny image rendering.

Kept free of web-framework imports so it can be tested standalone.

Data source is the public mirror of GitHub's contribution graph
(github-contributions-api.jogruber.de) — no GitHub token required.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).parent / "assets"
FONT_PATH = str(ASSETS / "DejaVuSans-Bold.ttf")
TEMPLATE = Image.open(ASSETS / "lenny.png").convert("RGB")  # 619 x 403

CONTRIB_API = "https://github-contributions-api.jogruber.de/v4/{user}?y={year}"
MAX_LOOKBACK_YEARS = 15

INK = (24, 26, 34)        # near-black, matches the template lettering
CARD_WHITE = (247, 247, 245)

# Template geometry (px, on the 619x403 original).
NUMBER_CARD = (64, 60, 152, 166)   # the top "0" card on the sign — we cover & redraw
CAPTION_BOX = (305, 105, 604, 228) # blank white area right of Lenny's head
CAPTION_BOX_FROM = (335, 106, 596, 210)  # tighter: clears Lenny's hair in ?from mode

# ?from mode covers the "DAYS WITHOUT" lettering (y 48-95, measured) with a
# stretched strip of clean sign texture, so the patch keeps the sign's real
# gradient. The sign tilts slightly, hence the small text rotation.
HEADER_AREA = (174, 38, 606, 104)
HEADER_PATCH_SRC = (592, 38, 610, 104)  # clean texture right of the lettering
HEADER_ANGLE = 1.0


class UnknownUser(Exception):
    pass


def _fetch_year(user: str, year: int) -> dict[str, int]:
    """Return {iso-date: contribution count} for one calendar year."""
    req = urllib.request.Request(
        CONTRIB_API.format(user=user, year=year),
        headers={"User-Agent": "lenny (github.com/jaal/lenny)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UnknownUser(user) from e
        raise
    return {c["date"]: c["count"] for c in data.get("contributions", [])}


def current_streak(user: str, today: dt.date) -> int:
    """Consecutive days with >=1 contribution, counting back from today.

    Today doesn't break the streak if it has no contributions yet — the day
    isn't over — so an empty today just shifts the walk to yesterday.
    """
    counts = _fetch_year(user, today.year)
    day = today
    if counts.get(day.isoformat(), 0) == 0:
        day -= dt.timedelta(days=1)
    streak = 0
    fetched = {today.year}
    while day.year > today.year - MAX_LOOKBACK_YEARS:
        if day.year not in fetched:
            counts.update(_fetch_year(user, day.year))
            fetched.add(day.year)
        if counts.get(day.isoformat(), 0) > 0:
            streak += 1
            day -= dt.timedelta(days=1)
        else:
            break
    return streak


def days_with_commits_since(user: str, start: dt.date, today: dt.date) -> int:
    """Number of days in [start, today] with >=1 contribution."""
    counts: dict[str, int] = {}
    for year in range(start.year, today.year + 1):
        counts.update(_fetch_year(user, year))
    return sum(
        1 for date, n in counts.items()
        if start.isoformat() <= date <= today.isoformat() and n > 0
    )


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_w: int, max_h: int,
              start_size: int) -> ImageFont.FreeTypeFont:
    size = start_size
    while size > 12:
        font = ImageFont.truetype(FONT_PATH, size)
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        if r - l <= max_w and b - t <= max_h:
            return font
        size -= 2
    return ImageFont.truetype(FONT_PATH, 12)


def _draw_centered(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
                   text: str, font: ImageFont.FreeTypeFont) -> None:
    x0, y0, x1, y1 = box
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    draw.text(((x0 + x1 - (r - l)) / 2 - l, (y0 + y1 - (b - t)) / 2 - t),
              text, font=font, fill=INK)


def render(number: int, since: dt.date | None = None) -> bytes:
    """Render the Lenny sign as PNG bytes.

    Default (streak) mode keeps the template's "DAYS WITHOUT" and captions it
    "MISSING A COMMIT". In ?from mode the header is redrawn as "DAYS WITH"
    and the caption states the window.
    """
    im = TEMPLATE.copy()
    draw = ImageDraw.Draw(im)

    # The number card: cover the baked-in "0", draw the real number.
    draw.rectangle(NUMBER_CARD, fill=CARD_WHITE)
    card_w = NUMBER_CARD[2] - NUMBER_CARD[0]
    card_h = NUMBER_CARD[3] - NUMBER_CARD[1]
    text = str(number)
    font = _fit_font(draw, text, card_w - 14, card_h - 14, 84)
    _draw_centered(draw, NUMBER_CARD, text, font)

    if since is None:
        caption_lines = ["MISSING", "A COMMIT"]
        x0, y0, x1, y1 = CAPTION_BOX
    else:
        hx0, hy0, hx1, hy1 = HEADER_AREA
        patch = im.crop(HEADER_PATCH_SRC).resize((hx1 - hx0, hy1 - hy0))
        im.paste(patch, (hx0, hy0))
        layer = Image.new("RGBA", (420, 60), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        header_font = _fit_font(ld, "DAYS WITH", 410, 52, 56)
        _draw_centered(ld, (0, 0, 420, 60), "DAYS WITH", header_font)
        layer = layer.rotate(HEADER_ANGLE, expand=True, resample=Image.BICUBIC)
        cx, cy = (hx0 + hx1) // 2, (hy0 + hy1) // 2
        im.paste(layer, (cx - layer.width // 2, cy - layer.height // 2), layer)
        caption_lines = ["≥ 1 COMMIT", f"SINCE {since.isoformat()}"]
        x0, y0, x1, y1 = CAPTION_BOX_FROM
    line_h = (y1 - y0) // len(caption_lines)
    for i, line in enumerate(caption_lines):
        font = _fit_font(draw, line, x1 - x0 - 16, line_h - 10, 40)
        _draw_centered(draw, (x0, y0 + i * line_h, x1, y0 + (i + 1) * line_h),
                       line, font)

    buf = io.BytesIO()
    # Palette PNG-8: ~4x smaller than truecolor, no visible loss on this art.
    im.quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(
        buf, format="PNG", optimize=True)
    return buf.getvalue()


def shrink(png: bytes, scale: float = 0.5) -> bytes:
    """Re-encode a rendered PNG at reduced size (bandwidth-saver mode)."""
    im = Image.open(io.BytesIO(png)).convert("RGB")
    im = im.resize((round(im.width * scale), round(im.height * scale)),
                   Image.LANCZOS)
    buf = io.BytesIO()
    im.quantize(colors=128, method=Image.Quantize.MEDIANCUT).save(
        buf, format="PNG", optimize=True)
    return buf.getvalue()
