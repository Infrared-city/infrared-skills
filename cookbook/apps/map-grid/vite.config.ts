// Dev server + the key-holding proxy from ../cloudflare-proxy (the same code runs there in production).
// The proxy runs in Node and adds the API key. The key never goes into the browser bundle:
// Vite only gives VITE_* variables to client code.
import { Readable } from "node:stream";
import { defineConfig, loadEnv, type Plugin } from "vite";
import { handleProxy } from "../cloudflare-proxy/src/proxy.ts";

function infraredProxy(apiKey: string): Plugin {
  return {
    name: "infrared-proxy",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        if (!req.url?.startsWith("/api/")) return next();
        // Node request -> Web Request -> handleProxy -> Node response.
        const hasBody = req.method !== "GET" && req.method !== "HEAD";
        const request = new Request(`http://${req.headers.host}${req.url}`, {
          method: req.method,
          headers: req.headers as Record<string, string>,
          body: hasBody ? (Readable.toWeb(req) as ReadableStream) : undefined,
          ...(hasBody ? { duplex: "half" } : {}),
        } as RequestInit);
        try {
          const response = await handleProxy(request, { INFRARED_API_KEY: apiKey });
          if (!response) return next();
          // Node's fetch already decoded the body: drop the encoding headers.
          const headers = Object.fromEntries([...response.headers].filter(
            ([k]) => !["content-encoding", "content-length", "transfer-encoding"].includes(k)));
          res.writeHead(response.status, headers);
          res.end(Buffer.from(await response.arrayBuffer()));
        } catch (error) {
          next(error);
        }
      });
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), ""); // .env file + shell environment
  if (!env.INFRARED_API_KEY) console.warn("INFRARED_API_KEY is not set: runs will fail.");
  return {
    plugins: [infraredProxy(env.INFRARED_API_KEY ?? "")],
    build: { target: "es2022" }, // top-level await
    // The SDK loads its WASM core from a URL; do not pre-bundle it.
    optimizeDeps: { exclude: ["@infrared-city/infrared-sdk"] },
  };
});
