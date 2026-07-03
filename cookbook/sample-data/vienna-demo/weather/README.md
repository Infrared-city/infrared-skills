# Weather (EPW) — download separately

The `.epw` files are **not committed** (~1.5 MB each). Download the real TMYx
files below, or let the generator fetch them
(`python cookbook/scripts/demo_vienna_scenarios.py` writes them here). The
`~/Downloads/vienna-demo/weather/` copy already contains both.

| File | Station | URL (zip → extract the `.epw`) |
|---|---|---|
| `vienna.epw` | Wien-Schwechat AP (LOWW), 48.12 N / 16.58 E | `https://climate.onebuilding.org/WMO_Region_6_Europe/AUT_Austria/NO_Lower_Austria/AUT_NO_Wien-Schwechat.AP.110360_TMYx.zip` |
| `madrid.epw` | Madrid-Barajas AP (LEMD), 40.47 N / -3.56 E | `https://climate.onebuilding.org/WMO_Region_6_Europe/ESP_Spain/MD_Madrid/ESP_MD_Madrid-Barajas-Suarez.AP.082210_TMYx.zip` |

```bash
curl -L -o vienna.zip "<vienna url above>" && unzip -o vienna.zip \
  && mv AUT_NO_Wien-Schwechat.AP.110360_TMYx.epw vienna.epw
```

## Usage

- `vienna.epw` — the local baseline climate. Drop on a scenario's **weather** row.
- `madrid.epw` — the **"Madrid's climate in Vienna"** demo: drop it on a
  scenario's weather row and re-run to see Vienna geometry under a hot-dry TMY.

Both are standard 8,760-hour TMYx EPWs and were verified against the platform's
EPW parser (real `LOCATION` header, all-finite dry-bulb).

## Licence

TMYx data from [climate.onebuilding.org](https://climate.onebuilding.org),
derived from ISD (NOAA) hourly records. Free for any use; attribution to
onebuilding.org / Lawrie & Crawley appreciated. See the site's
[terms](https://climate.onebuilding.org) and the `.stat` files in each zip for
provenance.
