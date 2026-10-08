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
  `Authorization`, cookies and `Origin`. It forwards only the routes the SDK
  calls (a strict allowlist). Every other route gets 403.
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
2. Route allowlist: `/api/ir/<path>` is forwarded only when method and path are an
   SDK call. Any other path or method gets 403.
3. Allowed calls go to `https://api.infrared.city/v2/<path>` with `X-Api-Key: env.INFRARED_API_KEY`.
4. `/api/s3/<host>/<key>` → GET/HEAD only, `host` must match the results bucket, no key.

| Method | Path (after `/v2`) | Why the SDK calls it |
|---|---|---|
| POST | `/uploads/presign` | Upload URL for the geometry |
| GET | `/binary/v1/capabilities` | Which geometry formats the API reads |
| POST | `/binary/v1/async/<analysis>`, `/async/<analysis>` | Submit one job |
| GET | `/async/jobs?ids=...`, `/async/jobs/<id>` | Job status (batch, one) |
| GET | `/async/jobs/<id>/results` | Result download URL |
| GET | `/billing/pricing` | Public price list (preview with live pricing) |

If a later SDK version calls a new route, that call gets 403. Add the route to
`API_ROUTES` in `src/proxy.ts`.

The apps' Vite dev servers run the same `handleProxy`, so dev = prod.
Do not start a dev server with `--host`: the dev server holds the real key, and on
the network a foreign page can pass the `Origin` check.

## Who spends your tokens

The proxy spends **your** key for every visitor that it lets through. The `Origin`
check stops other web pages, but not scripts. The rate limit caps the speed, not
the total. For a public app, add a sign-in check in the Worker. Then only your
signed-in users can start runs.

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
→ 403, relay to another host → 403, relay PUT → 403 or 405, a route that is not
on the allowlist → 403.
