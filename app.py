"""Flask app: landing page + per-user Lenny counter images.

  GET /            landing page (enter a GitHub URL/username)
  GET /<username>  PNG — current streak of days with >=1 commit
                   ?from=YYYY-MM-DD — days with >=1 commit since that date
                   ?hand=prev — the card in Lenny's hand shows yesterday's
                   number instead of the meme's "0"
  GET /<username>/widget/vivaldi
                   HTML — the badge as a Vivaldi Dashboard webpage widget

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
import time
import urllib.request
from collections import OrderedDict

from flask import Flask, Response, abort, render_template, request

import counter

app = Flask(__name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
CACHE_MAX = 2048
_cache: OrderedDict[tuple, tuple[int, bytes]] = OrderedDict()
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
# (a name someone typed); keep-warm pings send keepwarm; the Vivaldi widget
# sends widget; anything else — README embeds, direct URLs — counts as direct.
KNOWN_SOURCES = {"demo", "submit", "keepwarm", "widget"}


def _count(graph: counter.Graph, since: dt.date | None, day: dt.date) -> int:
    """The number the badge shows on `day`, in whichever mode is in force."""
    if since is None:
        return counter.current_streak(graph.user, day, graph)
    return counter.days_with_commits_since(graph.user, since, day, graph)


def _cached_png(user: str, since: dt.date | None, today: dt.date,
                source: str = "direct", hand: str = "zero") -> tuple[int, bytes]:
    """(number, PNG bytes) for one user-day, computed once and reused."""
    key = (user.lower(), since, today, hand)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    # One graph for both numbers: yesterday's costs no extra upstream call.
    graph = counter.Graph(user)
    number = _count(graph, since, today)
    prev = (_count(graph, since, today - dt.timedelta(days=1))
            if hand == "prev" else None)
    png = counter.render(number, since=since, hand=prev)
    # Cache miss = a picture actually got generated (vs merely served).
    _track("lenny_image_generated", {
        "username": user.lower(),
        "mode": "from" if since else "streak",
        "hand": hand,
        "source": source,
    })
    with _lock:
        _cache[key] = (number, png)
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)
    return number, png


# Per-IP politeness guard. The expensive request is a cache MISS: it pulls a
# contribution graph from jogruber's free community API and renders a PNG.
# Cache hits cost only bandwidth, which the budget above already covers, so
# hits are never throttled — a README badge, or a Vivaldi widget, costs one
# miss per user per UTC day and is unaffected. What this stops is one address
# walking a list of usernames.
RATE_MISSES = int(os.environ.get("RATE_MISSES", "20"))
RATE_WINDOW = int(os.environ.get("RATE_WINDOW_S", "3600"))
RATE_MAX_IPS = 4096
_misses: OrderedDict[str, list[float]] = OrderedDict()


def _client_ip() -> str:
    """Best-effort client address, most trustworthy source first.

    X-Lenny-Client-IP is set by our own Worker from the CF-Connecting-IP it was
    handed, and is the only one guaranteed to be the real visitor on the
    olekwrites.com path: the worker→Render hop is a fresh request whose own
    CF-Connecting-IP we do not control, and if that collapsed to a single
    address every visitor would share one throttle bucket. The rest are
    fallbacks for reaching the Render URL directly.

    All three are forgeable by anyone talking straight to Render, and that is
    accepted: this is politeness towards an upstream we don't pay for, not a
    security control. The daily bandwidth budget is the hard backstop.
    """
    for header in ("X-Lenny-Client-IP", "CF-Connecting-IP", "X-Forwarded-For"):
        if value := request.headers.get(header):
            return value.split(",")[0].strip()
    return request.remote_addr or "?"


def _rate_ok(ip: str) -> bool:
    """May this address trigger another render? Records the attempt if so."""
    now = time.monotonic()
    cutoff = now - RATE_WINDOW
    with _lock:
        hits = [t for t in _misses.get(ip, ()) if t > cutoff]
        allowed = len(hits) < RATE_MISSES
        if allowed:
            hits.append(now)
        _misses[ip] = hits
        _misses.move_to_end(ip)
        # Bounded, so a flood of addresses can't grow this without limit; the
        # evicted ones are the least recently seen.
        while len(_misses) > RATE_MAX_IPS:
            _misses.popitem(last=False)
        return allowed


def _since_arg() -> dt.date | None:
    """Parse ?from=YYYY-MM-DD; 400 on junk, clamped to GitHub's launch."""
    raw = request.args.get("from")
    if not raw:
        return None
    try:
        since = dt.date.fromisoformat(raw)
    except ValueError:
        abort(400, "from must be YYYY-MM-DD")
    # Clamp to GitHub's launch: an ancient date would mean thousands of
    # year-fetches upstream, and every unique date is a fresh cache key.
    return max(since, dt.date(2008, 1, 1))


def _hand_arg() -> str:
    """Parse ?hand=zero|prev — what the card in Lenny's hand shows.

    Rejected rather than silently defaulted: unlike ?source, this one is
    visible in the picture, so a typo should say so instead of quietly
    handing back the meme's "0".
    """
    hand = request.args.get("hand", "zero")
    if hand not in ("zero", "prev"):
        abort(400, "hand must be zero or prev")
    return hand


@app.route("/")
def index():
    # no-cache: neither Cloudflare (cacheEverything honors origin headers)
    # nor browsers may serve a stale landing page after a deploy. The
    # images carry their own long max-age; only the HTML must stay fresh.
    return Response(render_template("index.html"), headers={
        "Cache-Control": "no-cache",
    })


@app.route("/<name>")
def image(name: str):
    if name.endswith(".png"):
        name = name[:-4]
    if not USERNAME_RE.match(name):
        abort(404)

    since = _since_arg()
    hand = _hand_arg()

    now = dt.datetime.utcnow()
    midnight = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time())
    to_midnight = max(60, int((midnight - now).total_seconds()))

    mode = _bw_mode(now.date())
    if mode == "blocked":
        return Response("daily bandwidth budget exhausted, back at UTC midnight",
                        status=429, headers={"Retry-After": str(to_midnight)})

    raw_source = request.args.get("source", "")
    source = raw_source if raw_source in KNOWN_SOURCES else "direct"

    # Only a miss is worth throttling — a hit never touches the upstream API.
    with _lock:
        miss = (name.lower(), since, now.date(), hand) not in _cache
    if miss and not _rate_ok(_client_ip()):
        return Response("too many new badges from your address; try again later",
                        status=429, headers={"Retry-After": str(RATE_WINDOW)})

    try:
        number, png = _cached_png(name, since, now.date(), source, hand)
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
        # The number the picture already shows, in machine-readable form: it
        # saves the Vivaldi widget a second round trip just to title itself.
        "X-Lenny-Count": str(number),
    })


@app.route("/<name>/widget/vivaldi")
def widget_vivaldi(name: str):
    """A Vivaldi Dashboard "Webpage widget" wrapper around one user's badge.

    Deliberately does no counting: the page must paint from the widget's own
    localStorage cache the instant the Dashboard opens, so anything that would
    block this response on the contributions API (a ~30 s cold start) defeats
    the point. The badge, and its X-Lenny-Count, are fetched client-side.
    """
    if not USERNAME_RE.match(name):
        abort(404)
    since = _since_arg()
    hand = _hand_arg()
    # no-cache for the same reason as the landing page: the edge (and browsers)
    # must not hold widget HTML across a deploy. The badge inside it carries
    # its own long max-age.
    return Response(
        render_template("widget_vivaldi.html", username=name,
                        since=since.isoformat() if since else None, hand=hand),
        headers={"Cache-Control": "no-cache"},
    )


if __name__ == "__main__":
    app.run(debug=True, port=5001)
