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
import json
import os
import re
import threading
import urllib.request
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
# day's spend. Caps are deliberately ~10x below the Render allowance
# (~9 GB/mo worst case): still ~2000 full-size badge views/day, with
# room to raise via env vars if real traffic ever hits the guard.
BW_SOFT_CAP = int(float(os.environ.get("BW_SOFT_CAP_MB", "200")) * 1e6)
BW_HARD_CAP = int(float(os.environ.get("BW_HARD_CAP_MB", "300")) * 1e6)
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


# PostHog, same project as olekwrites.com. The key is the public write-only
# project key (it already ships in the site's JS); env vars can override or
# disable (POSTHOG_KEY="").
POSTHOG_KEY = os.environ.get(
    "POSTHOG_KEY", "phc_utnQMZEK2rhWwjcpQLP063wfEMqoGSFvRATNF8YzXoX")
POSTHOG_HOST = os.environ.get("POSTHOG_HOST", "https://eu.posthog.com")
ENV = "prod" if os.environ.get("RENDER") else "dev"


def _track(event: str, props: dict) -> None:
    """Fire-and-forget server-side capture; never blocks or fails a request."""
    if not POSTHOG_KEY:
        return
    payload = json.dumps({
        "api_key": POSTHOG_KEY,
        "event": event,
        "distinct_id": "lenny-server",
        "properties": {**props, "env": ENV, "$process_person_profile": False},
    }).encode()

    def send():
        try:
            urllib.request.urlopen(urllib.request.Request(
                POSTHOG_HOST + "/capture/", data=payload,
                headers={"Content-Type": "application/json"}), timeout=10)
        except OSError:
            pass

    threading.Thread(target=send, daemon=True).start()


# Self-declared request source, for analytics only (not part of the cache
# key). The landing page sends demo (its auto-loaded jaal badge) or submit
# (a name someone typed); keep-warm pings send keepwarm; anything else —
# README embeds, direct URLs — counts as direct.
KNOWN_SOURCES = {"demo", "submit", "keepwarm"}


def _cached_png(user: str, since: dt.date | None, today: dt.date,
                source: str = "direct") -> bytes:
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
    # Cache miss = a picture actually got generated (vs merely served).
    _track("lenny_image_generated", {
        "username": user.lower(),
        "mode": "from" if since else "streak",
        "source": source,
    })
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
        # Clamp to GitHub's launch: an ancient date would mean thousands of
        # year-fetches upstream, and every unique date is a fresh cache key.
        since = max(since, dt.date(2008, 1, 1))

    now = dt.datetime.utcnow()
    midnight = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time())
    to_midnight = max(60, int((midnight - now).total_seconds()))

    mode = _bw_mode(now.date())
    if mode == "blocked":
        return Response("daily bandwidth budget exhausted, back at UTC midnight",
                        status=429, headers={"Retry-After": str(to_midnight)})

    raw_source = request.args.get("source", "")
    source = raw_source if raw_source in KNOWN_SOURCES else "direct"

    try:
        png = _cached_png(name, since, now.date(), source)
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
