# Warnings and refusals

A run can finish with warnings. Read them: they tell you what the server changed. Python:
`result.warnings` (also `warnings.warn`). TypeScript: `result.warnings`. .NET: `result.Warnings`.
Each text starts with a code, then a colon.

| Code | Meaning |
|---|---|
| `WIND_SPEED_MISSING` | Null wind hours were filled by interpolation. |
| `TEMPERATURE_MISSING`, `HUMIDITY_MISSING` | Null hours were filled. |
| `UTCI_INPUT_OUT_OF_RANGE` | Hours were clamped: air temperature -50 to 50 C, mean radiant minus air -30 to 70 K, wind 0.5 to 17 m/s, vapour pressure up to 5 kPa. The text gives the share of hours. |
| `WIND_SPEED_NEGATIVE` | A negative wind speed. The model used its absolute value. |
| `BUILDING_HEIGHT_CLIPPED_FOR_WIND` | A geometry is taller than 100 m. The wind model clips it. |
| `DAYLIGHT_NO_SUN_HOURS` | No sun in the window (polar night). The result is 0 %, not an error. |
| `MATERIAL_IGNORED_BY_MODEL` | A building `material` went to a model that does not read it (solar radiation, daylight, sun hours, SVF). It has no effect. |
| `MATERIAL_FIELD_INVALID`, `MATERIAL_PRESET_UNKNOWN` | A material field was removed, or an unknown preset became `default`. |
| `INSTALLATION_DROPPED` | An installation has no effect and was dropped. |
| `INSTALLATIONS_WIND_NOT_MODELLED` | UTCI or TCS with sails, meshes or screens: the pieces change the radiation, not the wind. The wind is the weather-file wind. Normal; say it in the report. |
| `ROOF_MATERIAL_ADVANCED_ONLY` | `roof-material` was sent with `physics` = `standard`. It was ignored. Use `advanced`, or remove it. |
| `PHYSICS_TIER_RETIRED` | A retired `physics` value ran as `standard`. |

The SDK checks materials before it sends a job. Its texts have the shape
`CODE (group, n entries, e.g. ids): text`, for example `MATERIAL_NOT_SUPPORTED (installations,
9 entries, e.g. sail, ...)`: the model does not read `material` (sky view factor, sun hours),
so the pieces run as opaque shapes.

The server serves these inputs and warns. A warning is not a failure: check that the result is
what the user meant (a clamped UTCI hour is not a measured one).

## Refused before the charge (HTTP 422)

For thermal comfort the server checks the weather at accept. It refuses, and does not charge, when:

- a weather series has not exactly one value for each hour of the window;
- an entry is not a number;
- all air temperature values, or all humidity values, are null;
- the `utci-output` value is unknown.

Do not retry the same input. Fix the series (use `from_weatherfile_payload` with the same `TimePeriod`).

## Installations

Thin pieces (green panels, fins, PV canopies) in `installations` shade the analysed surfaces. They
give no sensors. Wind ignores them.

| Model | How installations act |
|---|---|
| solar radiation, daylight availability | Shade the ground grids. `transmittance` lets light through. |
| direct sun hours, sky view factor | Shade the grids. Every piece is opaque on purpose. |
| thermal comfort | Read them. |

## Physics tiers

`physics` is `standard` (default) or `advanced` (roof material and ground afterglow after sunset).
`advanced-moist` is the old name of `standard`. `v1` and `detail` are retired: they run as
`standard` with `PHYSICS_TIER_RETIRED`.

## No warning, no effect (UX panel, 2026-10-20)

These settings change nothing, and no warning tells you. Check them before you report:

- A `light-paint` facade in UTCI: only the cooler wall counts; the reflected sun on people is
  not modelled yet.
- `physics="advanced"` in a daytime window: almost the same grid as `standard`.
- A tree with no `height` or `crownDiameter`: 6 m and 4 m.
- An irrigated lawn on top of an asphalt layer that covers the same area: the lawn can be lost.
  Cut the asphalt around the lawn.
- A request body that ran in the last 24 hours: a cache hit, the same numbers.
- Swapped lat/lon in the polygon: the run works, in the wrong place. Check `result.bounds`.
- Air temperature in Fahrenheit: the run works; UTCI hours are clamped with
  `UTCI_INPUT_OUT_OF_RANGE`. Use degrees C.
- `preview_area` does not check materials, layer names or values. Only the run does.
