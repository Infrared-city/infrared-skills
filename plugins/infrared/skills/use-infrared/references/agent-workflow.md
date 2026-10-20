# Agent workflow: design variants, step by step

Use this checklist when a user asks "what cools this place?", "compare A and B", "where do we
put PV?" or "which floors need air-con first?". Each step links to the page with the code.

1. **Ask before you run.** Which environment (production or staging, see
   [run-model](run-model.md))? Which site polygon? Whose geometry (their model, or public
   data)? Which period (a hot afternoon, a summer, a year)? Which costs, if they want a cost
   table?
2. **Plan the variants.** One baseline and one change per variant. Write them as a dict:
   name -> request fields and layers. Do not mix two changes in one variant if the user
   wants to know the effect of each.
3. **Build the inputs** with the examples in [design-variants](design-variants.md).
   Installations go on the request. Ground layers do not overlap. Trees have a height.
4. **Preview** each request: `client.preview_area(polygon, payload=request, buildings=...)`.
   Tell the user the job count before a large batch.
5. **Run** the baseline and the variants. Same polygon, same weather, same time.
6. **Check the warnings** of every result ([warnings-and-refusals](warnings-and-refusals.md)).
   A warning that an input was removed means the variant did not test what you planned.
   Fix it or report it.
7. **Look at a picture** of the baseline and of each delta. Buildings on buildings, cooling
   under the measure. Only then compute numbers.
8. **Compare** with [recipes/compare-and-derive](recipes/compare-and-derive.md): polygon
   mean, area above a threshold, best cell, cost per kelvin, PV kWh, air-con rank.
9. **Report** in plain words:
   - the numbers with units, the polygon, the period and the station;
   - "screening grade": good to rank variants, not a certified result;
   - what the model does not do (wind under a sail, the reflected sun of a light facade);
   - every warning that changed an input;
   - costs are the user's numbers.

Do not:
- run the same request twice to "confirm" (a cache hit gives the same numbers);
- offer light paint or cool pavement as afternoon cooling (they reflect sun onto people);
- report a single best cell as the effect of a measure;
- use `physics="advanced"` to improve a daytime result (it changes almost nothing by day).
