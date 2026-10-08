// An area result as an image for deck.gl's BitmapLayer.
//
// Rules that matter (get one wrong and the map is upside down or shifted):
// - Read values with `areaGridValuesF32(result)`: real units, NaN = no value.
//   Never read `result.mergedGrid` directly (f16 grids hold half-float bits).
// - Row 0 of the grid is the SOUTH edge. An image has row 0 at the top (north),
//   so flip the rows.
// - Place the image with `result.bounds` = [west, south, east, north] (degrees).

import { areaGridValuesF32, type AreaResult } from "@infrared-city/infrared-sdk-ts";

export function gridToCanvas(
  result: AreaResult, lut: Uint8Array, range: readonly [number, number],
): HTMLCanvasElement {
  const [rows, cols] = result.gridShape;
  const values = areaGridValuesF32(result);
  const [lo, hi] = range;
  const scale = 255 / Math.max(hi - lo, 1e-9);

  const canvas = document.createElement("canvas");
  canvas.width = cols;
  canvas.height = rows;
  const ctx = canvas.getContext("2d")!;
  const image = ctx.createImageData(cols, rows);
  for (let y = 0; y < rows; y += 1) {
    const srcRow = rows - 1 - y;                       // flip: image row 0 = north
    for (let x = 0; x < cols; x += 1) {
      const v = values[srcRow * cols + x];
      if (Number.isNaN(v)) continue;                   // no value (e.g. inside a building): transparent
      const i = Math.min(255, Math.max(0, Math.round((v - lo) * scale))) * 4;
      image.data.set([lut[i], lut[i + 1], lut[i + 2], 255], (y * cols + x) * 4);
    }
  }
  ctx.putImageData(image, 0, 0);
  return canvas;
}
