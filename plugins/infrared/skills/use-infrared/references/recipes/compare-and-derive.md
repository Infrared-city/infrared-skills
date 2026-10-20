# Recipes: compare variants and derive values (client side)

The SDK gives the simulation results. Derived values (A vs B, PV potential, air-con priority,
cost per kelvin) are simple arithmetic on those results, in your app or your agent. These
recipes ran on staging with SDK 1.1.4.dev2 on 2026-10-20, after the examples in
[../design-variants](../design-variants.md) (they reuse `client`, `polygon`, `buildings`,
`trees`, `ground`, `installations`, `utci_request`, `result`, `solar_result`).

## 1. A vs B: delta grid, polygon mean, heat-stress area

![A vs B: one change, same grid](../images/ab-compare.svg)

```python
import numpy as np
from matplotlib.path import Path


def cell_mask(result, geojson_polygon):             # True for grid cells inside a lon/lat polygon
    west, south, east, north = result.bounds
    rows, cols = result.physical_grid().shape
    lon = west + (np.arange(cols) + 0.5) * (east - west) / cols
    lat = south + (np.arange(rows) + 0.5) * (north - south) / rows   # row 0 = south
    pts = np.column_stack([g.ravel() for g in np.meshgrid(lon, lat)])
    return Path(geojson_polygon["coordinates"][0]).contains_points(pts).reshape(rows, cols)


base = client.run_area_and_wait(utci_request(), polygon, buildings=buildings,
                                vegetation=trees, ground_materials=ground)        # A: no installations
a, b = base.physical_grid(), result.physical_grid()  # B: the run with installations (above)
assert base.bounds == result.bounds                  # same polygon -> same grid
delta = b - a                                        # K; negative = cooler in B
court = cell_mask(base, rect_ll(40, 35, 100, 85)) & np.isfinite(delta)
print(f"mean A {np.nanmean(a[court]):.2f} C, B {np.nanmean(b[court]):.2f} C, "
      f"delta {np.nanmean(delta[court]):+.2f} K, best cell {np.nanmin(delta[court]):+.2f} K")
cell_m2 = 1.0                                        # ground cells are 1 m x 1 m
for name, g in (("A", a), ("B", b)):
    print(name, "area above 32 C (strong heat stress):", int((g[court] > 32).sum() * cell_m2), "m2")
```

Output of the run: `mean A 30.14 C, B 29.13 C, delta -1.01 K, best cell -4.84 K`; area above
32 C: 650 m2 (A), 204 m2 (B).

- Change **one** layer between A and B. Keep polygon, weather, time, physics and the other
  inputs the same, so the grids line up cell by cell.
- Report the mean over the area of the measure (court, street), not the best cell. The best
  cell is useful only as "up to".
- UTCI 32 C is the lower limit of "strong heat stress"; 26 C of "moderate"; 38 C of "very
  strong". Use the band that the user asks for.
- Look at the delta map before you report a number (`imshow(delta, origin="lower")`). A
  cooling that is not under the measure, or a stripe pattern, means an alignment error.

## 2. Cost and cooling table for variants

```python
# Variants: name -> (request fields, ground, cost in EUR). Costs are YOUR inputs (ask the user).
variants = {
    "sail 20x15 m": ({"installations": {"sail": installations["sail"]}}, ground, 300 * 45),
    "PV canopy 25x15 m": ({"installations": {"pv-canopy": installations["pv-canopy"]}}, ground, 375 * 400),
    "lawn, no irrigation": ({}, {**ground, "vegetation": layer(feature(rect_ll(40, 55, 100, 85)))}, 1800 * 30),
}
a = base.physical_grid()                             # baseline A from the compare recipe
rows_out = []
for name, (fields, gm, cost_eur) in variants.items():
    run = client.run_area_and_wait(utci_request(**fields), polygon, buildings=buildings,
                                   vegetation=trees, ground_materials=gm)
    d = run.physical_grid() - a
    cool = -float(np.nanmean(d[court]))
    hot = int((run.physical_grid()[court] > 32).sum())
    per_k = cost_eur / cool if cool > 0 else float("inf")   # inf = no cooling
    rows_out.append((name, cool, hot, cost_eur, per_k))
print(f"{'variant':20} {'cooling K':>9} {'m2 > 32 C':>9} {'cost EUR':>9} {'EUR per K':>10}")
for name, cool, hot, cost, per_k in sorted(rows_out, key=lambda r: r[4]):
    print(f"{name:20} {cool:9.2f} {hot:9d} {cost:9.0f} {per_k:10.0f}")
```

Output of the run (baseline = the site with a watered lawn, no installations):

| variant | cooling K | m2 > 32 C | cost EUR | EUR per K |
|---|---|---|---|---|
| sail 20x15 m | 0.34 | 602 | 13,500 | 39,691 |
| PV canopy 25x15 m | 0.47 | 414 | 150,000 | 320,472 |
| lawn, no irrigation | -0.14 | 990 | 54,000 | no cooling |

- Costs are inputs from the user, not from Infrared. Say so in the report.
- Each variant is one run (one job per tile). Preview the job count first.
- A design agent loop (prototype, Vienna MuseumsQuartier courtyard, 500 x 500 m): try a size,
  read the measured rate (for example -0.84 K per 1000 m2 of canopy), resize, run again. Two
  rounds were enough to meet a -1 K and a -2 K goal.

## 3. PV potential per building (roofs and facades)

Run solar radiation for **one year** with `analysis_surfaces="all"` (section 5 of
design-variants). Then, for each cell:

PV energy (kWh/yr) = radiation (kWh/m2 yr) x efficiency 0.20 x performance ratio 0.77 x usable
share x cell area (m2).

```python
from collections import defaultdict

EFFICIENCY, PERFORMANCE_RATIO, USABLE_SHARE = 0.20, 0.77, 0.7
FACADE_MIN_KWH_M2_YR = 700          # facade cells below this are not worth a panel
cols = solar_result.columns         # annual solar-radiation run, analysis_surfaces="all"
rad = cols.physical_values()        # kWh/m2 over the window (here: one year)
pv_kwh = defaultdict(float)
for i, sid in enumerate(cols.ids):
    s, e = cols.cell_offsets[i], cols.cell_offsets[i + 1]
    normal = np.cross(cols.u_axis[i], cols.v_axis[i])               # outward normal
    kind = "roof" if normal[2] > 0.5 else "facade" if abs(normal[2]) <= 0.5 else "soffit"
    area = np.full(e - s, cols.grid_size[i] ** 2)                    # m2 per cell
    if cols.cell_area_state[i] == 2:
        area *= np.nan_to_num(cols.cell_area[s:e])                   # partly covered cells
    r = np.nan_to_num(rad[s:e])
    keep = r >= FACADE_MIN_KWH_M2_YR if kind == "facade" else np.full(r.shape, kind == "roof")
    building = sid.rsplit("/", 1)[0]                                 # surface id = "<building>/<part>"
    pv_kwh[building] += float((r * area * keep).sum()) * EFFICIENCY * PERFORMANCE_RATIO * USABLE_SHARE
for building, kwh in sorted(pv_kwh.items(), key=lambda kv: -kv[1]):
    print(f"{building}: {kwh / 1000:.1f} MWh/yr")
```

- **Performance ratio 0.77**: the radiation x efficiency value is gross. Check for a flat
  roof in Singapore: 1810 kWh/m2 yr (PVGIS-ERA5) x 0.20 = 362 kWh/m2 yr gross; PVGIS gives
  277 with system losses, a ratio of about 0.77.
- **Facade cut-off about 700 kWh/m2 yr**: below it a facade panel does not pay back.
  Published cut-offs are about 697 to 698 kWh/m2 yr (a Brazilian residential study and a
  Saudi commercial study). It is a parameter: say which value you used. Roofs: no cut-off.
- For a window shorter than a year, scale the cut-off by `days / 365`.
- Surface id = `"<building id>/<part>"`: the building is the text before the last `/`.
- Cell area = `grid_size**2`, times `cell_area` where `cell_area_state == 2` (part cells).
- Usable share (0.7 here) is your assumption for edges, roof equipment and windows.

## 4. Air-con priority (where the sun loads the envelope most)

Run solar radiation for a **summer** window (for example June to August) with
`analysis_surfaces="all"`. Then sum the solar load per building x floor band x compass sector.

```python
FLOOR_M = 3.0
WEIGHTS = [1.0, 1.0, 1.0, 1.0, 1.0, 1.1, 1.2, 1.1]   # N NE E SE S SW W NW: west sun hurts more
summer = solar_result.columns                       # use a SUMMER solar-radiation surface run
rad = summer.physical_values()
cells = []                                          # (building, z, sector or "roof", kWh)
for i, sid in enumerate(summer.ids):
    s, e, nu, gs = summer.cell_offsets[i], summer.cell_offsets[i + 1], summer.nu[i], summer.grid_size[i]
    n = np.cross(summer.u_axis[i], summer.v_axis[i])
    if n[2] < -0.5:
        continue                                    # soffit: skip
    k = np.arange(e - s)
    z = summer.origin[i][2] + (k // nu) * gs * summer.v_axis[i][2]   # cell centre height
    sector = "roof" if n[2] > 0.5 else int(round(np.degrees(np.arctan2(n[0], n[1])) % 360 / 45)) % 8
    w = 1.0 if sector == "roof" else WEIGHTS[sector]
    load = w * np.nan_to_num(rad[s:e]) * gs * gs
    cells += [(sid.rsplit("/", 1)[0], zz, sector, ll_) for zz, ll_ in zip(z, load)]
groups = defaultdict(float)
for b in {c[0] for c in cells}:
    walls = [c for c in cells if c[0] == b and c[2] != "roof"]
    z0 = min(c[1] for c in walls)
    top = max(int((c[1] - z0) // FLOOR_M) for c in walls)
    for _, zz, sec, load in (c for c in cells if c[0] == b):
        band = top if sec == "roof" else int((zz - z0) // FLOOR_M)   # roof load -> top floor
        groups[(b, band, sec)] += load
peak = max(groups.values())
ranked = sorted(groups.items(), key=lambda kv: -kv[1])
for rank, ((b, band, sec), load) in enumerate(ranked[:5], 1):
    print(rank, b, "floor", band, "sector", sec, f"score {load / peak:.2f}", f"{load:.0f} kWh")
```

- Outward normal = `u_axis x v_axis`. Wall: `|n.z| <= 0.5`; roof: `n.z > 0.5`; soffit:
  `n.z < -0.5` (skip it).
- Cell `k` of a surface: row `k // nu`, column `k % nu`; centre = `origin + column * gs * u +
  row * gs * v`. Floor band = `(z - lowest wall z of the building) // 3 m`.
- Roof cells count on the top floor (the floor under the roof).
- Sector = compass direction of the normal in 45 degree steps (0 N, 2 E, 4 S, 6 W).
- Score = load / largest load (0 to 1); rank 1 = cool first. Radiation alone does not put
  west above east: the afternoon heat comes with a hot air temperature. Use orientation
  weights (west 1.2, east 1.0) for that, and say so.
- This is solar load on the envelope, not a cooling need. For a need, use the interior energy
  balance (Beta).

## Report with honest caveats

- Say: screening grade, public or user geometry (name the source), weather station and window.
- Give the polygon mean, the area above a threshold, and "up to" for the best cell.
- Say which settings had no effect (see the table in design-variants) and which warnings came.
