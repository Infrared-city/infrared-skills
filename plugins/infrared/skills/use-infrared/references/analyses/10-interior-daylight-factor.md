# Interior: daylight factor (`daylight-factor`)

Daylight at points inside a room, in % of the open-sky illuminance, under a CIE overcast sky.
It needs no time and no weather. It is not an area model.
Call code: [../python/interior.md](../python/interior.md).
Energy balance: [12-interior-energy-balance.md](12-interior-energy-balance.md).

## Inputs

| Field | Role |
|---|---|
| `barriers` | Walls and slabs. Categories `"wall"`, `"floor"` |
| `openings` | Windows, category `"window"`. Glazing is read only from here |
| `spatial_volumes` | Optional closed volume for each room (category `"space"`) for room results |
| `sensor_points` | Your points. One value for each point |
| `sensor_surfaces` | Horizontal meshes (for example a roof). The model puts a grid on them. A facade is refused |
| `floors` | The storeys to calculate. Not with own sensors |
| `grid_size`, `analysis_height` | Sensor grid for floors: default 0.5 m and 0.8 m |
| `context_geometry` | Neighbours that cast shade. Without them the room reads too bright |
| `room_reflectances` | `floor`, `walls`, `ceiling`: default 0.2, 0.5, 0.7 |
| `glazing_transmittance` | For a window without its own factor. Default 0.63 |
| `window_area` | Optional override of the window area. Default: derived from the `openings` mesh |

If you send `sensor_points` and `sensor_surfaces`, the SDK refuses it. The `floors` and `buildings`
tiers need barriers with `category="floor"` and a position and rotation.

## Nested entities

Interior entities are nested: `{"geometry": {"payload": {"coordinates", "indices"}}}`.
`ground_geometry` and `vegetation` stay flat. A flat mesh in a nested field is skipped with no error
and the room reads wrong. Convert with `to_interior_entity` and `interior_entities`.

| Field | Shape |
|---|---|
| `barriers`, `openings`, `context_geometry`, `sensor_surfaces`, `spatial_volumes` | nested |
| `ground_geometry`, `vegetation` | flat |

## Geometry rules

- Metres. Finite coordinates. Indices inside the array. Triangulated. One frame for all parts.
- Enclose the room. A missing wall is a hole that the sky pours through.
- Cover the floor with one pitch of points, and keep all points inside the room.
  The floor area is inferred from the points. A few stray points shift the mean.
- `get_area()` buildings are in the frame of the polygon corner. Your room may use another frame.
  Mixing them places the neighbours wrong, with no error.

## Windows

`opening_factor` (visible-light transmittance, 0 to 1) is set for each opening in
`to_interior_entity(..., opening_factor=0.7)`. Without it the window is clear glass (1.0).
Do not put a window in `barriers`: it is then opaque and the field is flat.
The `openings` mesh and the factor set how much light enters. Use `window_area` only to override the derived area.
`exterior_ground_reflectance` is accepted but has no effect.
Exterior light is traced: buildings seen through the openings re-emit part of the sky. A sealed room
or a room with no openings gives exactly 0, and that is the answer.

## Tiers and caps

The SDK refuses a mix of `sensor_points` and `sensor_surfaces`: do not send two. The server dispatches in the order `sensor_points`, `sensor_surfaces`, `buildings`, `floors`.
The caps (floors, sensors for each floor, occluder triangles) are in the
[Analyses page](https://infrared.city/docs/sdk/1.0/python/analyses/index.md). A server cap is
enforced after the charge, so the SDK checks it locally before it submits. Use `preview_parts`
to see parts and cost first.

## Reading the result

`result.columns.values` has one value for each sensor (`result.columns.room` gives the room of each point). With rooms you also get mean, minimum, maximum and
the share of area at 2 % or more for each room.
Check for a uniform field in a room that has openings: it means the occluders or the geometry did
not reach the model. Below about 1 % is dim, 1.5 to 4 % is normal, above 4 to 5 % is generous, and
values fall off away from the window. How much neighbours cut the mean depends on the scene: do not
quote a fixed number.
