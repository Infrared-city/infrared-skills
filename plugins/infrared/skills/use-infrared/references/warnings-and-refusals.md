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
| `PHYSICS_TIER_RETIRED` | A retired `physics` value ran as `standard`. |

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
