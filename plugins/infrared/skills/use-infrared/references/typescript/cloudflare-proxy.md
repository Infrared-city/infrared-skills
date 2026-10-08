# Production: keep the API key in a proxy (Cloudflare Worker)

Runnable app: [cookbook/apps/cloudflare-proxy](https://github.com/Infrared-city/infrared-skills/tree/main/cookbook/apps/cloudflare-proxy).
Guide: [Serve many users](https://infrared.city/docs/sdk/1.0/#serve-many-users),
[TypeScript in the browser](https://infrared.city/docs/sdk/1.0/#typescript-in-the-browser).

**Never send the API key to a browser.** Not in the bundle, not in a `VITE_*`
variable, not in a request header from the page. The browser calls a path on its
own origin; a server adds the key.

## The shape

```
browser ── /api/ir/*  ──> Worker (+ X-Api-Key) ──> https://api.infrared.city/v2/*
browser ── /api/s3/<host>/<key> ──> Worker (no key) ──> presigned result download
browser ── PUT presigned upload URL ──> storage, direct (no proxy)
```

- **API calls** go through the proxy. It adds `X-Api-Key` and drops the browser's
  `Authorization`, cookies and `Origin`.
- **Result downloads** go through a relay route. They are presigned storage URLs on
  another origin, and the results bucket sends no CORS headers, so the browser
  blocks a direct download. The relay adds no key: the URL carries its signature.
  Allow only the results bucket host (an open relay is an open proxy).
- **Geometry uploads** (presigned PUT) go straight to storage. That bucket allows it.

## Browser client

```ts
const client = new InfraredClient({
  baseUrl: `${location.origin}/api/ir`,
  auth: async () => ({}),   // the proxy signs; see below
  fetch: (input, init) => fetch(input instanceof Request ? input : relayUrl(String(input)), init),
});
```

`InfraredClient` needs one credential option. With none of `apiKey`, `token`,
`getToken` or `auth`, the constructor throws ("provide at least one of `apiKey`,
`token`, or `getToken`"). An `auth` function that returns no header is accepted.
With your own sign-in, return your session token here and check it in the Worker:

```ts
auth: async () => ({ Authorization: `Bearer ${await session.token()}` }),
```

`relayUrl` rewrites a results-bucket URL to `/api/s3/<host>/<path>?<query>` and
leaves every other URL alone. A custom `fetch` also carries the presigned upload
(the SDK uses XHR only with its default fetch).

## Worker (shape)

```ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // 1. Rate limit write calls (binding "ratelimits" in wrangler.jsonc).
    // 2. Your sign-in check (session cookie or JWT). This protects your token budget.
    // 3. Proxy /api/ir/* and /api/s3/*; else serve the static app.
    return (await handleProxy(request, env)) ?? env.ASSETS.fetch(request);
  },
};
```

`handleProxy` (in `src/proxy.ts`, Web `Request`/`Response` only, about 60 lines):

1. `Origin` check: a POST must come from the Worker's own origin or `ALLOWED_ORIGINS`.
   This stops other web pages. It does not stop scripts.
2. `/api/ir/<path>` → `https://api.infrared.city/v2/<path>` with `X-Api-Key: env.INFRARED_API_KEY`.
3. `/api/s3/<host>/<key>` → GET/HEAD only, `host` must match the results bucket, no key.

The apps' Vite dev servers run the same `handleProxy`, so dev = prod.

## Config and secrets

```jsonc
// wrangler.jsonc
"assets": { "directory": "../map-grid/dist", "binding": "ASSETS", "run_worker_first": ["/api/*"] },
"vars": { "ALLOWED_ORIGINS": "" },
"ratelimits": [{ "name": "RUN_LIMITER", "namespace_id": "1001", "simple": { "limit": 60, "period": 60 } }]
```

- Production: `npx wrangler secret put INFRARED_API_KEY`, then `npx wrangler deploy`.
- Local: put `INFRARED_API_KEY=...` in `.dev.vars` (git-ignored), then `npx wrangler dev`.
- A run of N tiles makes about 2 N POSTs (upload URL + submit). Set the limit above
  that for your largest run, and key it on the signed-in user, not the IP.

## Other hosts

Any server that can forward a request works the same way (Node, Deno, a Pages
`_worker.js`, nginx). Keep the three rules: key added on the server, results relay
for one host only, uploads direct. Node and Workers can also call the API
directly with `apiKey`: CORS applies only in browsers.

## Tested

`wrangler dev` on a local port, against the production API: one SVF run from the
map-grid app (1 tile), result drawn. Foreign `Origin` → 403, POST without `Origin`
→ 403, relay to another host → 403, relay PUT → 403.
