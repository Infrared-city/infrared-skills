// Cloudflare Worker: serves the built app and proxies the Infrared API.
// The API key lives only here, as a Worker secret. The browser never sees it.
import { handleProxy, type ProxyEnv } from "./proxy.ts";

interface Env extends ProxyEnv {
  ASSETS: Fetcher;              // the built app (wrangler.jsonc "assets")
  RUN_LIMITER?: RateLimit;      // optional rate limit binding (wrangler.jsonc "ratelimits")
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    // A simple limit on write calls (job submit, upload URLs) per client IP.
    // An IP is a weak identity: key the limit on your signed-in user when you have one.
    if (env.RUN_LIMITER && request.method === "POST" && url.pathname.startsWith("/api/ir/")) {
      const { success } = await env.RUN_LIMITER.limit({ key: request.headers.get("CF-Connecting-IP") ?? "unknown" });
      if (!success) return new Response("Too many requests", { status: 429 });
    }
    // Your sign-in check goes here (for example, verify a session cookie or JWT).
    return (await handleProxy(request, env)) ?? env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;
