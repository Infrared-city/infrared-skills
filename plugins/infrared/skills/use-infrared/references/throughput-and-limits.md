# What can one account do? Speed and limits

Use this page to get a feel for the numbers. All figures are rounded.
They are indicators, not promises. Check a real run with a free preview.

## The short version

- A normal account can run up to about 100 tiles (jobs) per second.
- At high rates, your own upload and download (network I/O) is usually the
  bottleneck, not the backend.
- Enterprise clients can go much higher. See <https://infrared.city> to learn
  more, and contact us for a custom setup.
- A ground analysis of 6 km² finishes in about 3 seconds when it is warm.
  40 km² takes about 8 seconds.
- Millions of facade sensors finish in seconds.
- The first run is slower than the next runs. The first run uploads your
  geometry. The next runs reuse it.

## How an area becomes tiles and jobs

The SDK cuts an area into 512 m tiles. One tile is one job. Solar-family
analyses (SVF, solar radiation, direct sun hours) use few tiles. Wind uses
more, because wind tiles step 256 m.

| Area | Solar-family tiles | Wind tiles |
|---|---|---|
| 1 km² | about 4 | about 16 |
| 6 km² | 25 | 100 |
| 20 km² | 81 | 324 |
| 40 km² | about 170 | about 650 |

- The default cap is 100 tiles per run. A bigger run is refused until you
  pass `max_tiles_override` (Python) or `maxTilesOverride` (TypeScript).
  Wind passes the cap at about 6 km².
- For one analysis over one area, the run builds one grid. Several analyses
  on the same site share one upload of the geometry.
- Facade runs bill per batch of buildings, not per tile. Use
  `previewAreaBatches` (TypeScript) or `preview_area` (Python). Both are
  free and local.

## How tokens scale

- A grid job costs about 10 tokens. A preview shows the exact number:
  25 tiles gave about 250 tokens, 27 facade jobs about 270.
- So tokens are roughly `tiles x 10 x number of analyses`.
- Run the preview before every large run. Read `estimated_cost_tokens`.
- A failed submit that is sent again is never billed twice.

## Speed ceiling, from the request limit

Derive the ceiling yourself:

1. Limit: about 100 tiles per second.
2. One solar-family tile covers about 0.26 km² (512 m x 512 m).
3. 100 tiles/s x 0.26 km² = about 26 km² per second, or about
   1,500 km² per minute.
4. One wind tile covers about 0.066 km² (256 m step).
   100 x 0.066 = about 6.5 km² per second, or about 390 km² per minute.

This is a ceiling. A real run is slower, because it also waits for the
upload of your geometry, the server queue and the download of the
results. Usually your uplink is the bottleneck. Use the measured numbers
below for planning.

## Measured speed (SDK 1.0.0, production, October 2026)

Python SDK on a 32-core machine, SVF ground analysis, buildings already
loaded (the building fetch is not in the time).

| Run | Tiles | Cold first run | Warm re-run |
|---|---|---|---|
| 6 km², about 3,400 buildings | 25 | about 8.5 s | about 3 s |
| 40 km², about 24,000 buildings | 169 | about 15 s | about 8 s |

- Cold means the first run: the geometry upload is in the time.
- Warm means a repeat in the same process: the SDK reuses the upload.
- Rule of thumb: about 150 km² per minute cold and about 300 km² per
  minute warm for a ground analysis. This is below the ceiling above. A
  small area is slower per km², because fixed costs dominate.

Facades, 6 km² of a dense city, SVF: about 2.8 million sensors on about
42,000 surfaces. The run took about 4 s cold and about 2.6 s warm. A larger
multi-million-sensor city run takes about 10 seconds.

How the time splits on the 40 km² cold run (total about 15 s):

- about 1.6 s to the first job (plan, first upload),
- about 13 s in the cloud, with uploads and the first downloads running
  at the same time,
- the rest is the final merge.

The warm run has no upload. It is almost half the time.

### Facades and roofs, small site and city block (local Python SDK)

Python SDK 1.0.0 on a 12-core laptop, staging API, `analysis_surfaces="all"`, Hong Kong
city model. Time of `run_area_and_wait`, one client. "4 analyses" = SVF, solar radiation,
daylight availability and direct sun hours in one call.

| Site | Buildings | Cells | Sensors | Analyses | Total sensors | Jobs | Cold | Warm |
|---|---|---|---|---|---|---|---|---|
| 70 m x 70 m | 4 | 2 m | 11,788 | 1 | 11,788 | 1 | 1.9-5.6 s | 0.9 s |
| 70 m x 70 m | 4 | 2 m | 11,788 | 4 | 47,152 | 4 | 2.8-4.2 s | 2.3 s |
| 1.2 km x 1.2 km | 1,843 | 2 m | 2.5 million | 1 | 2.5 million | 16 | 9.5-15 s | 7.5-10 s |
| 1.2 km x 1.2 km | 1,843 | 4 m | 0.85 million | 4 | 3.4 million | 36 | 12 s | 11.5 s |
| 1.2 km x 1.2 km | 1,843 | 2 m | 2.5 million | 4 | 10 million | 64 | 23-26 s | 16 s |
| 1.2 km x 1.2 km | 1,843 | 1 m | 8.1 million | 4 | 32 million | 228 | - | 33 s |

"Sensors" is for one analysis; "Total sensors" is for the whole call.

- Cold = new client: first upload (about 20 MiB for the 1.2 km block), connections. Warm = same
  client, the geometry is reused. A small site runs one real analysis in about 1 s warm.
- Sensors drive jobs and price: about 250,000 sensors per job. 1 m costs 3.6 times 2 m.
- From a new client, 4 analyses in one call took 23 s; one call each took 36 s. In 1.0.0, each
  analysis plans its facade jobs again on your machine (1.4 s at 2 m, 3.5 s at 1 m, per analysis).

## Local planning is free

Planning is local CPU work and costs no tokens. Measured on 2026-10-08,
Node 22, about 20 km² with about 68,000 buildings: on one core, a ground run
plans in about 3 seconds and a facade run (about 18 million sensors) in
about 9 seconds. The threaded
core halves the facade plan. See `typescript/threads-and-workers.md`.

## Example scenarios

These are estimates from the numbers above.

**A district of 5 km².**
About 25 solar-family tiles per analysis, so about 250 tokens each.
Cold run about 8 s, warm run about 3 s. SVF, solar and UTCI together reuse
one upload. Wind needs about 81 tiles (about 810 tokens), still under the
default cap.

**A whole city centre of 40 km².**
About 170 solar-family tiles, about 1,700 tokens per analysis. You must
pass `max_tiles_override`. Expect about 15 s cold and about 8 s warm. Wind
would be about 650 tiles (about 6,500 tokens). Split the area if the
result grid is too large for your memory.

**1,000 design variants overnight.**
Take a block of about 0.5 km². It is about 4 tiles, so about 40 tokens a
variant and about 40,000 tokens for 1,000 variants. Each variant is a warm
run of a few seconds at most, so 1,000 variants one after another fit in
about an hour. Run them in one process so the SDK reuses what it can. A
changed building is new geometry and uploads again. Preview one variant
first and multiply.

## Practical advice

- Preview first. It is free.
- Keep one SDK client per process. See `typescript/threads-and-workers.md`.
- For many analyses on one site, pass them in one call or in one process.
- Do not poll faster than the SDK does. The SDK sends batched status calls.
- If you see HTTP 429 (too many requests), the SDK waits and retries. If it
  is frequent, you are near your account limit. Contact us for more.
