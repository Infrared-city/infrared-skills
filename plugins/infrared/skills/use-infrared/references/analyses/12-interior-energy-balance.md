# Interior: energy balance (`energy-balance`)

The monthly heating and cooling energy **need** of each zone. Beta. It is not delivered energy:
no boiler, heat pump or chiller efficiency applies. Call code: [../python/interior.md](../python/interior.md).

## Inputs

1. `spatial_volumes`: one closed volume for each zone, category `"space"`. Required.
2. `barriers`: walls (`"wall"`) and every slab (`"floor"`), the roof too.
3. `openings`: windows.
4. `context_geometry`, `ground_geometry`: shade only with `solar_model="irradiance"`.
5. Weather: one year of hourly data: `EnergyBalanceModelRequest.from_weather(rows, ...)`.
   A leap year (8784 hours) needs `year=`.
6. `solar_model`: `"legacy-flat"` (default) uses two series and ignores shade.
   `"irradiance"` uses the shade geometry. It needs latitude, longitude and four series.
7. `energy_settings=EnergySettings(...)`: U-values, glazing, set-points, gains, infiltration, thermal mass.
   All optional. An unset field uses the server default.
8. `operation`: `Operation.continuous()` (default) or `Operation.intermittent(hours=(8, 18), days="weekdays")`.

Defaults: wall 0.13, flat roof 0.25, ground floor 0.30 W/m2K. Glazing U 1.1, SHGC 0.60.
Set-points 21 and 26 C. Ground reflectance 0.2. The guide chapter "Configuration and limits"
lists every name, unit and default.

## Rules

- Keep one building whole in one request. A slab with heated rooms on both sides is internal.
  A single storey sent alone loses heat through its slabs.
- You cannot set a value for one wall or one window. Properties apply to the whole request.
  For several buildings in one request, each entry of `buildings` can override.
- It runs as one job (no parts). Nested entities as in the daylight page.

## Result

A dict: `output` has one entry for each zone with `annual` (`Q_heat_kWh`, `Q_cool_kWh`, `EUI_heat`,
`EUI_cool` in kWh/m2 a) and 12 `monthly` rows. Also `T_monthly`, `G_monthly`, `settings`, `warnings`.
