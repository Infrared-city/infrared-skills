// A small colour ramp and an HTML legend. No colour package needed.
//
// The ramp is a list of sRGB stops. `rampAt` maps x in [0, 1] to a colour.
// `rampTable` gives 256 RGBA entries: a lookup table (CPU) or a 256 x 1 texture (GPU).

export type Rgb = readonly [number, number, number];

// "Inferno"-like stops: dark (little sun) to bright yellow (much sun).
export const SOLAR: readonly Rgb[] = [
  [20, 11, 52], [87, 16, 110], [151, 38, 103], [207, 68, 70],
  [243, 120, 25], [250, 193, 39], [252, 255, 164],
];

/** Linear interpolation between the stops, `x` in [0, 1]. */
export function rampAt(stops: readonly Rgb[], x: number): Rgb {
  const t = Math.min(1, Math.max(0, x)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(t));
  const f = t - i;
  const [a, b] = [stops[i], stops[i + 1]];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

/** 256 RGBA bytes for a 256 x 1 lookup texture. */
export function rampTable(stops: readonly Rgb[]): Uint8Array {
  const out = new Uint8Array(256 * 4);
  for (let i = 0; i < 256; i += 1) {
    const [r, g, b] = rampAt(stops, i / 255);
    out.set([Math.round(r), Math.round(g), Math.round(b), 255], i * 4);
  }
  return out;
}

/** Fill a legend element: title with units, a gradient bar, min / mid / max ticks. */
export function renderLegend(
  el: HTMLElement, stops: readonly Rgb[], range: readonly [number, number], title: string,
): void {
  const css = stops.map((c, i) => `rgb(${c.join(",")}) ${(100 * i) / (stops.length - 1)}%`);
  const fmt = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1));
  const [lo, hi] = range;
  el.innerHTML = `
    <div class="legend-title">${title}</div>
    <div class="legend-bar" style="background: linear-gradient(to right, ${css.join(",")})"></div>
    <div class="legend-ticks"><span>${fmt(lo)}</span><span>${fmt((lo + hi) / 2)}</span><span>${fmt(hi)}</span></div>`;
}
