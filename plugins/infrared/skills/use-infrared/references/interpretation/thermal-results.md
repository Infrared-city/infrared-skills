# Thermal comfort results

Grid layout, helpers and legend rules: [grid-conventions.md](grid-conventions.md).
This file covers units and classes.

## thermal-comfort-index (UTCI)

The UTCI in degrees C per cell at about 1.5 m. It combines air temperature, mean radiant
temperature (computed inside the model), humidity and wind. The grid is one aggregate over your
`TimePeriod`. It is not one instant and not an annual mean.

| UTCI (C) | Stress class |
|---|---|
| above 38 | Strong to extreme heat stress |
| 32 to 38 | Strong heat stress |
| 26 to 32 | Moderate heat stress |
| **9 to 26** | **No thermal stress** |
| 0 to 9 | Slight cold stress |
| below 0 | Moderate to extreme cold stress |

Read values with `physical_grid()`. The stored type is f16 and the helper handles it.
The model has a wall afterglow of about 3 hours and a ground lag of about 43 minutes, and no memory
over several days. Do not call night values validated.

**Pitfalls**: surface material changes the value a lot (sunny asphalt against shaded grass: 10 to
15 C three metres apart). Do not average across material classes. Trees and ground materials
matter: pass them.

## thermal-comfort-statistics (TCS)

The percent of the `TimePeriod` window (0 to 100) that the UTCI is in the band of the `subtype`.
All cells of one run share the same window.

| `TcsSubtype` | Band |
|---|---|
| `thermal_comfort` | UTCI 9 to 26 C |
| `heat_stress` | UTCI 26 C or more |
| `cold_stress` | UTCI 9 C or less |

The window is a cascade: months, then days, then hours (see [../03-time-period.md](../03-time-period.md)).
One call gives one subtype. The three bands do not need to add up to 100 %.

**Pitfalls**: compare designs only with the same weather file and the same window. Different windows
give different shares.

See also: [../analyses/07-thermal-comfort-utci.md](../analyses/07-thermal-comfort-utci.md),
[../analyses/08-thermal-comfort-statistics.md](../analyses/08-thermal-comfort-statistics.md).
