"""Infrared facade and roof results in Blender (headless, Blender 4.5 LTS).

    Blender -b --factory-startup --python-exit-code 1 \\
        --python blender_facade_results.py -- \\
        --analysis "svf.npz|Sky view factor (%)|0|100" \\
        --analysis "solar.npz|Solar radiation (kWh/m2)|0|140" \\
        [--context model.obj] [--trees trees.json] --out renders/

Each `--analysis` is a file from `export_buffers.save_buffers` plus a label and a FIXED colour
domain. All files must share one layout (same geometry and surface grid). The layout is built
once: one texture atlas (one texel per cell, sampled "Closest") and one mesh of the frame
outlines. Each analysis adds only its own atlas image and material.

`--context`: an OBJ in your model frame (z up). Objects whose names were analysed are removed,
the rest is joined into one grey mesh. `--trees`: JSON list of [x, y, height, crown_diameter]
in the same frame. Output: `<slug>_hero.png`, `<slug>_aerial.png`, `legend_<slug>.json` and
`ir_facade_results.blend` (switch analyses by changing the material of `IR_results`).
"""

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass

import bpy
import numpy as np
from mathutils import Vector

ATLAS_W, PAD = 4096, 1
LAYOUT_KEYS = ("anchor", "frames", "dims", "outline", "outline_offsets")
VIRIDIS = (
    np.array(
        [
            [68, 1, 84],
            [72, 36, 117],
            [65, 68, 135],
            [53, 95, 141],
            [42, 120, 142],
            [33, 145, 140],
            [34, 168, 132],
            [68, 191, 112],
            [122, 209, 81],
            [189, 223, 38],
            [253, 231, 37],
        ]
    )
    / 255.0
)
NO_VALUE = (
    0.42,
    0.42,
    0.44,
)  # cells without a value: neutral grey, not a colour of the scale


@dataclass
class Analysis:
    slug: str
    path: str
    label: str
    vmin: float
    vmax: float


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--analysis", action="append", required=True, help="npz|label|vmin|vmax"
    )
    p.add_argument("--context")
    p.add_argument("--trees")
    p.add_argument("--out", required=True)
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    analyses = []
    for spec in args.analysis:
        path, label, vmin, vmax = spec.split("|")
        slug = os.path.splitext(os.path.basename(path))[0]
        analyses.append(Analysis(slug, path, label, float(vmin), float(vmax)))
    args.analyses = analyses
    return args


def colormap(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0) * (len(VIRIDIS) - 1)
    i = np.minimum(x.astype(int), len(VIRIDIS) - 2)
    f = (x - i)[:, None]
    return VIRIDIS[i] * (1 - f) + VIRIDIS[i + 1] * f


class Layout:
    """Frames, outline triangles and the atlas position of every frame and cell."""

    def __init__(self, data):
        self.anchor = data["anchor"].astype(np.float64)
        self.frames = (
            data["frames"].reshape(-1, 9).astype(np.float64)
        )  # corner, u_step, v_step
        self.dims = data["dims"].reshape(-1, 3).astype(np.int64)  # nu, nv, first cell
        self.outline = (
            data["outline"].reshape(-1, 3, 2).astype(np.float64)
        )  # (s, t), cell units
        self.offsets = data["outline_offsets"].astype(np.int64)
        self.offset = np.r_[data["frame_offset"], 0.0]
        nu, nv = self.dims[:, 0], self.dims[:, 1]
        self.px, self.py, self.height = self._shelf_pack(nu, nv)
        # cell k of frame f is (i, j) with k = start + j * nu + i  ->  texel (px + i, py + j)
        frame = np.repeat(np.arange(len(nu)), nu * nv)
        k = np.arange(int((nu * nv).sum())) - self.dims[frame, 2]
        i, j = k % nu[frame], k // nu[frame]
        self.tx, self.ty = self.px[frame] + i, self.py[frame] + j
        # border cells, copied into the 1-texel padding so no texel reads a neighbour frame
        self.borders = [
            (0, -1, j == 0),
            (0, 1, j == nv[frame] - 1),
            (-1, 0, i == 0),
            (1, 0, i == nu[frame] - 1),
        ]

    @staticmethod
    def _shelf_pack(nu, nv):
        px, py = np.zeros(len(nu), np.int64), np.zeros(len(nu), np.int64)
        x = y = shelf = 0
        for f in np.argsort(-nv, kind="stable"):  # tallest first: tight shelves
            w, h = nu[f] + 2 * PAD, nv[f] + 2 * PAD
            if x + w > ATLAS_W:
                x, y, shelf = 0, y + shelf, 0
            px[f], py[f] = x + PAD, y + PAD
            x, shelf = x + w, max(shelf, h)
        return px, py, int(y + shelf)

    def mesh_arrays(self):
        """Vertices (model frame) and atlas UVs of every outline triangle."""
        tri_frame = np.repeat(np.arange(len(self.dims)), np.diff(self.offsets))
        fr = self.frames[tri_frame]
        s, t = self.outline[..., 0], self.outline[..., 1]
        co = (
            self.anchor
            + self.offset
            + fr[:, None, 0:3]
            + s[..., None] * fr[:, None, 3:6]
            + t[..., None] * fr[:, None, 6:9]
        ).reshape(-1, 3)
        uv = np.stack(
            [
                (self.px[tri_frame][:, None] + s) / ATLAS_W,
                (self.py[tri_frame][:, None] + t) / self.height,
            ],
            -1,
        ).reshape(-1, 2)
        return co, uv

    def atlas(self, name, values, valid, vmin, vmax):
        rgb = np.where(
            valid[:, None], colormap((values - vmin) / (vmax - vmin)), NO_VALUE
        )
        pix = np.empty((self.height, ATLAS_W, 4), np.float32)
        pix[...] = (*NO_VALUE, 1.0)
        pix[self.ty, self.tx, :3] = rgb
        for dx, dy, edge in self.borders:
            pix[self.ty[edge] + dy, self.tx[edge] + dx, :3] = rgb[edge]
        img = bpy.data.images.new(name, ATLAS_W, self.height, alpha=False)
        img.pixels.foreach_set(pix.ravel())
        img.pack()
        return img


def mesh_object(name, verts, tris, uvs=None):
    """One mesh from flat arrays (foreach_set: much faster than from_pydata at this size)."""
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    me.loops.add(tris.size)
    me.loops.foreach_set("vertex_index", tris.astype(np.int32).ravel())
    me.polygons.add(len(tris))
    me.polygons.foreach_set("loop_start", np.arange(0, tris.size, 3, dtype=np.int32))
    if uvs is not None:
        me.uv_layers.new(name="UVMap").data.foreach_set(
            "uv", uvs.astype(np.float32).ravel()
        )
    me.update(calc_edges=True)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def material(name, color=None, image=None, emission=0.35):
    """Diffuse, plus emission from the atlas so the scale stays readable in shade.
    A Principled BSDF makes the first EEVEE frame compile for ~10 s; this takes ~1 s."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nodes, links = m.node_tree.nodes, m.node_tree.links
    nodes.remove(nodes["Principled BSDF"])
    out, diffuse = nodes["Material Output"], nodes.new("ShaderNodeBsdfDiffuse")
    if image is None:
        diffuse.inputs["Color"].default_value = (*color, 1.0)
        links.new(diffuse.outputs[0], out.inputs["Surface"])
        return m
    tex = nodes.new("ShaderNodeTexImage")
    tex.image, tex.interpolation = image, "Closest"
    glow, add = nodes.new("ShaderNodeEmission"), nodes.new("ShaderNodeAddShader")
    glow.inputs["Strength"].default_value = emission
    links.new(tex.outputs["Color"], diffuse.inputs["Color"])
    links.new(tex.outputs["Color"], glow.inputs["Color"])
    links.new(diffuse.outputs[0], add.inputs[0])
    links.new(glow.outputs[0], add.inputs[1])
    links.new(add.outputs[0], out.inputs["Surface"])
    return m


def add_context(path, analysed):
    """Import the OBJ only if some object was not analysed; join the rest into one mesh."""
    with open(path) as fh:
        names = {line[2:].strip() for line in fh if line.startswith("o ")}
    if not names - analysed:
        return
    before = set(bpy.context.scene.objects)
    bpy.ops.wm.obj_import(
        filepath=path, forward_axis="Y", up_axis="Z", use_split_objects=True
    )
    new = [o for o in bpy.context.scene.objects if o not in before]
    keep = []
    for ob in new:
        if ob.name.split(".")[0] in analysed:  # the results already draw this building
            bpy.data.objects.remove(ob, do_unlink=True)
        else:
            keep.append(ob)
    with bpy.context.temp_override(
        active_object=keep[0], selected_editable_objects=keep
    ):
        bpy.ops.object.join()
    keep[0].name = "Context"
    keep[0].data.materials.clear()
    keep[0].data.materials.append(material("context", color=(0.36, 0.37, 0.4)))


def add_trees(path, lo, hi):
    """Each tree as an 8-sided double cone: cheap, reads as a canopy from above."""
    verts, tris = [], []
    for x, y, h, crown in json.load(open(path)):
        if not (lo[0] < x < hi[0] and lo[1] < y < hi[1]):
            continue
        r, n = crown / 2, len(verts)
        z = max(h - r, 1.5)
        verts += [
            (x + r * math.cos(a), y + r * math.sin(a), z)
            for a in np.linspace(0, 2 * math.pi, 8, endpoint=False)
        ]
        verts += [(x, y, h), (x, y, max(z - 0.6 * r, 0.5))]
        for i in range(8):
            j = (i + 1) % 8
            tris += [(n + i, n + j, n + 8), (n + j, n + i, n + 9)]
    if verts:
        ob = mesh_object("Trees", np.array(verts), np.array(tris))
        ob.data.materials.append(material("tree", color=(0.16, 0.42, 0.18)))


def setup_scene(centre):
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=6000, location=(centre.x, centre.y, -0.05))
    bpy.context.object.data.materials.append(
        material("ground", color=(0.09, 0.09, 0.1))
    )
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy, sun.data.angle = 3.2, math.radians(3)
    sun.rotation_euler = (math.radians(40), 0, math.radians(35))
    sc.collection.objects.link(sun)
    sc.world = bpy.data.worlds.new("sky")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.55,
        0.62,
        0.75,
        1,
    )
    sc.render.engine = "BLENDER_EEVEE_NEXT"
    sc.view_settings.view_transform = (
        "Standard"  # AgX / Filmic would shift the colour scale
    )
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1200
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    cam.data.clip_end = 20000  # the default 100 m cuts a city off
    sc.collection.objects.link(cam)
    sc.camera = cam
    return sc, cam


def render(sc, cam, path, eye, target, lens):
    cam.location, cam.data.lens = eye, lens
    cam.rotation_euler = (target - eye).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    args = parse_args()
    os.makedirs(args.out, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)

    first = np.load(args.analyses[0].path)
    layout = Layout(first)
    co, uv = layout.mesh_arrays()
    results = mesh_object("IR_results", co, np.arange(len(co)).reshape(-1, 3), uv)
    print(
        f"{len(layout.dims)} frames, {len(layout.tx)} cells, {len(co) // 3} outline triangles, "
        f"atlas {ATLAS_W} x {layout.height}"
    )

    mats = []
    for a in args.analyses:
        data = np.load(a.path)
        if not all(np.array_equal(first[k], data[k]) for k in LAYOUT_KEYS):
            raise SystemExit(f"{a.path}: other layout than {args.analyses[0].path}")
        img = layout.atlas(
            f"ir_{a.slug}", data["values"], data["valid"], a.vmin, a.vmax
        )
        mats.append(material(f"ir_{a.slug}", image=img))
    results.data.materials.append(mats[0])

    if args.context:
        add_context(args.context, {str(n) for n in first["building_ids"]})
    if args.trees:
        add_trees(args.trees, co[:, :2].min(0) - 400, co[:, :2].max(0) + 400)
    centre = Vector(co.mean(0).tolist())
    sc, cam = setup_scene(centre)

    top = co[np.argmax(co[:, 2])]
    hero = Vector(
        (top[0], top[1], 0.45 * top[2])
    )  # aim at the tallest analysed surface
    for a, mat in zip(args.analyses, mats):
        results.data.materials[0] = mat  # same mesh and UVs: only the atlas changes
        render(
            sc,
            cam,
            os.path.join(args.out, f"{a.slug}_hero.png"),
            hero + Vector((210, -330, 260)),
            hero,
            32,
        )
        render(
            sc,
            cam,
            os.path.join(args.out, f"{a.slug}_aerial.png"),
            centre + Vector((0, -380, 900)),
            centre,
            35,
        )
        with open(os.path.join(args.out, f"legend_{a.slug}.json"), "w") as fh:
            json.dump(
                {
                    "label": a.label,
                    "vmin": a.vmin,
                    "vmax": a.vmax,
                    "stops": VIRIDIS.tolist(),
                },
                fh,
            )
    results.data.materials[0] = mats[0]
    bpy.ops.wm.save_as_mainfile(
        filepath=os.path.join(args.out, "ir_facade_results.blend")
    )


main()
