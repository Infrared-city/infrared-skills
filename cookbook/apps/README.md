# TypeScript app recipes

Small, runnable web apps on the [Infrared TypeScript SDK](https://infrared.city/docs/sdk/1.0/api/typescript/)
(`@infrared-city/infrared-sdk-ts` 1.0.0). Copy one and change it.

| App | What it shows |
|---|---|
| [`map-grid/`](map-grid/) | MapLibre + deck.gl. Draw an area, see the job preview, press Run, see the ground grid with a legend. |
| [`facades-3d/`](facades-3d/) | three.js. Solar radiation on facades and roofs, one colour per cell, value on hover. |
| [`cloudflare-proxy/`](cloudflare-proxy/) | Production setup. A Cloudflare Worker holds the API key and serves the app. |

All three use the same rule: **the browser never holds the API key.** The browser
calls `/api/ir/*` on its own origin. A proxy adds the key and forwards the call to
`https://api.infrared.city/v2/*`. It forwards only the routes the SDK calls; all
other routes get 403. In development the Vite dev server is the proxy.
In production the Worker is the proxy. Both run the same file:
[`cloudflare-proxy/src/proxy.ts`](cloudflare-proxy/src/proxy.ts). Keep the three
folders side by side.

Requirements: Node 20 or later, an Infrared API key (<https://infrared.city>).
Each folder has a local `.npmrc` that gets the SDK from the public npm registry.
