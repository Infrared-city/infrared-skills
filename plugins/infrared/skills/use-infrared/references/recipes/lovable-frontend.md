# Recipe: Lovable.dev Frontend → Your FastAPI Backend

> **No affiliation.** Lovable.dev is an independent third-party tool — feel free to swap for v0.dev, bolt.new, or hand-built React; the FastAPI side of the recipe is unchanged.
> **Official docs:** [docs.lovable.dev](https://docs.lovable.dev) (agent-friendly: [llms.txt](https://docs.lovable.dev/llms.txt)).

Generate the entire UI with [Lovable](https://lovable.dev) in a chat, point it at your Infrared-wrapping FastAPI on Railway, and ship a hackathon demo in under an hour. The trick is one URL: your FastAPI service's `/openapi.json`, which Lovable consumes to scaffold a typed fetch client.

Pairs with [`python-fastapi-railway.md`](python-fastapi-railway.md) (the backend) and optionally [`persistence-and-users.md`](persistence-and-users.md) (DB + auth).

## What Lovable outputs

A standard **Vite + React + TypeScript + Tailwind + shadcn/ui** project. SPA only — no SSR, no server-side routes. The build is static `dist/`, hostable anywhere (Lovable Cloud, Cloudflare Pages, Vercel, Netlify, S3 + CloudFront, even GitHub Pages).

Lovable bundles a Supabase integration ("Lovable Cloud") for DB + auth. **You don't need it for this recipe** — your backend is FastAPI. Mention Supabase only if you specifically want Lovable to handle auth (then your FastAPI verifies the JWT with Supabase's JWT secret — use `PyJWT` or `python-jose`; verification code is not in the sibling recipe — implement it before going live with real users). See [`persistence-and-users.md`](persistence-and-users.md) Path C.

## The integration shape

```
[ Browser: Lovable-generated React SPA ]
              │
              │  fetch  (VITE_API_BASE_URL)
              ▼
[ Railway: your FastAPI + Infrared SDK ]
              │
              │  X-Api-Key
              ▼
[ api.infrared.city ]
```

- **Secrets in the browser bundle:** only `VITE_API_BASE_URL`. **Never** `INFRARED_API_KEY`.
- **CORS:** your FastAPI must allow the exact Lovable preview URL and your production domain (see step 1 below).
- **No proxy required.** Browser → FastAPI directly. FastAPI holds the Infrared key.

## Step-by-step

### 1. Backend ready

Follow [`python-fastapi-railway.md`](python-fastapi-railway.md). Confirm two things:

```bash
curl https://my-api.up.railway.app/openapi.json        # returns JSON
curl -X POST https://my-api.up.railway.app/sims/sun-hours \
  -H 'Content-Type: application/json' \
  -d '{"lat":48.21,"lon":16.36,"month":7}'              # returns a grid
```

Add Lovable preview to your CORS allowlist via Railway Variables:

```
CORS_ORIGINS=["https://abcd1234.lovable.app","https://my-app.pages.dev"]
```

List the specific preview URL Lovable gives you (e.g. `https://abcd1234.lovable.app`) plus your prod domain. FastAPI/Starlette `CORSMiddleware` does NOT support wildcard subdomains — only literal origins or the all-allow `"*"`.

### 2. New Lovable project

1. lovable.dev → **New Project**.
2. Open the chat. Paste your OpenAPI URL with a directive:

> Use the API at `https://my-api.up.railway.app/openapi.json` for all data. Build a single-page UI: a MapLibre map centred on Vienna, a "Run sun-hours" button that calls `POST /sims/sun-hours` with the map centre, and a panel showing min/mean/max from the result grid. Don't use Supabase. Save the API base URL as `VITE_API_BASE_URL`.

Lovable scaffolds `src/lib/api.ts` with typed fetch wrappers per endpoint, drops a `MapView.tsx`, wires the button.

### 3. Set the env var

In Lovable → **Cloud tab** (the `+` button next to Preview) → **Secrets**:

```
VITE_API_BASE_URL=https://my-api.up.railway.app
```

Anything `VITE_*` lands in the browser bundle — that's correct for a public API base URL. Anything sensitive stays on the FastAPI side. **Deploy gotcha:** Lovable's Cloud Secrets do NOT auto-transfer to Cloudflare Pages or Vercel — when you deploy externally (step 5), re-add `VITE_API_BASE_URL` in the host's env-var UI or the deployed app shows `undefined`.

### 4. Iterate in chat

- "Add a dropdown to pick the analysis: sun-hours, pwc, utci."
- "Show the result grid as a heatmap layer using the bounds field from the response."
- "Add a KPI panel with the three numbers — mean, min, max — using shadcn `Card`."

Lovable's `Visual Edit` mode lets you click on a component and ask for tweaks ("make this title smaller, less margin"). For the patterns in [`typescript-frontend-patterns.md`](typescript-frontend-patterns.md), paste the snippet into chat with "use this code as the heatmap layer."

### 5. Deploy

Lovable hosts a preview at `https://your-project.lovable.app` automatically. For a real domain:

1. Lovable → **Connect** → GitHub. Auto-pushes generated code to a repo.
2. From the repo, deploy to Cloudflare Pages:
   - Build command: `npm run build`
   - Output dir: `dist`
   - Env var: `VITE_API_BASE_URL=https://my-api.up.railway.app`
3. Push to the repo (from Lovable or manually) → CF Pages auto-redeploys.

Don't forget to add the CF Pages URL to your FastAPI `CORS_ORIGINS`.

## Adding credits and Stripe payments

Your FastAPI from [`python-fastapi-railway.md`](python-fastapi-railway.md) plus the Stripe webhook stub in [`persistence-and-users.md`](persistence-and-users.md) provides the backend half: `POST /billing/checkout-session` returns a Stripe Checkout URL, `POST /webhooks/stripe` tops up credits, `deduct_credits()` decrements per sim run.

Lovable's **native** "Add Stripe integration" button is Supabase-locked — it scaffolds Supabase Edge Functions for session creation + webhook. For our FastAPI backend, **ignore the native button** and prompt Lovable to write plain fetches to your own backend instead.

**Contract reminder:** on the FastAPI side, when creating the Stripe Checkout Session, set both `client_reference_id=user.id` AND `metadata={"credits": "50"}`. The webhook in `persistence-and-users.md` reads both — without them it crashes with `KeyError`.

### Step 1 — Wire the Buy Credits button

In Lovable chat:

> Add a "Buy Credits" button in the nav bar. Clicking it POSTs to `${VITE_API_BASE_URL}/billing/checkout-session` with body `{ "user_id": currentUserId, "credits": 50 }`. Take the returned `checkout_url` and do `window.location.href = checkout_url`.

### Step 2 — Show credit balance

> Add a credit balance to the nav bar. Fetch `GET ${VITE_API_BASE_URL}/users/me` (returns `{ credits: number }`) on mount and after each sim run. Also refresh when the URL contains `?payment=success`.

Add a `GET /users/me` route to your FastAPI alongside the existing credit-deduction logic.

### Step 3 — Stripe success redirect

On the FastAPI side, set the Checkout Session's `success_url` to `{FRONTEND_URL}/?payment=success&session_id={CHECKOUT_SESSION_ID}` so the frontend can detect the return and refresh the balance. `cancel_url` to `{FRONTEND_URL}/?payment=cancelled`.

### Pitfalls

- **Stripe doesn't work in Lovable preview mode** — the editor preview runs in a sandboxed iframe, and Stripe.js blocks iframe contexts for security. Test on the deployed `.lovable.app` URL or your custom domain, not in chat preview.
- **CORS on the Stripe POST** — the `POST /billing/checkout-session` call goes through your FastAPI before Stripe sees it. Add your `.lovable.app` URL and any custom domain to `CORS_ORIGINS` on the FastAPI side. Symptom of missing CORS: "Network Error" on the Buy button.
- **Lovable will push you to Supabase** — when it says "I need to connect Supabase first to set up Stripe," ignore it. Your FastAPI is the backend.
- **Webhooks need HTTPS** — Railway gives you that for free; use the public Railway URL in Stripe Dashboard → Developers → Webhooks.
- **Local webhook testing** — `stripe listen --forward-to localhost:8000/webhooks/stripe`.

For EU VAT handling (Polar Merchant of Record) and a no-ledger metered-billing alternative, see the **Billing shortcuts** section in [`persistence-and-users.md`](persistence-and-users.md).

## Pricing and limits

Lovable has a free tier with daily usage caps and paid tiers with more headroom. Current limits and pricing: [docs.lovable.dev](https://docs.lovable.dev). For a hackathon, free is usually enough to scaffold + a handful of tweaks; upgrade if your team will be iterating heavily.

## Pitfalls

- **Lovable wants to add Supabase** — when it asks, say "no, I'm using my own FastAPI backend at `<URL>`." It will respect that, but the default suggestion is always Supabase.
- **CORS preflight failures** — symptom: empty response or "Network Error" in the browser. Check the response headers for `access-control-allow-origin` matching the Lovable preview origin exactly. Wildcards with credentials are forbidden by spec.
- **API key in `VITE_` env** — anything prefixed `VITE_` is bundled into the browser JS. If you accidentally do `VITE_INFRARED_API_KEY`, your key is public. Rotate immediately and remove. The only safe env is `VITE_API_BASE_URL`.
- **OpenAPI schema drift** — Lovable scaffolds from your `/openapi.json` at the time you paste it. If you change the FastAPI route shape later, paste the URL again and ask Lovable to "refresh the client from the updated OpenAPI spec."
- **No SSR** — Lovable's output is pure SPA. If SEO matters or you need per-request server logic, you'll outgrow it. For hackathon demos: a non-issue.
- **GitHub export only** — there's no ZIP download. To work locally you must connect GitHub first.
- **Rate limits on free** — heavy chat iteration will deplete the 5/day fast. Batch your asks ("add the heatmap + KPI panel + scenario dropdown in one prompt") instead of one ask per change.

## When Lovable isn't right

- You want a non-React stack (Svelte, Vue, vanilla). Lovable is React-only.
- You need real SSR or Edge Functions in the frontend. Use Next.js by hand.
- You need full design control from day 1. Lovable's shadcn output is great but opinionated; rebranding takes effort.
- The hackathon judging values craft over speed. Hand-built frontends still win on polish.

## See also

- Backend Lovable points at: [`python-fastapi-railway.md`](python-fastapi-railway.md)
- Hand-written equivalents of what Lovable scaffolds: [`typescript-frontend-patterns.md`](typescript-frontend-patterns.md)
- Add real users + billing behind the backend: [`persistence-and-users.md`](persistence-and-users.md)
