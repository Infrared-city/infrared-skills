"""Infrared facade + roof results in Blender (headless, Blender 4.5 LTS).

Run:
  Blender -b --factory-startup --python-exit-code 1 --python cookbook/scripts/blender/blender_facade_results.py -- \
      <facade_buffers.npz> <context.obj> <trees_local.json> <out_dir> [label] [vmin] [vmax]

facade_buffers.npz = `result.columns.render_buffers()` of an `analysis_surfaces` run, saved as in
references/recipes/blender.md (+ `valid` unpacked, `polygon_sw_local` = polygon SW in the OBJ frame).

How it stays fast: no mesh per cell. Every frame (one planar surface, nu x nv cells) gets a block
in ONE texture atlas, one texel per cell, sampled with "Closest" so cells stay crisp. The mesh is
only the outline triangles of the frames, UV-mapped into their block. Context buildings (not
analysed) and trees are each merged into a single mesh.
"""

import json
import math
import os
import sys
import time


import bpy
import numpy as np
from mathutils import Vector

_T0 = _T = time.perf_counter()


def lap(what):
    global _T
    now = time.perf_counter()
    print(f"[t] {what:28s} {now - _T:6.2f} s   (total {now - _T0:6.2f})", flush=True)
    _T = now


A = sys.argv[sys.argv.index("--") + 1 :]
NPZ, CTX_OBJ, TREES, OUT = A[:4]
LABEL = A[4] if len(A) > 4 else "Sky view factor (%)"
VMIN, VMAX = (
    (float(A[5]), float(A[6])) if len(A) > 6 else (0.0, 100.0)
)  # fixed per-analysis domain
os.makedirs(OUT, exist_ok=True)
ATLAS_W, PAD = 4096, 1

VIRIDIS = (
    np.array(
        [  # 11 stops of matplotlib viridis (sRGB)
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
NO_VALUE = np.array(
    [0.42, 0.42, 0.44]
)  # masked cell: neutral grey, never a colour of the scale


def colormap(x):
    x = np.clip(x, 0, 1) * (len(VIRIDIS) - 1)
    i = np.minimum(x.astype(int), len(VIRIDIS) - 2)
    f = (x - i)[:, None]
    return VIRIDIS[i] * (1 - f) + VIRIDIS[i + 1] * f


# ----------------------------------------------------------------- load buffers
d = np.load(NPZ)
anchor = d["anchor"].astype(np.float64)
frames = (
    d["frames"].reshape(-1, 9).astype(np.float64)
)  # corner, u_step, v_step (rel. anchor)
dims = d["dims"].reshape(-1, 3).astype(np.int64)  # nu, nv, cell start
outline = d["outline"].reshape(-1, 3, 2).astype(np.float64)  # (s, t) in cell units
offs = d["outline_offsets"].astype(np.int64)
values, valid = d["values"], d["valid"]
shift = np.r_[d["polygon_sw_local"], 0.0]  # polygon-SW frame -> OBJ frame
S = len(dims)
lap("load npz")
print(
    f"{S} frames, {len(values)} cells, {len(outline)} outline tris, {int(valid.sum())} valid"
)

# ----------------------------------------------------------------- shelf-pack the atlas
nu, nv = dims[:, 0], dims[:, 1]
order = np.argsort(-nv, kind="stable")
px, py = np.zeros(S, np.int64), np.zeros(S, np.int64)
x = y = shelf_h = 0
for f in order:
    w, h = nu[f] + 2 * PAD, nv[f] + 2 * PAD
    if x + w > ATLAS_W:
        x, y, shelf_h = 0, y + shelf_h, 0
    px[f], py[f] = x + PAD, y + PAD
    x += w
    shelf_h = max(shelf_h, h)
ATLAS_H = int(y + shelf_h)
lap("shelf pack")
print(f"atlas {ATLAS_W} x {ATLAS_H}")

# texel of every cell: frame f, cell k = j * nu + i  ->  (px + i, py + j)
cell_frame = np.repeat(np.arange(S), nu * nv)
k = np.arange(len(values)) - dims[cell_frame, 2]
ci, cj = k % nu[cell_frame], k // nu[cell_frame]
rgb = np.where(valid[:, None], colormap((values - VMIN) / (VMAX - VMIN)), NO_VALUE)
pix = np.zeros((ATLAS_H, ATLAS_W, 4), np.float32)
pix[..., :3] = NO_VALUE
pix[..., 3] = 1
pix[py[cell_frame] + cj, px[cell_frame] + ci, :3] = rgb
# bleed each frame's border cells into its padding so edge texels never pick up a neighbour
for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
    edge = (
        ((cj == 0) if dy < 0 else (cj == nv[cell_frame] - 1))
        if dy
        else ((ci == 0) if dx < 0 else (ci == nu[cell_frame] - 1))
    )
    pix[
        py[cell_frame][edge] + cj[edge] + dy, px[cell_frame][edge] + ci[edge] + dx, :3
    ] = rgb[edge]

lap("atlas pixels (numpy)")
bpy.ops.wm.read_factory_settings(use_empty=True)
img = bpy.data.images.new("ir_atlas", ATLAS_W, ATLAS_H, alpha=False)
img.colorspace_settings.name = "sRGB"
img.pixels.foreach_set(pix.ravel())
img.filepath_raw = os.path.join(OUT, "ir_atlas.png")
img.file_format = "PNG"
img.save()

lap("atlas image + png save")
# ----------------------------------------------------------------- outline mesh with atlas UVs
tri_frame = np.repeat(np.arange(S), np.diff(offs))
fr = frames[tri_frame]  # (T, 9)
s, t = outline[..., 0], outline[..., 1]  # (T, 3)
co = (
    anchor
    + shift
    + fr[:, None, 0:3]
    + s[..., None] * fr[:, None, 3:6]
    + t[..., None] * fr[:, None, 6:9]
).reshape(-1, 3)
uv = np.stack(
    [(px[tri_frame][:, None] + s) / ATLAS_W, (py[tri_frame][:, None] + t) / ATLAS_H], -1
).reshape(-1, 2)


def mesh_object(name, verts, tris, uvs=None):
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
    me.validate(clean_customdata=False)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


results = mesh_object("IR_results", co, np.arange(len(co)).reshape(-1, 3), uv)


def material(name, color=None, image=None, emit=0.0):
    """Diffuse (+ emission from the atlas). Principled BSDF made the first EEVEE frame
    compile for ~10 s; this pair compiles in ~1 s and reads the same at city scale."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    out = nt.nodes["Material Output"]
    dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
    if image is None:
        dif.inputs["Color"].default_value = (*color, 1)
        nt.links.new(dif.outputs[0], out.inputs["Surface"])
        return m
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image, tex.interpolation = image, "Closest"
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = emit  # keeps the scale readable in shade
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(tex.outputs["Color"], dif.inputs["Color"])
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(dif.outputs[0], add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    return m


lap("outline mesh")
results.data.materials.append(material("ir_result", image=img, emit=0.35))

# ----------------------------------------------------------------- context buildings (grey)
analysed = set(str(n) for n in d["names"])
with open(
    CTX_OBJ
) as fh:  # name scan (~0.1 s): skip the import when nothing is left as context
    names = {ln[2:].strip() for ln in fh if ln.startswith("o ")}
if names - analysed:
    bpy.ops.wm.obj_import(
        filepath=CTX_OBJ, forward_axis="Y", up_axis="Z", use_split_objects=True
    )
lap("context import")
ctx = [
    o for o in bpy.context.scene.objects if o.type == "MESH" and o.name != "IR_results"
]
for o in ctx:
    if o.name.split(".")[0] in analysed:
        bpy.data.objects.remove(o, do_unlink=True)
ctx = [
    o for o in bpy.context.scene.objects if o.type == "MESH" and o.name != "IR_results"
]
if ctx:  # empty when every building was analysed
    with bpy.context.temp_override(active_object=ctx[0], selected_editable_objects=ctx):
        bpy.ops.object.join()
    context = ctx[0]
    context.name = "Context_buildings"
    context.data.materials.clear()
    context.data.materials.append(material("context", color=(0.36, 0.37, 0.4)))

# ----------------------------------------------------------------- trees (one merged mesh)
trees = json.load(open(TREES))
lo, hi = co[:, :2].min(0) - 400, co[:, :2].max(0) + 400
tv, tf = [], []
for x, y, h, c in trees:
    if not (lo[0] < x < hi[0] and lo[1] < y < hi[1]):
        continue
    r, n0 = c / 2, len(tv)
    crown_z = max(h - r, 1.5)
    for i in range(8):  # 8-gon double cone: cheap, reads as a canopy from above
        a = 2 * math.pi * i / 8
        tv.append((x + r * math.cos(a), y + r * math.sin(a), crown_z))
    tv += [(x, y, h), (x, y, max(crown_z - r * 0.6, 0.5))]
    for i in range(8):
        j = (i + 1) % 8
        tf += [(n0 + i, n0 + j, n0 + 8), (n0 + j, n0 + i, n0 + 9)]
canopy = mesh_object("Trees", np.array(tv), np.array(tf))
canopy.data.materials.append(material("tree", color=(0.16, 0.42, 0.18)))

lap("trees")
# ----------------------------------------------------------------- ground, light, world
centre = Vector(co.mean(0).tolist())
bpy.ops.mesh.primitive_plane_add(size=6000, location=(centre.x, centre.y, -0.05))
bpy.context.object.data.materials.append(material("ground", color=(0.09, 0.09, 0.1)))

sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
sun.data.energy, sun.data.angle = 3.2, math.radians(3)
sun.rotation_euler = (math.radians(40), 0, math.radians(35))
bpy.context.scene.collection.objects.link(sun)

sc = bpy.context.scene
sc.world = bpy.data.worlds.new("sky")
sc.world.use_nodes = True
bg = sc.world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.55, 0.62, 0.75, 1)
bg.inputs["Strength"].default_value = 0.9

lap("ground/light/world")
sc.render.engine = "BLENDER_EEVEE_NEXT"
try:
    sc.eevee.use_shadows = True
    sc.eevee.use_raytracing = True
except AttributeError:
    pass
sc.view_settings.view_transform = "Standard"  # AgX/Filmic would shift the colour scale
sc.render.resolution_x, sc.render.resolution_y = 1920, 1200
sc.render.film_transparent = False

cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.clip_end = 20000


def shoot(name, eye, look, lens):
    cam.location, cam.data.lens = eye, lens
    cam.rotation_euler = (look - eye).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(OUT, name)
    bpy.ops.render.render(write_still=True)


lap("scene setup")
top = co[np.argmax(co[:, 2])]
tower = Vector((top[0], top[1], top[2] * 0.45))  # aim at the tallest analysed surface
shoot("hero.png", tower + Vector((210, -330, 260)), tower, 32)
lap("render hero")
shoot("street.png", tower + Vector((-140, -170, 60)), tower + Vector((0, 0, 40)), 24)
lap("render street")
shoot("aerial.png", centre + Vector((0, -380, 900)), centre, 35)

lap("render aerial")
json.dump(
    {"label": LABEL, "vmin": VMIN, "vmax": VMAX, "stops": VIRIDIS.tolist()},
    open(os.path.join(OUT, "legend.json"), "w"),
)
img.pack()
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "ir_facade_results.blend"))
lap("pack + save .blend")
print("done")
