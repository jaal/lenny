"""Flask app: landing page + per-user Lenny counter images.

  GET /            landing page (enter a GitHub URL/username)
  GET /<username>  PNG — current streak of days with >=1 commit
                   ?from=YYYY-MM-DD — days with >=1 commit since that date

Images are computed from live contribution data on request and cached
in-process for the rest of the UTC day, with Cache-Control set so embed
proxies (GitHub Camo etc.) refresh them regularly.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import threading
from collections import OrderedDict

from flask import Flask, Response, abort, render_template, request

import counter

app = Flask(__name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
CACHE_MAX = 2048
_cache: OrderedDict[tuple, bytes] = OrderedDict()
_lock = threading.Lock()

# Daily bandwidth budget (Render free tier: 100 GB/month ~ 3.2 GB/day).
# Under the soft cap images are served full-size; between soft and hard cap
# half-size; past the hard cap 429 until UTC midnight, when the budget —
# like the count itself — resets. In-process, so a restart forgets the
# day's spend; the caps leave margin for that.
BW_SOFT_CAP = int(float(os.environ.get("BW_SOFT_CAP_MB", "2000")) * 1e6)
BW_HARD_CAP = int(float(os.environ.get("BW_HARD_CAP_MB", "3000")) * 1e6)
_bw_day: dt.date | None = None
_bw_bytes = 0


def _bw_mode(today: dt.date) -> str:
    """'full' | 'small' | 'blocked' based on today's bytes served so far."""
    global _bw_day, _bw_bytes
    with _lock:
        if _bw_day != today:
            _bw_day, _bw_bytes = today, 0
        if _bw_bytes >= BW_HARD_CAP:
            return "blocked"
        return "small" if _bw_bytes >= BW_SOFT_CAP else "full"


def _bw_spend(n: int) -> None:
    global _bw_bytes
    with _lock:
        _bw_bytes += n


def _cached_png(user: str, since: dt.date | None, today: dt.date) -> bytes:
    key = (user.lower(), since, today)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    if since is None:
        number = counter.current_streak(user, today)
    else:
        number = counter.days_with_commits_since(user, since, today)
    png = counter.render(number, since=since)
    with _lock:
        _cache[key] = png
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)
    return png


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/<name>")
def image(name: str):
    if name.endswith(".png"):
        name = name[:-4]
    if not USERNAME_RE.match(name):
        abort(404)

    since = None
    if raw := request.args.get("from"):
        try:
            since = dt.date.fromisoformat(raw)
        except ValueError:
            abort(400, "from must be YYYY-MM-DD")

    now = dt.datetime.utcnow()
    midnight = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time())
    to_midnight = max(60, int((midnight - now).total_seconds()))

    mode = _bw_mode(now.date())
    if mode == "blocked":
        return Response("daily bandwidth budget exhausted, back at UTC midnight",
                        status=429, headers={"Retry-After": str(to_midnight)})

    try:
        png = _cached_png(name, since, now.date())
    except counter.UnknownUser:
        abort(404, f"GitHub user '{name}' not found")

    if mode == "small":
        png = counter.shrink(png)
    _bw_spend(len(png))

    # The count only moves at UTC midnight (or with the day's first commit),
    # so let caches hold it up to 6h — but never past midnight, when the
    # number can actually change.
    max_age = min(21600, to_midnight)
    return Response(png, mimetype="image/png", headers={
        "Cache-Control": f"public, max-age={max_age}",
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001)
