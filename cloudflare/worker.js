/**
 * Proxies olekwrites.com/lenny* to the Render service.
 *
 * Setup (Cloudflare dashboard, free plan):
 *   1. Workers & Pages → Create → Worker, paste this file, deploy.
 *   2. Websites → olekwrites.com → Workers Routes → Add route:
 *        Route:  olekwrites.com/lenny*
 *        Worker: this one
 *   3. Update UPSTREAM below if the Render URL differs.
 *
 * Cloudflare's edge cache honors the app's Cache-Control (1 h), so repeat
 * image views are served from the edge without waking Render.
 */

const UPSTREAM = "https://days-with-commits.onrender.com";
const PREFIX = "/lenny";

// A badge path: "/<github-username>" or "/<github-username>.png", matching the
// app's own USERNAME_RE. Everything else this service serves is HTML — the
// landing page and the Vivaldi widget page.
const BADGE = /^\/[A-Za-z0-9][A-Za-z0-9-]{0,38}(\.png)?$/;

export default {
  async fetch(request) {
    const url = new URL(request.url);
    let path = url.pathname.slice(PREFIX.length) || "/";
    if (!path.startsWith("/")) path = "/" + path;
    const upstream = new Request(UPSTREAM + path + url.search, request);
    // Edge-cache the badges only. cacheEverything on an HTML response makes
    // Cloudflare cache it, and once it does, the zone's Browser Cache TTL (4 h)
    // overwrites the origin's Cache-Control — so the app's `no-cache` on the
    // landing page and the widget page was being rewritten to max-age=14400 and
    // browsers held stale HTML across deploys. Leaving HTML uncached lets the
    // origin headers through untouched. Badges want the opposite: they carry a
    // long max-age on purpose, and every edge hit is a Render wake-up avoided.
    return fetch(upstream, { cf: { cacheEverything: BADGE.test(path) } });
  },
};
