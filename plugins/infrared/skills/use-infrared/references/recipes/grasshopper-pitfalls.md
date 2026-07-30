# Pitfalls, numbers and performance: Rhino/Grasshopper + Infrared SDK

Read [`grasshopper-component-shape.md`](grasshopper-component-shape.md) to
build one, and [`grasshopper-analyses.md`](grasshopper-analyses.md) for what
your analysis needs. Read this when something is wrong, or before you trust a number.

Everything here was measured on a real ~1,000-building Hong Kong site across
about forty failures. **The expensive ones all returned HTTP 200.**

---

## 0. Corrections to the existing skill pages

Four notes on the existing pages: **one retraction of a claim I made and got
wrong**, and three proposed edits that would each have saved a builder real
time. Each states its evidence and how strong it is.

### 0.1 `analyses/10-interior-daylight-factor.md` — RETRACTED

An earlier draft of this page claimed the following guidance was harmful:

> *"Windows are `openings`, not holes. Keep the wall; place the aperture in its
> plane, nudged a hair inside so it clearly belongs to that surface."*

**That claim was wrong, and the page is correct as written.** An adversarial
review of the server's interior-visibility behaviour found the design is not
only supported but unit-tested. In substance:

```text
APERTURE_COINCIDENCE_TOL = 0.5 m
  "an opaque hit within this band of an aperture hit means the opening is cut
   into that surface"

transmit  <-  aperture_distance is finite AND aperture_distance <= opaque_distance + TOL
```

and a test named for exactly this case builds a **solid wall with glazing
0.1 m behind it** and asserts it transmits at the opening factor. A coincident aperture in an unbroken wall is the intended path, the
tolerance is 0.5 m, and a 5 cm inset is comfortably inside it. The transmissive
march has been live since June, over a month before we hit the problem.

**So the wall does not need a hole.** Building one (opaque band below the sill,
band above the head, piers between punched windows) is legitimate — it is more
realistic geometry and it gives sensors variation along the wall — but it was
**not required to admit light**, and the earlier claim that it was is retracted.

**What actually caused ~0 daylight factor on every interior floor is not
established.** Ruled out: the apertures were correctly filed under `openings`
(verified in the payload dump — `category: "opening"`, `openingFactor: 0.7`),
so this was not the misfiled-aperture case the page itself warns about in §3.

The leading unexamined hypothesis is **sensor height versus sill height**, and
it is arithmetic rather than a bug: the analysis plane defaults to **0.8 m**,
while the window band computed a sill at **≈0.92 m**. Every sensor therefore
sat *below* the glazing, with an opaque floor slab above it, so sky access was
confined to a narrow near-horizon wedge — dim, and further blocked by
neighbours. On that reading the low values were substantially **physics, not a
defect**, and the deep-plate darkness in the final render is real.

**Experiment that would settle it** (small payload, one building, three floors):

| variant | geometry | expectation if the hypothesis holds |
|---|---|---|
| A | solid wall, coincident aperture, sill **below** 0.8 m | graded DF — matches the unit test |
| B | solid wall, coincident aperture, sill **above** 0.8 m | ~0, reproducing the failure |
| C | punched wall (real gap), sill above 0.8 m | ~0 as well, proving the gap was never the lever |

One more path worth ruling out first, cheaply: an **empty `openings` map**
falls through to a legacy all-or-nothing boolean visibility path, so a scene that lost its apertures anywhere upstream reads
as fully blocked rather than erroring. Check the dumped payload has them.

Until that runs, treat the punched-wall geometry as a modelling preference and
**check `analysis_height` against your sill before blaming anything else.**

### 0.2 `recipes/grasshopper.md` Pattern 4 — "Off-UI-thread work"

Current text recommends a worker thread calling `ExpireSolution(True)` for
`run_area_and_wait`.

**Do not do this for SDK area calls.** `run_area_and_wait` already does
submit → poll → merge internally, so a thread adds only a state machine — one
that can re-submit on a stuck toggle, file a result under the wrong AOI key,
and re-solve the whole document on every poll.

(An earlier draft supported this with "it lost the wait, then hung past six
minutes." That is a **different** failure: it came from splitting the call into
`run_area` + hand-rolled polling to get job ids early, which is a mistake on
any thread. Use `on_progress` for the ids instead — it hands over an
`AreaState` on the first poll. The two cautions are independent and conflating
them overstated the case against threading.)

**Blocking is the correct design here.** Grasshopper freezes for the duration;
say so in the log before it starts, and bound it with an explicit timeout. The
threading pattern remains fine for genuinely external work (a browser picker,
file I/O) — it is specifically wrong for a call that already manages its own
lifecycle.

Suggested replacement heading: *"Pattern 4 — Blocking is correct for area
runs (and why threading fails)."*

### 0.3 `recipes/grasshopper.md` Pattern 9 — the `Compact()` call

Pattern 9 is the only worked vertex-coloured-mesh example in the skill, and it
ends:

```python
m.Normals.ComputeNormals(); m.Compact()
```

`Compact()` drops unused vertices and degenerate faces and **re-indexes the
rest** — which a parallel `VertexColors` list does not follow.

As written, Pattern 9 happens to be safe: it adds a face for **every** cell
(colouring NaN grey rather than dropping it), so no vertex is unreferenced and
`Compact()` is close to a no-op. But that safety is invisible and conditional.
The moment you drop faces touching masked cells — which is the right thing to
do, since ~78% of a tile is NaN outside the AOI, and which this same skill
recommends elsewhere — unreferenced vertices appear and the colours silently
shuffle.

Because the safe case and the destructive case look identical at the call site,
the guidance should be unconditional: **do not call `Compact()` on a mesh whose
colours were added by index.** Suggested edit: drop it from Pattern 9 and add
the one-line reason.

Precision note: this is reasoning about `Compact()`'s documented behaviour plus
our own observed colour-desync, not a controlled test of Pattern 9 as written.
The recommendation is to remove a call that buys nothing and can silently
corrupt — not a claim that Pattern 9 is currently broken.

### 0.4 `analyses/07-thermal-comfort-utci.md` — the legend bounds

Current text, in the Response section:

> *"`min_legend` / `max_legend` are the canonical color-scale bounds — **use
> them for plotting**."*

**For an AREA run they are always `None`.** Both fields are declared and both
come back null, every time — so `if x is not None` silently takes its fallback
branch on every single run, and code that trusts them either crashes or plots
against a placeholder. Surface results *do* populate them; the ordinary
merged-grid response does not.

`SKILL.md`'s own invariants already say this — *"The API currently returns
`None` for these; always guard"* — so the analysis page contradicts the router
that points at it. Suggested replacement:

> `min_legend` / `max_legend` are **`None`** on an area run. Use the fixed
> UTCI domain, or percentile-clip `merged_grid`, and say in your output which
> you did — an auto-scaled run is not comparable to another one.

Worth stating why it matters beyond a crash: UTCI's fixed domain is the
stress-category scale, **−40…46 °C = 86 °C wide**, and a real city occupies
about 8% of it. A client that falls back to the fixed domain *without knowing
it did* renders the whole site one flat colour and reads it as "the model did
nothing."

---

## 1. Hard numbers

| Value | What it governs | Consequence of ignoring it |
|---|---|---|
| **262,144** sensors/job | server cap on synthesized surface sensors | 422 **after** the job runs and is billed; strict surface merge then discards every sibling |
| **~2×** estimator undercount | `estimate_synthesized_sensor_count` vs real `sensor_count`; measured 1.88 / 1.97 / 2.09 on three jobs | the SDK's own default budget (235,930 estimated) is ~470,000 actual — the default path cannot submit a dense facade job |
| **235,930** | `MAX_SYNTH_SENSORS × 0.9`, the SDK's default budget | `resolve_sensor_batch_cap` **rejects** anything above it, so a client cannot opt out upward |
| **~106,000** | corrected ceiling: `cap / 2.1 × 0.85` | staying here kept the worst batch at 67% of the real cap |
| **64 MiB** decompressed | server payload cap | `413 REF_TOO_LARGE`; batching splits *sensors*, not *bytes*, so it cannot help |
| **5 MiB** zip | SDK inline-vs-S3 threshold | **dead zone**: a zip just *under* it is POSTed inline and 413s. Smaller works, bigger works. Set `INFRARED_BIG_PAYLOADS_THRESHOLD_BYTES=1048576` |
| **15** floors/request | `MAX_FLOORS_PER_REQUEST` | checked before charging; split on storey boundaries |
| **100,000** sensors/floor | `MAX_SENSORS_PER_FLOOR` | a large plate at 0.5 m can exceed it |
| **2,000,000** triangles | `MAX_OCCLUDER_TRIANGLES` | interior occluder ceiling |
| **20%** area ratio | the server drops any storey cluster under 20% of the batch's largest floor | 422 *and* silent index shift; apply the same rule client-side |
| **±1 m** | `assume-aligned` tolerance | 422 for the whole job; only ~18% of real objects qualify, ~22% after merging stacks |
| **512 m** tile, **1 m** cell | area tiling | ~78% of a tile is NaN outside the AOI |
| **300 s** | SDK default job timeout | not enough for 15 floors at 0.5 m; the job keeps running **and billing** after the client gives up |
| **0.53°** | angular width of the sun disc — *general astronomy, not measured here* | a horizon error below it cannot change a shading result. Useful for sizing far-terrain pitch: 20 m at 1.5 km subtends ≈0.76°, i.e. already at the limit of what matters |

### Measured on the geometry, not the API

| Value | Meaning |
|---|---|
| **54%** | of objects sit on another object (1,011 of 1,877) — podium/tower modelled separately |
| **−43 m to +45 m** | displacement `auto-align` applies to stacked solids |
| **6.6×** | facade-vs-roof median separation (8.2 vs 53.9 kWh/m²) |
| **97** | triangles `MeshingParameters.Default` produced on a flat 4.6 × 1.3 m quad |
| **174 vs 0** | perceived-lightness reversals in jet vs magma over 512 samples |
| **~5%** | of returned triangles are degenerate; one invalidates a whole mesh |

---

## 2. Silent-failure catalogue

The highest-value section. Each of these returns success and a plausible
result. Ordered by what they cost.

| Symptom | Actual cause | The check |
|---|---|---|
| every interior floor ~0 DF, roof bright | **not** a missing hole in the wall — a coincident aperture transmits (§0.1). Check the sensor plane against the sill, and that `openings` is non-empty | compare `analysis_height` with your computed sill; dump the payload and count the openings |
| `ground materials: none` on a full file | `Objects.FindByLayer(str)` matches the layer **NAME, not the path**; nested layers return `[]` while `FindByFullPath` succeeds | pass the **Layer object**, not the path |
| results sit metres below the source | `auto-align` re-based each stacked solid onto terrain | compare source vs result Z per building |
| whole city one flat colour | ramp range vs data range mismatch — a fixed domain 86 °C wide over 6.6 °C of data | print data min/max **and** ramp min/max |
| every wall the same blue | one ramp over two populations 6.6× apart | scale to the population you are studying |
| 13 real floors flat, one bright | an **unenclosed** level (roof terrace) setting the scale | exclude floors whose median is ≫ typical |
| "very low resolution" render | quad size ≠ grid pitch, so cells do not tile | derive cell size from the pitch, never a constant |
| jobs 30× slower than before | a mesher subdividing planar quads; or context geometry duplicated per batch | **log triangle counts** — nothing else shows it |
| `submission failed: ` (empty) | gateway returns RFC 7807; the classifier reads `message`/`error`, the text is in **`detail`** | read `detail` |
| `baked 0 object(s)` after a paid run | one degenerate face invalidates the mesh; `AddMesh` returns `Guid.Empty` | compare against `Guid.Empty`, call `IsValidWithLog()` |
| batching silently disabled | `estimate_synthesized_sensor_count` returns **0.0** for a mesh dict without `coordinates`/`indices` | check your key names |
| a toggle re-submitting on any canvas change | a Boolean Toggle is a **level**, not an event | latch the rising edge in `sticky` |
| cache appears not to help | keyed on `id(RhinoDoc.ActiveDoc)`; pythonnet may not keep a stable wrapper identity | key on `RuntimeSerialNumber`; log the hit rate once |
| one batch times out, **all** results lost | `pool.map` re-raises on consumption | `submit` + `as_completed`, per-job `try/except` |
| 502 on submit | often a **size** failure wearing a server-error code | measure what you sent before blaming the server |
| a `try/except` that should "log and continue" hard-aborts instead | a variable the code reads after the block was bound INSIDE the `try`, so a later unconditional read raises `NameError` -- the tolerant branch is dead code that has never executed | bind it to `None` ABOVE the `try` |
| a shared module's config default silently overrides the component's | a build step that flattens modules into one namespace emits the library's `PALETTE = ...` AFTER your settings block, so the library wins. The component logs the value it *thinks* it set | make any module-level name a settings block might redefine PRIVATE (`_PALETTE`) in the shared module |
| interior DF implausibly HIGH (tens of %, where 1–5% is typical) | the room is not enclosed. A wall tiled to the CEILING plane rather than the slab above leaves an open ribbon of `storey_height − floor_to_ceiling` — 0.4 m on common defaults — admitting unglazed sky and not counted in `window_area` either | seal walls floor-to-slab; only the window stays inside the ceiling plane |
| a uniform daylight field, HTTP 200 | geometry never reached the model in the expected shape | assert non-uniformity and refuse to trust it |

---

## 3. Performance

Three cost centres, in the order they hurt.

**Marshalling.** Every RhinoCommon call crosses CPython↔.NET. Use the bulk
overloads — `ToFloatArray`, `ToIntArray(True)`, `AddVertices`, `AddFaces`,
`SetColors` — and **verify the count afterwards**, falling back to per-item if
it disagreed. A partial bulk add misaligns face indices and renders as spikes.

**Never mesh a shape you can enumerate.** If the geometry is planar and you
know its corners, write the vertices. `MeshingParameters.Default` exists to
approximate curvature; hand it a rectangle and it subdivided one 48×, measured.
Direct construction took 300 wall patches from 29,170 triangles to 600. Also
check `CreateFromPlanarBoundary` and `CreateFromBrep` — `SimplePlanes = True`
keeps Rhino's triangulation without the subdivision.

**Nothing expensive above the run gate.** Grasshopper re-solves at 10–30 Hz
while anything is dragged. Bbox tests are fine; mesh conversion, contouring and
shell repair are not. If a pre-gate preview is genuinely wanted, memoise it on
`(target id, document stamp, the settings that affect it)`.

**Send only geometry that can change the result.** For a single-building
analysis, occluder context needs a **radius**, not the AOI. The whole AOI was
**1,167 buildings / 621k triangles / 55 MB per batch** and produced a 502.

What a radius saves is **target-dependent** and should not be quoted as one
number: measured on the same site, 100 m around a tower in a dense block kept
67 buildings (~3.9 MB) while 100 m around a building on an open edge kept 12
(~2.4 MB). Ranges from the same file: 100 m → 12-67 buildings, 150 m → ~124,
200 m → ~252, whole AOI → 1,167. **Measure yours; do not inherit the figure.** Do **not** cull context vertically: a neighbour's
upper floors block sky access for a low floor.

**Round coordinates to millimetres** before serialising: 24% smaller payload,
measured, and finer than any sensor grid.

**Instrument the quantity that hid the last bug.** Triangle counts, payload
bytes, entity counts, cache hit rate. Three of the worst bugs here were
invisible to the eye, to payload validation *and* to 94 passing tests.

---

## 4. Debugging discipline

Five rules, each of which was learned by violating it.

1. **Validate the delivery mechanism before writing analysis code.** A pasted
   `GH_ScriptInstance` class defines something Rhino never calls: no error,
   nothing happens. Hours of work targeted a flow that was never tested.
2. **When an error names a quantity, measure your input against that
   quantity.** A 422 quoting 262,144 took ten seconds to refute by measuring
   the buildings — after a wrong fix had already shipped.
3. **When the symptom is an absence** — empty message, zero objects, no
   batching — **suspect a layer that swallowed the value**, not one that
   computed it wrong.
4. **Prefer the instrument that exercises the real path.** A harness that
   stubs the function under test proves nothing: one such harness validated
   everything except the interface that was broken, and shipped an
   `IndexError`. Submitting a payload for real costs nothing when it fails.
5. **A green test suite is evidence about your logic, not your integration.**
   94 tests passed throughout and never caught a bug that mattered, because
   everything expensive lived in the layer they stub: Rhino's mesh internals,
   the live API, the wire format.

And the one that outranks all of them: **render the inputs and look at them
before quoting any number.** A correct simulation with a wrong colour scale is
indistinguishable from a broken one.
