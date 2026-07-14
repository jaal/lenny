# days-with-commits — plan & TODO

## Goal

Ship **days-with-commits** as a public, always-on service at **$0/month**: anyone pastes a
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

1. ⬜ After a day of keep-warm pings, confirm in the Render dashboard that the service never
   slept and response times stay warm (~ms, not ~30 s).
1. ⬜ Zone Browser Cache TTL (4 h) overrides the app's 1 h `Cache-Control` on the proxied
   images — harmless for a once-a-day number, but if fresher is wanted set Cloudflare →
   Caching → Browser Cache TTL to "Respect Existing Headers". (added: 2026-07-14)
1. ⬜ Decide the Cloudflare API token's fate: keep it (needed for future `worker.js`
   deploys — the API is the deploy path now) but note it was pasted into a Claude session
   transcript; rotating it at dash.cloudflare.com/profile/api-tokens is the tidy move.
   (added: 2026-07-14)
1. ⬜ Verify the embed end-to-end: put the image in a test README, confirm Camo renders it
   and refreshes within ~1 h of a new commit day.
1. ⬜ Redeploy `cloudflare/worker.js` (needs the Cloudflare API token): edge cache is now
   image-only, so landing-page deploys show up immediately instead of after the 4 h zone
   TTL. Until redeployed, stale HTML persists. (added: 2026-07-14)
1. ⬜ Embed my own counter — olekwrites.com done (badge in the 100-days-of-code post +
   `/lenny` index note, both pushed 2026-07-14); still to do: profile README.
   (updated: 2026-07-14)
1. ⬜ Per-IP throttle if traffic ever warrants it (jogruber's API is a free community
   service — be polite); the bandwidth side is now covered by the daily budget guard.
   (updated: 2026-07-14)
1. ⬜ **Render auto-deploy is not firing** — pushes 239d159/e127154 sat ~1 h with the old
   code still serving (verified: origin badge still 299 KB truecolor). Likely the GitHub →
   Render hookup broke with the repo rename (days-with-commits → lenny). Fix in the Render
   dashboard: reconnect the repo / Manual Deploy, then confirm the redesigned landing page +
   bandwidth guard are live on olekwrites.com/lenny. (added: 2026-07-14)
1. ⬜ Nice-to-have: OG tags on the landing page so pasting the site link unfurls with a
   Lenny preview.

# Bugs

(none yet)

# Done

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
