# Geometry pitfalls: your own building meshes

Read this before a facade or roof run on meshes that you prepared yourself.
All these errors run, bill and return a plausible result. No error is raised.
Basics (frame, closed solids, welding): [byo-inputs.md](byo-inputs.md).

## How sensors and solids interact

- The SDK puts sensors on every body in `buildings`: your analysed buildings and the context bodies.
- A sensor inside a solid, or flush against a solid, sees no sky and no sun.
  Its SVF is 0 and its sun hours are 0. In 3D, the face is dark and flat.
- A value of 0 is a real result. It is not "no data".
- The SDK culls a cell that it cannot place (inside a solid, below the terrain).
  That cell comes back as NaN (no data) by design. A rerun does not change it.

Overlapping solids give large faces at 0. The causes below are the usual ones.

## 1. Duplicate envelopes

Do not send a coarse block of a building together with its detailed mesh.
A coarse block is, for example, an LoD1 box or a footprint extruded to a default height.
The block fills the volume of the detailed building, and the detailed facades read 0.

Rule: drop a context block when more than 50% of its own footprint is inside the union
of the detailed footprints. Keep a real podium block that has no detailed model.
It then also gets values.

## 2. Hole filling of open meshes

If you close open triangle soups yourself, do not cap a tall, non-planar boundary loop
as a floor in plan view. The cap cuts vertically through the building. It closes the facade
slots, and the cap faces read 0.

Rule: cap a loop as a floor only when its z-range is about 3 m or less.

## 3. Extending buildings down to the terrain (pedestal)

`terrain_alignment="as-is"` does not extend a building down to the terrain.
If you add a pedestal yourself, add it only over open ground. A tower that starts on top
of a podium must not get walls down through the podium. Those walls are inside the podium
and read 0. See [analyses/11-terrain-and-context.md](analyses/11-terrain-and-context.md).

## 4. Double shells in source meshes

City models (for example LoD2 or LoD3 towers) can contain a second, overlapping outer shell
around slots, fins or balconies. The faces of the inner shell are inside the solid.
Their sensors read 0 (correct for that mesh), or the SDK culls them.

Rule: if you can, merge or remove the inner shells before the run. If you cannot,
expect these zeros and do not report them as shade.

## 5. Show "no data" as a surface, not as a hole

When you colour facade results in a viewer, draw the cells that have no value
(NaN or the no-data code) in a neutral, opaque colour. If the viewer discards these cells
(transparent), people look through the outer shell at inner faces that read 0.
They then think that the facade is dark.

Rule: do not discard no-data cells on facades. Roofs and ground can keep the discard
where their no-data cells lie over real values.

## How to check

1. For each building, calculate the share of facade area where sun hours AND SVF are 0.
2. Flag a large face (for example, more than 150 m2) that is more than 80% at 0
   and has no geometry within about 0.5 m in front of it. Such a face is usually
   inside or against another solid.
3. Look at the result in 3D before you trust a number.
4. Look at the result in 3D from the side that the user will see, before you trust a count.

A face at 0 with a real wall close in front of it (a party wall, a light well) is correct.
