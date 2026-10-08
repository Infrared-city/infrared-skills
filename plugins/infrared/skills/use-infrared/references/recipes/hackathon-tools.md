# Hackathon and demo: the fastest path

Ship a working Infrared demo in a day. Pick one row, copy the cookbook app, change it.
For speed rules (one client, preview first, let the SDK poll, baked samples), read
[../building-fast-apps.md](../building-fast-apps.md) once.

## Pick a starting point

| You want | Start from | Time to first map |
|---|---|---|
| A map in the browser, for yourself | `cookbook/apps/map-grid` ([../typescript/map-grid.md](../typescript/map-grid.md)) | minutes |
| Facades and roofs in 3D | `cookbook/apps/facades-3d` ([../typescript/facades-3d.md](../typescript/facades-3d.md)) | minutes |
| A public URL that others can use | map-grid + `cookbook/apps/cloudflare-proxy` ([../typescript/cloudflare-proxy.md](../typescript/cloudflare-proxy.md)) | an hour |
| A Python API for any front end (web, mobile, CAD) | `cookbook/apps/python-fastapi` ([python-fastapi-app.md](python-fastapi-app.md)) | an hour |
| Sign-in, stored runs, credits | add [persistence-and-users.md](persistence-and-users.md) | half a day |
| A plot or a study, no app | `cookbook/notebooks/00_quickstart.ipynb` ([../python/quickstart.md](../python/quickstart.md)) | minutes |
| A plugin in SketchUp or another CAD tool | [sketchup-plugin.md](sketchup-plugin.md) | a day |

## Five rules for a demo that works on stage

1. **Bake the first map.** Run the sample site one time before the demo and ship the result as
   a static file. The page shows a map at once, with no job and no wait
   ([../building-fast-apps.md](../building-fast-apps.md), section 7).
2. **Preview before Run.** Show jobs and tokens. The preview is free.
3. **Use the user's own model if they have one.** Public buildings (`infrared-sdk[geodata]`)
   are the fallback. Say where the data comes from.
4. **One fixed colour scale per analysis, with a legend and a unit**
   ([rendering-results-well.md](rendering-results-well.md)).
5. **Keep the key on a server.** Never in a `VITE_*` variable or the bundle. Set it as a
   secret on the host (Cloudflare, Railway, Render, Hugging Face Space secrets).

## A quick Python UI (Gradio or Streamlit)

Good for a one-screen tool on Hugging Face Spaces. Keep it thin:

- Make one `InfraredClient()` at module level, not in the click handler.
- Run with `run_area_and_wait(..., on_progress=...)` and show `succeeded / total`.
  Do not write a poll loop.
- Draw with `result.physical_grid()`, never `merged_grid` (its stored type differs per
  analysis). For the official colours, `client.weather.gen_grid_image(grid=rows, analysis_type=...)`
  with `rows = result.to_list()[::-1]` (north at the top).
- A map picker: Gradio has no map component. Put Leaflet in a `gr.HTML` block, or take lat/lon as
  two number fields.
- Cache results by input hash in a dict. A double click must not bill twice.

## Hosting

| Host | Fits | Notes |
|---|---|---|
| Cloudflare Workers + static assets | TypeScript apps and the key proxy | Free tier; `npx wrangler deploy` |
| Railway, Render, Fly.io | The Python service | One instance, one worker. Free tiers sleep: call `/health` before the demo. |
| Hugging Face Spaces | Gradio or Streamlit | The key goes into Space secrets |
| Supabase | Sign-in, Postgres, storage | Free projects pause after a week with no use |

These are independent third-party services. Infrared has no affiliation with them.

## Payments in a demo

Leave them out. If the demo must show credits, use Stripe test mode or Polar with the
ledger in [persistence-and-users.md](persistence-and-users.md).
