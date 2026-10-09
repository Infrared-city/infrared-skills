// Facade and roof results as one three.js mesh, built from the SDK render buffers.
//
// The render buffers have no mesh for each cell. Each frame (one flat wall or
// roof part) has a few outline triangles in cell units (s, t). The fragment
// shader finds the cell under each pixel and reads its value from a texture.
// So one draw call shows every cell with its exact colour.
//
// Format: https://infrared.city/docs/sdk/1.0/sdk.md (section "Draw facade and roof results fast").

import * as THREE from "three";
import type { SurfaceRenderBuffers } from "@infrared-city/infrared-sdk";

/** Width of the value and validity textures. Cell k sits at (k % W, floor(k / W)). */
const TEX_WIDTH = 4096;

/**
 * One vertex for each outline corner.
 * - `position`: corner + s * uStep + t * vStep, relative to `buffers.anchor` (f32 is fine near the anchor).
 * - `cell`: (s, t) in cell units, straight from `buffers.outline`.
 * - `frame`: nu, nv, cellStart of the frame. Floats are exact up to 16.7 M cells.
 */
export function surfaceVertexArrays(b: SurfaceRenderBuffers) {
  const frameCount = b.dims.length / 3;
  const vertexCount = b.outline.length / 2;
  const position = new Float32Array(vertexCount * 3);
  const frame = new Float32Array(vertexCount * 3);
  for (let f = 0; f < frameCount; f += 1) {
    const [cx, cy, cz, ux, uy, uz, vx, vy, vz] = b.frames.subarray(9 * f, 9 * f + 9);
    const [nu, nv, cellStart] = b.dims.subarray(3 * f, 3 * f + 3);
    // Frame f owns triangles outlineOffsets[f] .. outlineOffsets[f + 1]; 3 vertices each.
    for (let v = 3 * b.outlineOffsets[f]; v < 3 * b.outlineOffsets[f + 1]; v += 1) {
      const s = b.outline[2 * v];
      const t = b.outline[2 * v + 1];
      position[3 * v] = cx + s * ux + t * vx;
      position[3 * v + 1] = cy + s * uy + t * vy;
      position[3 * v + 2] = cz + s * uz + t * vz;
      frame[3 * v] = nu;
      frame[3 * v + 1] = nv;
      frame[3 * v + 2] = cellStart;
    }
  }
  return { position, cell: b.outline, frame, vertexCount };
}

/** The cell index of point (s, t) of a frame. The same rule as the shader. */
export function cellIndex(nu: number, nv: number, cellStart: number, s: number, t: number): number {
  const j = Math.min(nu - 1, Math.max(0, Math.floor(s)));
  const i = Math.min(nv - 1, Math.max(0, Math.floor(t)));
  return cellStart + i * nu + j;
}

/** True when cell k has a value (bit k & 7 of byte k >> 3). Values are never NaN: test the bit. */
export function cellIsValid(b: SurfaceRenderBuffers, k: number): boolean {
  return ((b.validity[k >> 3] >> (k & 7)) & 1) === 1;
}

const vertexShader = /* glsl */ `
  in vec2 cell;
  in vec3 frame;
  out vec2 vCell;
  flat out vec3 vFrame;
  out vec3 vViewPos;
  void main() {
    vCell = cell;
    vFrame = frame;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vViewPos = mv.xyz;
    gl_Position = projectionMatrix * mv;
  }`;

const fragmentShader = /* glsl */ `
  precision highp float;
  precision highp int;
  uniform highp sampler2D uValues;  // R16F or R32F, one texel per cell
  uniform sampler2D uValid;         // R8, 1 = cell has a value
  uniform sampler2D uRamp;          // 256 x 1 colour ramp (sRGB bytes)
  uniform vec2 uRange;              // legend min, max
  in vec2 vCell;
  flat in vec3 vFrame;
  in vec3 vViewPos;
  out vec4 fragColor;
  void main() {
    int nu = int(vFrame.x);
    int nv = int(vFrame.y);
    int j = clamp(int(floor(vCell.x)), 0, nu - 1);
    int i = clamp(int(floor(vCell.y)), 0, nv - 1);
    int k = int(vFrame.z) + i * nu + j;
    ivec2 p = ivec2(k % ${TEX_WIDTH}, k / ${TEX_WIDTH});
    vec3 color = vec3(0.80);                     // no value: neutral grey
    if (texelFetch(uValid, p, 0).r > 0.5) {
      float v = texelFetch(uValues, p, 0).r;
      float x = clamp((v - uRange.x) / max(uRange.y - uRange.x, 1e-6), 0.0, 1.0);
      color = texture(uRamp, vec2(x, 0.5)).rgb;
    }
    // Mild flat shading from the face normal, so walls and roofs read as 3D.
    // Keep it mild: the colour carries the value.
    vec3 n = normalize(cross(dFdx(vViewPos), dFdy(vViewPos)));
    float shade = 0.82 + 0.18 * abs(dot(n, normalize(vec3(0.4, 0.6, 1.0))));
    fragColor = vec4(color * shade, 1.0);
  }`;

/** Put one value per cell into a 2D texture (WebGL limits the width). */
function cellTexture(b: SurfaceRenderBuffers): { values: THREE.DataTexture; valid: THREE.DataTexture } {
  const cells = b.values.length;
  const height = Math.max(1, Math.ceil(cells / TEX_WIDTH));
  const size = TEX_WIDTH * height;
  // f16 values stay as half-float bits; three.js uploads them as R16F.
  const isHalf = b.valueDtype === "f16";
  const data = isHalf ? new Uint16Array(size) : new Float32Array(size);
  data.set(b.values as ArrayLike<number>);
  const values = new THREE.DataTexture(data, TEX_WIDTH, height, THREE.RedFormat,
    isHalf ? THREE.HalfFloatType : THREE.FloatType);
  // Expand the validity bits to one byte per cell: simple to read in the shader.
  const validBytes = new Uint8Array(size);
  for (let k = 0; k < cells; k += 1) validBytes[k] = cellIsValid(b, k) ? 255 : 0;
  const valid = new THREE.DataTexture(validBytes, TEX_WIDTH, height, THREE.RedFormat, THREE.UnsignedByteType);
  for (const t of [values, valid]) {
    t.magFilter = t.minFilter = THREE.NearestFilter;  // exact texel per cell
    t.needsUpdate = true;
  }
  return { values, valid };
}

/**
 * Build the mesh. Put it at `buffers.anchor` (64-bit numbers, kept in the object
 * transform) so the f32 vertex positions stay small and exact.
 */
export function createSurfaceMesh(
  b: SurfaceRenderBuffers, rampBytes: Uint8Array, range: readonly [number, number],
): THREE.Mesh {
  const { position, cell, frame } = surfaceVertexArrays(b);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(position, 3));
  geometry.setAttribute("cell", new THREE.BufferAttribute(cell, 2));
  geometry.setAttribute("frame", new THREE.BufferAttribute(frame, 3));
  geometry.computeBoundingSphere();

  const { values, valid } = cellTexture(b);
  const ramp = new THREE.DataTexture(rampBytes, 256, 1, THREE.RGBAFormat);
  ramp.magFilter = ramp.minFilter = THREE.LinearFilter;
  ramp.needsUpdate = true;

  const material = new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader,
    fragmentShader,
    side: THREE.DoubleSide,  // a wall can face any way
    uniforms: {
      uValues: { value: values },
      uValid: { value: valid },
      uRamp: { value: ramp },
      uRange: { value: new THREE.Vector2(range[0], range[1]) },
    },
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.set(b.anchor[0], b.anchor[1], b.anchor[2]);
  return mesh;
}
