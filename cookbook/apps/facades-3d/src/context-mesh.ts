// The buildings as one grey mesh, for context under the result colours.
// Building meshes are flat `coordinates` (x, y, z in metres) and `indices`,
// in the frame of the polygon's south-west corner. The facade result uses the same frame.

import * as THREE from "three";

type MeshMap = Readonly<Record<string, { coordinates: ArrayLike<number>; indices: ArrayLike<number> }>>;

export function createContextMesh(buildings: MeshMap): THREE.Mesh {
  // Merge all buildings into one geometry: one draw call, not one per building.
  let vertexCount = 0;
  let indexCount = 0;
  for (const m of Object.values(buildings)) {
    vertexCount += m.coordinates.length / 3;
    indexCount += m.indices.length;
  }
  const position = new Float32Array(vertexCount * 3);
  const index = new Uint32Array(indexCount);
  let v = 0;
  let i = 0;
  for (const m of Object.values(buildings)) {
    position.set(m.coordinates, v * 3);
    for (let k = 0; k < m.indices.length; k += 1) index[i + k] = m.indices[k] + v;
    v += m.coordinates.length / 3;
    i += m.indices.length;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(position, 3));
  geometry.setIndex(new THREE.BufferAttribute(index, 1));
  // Split the vertices so each face gets a flat normal (crisp building edges).
  const flat = geometry.toNonIndexed();
  flat.computeVertexNormals();
  const material = new THREE.MeshLambertMaterial({
    color: 0xdfe2e7,
    side: THREE.DoubleSide,
    // Push the grey walls back a little, so the result colours on the same walls win.
    polygonOffset: true,
    polygonOffsetFactor: 1,
    polygonOffsetUnits: 1,
  });
  return new THREE.Mesh(flat, material);
}
