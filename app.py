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
import re
import threading
from collections import OrderedDict

from flask import Flask, Response, abort, render_template, request

import counter

app = Flask(__name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
CACHE_MAX = 512
_cache: OrderedDict[tuple, bytes] = OrderedDict()
_lock = threading.Lock()


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

    try:
        png = _cached_png(name, since, dt.datetime.utcnow().date())
    except counter.UnknownUser:
        abort(404, f"GitHub user '{name}' not found")

    return Response(png, mimetype="image/png", headers={
        # Camo and browsers re-fetch hourly; the count only moves ~daily.
        "Cache-Control": "public, max-age=3600",
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001)
