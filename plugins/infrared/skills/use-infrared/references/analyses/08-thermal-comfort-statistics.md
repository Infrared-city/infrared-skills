# Thermal comfort statistics (`thermal-comfort-statistics`, TCS)

For each cell, the **percent of the time window** that the UTCI is in one band.
You choose the band for each call with `subtype`.

```python
from infrared_sdk.analyses.types import TcsModelRequest
from infrared_sdk.analyses.types import AnalysesName, TcsModelBaseRequest, TcsSubtype
from infrared_sdk.models import Location

request = TcsModelRequest.from_weatherfile_payload(
    payload=TcsModelBaseRequest(
        analysis_type=AnalysesName.thermal_comfort_statistics,
        subtype=TcsSubtype.heat_stress,        # thermal_comfort, heat_stress or cold_stress
    ),
    location=Location(latitude=48.208, longitude=16.371),
    time_period=tp, weather_data=rows,         # as in the UTCI page
)
result = client.run_area_and_wait(request, polygon,
                                  buildings=buildings, vegetation=trees, ground_materials=ground)
share = result.physical_grid()                 # 0 to 100 (% of the window), NaN = no value
```

## Subtypes

| `TcsSubtype` | Counts the hours with |
|---|---|
| `thermal_comfort` | UTCI from 9 to 26 C |
| `heat_stress` | UTCI of 26 C or more |
| `cold_stress` | UTCI of 9 C or less |

For all three, run three requests. Each call is one subtype.

## Pitfalls

- The window comes only from the `TimePeriod`: months, then days, then hours.
- Percent is relative to the window. Do not compare runs with different windows without care.
- Keep the weather file fixed when you compare designs.
- Same inputs and materials as UTCI: pass trees and ground.

Read the result: [../interpretation/thermal-results.md](../interpretation/thermal-results.md)
