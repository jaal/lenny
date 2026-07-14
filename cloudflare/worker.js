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

export default {
  async fetch(request) {
    const url = new URL(request.url);
    let path = url.pathname.slice(PREFIX.length) || "/";
    if (!path.startsWith("/")) path = "/" + path;
    const upstream = new Request(UPSTREAM + path + url.search, request);
    return fetch(upstream, { cf: { cacheEverything: true } });
  },
};
