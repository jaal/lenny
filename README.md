# days-with-commits

**Days without missing a commit** — your GitHub commit streak on the Lenny
("0 days without an accident") Simpsons sign, as a live image anyone can embed.

- Landing page at `/` — paste a GitHub URL or username, get the image + embed snippets.
- Stable image URL per user: `https://<domain>/<githubname>` (`.png` optional).
  The number is computed from live contribution data on every fetch, so the
  image is always current — no cron needed.
- `?from=YYYY-MM-DD` switches from streak to "days with ≥ 1 commit since that
  date" (e.g. `/jaal?from=2026-05-27`).

## How it works
- `counter.py` — fetches the contribution graph from the public mirror
  (github-contributions-api.jogruber.de, no GitHub token), computes the
  streak / windowed count, and draws the number + captions onto
  `assets/lenny.png` with Pillow (bundled DejaVu Sans Bold, free license).
- `app.py` — Flask: `/` landing page, `/<username>` PNG endpoint. Results are
  cached in-process per user per UTC day; `Cache-Control: max-age` is set to
  6 h, shortened near UTC midnight so caches expire right when the count can
  actually change.
- Bandwidth guard: a per-UTC-day budget protects the Render free tier's
  100 GB/month. Under the soft cap (`BW_SOFT_CAP_MB`, default 2000) images
  are full-size; between soft and hard cap (`BW_HARD_CAP_MB`, default 3000)
  they're served half-size; past the hard cap requests get 429 + Retry-After
  until midnight. The counter is in-process, so a restart forgets the day's
  spend — the caps leave margin for that (3 GB/day ≈ 93 GB/month worst case).

## Run locally
```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python app.py   # http://127.0.0.1:5001
```

## Deploy
`render.yaml` defines the service (free plan, `gunicorn app:app`). Push the
repo to GitHub and create a Blueprint on Render.

Public URL: **olekwrites.com/lenny** — a Cloudflare Worker
(`cloudflare/worker.js`, setup steps inside) proxies `olekwrites.com/lenny*`
to the Render service, e.g. `olekwrites.com/lenny/jaal`. The landing page is
prefix-aware, and Cloudflare's edge cache serves repeat image views without
touching Render.

⚠️ Free-plan caveat: Render spins the service down after ~15 min idle and a
cold start takes ~30 s — longer than GitHub Camo's ~4 s image timeout, so
README embeds can show a broken image until the service is warm. Fixes:
starter plan (~$7/mo), or an external uptime pinger.
