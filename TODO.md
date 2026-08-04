# lenny — plan & TODO

## Goal

Ship **lenny** (né days-with-commits) as a public, always-on service at **$0/month**: anyone pastes a
GitHub username and gets a daily-fresh meme image — their commit streak on the Lenny
"0 days without an accident" Simpsons sign — with a stable embed URL per user
(`<domain>/<githubname>`, `?from=YYYY-MM-DD` for the fixed-start-date variant).
(idea added: 2026-07-13, scope upgraded from personal cron to public service 2026-07-14)

Success = my own live counter embedded on my profile README / olekwrites.com, the service
surviving strangers' traffic, and no monthly bill.

## Scope

**In:** the Flask + Pillow service (already built and tested locally), Render free-tier
deploy, solving the cold-start-vs-Camo problem for free, polite rate limiting, my own embed.

**Out (for now):** accounts/auth, non-code habits (that's the separate `habitlikecommits`
idea), paid tiers, other meme templates, other data sources.

## How it's built (already done, see Done)

- `counter.py` — pulls the contribution graph from the public mirror
  (github-contributions-api.jogruber.de, no GitHub token), computes streak / windowed
  count, draws the number onto `assets/lenny.png` with Pillow.
- `app.py` — Flask: `/` landing page, `/<username>[.png]` image endpoint; per-user
  per-UTC-day in-process cache; `Cache-Control: max-age` 6 h clamped to UTC midnight;
  daily bandwidth budget (full → half-size → 429 across `BW_SOFT/HARD_CAP_MB`).
- `render.yaml` — Render Blueprint: free plan, `gunicorn app:app`.

## Free hosting: Render + GitHub, $0/month

**What's free and why it's enough:**

- **Render free web service** — 750 instance-hours/month; one service running 24/7 is
  ~744 h, so a single always-warm service fits exactly. Free `*.onrender.com` subdomain;
  attaching a custom domain is also free (the domain name itself, ~$10/yr, is the only
  optional spend in the whole project).
- **GitHub public repo** — free code hosting, and **Actions minutes are unlimited on
  public repos**. This matters: a keep-warm ping every 10 min ≈ 4,300 one-minute-billed
  jobs/month, which would blow through the 2,000 free minutes of a *private* repo. Public
  repo → genuinely free. (The project is a show-off toy anyway — public is a feature.)

**The one hard problem — cold starts vs. GitHub Camo (this is what $7/mo would otherwise buy):**
Render free spins the service down after ~15 min idle; a cold start takes ~30 s; GitHub
Camo gives an image ~4 s before showing a broken icon. Fix for free: **never let it go idle.**

- **Keep-warm via GitHub Actions**: a scheduled workflow curls the service every 10 min
  (spin-down threshold is ~15 min, so 10 min holds even with GitHub's few-minute cron
  drift; an occasional missed ping = one cold start, which Camo's hourly cache hides from
  almost all viewers).
- The same ping hits my own image URL once, so the first real viewer of the day gets the
  in-process-cached fast path too.
- Belt-and-braces alternative/addition: UptimeRobot free plan pings every 5 min (not
  GitHub, still $0) — use it if Actions drift ever proves annoying in practice.
- Rejected: pre-rendering static images via Actions and serving them from GitHub Pages —
  free and cold-start-proof, but only works for a known user list; on-demand-for-anyone
  *is* the product.

`.github/workflows/keep-warm.yml` sketch:

```yaml
name: keep-warm
on:
  schedule:
    - cron: "*/10 * * * *"
  workflow_dispatch:
jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - run: |
          curl -fsS -o /dev/null --max-time 90 https://days-with-commits.onrender.com/
          curl -fsS -o /dev/null --max-time 90 "https://days-with-commits.onrender.com/jaal?from=2026-05-27"
```

(`--max-time 90` on purpose: the pinger itself must tolerate a cold start so it can *end* one.)

# Tasks

1. ⬜ **Verify the Vivaldi widget in a real Dashboard** — deployed and verified
   live in a normal tab, but only Tall has been seen at its true size, and only
   with the CSS dark fallback. Still to check: Regular (~155px, where the sign
   crops to fill the width and the header/caption drop out), a dark Vivaldi
   theme with *Share Theme Colors* **ticked**, the same **unticked**, and
   whether a plain left-click opens github.com/<name> or falls back to
   navigating the widget itself. (added: 2026-08-01)
1. ⬜ `/legal` + `/privacy` pass on the widget as a new surface: it parks a
   ~142 KB badge data-URL in olekwrites.com's localStorage (`lenny_w_*`) and
   runs no frontend analytics — the badge fetch tags itself `source=widget` for
   the existing server-side event. Nothing new leaves the browser, but the
   storage is worth a line somewhere. (added: 2026-08-01)
1. ⬜ **Keep-warm is not working — the service sleeps most of the day.** Evidence
   (2026-07-16): GitHub ran the */10 cron at gaps of 1.5–3.7 h (12:54, 11:10, 09:02,
   06:37…) — GitHub throttles scheduled workflows hard; also visible as ~13 jaal
   re-renders/night in PostHog (each sleep wipes the in-process cache). Fix: the
   UptimeRobot free plan (5-min pings, needs signup) already contemplated below, or
   Render starter. Mitigated meanwhile: demo badge is edge-cached (stable URL, no ?t=)
   so the landing page shows instantly, and the page now shows a "drawing the sign…"
   status during slow loads. (updated: 2026-07-16)
1. ⬜ Rotate the Cloudflare API token at dash.cloudflare.com/profile/api-tokens.
   It lives in `CLOUDFLARE_API_TOKEN` in the shell environment and is the deploy
   path for `worker.js` — used again on 2026-08-02 to ship the cacheEverything
   narrowing and the client-IP forwarding, so it has now been exercised from a
   second Claude session on top of the transcript it was originally pasted into.
   Keep the capability, replace the secret. (added: 2026-07-14, updated: 2026-08-02)
1. ⬜ Verify the embed end-to-end: put the image in a test README, confirm Camo renders it
   and refreshes within ~1 h of a new commit day.
1. ⬜ Embed my own counter — olekwrites.com done (badge in the 100-days-of-code post +
   `/lenny` index note, both pushed 2026-07-14); still to do: profile README.
   (updated: 2026-07-14)
1. ⬜ Consider Render Build Filters: ignore `TODO.md`/`*.md` so docs-only pushes don't
   trigger a rebuild (every TODO commit currently redeploys the service). (added: 2026-07-14)
1. ⬜ Nice-to-have: OG tags on the landing page so pasting the site link unfurls with a
   Lenny preview.

# Bugs

(none open)

# Done

1. **`?hand=prev`: the card in Lenny's hand shows yesterday's number.** Second
   steering param after `?from=`, same shape (strict parse, 400 on junk, part of
   the cache key, forwarded by the Vivaldi widget). Default is unchanged — the
   meme's own "0" stays baked in. Yesterday's number is the real one, computed,
   not `n - 1`: after a broken streak those differ (commits Mon–Wed, none Thu,
   one Fri → the sign says 1, his hand says 3). Costs no extra call to jogruber's
   API: `counter.Graph` now holds one user's fetched years for the span of a
   render, so both days are counted off the same data. Drawing follows the
   existing header-patch trick — a parallelogram of matched card-white over the
   baked "0", digits rotated 15° to sit with the card's lean, clear of the
   fingers on the bottom edge. Verified live on /jaal (70 on the sign, 69 in
   hand) in both streak and `?from` modes, 1–4 digits. (done: 2026-08-04)

1. **Stale HTML fixed for real, at the edge this time.** The zone's Browser
   Cache TTL (4 h) was rewriting the origin's `no-cache` on every HTML response
   to `max-age=14400`, so browsers kept the landing page and the widget page
   across deploys — the same class as the July "submit doesn't work" report,
   which e08cfe6 had only appeared to fix. Root cause was that the worker
   narrowing committed in e127154 on 2026-07-14 was **never deployed**: the live
   worker was still `cacheEverything: true` for everything, and the zone TTL only
   applies to responses Cloudflare actually caches. `cacheEverything` now matches
   badge paths only (`/<user>` or `/<user>.png`), and the worker was deployed via
   the Cloudflare API. Verified: HTML is `DYNAMIC` + `no-cache`, badges still go
   `EXPIRED` → `HIT` at `max-age=21600` with `X-Lenny-Count` intact, `.png` and
   `?from` unaffected, blog untouched. The zone setting itself is unchanged and
   would bite again if any HTML response were ever given `cacheEverything`.
   (done: 2026-08-02)
1. **Per-IP throttle on renders** — 20 cache *misses* per address per hour, then
   429 with `Retry-After`. Only misses count: a miss is what pulls a contribution
   graph from jogruber's free community API and renders a PNG, while a hit costs
   bandwidth only and is already covered by the daily budget. So a README badge
   or a Vivaldi widget — one miss per user per UTC day — never sees it; what it
   stops is one address walking a list of usernames. Tunable via `RATE_MISSES` /
   `RATE_WINDOW_S`; the IP table is bounded at 4096, evicting least-recently-seen.
   The subtle part was *which* address: the worker→Render hop is a fresh request
   whose `CF-Connecting-IP` we don't control, and had it collapsed to one value
   every visitor would have shared a bucket and the service would 429 everyone —
   worse than the abuse being prevented. The worker now forwards the visitor as
   `X-Lenny-Client-IP` and the origin prefers it. Verified live: a bucket filled
   at the origin under a forged IP kept 429-ing there, while the *same* forged
   header sent through olekwrites.com came back 404 — the worker overwrites it,
   so bucketing follows the real visitor and a forged header cannot poison
   someone else's bucket. Badge, widget and landing page all unaffected
   throughout. (done: 2026-08-02)
1. **Vivaldi Dashboard widget shipped** — `<domain>/<name>/widget/vivaldi`
   (`?from=` supported), live at olekwrites.com/lenny/jaal/widget/vivaldi.
   Pointing a Webpage widget straight at the badge URL worked but gave
   Vivaldi's bare image viewer: PNG letterboxed in black, card titled
   "jaal (619×403)". The page replaces that with a Vivaldi-themed frame
   (`--colorBg`/`--colorFg`/`--radius`/`--isDarkTheme`, with light and dark
   fallbacks for *Share Theme Colors* off), a title that rewrites itself to
   "67 days without missing a commit · @jaal", and a clean URL under the card.
   Cache-first: it paints a localStorage copy of the badge the instant the
   Dashboard opens (Vivaldi reloads widget pages on every open, and the service
   naps on Render free) and refetches only once the UTC day has turned — which
   is also the only time the answer can change, since the origin freezes one
   badge per user per UTC day. Two more limits sit behind that, because the day
   gate only covers the happy path: a **2-minute lease** written to localStorage
   *before* each fetch, so opening and closing the Dashboard during a cold start
   starts one request instead of one per open (each page is a fresh JS context —
   disk is the only place they can see each other), and a **failure cooldown**
   sized to the reason — 5 min transient, 6 h for a username that does not
   exist, until UTC midnight on a 429, which is what the origin itself promises.
   New `X-Lenny-Count` response header carries the
   number so the title costs no second request; it survives the Cloudflare edge.
   Regular (~155px) crops the sign to fill the width, Tall (~380px) shows the
   whole picture plus a caption. Landing page gained a widget snippet and an
   "On your Vivaldi startpage" section. Verified live: both modes, cache-hit
   path (zero requests on a same-day reload), stale-day refresh, unknown-user
   error state, proxy-prefix URL math. Confirmed live 2026-08-02 that the day
   gate does its job in the wild: the count rolled 67 → 68 at UTC midnight on
   the first Dashboard-equivalent load of the new day, and a reload after it
   made zero requests. (done: 2026-08-01, fetch limits added: 2026-08-02)
1. Stale-HTML class fixed at the origin: landing page served with
   `Cache-Control: no-cache`, so neither the Cloudflare edge nor browsers hold the
   page across deploys (the zone default had been stamping max-age=14400 on it).
   Trigger: "submit doesn't work" report that was a 4 h-stale browser copy — live
   site verified working (autoload + submit) before and after. (done: 2026-07-16)
1. PostHog analytics shipped for /lenny: lenny_submit (frontend, demo auto-submit
   excluded, no usernames) + lenny_image_generated (backend, per cache miss, with
   env prod/dev and source demo/submit/keepwarm/direct, junk sanitized to direct).
   Verified end-to-end dev + prod; insight "Lenny — submits & images generated"
   (WuAJ24fn) splits on-demand vs housekeeping renders. (done: 2026-07-16)
1. Deploy verified live in production: origin badge now 109 KB PNG-8 (was 299 KB
   truecolor), `?from=0001-01-01` answers in ~23 s with 200 (clamp working — old code
   would fetch ~2000 years), olekwrites.com/lenny/jaal proxies fine. (done: 2026-07-14)
1. **Render auto-deploy fixed** — root cause: the repo rename dropped `lenny` from the
   Render GitHub App's repository access (Render's source picker showed "No results for
   lenny"). Fixed by re-granting access at github.com/settings/installations and
   reconnecting the source in the Render dashboard. Verified end-to-end: push 2c05e63
   triggered "New commit via Auto-Deploy". (done: 2026-07-14)
1. Render service renamed `days-with-commits` → `lenny-days-without` (dashboard) and
   `render.yaml` synced. Empirically the onrender.com subdomain did NOT change — it's
   fixed at creation — so days-with-commits.onrender.com stays the live URL and
   `worker.js`/`keep-warm.yml` needed no changes (no worker redeploy needed after all).
   (done: 2026-07-14)
1. Bug fixed: `?from` now clamped to 2008-01-01 (GitHub launch) — kills the
   ~2000-year-fetch slow-request DoS and collapses pathological dates onto one cache key;
   covered by a clamp test. (added: 2026-07-14 in security review, done: 2026-07-14)

1. MIT license added (LICENSE + README section) with a carve-out: `assets/lenny.png` is
   Simpsons fan art excluded from the license; DejaVu font keeps its own license. The
   public repo is now properly open source. (done: 2026-07-14)
1. Landing page restyled to match olekwrites.com (grid paper, Chivo, rainbow links,
   section cards; loads `jaal` by default; cross-linked with the 100-days-of-code post;
   dead Frinkiac link replaced). (done: 2026-07-14)
1. Bandwidth safety: PNG-8 badges (~300 KB → ~105 KB), `max-age` 6 h clamped to UTC
   midnight, LRU 512 → 2048, and a daily budget guard — full-size under 2 GB/day,
   half-size to 3 GB/day, then 429 until midnight; caps via `BW_SOFT/HARD_CAP_MB`.
   Worst case ~93 GB/mo, under Render's 100 GB cap. (done: 2026-07-14)
1. **Shipped: https://olekwrites.com/lenny is live.** Render service deployed
   (days-with-commits.onrender.com) and the `lenny` Worker + `olekwrites.com/lenny*` route
   created via the Cloudflare API. Verified end-to-end: landing page, `/lenny/jaal` (49!),
   `?from=2026-05-27`, edge cache HIT on repeat views, blog untouched. (done: 2026-07-14)
1. Public repo created and pushed — https://github.com/jaal/lenny (renamed from
   days-with-commits, 2026-07-14) — including
   `keep-warm.yml` (starts pinging once the Render service exists; harmless failures until
   then). (done: 2026-07-14)
1. Free-hosting plan locked (2026-07-14): Render free web service kept warm by a GitHub
   Actions 10-min ping from the (public) repo — replaces the "starter plan ~$7/mo vs.
   pinger" open decision with the $0 answer.
1. Public-service scope decided (streak default + `?from=` override, Render hosting);
   self-rendering chosen over the imgflip API (no shared account, no rate limits, exact
   text placement). (done: 2026-07-14)
1. Image rendering built and visually verified in both modes: streak ("N DAYS WITHOUT
   MISSING A COMMIT") and `?from` (header re-lettered to "DAYS WITH", texture-patched over
   the tilted sign so no ghost lettering). Handles 1–4-digit numbers. (done: 2026-07-14)
1. Flask service built and tested locally end-to-end: landing page with URL→embed-snippet
   flow, `/<name>[.png]` endpoint, per-day in-process cache (repeat hits ~1 ms),
   `Cache-Control: max-age=3600`, 404 on unknown user, 400 on bad `?from`. (done: 2026-07-14)
1. ~~v0 scaffold: personal cron via GitHub Actions + imgflip API~~ — superseded by the
   public service the same week; files removed. (done: 2026-07-13, retired: 2026-07-14)
