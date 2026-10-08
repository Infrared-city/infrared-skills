// The key-holding proxy, written with Web standard Request/Response only.
// The Cloudflare Worker (worker.ts) uses it in production. The Vite dev servers
// of ../map-grid and ../facades-3d use the same file, so dev = prod.
//
//   /api/ir/<path>          -> https://api.infrared.city/v2/<path>  (+ X-Api-Key)
//   /api/s3/<host>/<key>?.. -> https://<host>/<key>?..              (result download, no key)
//
// Why the second route: the result download is a presigned storage URL on
// another origin, and that bucket sends no CORS headers, so the browser blocks
// it. The relay forwards it without any credential: the URL carries its own signature.

export interface ProxyEnv {
  /** The Infrared API key. A secret: `wrangler secret put INFRARED_API_KEY`. */
  INFRARED_API_KEY: string;
  /** Comma-separated extra origins that may call the proxy (the page's own origin always may). */
  ALLOWED_ORIGINS?: string;
}

const API_BASE = "https://api.infrared.city/v2";
const API_PREFIX = "/api/ir/";
const RELAY_PREFIX = "/api/s3/";
/** Only the results bucket may be relayed. Never relay any host: that is an open proxy. */
export const RESULTS_HOST = /^infrared-async-inference-jobs-outputs\.s3\.[a-z0-9-]+\.amazonaws\.com$/;

/** Browser-side helper: the relay path for a presigned result URL, or the URL unchanged. */
export function relayUrl(url: string): string {
  const u = new URL(url, "http://relative.invalid");
  return RESULTS_HOST.test(u.host) ? `${RELAY_PREFIX}${u.host}${u.pathname}${u.search}` : url;
}

const json = (status: number, message: string) =>
  new Response(JSON.stringify({ error: message }), { status, headers: { "content-type": "application/json" } });

/** Handle one request. Returns `undefined` when the path is not a proxy path. */
export async function handleProxy(request: Request, env: ProxyEnv): Promise<Response | undefined> {
  const url = new URL(request.url);
  const isApi = url.pathname.startsWith(API_PREFIX);
  const isRelay = url.pathname.startsWith(RELAY_PREFIX);
  if (!isApi && !isRelay) return undefined;

  // 1. Origin check. A browser sends `Origin` on every POST and on cross-origin GETs.
  //    It stops other web pages from using your key. It does NOT stop scripts:
  //    add your own sign-in check and a rate limit for that (see README).
  const origin = request.headers.get("Origin");
  const allowed = new Set([url.origin, ...(env.ALLOWED_ORIGINS ?? "").split(",").map((s) => s.trim()).filter(Boolean)]);
  if (origin && !allowed.has(origin)) return json(403, "origin not allowed");
  if (request.method !== "GET" && request.method !== "HEAD" && !origin) return json(403, "missing Origin");

  if (isApi) {
    if (!env.INFRARED_API_KEY) return json(500, "INFRARED_API_KEY is not set on the proxy");
    const target = `${API_BASE}/${url.pathname.slice(API_PREFIX.length)}${url.search}`;
    const headers = new Headers(request.headers);
    for (const h of ["host", "cookie", "authorization", "origin", "referer"]) headers.delete(h);
    headers.set("X-Api-Key", env.INFRARED_API_KEY);  // the only place the key exists
    const hasBody = request.method !== "GET" && request.method !== "HEAD";
    return fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      // Node's fetch needs this for a streamed body; Workers ignore it.
      ...(hasBody ? { duplex: "half" } : {}),
    } as RequestInit);
  }

  // Relay: GET/HEAD only, results bucket only, no key, no cookies.
  if (request.method !== "GET" && request.method !== "HEAD") return json(405, "relay is read-only");
  const rest = url.pathname.slice(RELAY_PREFIX.length);
  const slash = rest.indexOf("/");
  const host = slash > 0 ? rest.slice(0, slash) : "";
  if (!RESULTS_HOST.test(host)) return json(403, "host not allowed");
  return fetch(`https://${host}${rest.slice(slash)}${url.search}`, { method: request.method });
}
