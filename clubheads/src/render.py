"""render.py: orthographic renders + anchors for one club built by clubs.py.

    Blender -b --factory-startup --python render.py -- --club driver [--looks light,dark,line]
          [--views top,side,face,back] [--preview]

Writes out/<club>/<club>_<view>_<look>.png (looks: light, dark, line-black) and
out/<club>/<club>_<view>.json (anchors).  sheets.py makes line-white, @512 copies and sheets.
"""
import sys, os, math, json, time
import numpy as np
import bpy
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.join(ROOT, 'work')
OUT = os.path.join(ROOT, 'out')
HDRI = os.path.join(ROOT, 'ref', 'studio_small_08_2k.hdr')

# camera frames: B points from the club toward the camera, U is image-up.  R = U x B.
VIEWS = {
    'top':  dict(B=(0, 0, 1), U=(0, 1, 0)),     # plan, target right, heel/shaft up
    'side': dict(B=(0, -1, 0), U=(0, 0, 1)),    # from the toe, face right, ground horizontal
    'face': dict(B=(1, 0, 0), U=(0, 0, 1)),     # from the target, heel/shaft right
    'back': dict(B=(-1, 0, 0), U=(0, 0, 1)),    # from behind (irons: the cavity)
    'iso': dict(B=(0.55, -0.62, 0.56), U=(-0.37, 0.42, 0.83)),     # debug only: front-toe-above
    'isob': dict(B=(-0.5, -0.55, -0.67), U=(-0.45, -0.5, 0.74)),   # debug only: sole from toe-back
}
for _v in VIEWS.values():
    _B = np.array(_v['B'], float); _B /= np.linalg.norm(_B); _U = np.array(_v['U'], float)
    _U = _U - _B * np.dot(_U, _B); _U /= np.linalg.norm(_U); _v['B'] = tuple(_B); _v['U'] = tuple(_U)
LONG = 2048


def args():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--club', required=True)
    ap.add_argument('--looks', default='light,dark,line')
    ap.add_argument('--views', default=None)
    ap.add_argument('--preview', action='store_true')
    ap.add_argument('--samples', type=int, default=128)
    ap.add_argument('--suffix', default='')
    return ap.parse_args(argv)


def world_verts(ob):
    me = ob.data
    co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3).astype(float)
    M = np.array(ob.matrix_world)
    w = co @ M[:3, :3].T + M[:3, 3]
    return w * 1000.0  # mm


def setup_cycles(scn, samples, preview):
    scn.render.engine = 'CYCLES'
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = os.environ.get('CYCLES_DEVICE', 'NONE')
        prefs.get_devices()
        for d in prefs.devices:
            d.use = (d.type != 'CPU')
        for k, v in (('kernel_optimization_level', os.environ.get('CYCLES_KOPT', 'OFF')),
                     ('metalrt', os.environ.get('CYCLES_METALRT', 'OFF'))):
            try:
                setattr(prefs, k, v)
            except Exception as e:
                print('pref', k, e)
        scn.cycles.device = 'GPU' if os.environ.get('CYCLES_DEVICE', 'NONE') != 'NONE' else 'CPU'
    except Exception as e:
        print('GPU setup failed', e)
    c = scn.cycles
    c.samples = 24 if preview else samples
    c.use_adaptive_sampling = True; c.adaptive_threshold = 0.01
    c.use_denoising = os.environ.get('NO_DENOISE') != '1'
    for k, v in (('denoising_quality', os.environ.get('DN_Q', 'BALANCED')), ('denoising_prefilter', os.environ.get('DN_PF', 'FAST')),
                 ('denoising_input_passes', 'RGB_ALBEDO_NORMAL')):
        try:
            setattr(c, k, v)
        except Exception as e:
            print('denoise opt', k, e)
    try:
        c.denoising_use_gpu = os.environ.get('DENOISE_GPU', '0') == '1'
    except Exception as e:
        print('denoise gpu', e)
    try:
        c.denoiser = 'OPENIMAGEDENOISE'
    except Exception:
        pass
    c.max_bounces = 10; c.glossy_bounces = 6; c.diffuse_bounces = 3; c.transparent_max_bounces = 8
    c.filter_width = 1.4
    c.use_auto_tile = True; c.tile_size = int(os.environ.get('TILE', '512'))
    scn.render.use_persistent_data = False
    scn.render.film_transparent = True
    vs = scn.view_settings
    vs.view_transform = 'AgX'
    try:
        vs.look = 'AgX - Medium High Contrast'
    except Exception:
        try:
            vs.look = 'Medium High Contrast'
        except Exception:
            pass
    scn.render.image_settings.file_format = 'PNG'
    scn.render.image_settings.color_mode = 'RGBA'
    scn.render.image_settings.color_depth = '8'
    scn.render.image_settings.compression = 15
    scn.render.use_stamp = False          # no burnt-in stamp
    for k in dir(scn.render):            # and no metadata chunks (file path, date, render stats)
        if k.startswith('use_stamp_'):
            try:
                setattr(scn.render, k, False)
            except Exception:
                pass


def soft_hdri(sig_az=60.0, sig_el=10.0):
    """The studio HDRI with its detail smeared out (Gaussian, degrees in azimuth and elevation, by
    three box passes): the room's broad light and gradient stay, the props and stands go.  A gloss
    black crown mirrors the environment crisply, so it reflects this instead."""
    im = bpy.data.images.get('studio_soft')
    if im:
        return im
    src = bpy.data.images.load(HDRI, check_existing=True)
    W, H = src.size
    px = np.empty(W * H * 4, np.float32); src.pixels.foreach_get(px); px = px.reshape(H, W, 4)
    def box(a, r, axis, wrap):
        n = a.shape[axis]
        pad = [(0, 0)] * a.ndim; pad[axis] = (r + 1, r)
        a = np.pad(a, pad, mode='wrap' if wrap else 'edge')
        c = np.cumsum(a, axis=axis, dtype=np.float64)
        return ((np.take(c, range(2 * r + 1, n + 2 * r + 1), axis=axis) - np.take(c, range(0, n), axis=axis)) / (2 * r + 1)).astype(np.float32)
    for sig, axis, wrap in ((sig_az * W / 360.0, 1, True), (sig_el * H / 180.0, 0, False)):
        r = max(1, int(round(sig * math.sqrt(12.0 / 3.0 + 1.0) / 2.0)))   # three boxes ~ one Gaussian
        for _ in range(3):
            px = box(px, r, axis, wrap)
    im = bpy.data.images.new('studio_soft', W, H, float_buffer=True)
    im.pixels.foreach_set(px.ravel())
    return im


def setup_world(scn, strength, rot_z, soft=False):
    w = bpy.data.worlds.get('studio') or bpy.data.worlds.new('studio')
    scn.world = w
    nt = w.node_tree; nt.nodes.clear()
    tc = nt.nodes.new('ShaderNodeTexCoord'); mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Rotation'].default_value = (0, 0, math.radians(rot_z))
    env = nt.nodes.new('ShaderNodeTexEnvironment')
    if os.environ.get('NO_HDRI') != '1':
        env.image = soft_hdri() if soft else bpy.data.images.load(HDRI, check_existing=True)
    bg = nt.nodes.new('ShaderNodeBackground'); bg.inputs['Strength'].default_value = strength
    out = nt.nodes.new('ShaderNodeOutputWorld')
    nt.links.new(tc.outputs['Generated'], mp.inputs['Vector'])
    nt.links.new(mp.outputs[0], env.inputs['Vector'])
    nt.links.new(env.outputs['Color'], bg.inputs['Color'])
    nt.links.new(bg.outputs[0], out.inputs['Surface'])


# Dark-look rule: every part of the silhouette must separate from #15171A (dL* >= 12, checked by
# sheets.py --check).  Lights from below and behind, in camera space, graze the soles, skirts and
# trailing edges that the top-weighted key and rims leave in shadow.
DARK_SEPARATION = [] if os.environ.get('NO_SEP') == '1' else [
    ((0.00, -0.75, 0.66), 0.60, 0.40, 2.2, (0.95, 0.97, 1.0)),     # low front kicker (sole band)
    ((0.00, -1.00, -0.45), 0.55, 0.06, 12.0, (1.0, 1.0, 1.0)),     # bottom rim (trailing edge)
    ((-1.00, -0.45, -0.60), 0.55, 0.05, 10.0, (0.92, 0.96, 1.0)),  # lower-left rim
    ((1.00, -0.45, -0.60), 0.55, 0.05, 10.0, (1.0, 0.97, 0.94)),   # lower-right rim
    ((-1.00, 0.05, -0.50), 0.55, 0.06, 8.0, (0.92, 0.96, 1.0)),   # mid-left rim
    ((1.00, 0.05, -0.50), 0.55, 0.06, 8.0, (1.0, 0.97, 0.94)),    # mid-right rim
]
LIGHTS = {
    # (right, up, toward-camera) direction, distance m, size m, power W, colour
    'light': dict(world=0.45, rot=40, lights=[
        ((-0.75, 0.55, 0.35), 0.6, 0.22, 22.0, (1.0, 0.98, 0.96)),   # key, upper left
        ((0.85, 0.30, 0.30), 0.6, 0.22, 8.0, (0.96, 0.98, 1.0)),     # fill, right
        ((0.10, 0.85, -0.55), 0.6, 0.30, 26.0, (1.0, 1.0, 1.0)),     # top-back rim
    ]),
    'dark': dict(world=0.10, rot=40, lights=[
        ((-1.00, 0.30, -0.80), 0.55, 0.08, 40.0, (0.92, 0.96, 1.0)),  # rim left
        ((1.00, 0.40, -0.80), 0.55, 0.08, 40.0, (1.0, 0.97, 0.94)),   # rim right
        ((0.05, 1.00, -0.70), 0.55, 0.14, 16.0, (1.0, 1.0, 1.0)),     # top rim
        ((-0.55, 0.55, 0.60), 0.70, 0.30, 5.0, (1.0, 1.0, 1.0)),      # soft key
    ] + DARK_SEPARATION),
}


# Steep lofts (irons, wedge): the face mirrors the sky behind the club, so the top-back rims are
# dropped lower behind it and a broad dim card in front gives the satin face a mid-grey reflection
# from every view.
LIGHTS['light_steep'] = dict(world=0.40, rot=40, lights=[
    ((-0.75, 0.55, 0.35), 0.6, 0.22, 20.0, (1.0, 0.98, 0.96)),
    ((0.85, 0.30, 0.30), 0.6, 0.22, 8.0, (0.96, 0.98, 1.0)),
    ((0.15, 0.40, -0.90), 0.6, 0.26, 24.0, (1.0, 1.0, 1.0)),
])
LIGHTS['dark_steep'] = dict(world=0.10, rot=40, lights=[
    ((-1.00, 0.45, -0.80), 0.55, 0.08, 32.0, (0.92, 0.96, 1.0)),
    ((1.00, 0.55, -0.80), 0.55, 0.08, 44.0, (1.0, 0.97, 0.94)),
    ((0.05, 0.50, -0.85), 0.55, 0.14, 14.0, (1.0, 1.0, 1.0)),
    ((-0.55, 0.55, 0.60), 0.70, 0.30, 5.0, (1.0, 1.0, 1.0)),
] + DARK_SEPARATION)


# Dark look, top view of a gloss-black head: a level light from the target side, so the skirt seen edge-on
# beside the face (black gloss mirroring the dark room) still separates from the background.  It sits
# below anything the upward-facing crown can mirror.
GLOSS_TOP_DARK = [((1.00, 0.10, 0.0), 0.55, 0.12, float(os.environ.get('GLOSS_EDGE_W', 8.0)), (1.0, 0.97, 0.94))]


def clear_lights():
    for ob in list(bpy.data.objects):
        if ob.type == 'LIGHT':
            bpy.data.objects.remove(ob)


def setup_lights(look, R, U, B, centre_m, steep=False, face_n=None, skip=(), extra=()):
    """skip: lights left out of this view, extra: lights added to it (a gloss crown mirrors every light
    it faces, and gloss edges seen edge-on only show what they mirror)."""
    clear_lights()
    cfg = LIGHTS[look + '_steep'] if steep else LIGHTS[look]
    for i, (d, dist, size, power, col) in enumerate(list(cfg['lights']) + list(extra)):
        if any(L is k for L in cfg['lights'][i:i + 1] for k in skip):
            continue
        v = d[0] * R + d[1] * U + d[2] * B
        v = v / np.linalg.norm(v)
        L = bpy.data.lights.new('L%d' % i, 'AREA')
        L.shape = 'DISK'; L.size = size; L.energy = power; L.color = col
        ob = bpy.data.objects.new('L%d' % i, L)
        bpy.context.scene.collection.objects.link(ob)
        pos = Vector(centre_m + v * dist)
        ob.location = pos
        ob.rotation_euler = (Vector(centre_m) - pos).to_track_quat('-Z', 'Y').to_euler()
    if steep and face_n is not None and float(np.dot(face_n, B)) > 0.15:
        # face card: a broad dim softbox at the face's mirror direction for this view, so a
        # steep blasted face reads as mid-grey satin instead of mirroring a hot light or a void
        d = -B; r = d - 2 * np.dot(d, face_n) * face_n; r = r / np.linalg.norm(r)
        L = bpy.data.lights.new('card', 'AREA'); L.shape = 'DISK'; L.size = 0.7
        L.energy = {'light': 1.1, 'dark': 0.9}[look]
        ob = bpy.data.objects.new('card', L); bpy.context.scene.collection.objects.link(ob)
        pos = Vector(centre_m + r * 0.6); ob.location = pos
        ob.rotation_euler = (Vector(centre_m) - pos).to_track_quat('-Z', 'Y').to_euler()
        try:
            ob.visible_camera = False
        except Exception:
            pass


def holdout_swap(on, store={}):
    """Line look: route every material's surface through a Holdout (restorable)."""
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        nt = m.node_tree
        outs = [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL']
        if not outs:
            continue
        o = outs[0]
        if on:
            links = [l for l in nt.links if l.to_socket == o.inputs['Surface']]
            store[m.name] = links[0].from_socket if links else None
            ho = nt.nodes.get('HOLDOUT') or nt.nodes.new('ShaderNodeHoldout')
            ho.name = 'HOLDOUT'
            nt.links.new(ho.outputs[0], o.inputs['Surface'])
        else:
            src = store.get(m.name)
            if src is not None:
                nt.links.new(src, o.inputs['Surface'])


def setup_freestyle(scn, thickness):
    scn.render.use_freestyle = True
    scn.render.line_thickness_mode = 'ABSOLUTE'
    scn.render.line_thickness = 1.0
    vl = scn.view_layers[0]
    fs = vl.freestyle_settings
    fs.mode = 'EDITOR'
    fs.crease_angle = math.radians(128)
    fs.use_smoothness = True
    ls = fs.linesets[0] if len(fs.linesets) else fs.linesets.new('ink')
    ls.select_by_visibility = True; ls.visibility = 'VISIBLE'
    ls.select_by_edge_types = True
    ls.select_silhouette = True; ls.select_border = True; ls.select_crease = True
    ls.select_material_boundary = True; ls.select_external_contour = True
    ls.select_contour = True
    if ls.linestyle is None:
        ls.linestyle = bpy.data.linestyles.new('ink')
    st = ls.linestyle
    st.color = (0.0, 0.0, 0.0)
    st.thickness = thickness
    st.thickness_position = 'CENTER'
    st.caps = 'ROUND'
    st.chaining = 'PLAIN'; st.use_same_object = True
    for gm in list(st.geometry_modifiers):
        st.geometry_modifiers.remove(gm)
    g = st.geometry_modifiers.new('sample', 'SAMPLING'); g.sampling = 1.5
    g = st.geometry_modifiers.new('bez', 'BEZIER_CURVE'); g.error = 1.2
    return ls


def zebra_swap(on, store={}):
    """Diagnostic look: every surface shows emissive stripes of its reflection vector (horizontal
    studio strip lights), so surface-continuity kinks show up as broken stripes."""
    for m in bpy.data.materials:
        if not m.node_tree or 'MAIN' not in m.node_tree.nodes:
            continue
        nt = m.node_tree; o = nt.nodes['MAIN']
        if on:
            links = [l for l in nt.links if l.to_socket == o.inputs['Surface']]
            store[m.name] = links[0].from_socket if links else None
            tc = nt.nodes.new('ShaderNodeTexCoord'); sep = nt.nodes.new('ShaderNodeSeparateXYZ')
            nt.links.new(tc.outputs['Reflection'], sep.inputs[0])
            mul = nt.nodes.new('ShaderNodeMath'); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = 9.0
            nt.links.new(sep.outputs['Z'], mul.inputs[0])
            sn = nt.nodes.new('ShaderNodeMath'); sn.operation = 'PINGPONG'; sn.inputs[1].default_value = 0.5
            nt.links.new(mul.outputs[0], sn.inputs[0])
            gt = nt.nodes.new('ShaderNodeMath'); gt.operation = 'GREATER_THAN'; gt.inputs[1].default_value = 0.25
            nt.links.new(sn.outputs[0], gt.inputs[0])
            em = nt.nodes.new('ShaderNodeEmission'); nt.links.new(gt.outputs[0], em.inputs['Color'])
            nt.links.new(em.outputs[0], o.inputs['Surface'])
        elif store.get(m.name) is not None:
            nt.links.new(store[m.name], o.inputs['Surface'])


def curv_swap(on, store={}, scale=0.06):
    """Diagnostic look: signed mean curvature (head mesh 'curv' attribute) as emission,
    red = convex, blue = concave, white = flat; full colour at |H| >= scale (1/mm)."""
    for m in bpy.data.materials:
        if not m.node_tree or 'MAIN' not in m.node_tree.nodes:
            continue
        nt = m.node_tree; o = nt.nodes['MAIN']
        if on:
            links = [l for l in nt.links if l.to_socket == o.inputs['Surface']]
            store[m.name] = links[0].from_socket if links else None
            at = nt.nodes.new('ShaderNodeAttribute'); at.attribute_name = 'curv'
            mr = nt.nodes.new('ShaderNodeMapRange'); mr.inputs[1].default_value = -scale; mr.inputs[2].default_value = scale
            nt.links.new(at.outputs['Fac'], mr.inputs[0])
            cr = nt.nodes.new('ShaderNodeValToRGB'); r = cr.color_ramp
            r.elements[0].position = 0.0; r.elements[0].color = (0.05, 0.25, 1.0, 1)
            r.elements[1].position = 1.0; r.elements[1].color = (1.0, 0.1, 0.05, 1)
            el = r.elements.new(0.5); el.color = (1, 1, 1, 1)
            for pos in (0.46, 0.54):
                e2 = r.elements.new(pos); e2.color = (1, 1, 1, 1)
            nt.links.new(mr.outputs[0], cr.inputs[0])
            em = nt.nodes.new('ShaderNodeEmission'); nt.links.new(cr.outputs[0], em.inputs['Color'])
            nt.links.new(em.outputs[0], o.inputs['Surface'])
        elif store.get(m.name) is not None:
            nt.links.new(store[m.name], o.inputs['Surface'])


def set_id_outputs(on):
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        nodes = m.node_tree.nodes
        if 'ID' in nodes and 'MAIN' in nodes:
            nodes['ID'].is_active_output = on
            nodes['MAIN'].is_active_output = not on


def render_line(scn, f, path_black, path_white, long_px, ss=3, stroke_px=2.1, face_n=None):
    """Engraved line art from a supersampled flat ID render: region-label boundaries, depth
    steps and inked groove/score centre lines, dilated to one even stroke and box-downsampled."""
    import numpy as np
    r = scn.render; c = scn.cycles
    keep = dict(samples=c.samples, den=c.use_denoising, fw=c.filter_width, vt=scn.view_settings.view_transform,
                look=scn.view_settings.look, rx=r.resolution_x, ry=r.resolution_y, fmt=r.image_settings.file_format,
                cd=r.image_settings.color_depth, ad=c.use_adaptive_sampling)
    stroke_mm = stroke_px * f['s'] * LONG / long_px
    for m in bpy.data.materials:
        if m.node_tree and 'INKW' in m.node_tree.nodes:
            grazing = face_n is not None and abs(float(np.dot(face_n, f['B']))) < 0.5
            m.node_tree.nodes['INKW'].outputs[0].default_value = 0.0 if grazing else stroke_mm * 0.95
    set_id_outputs(True)
    clear_lights()
    c.samples = 1; c.use_adaptive_sampling = False; c.use_denoising = False; c.filter_width = 0.01
    scn.view_settings.view_transform = 'Standard'; scn.view_settings.look = 'None'
    r.resolution_x = f['rx'] * ss; r.resolution_y = f['ry'] * ss
    r.image_settings.file_format = 'OPEN_EXR'; r.image_settings.color_depth = '32'
    tmp = os.path.join(WORK, '_id_tmp.exr')
    r.filepath = tmp
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(tmp)
    W, H = im.size
    px = np.empty(W * H * 4, np.float32); im.pixels.foreach_get(px)
    bpy.data.images.remove(im)
    px = px.reshape(H, W, 4)[::-1]
    lab = np.where(px[..., 3] > 0.5, np.rint(px[..., 0] * 32).astype(np.int16), 0)
    ink = (px[..., 1] > 0.5) & (px[..., 3] > 0.5)
    dep = px[..., 2] * 1000.0  # mm
    fg = lab > 0
    del px
    e = np.zeros((H, W), bool)
    e[:, :-1] |= lab[:, :-1] != lab[:, 1:]
    e[:-1, :] |= lab[:-1, :] != lab[1:, :]
    thr = max(1.2, 6 * f['s'])
    dz = np.abs(dep[:, :-1] - dep[:, 1:]) > thr; e[:, :-1] |= dz & fg[:, :-1] & fg[:, 1:]
    dz = np.abs(dep[:-1, :] - dep[1:, :]) > thr; e[:-1, :] |= dz & fg[:-1, :] & fg[1:, :]
    del dep, dz
    # drop specks: edge pixels with almost no edge neighbours in a 7x7 window
    cs = np.pad(e.astype(np.int32), ((4, 3), (4, 3))).cumsum(0).cumsum(1)
    nb = cs[7:, 7:] - cs[:-7, 7:] - cs[7:, :-7] + cs[:-7, :-7]
    e &= nb >= 5
    del cs, nb
    rad = stroke_px * ss / 2.0
    out = np.zeros((H, W), bool)
    R = int(math.ceil(rad))
    for dy in range(-R, R + 1):
        for dx in range(-R, R + 1):
            if dx * dx + dy * dy <= rad * rad + 0.25:
                out |= np.roll(np.roll(e, dy, 0), dx, 1)
    out |= ink
    a = out.reshape(H // ss, ss, W // ss, ss).mean(axis=(1, 3)).astype(np.float32)
    h, w = a.shape
    for path, col in ((path_black, 0.0), (path_white, 1.0)):
        img = bpy.data.images.new('ink', w, h, alpha=True)
        rgba = np.empty((h, w, 4), np.float32); rgba[..., :3] = col; rgba[..., 3] = a
        img.pixels.foreach_set(rgba[::-1].ravel())
        img.filepath_raw = path; img.file_format = 'PNG'
        img.save()
        bpy.data.images.remove(img)
    set_id_outputs(False)
    c.samples = keep['samples']; c.use_denoising = keep['den']; c.filter_width = keep['fw']
    c.use_adaptive_sampling = keep['ad']
    scn.view_settings.view_transform = keep['vt']; scn.view_settings.look = keep['look']
    r.resolution_x = keep['rx']; r.resolution_y = keep['ry']
    r.image_settings.file_format = keep['fmt']; r.image_settings.color_depth = keep['cd']


def main():
    a = args()
    club = a.club
    bpy.ops.wm.open_mainfile(filepath=os.path.join(WORK, club + '.blend'))
    scn = bpy.context.scene
    meta = json.load(open(os.path.join(WORK, club + '_meta.json')))
    kind = meta['kind']
    steep = meta['loft'] >= 30.0
    views = a.views.split(',') if a.views else (['top', 'side', 'face', 'back'] if kind == 'iron' else ['top', 'side', 'face'])
    looks = a.looks.split(',')
    odir = os.path.join(OUT, club); os.makedirs(odir, exist_ok=True)
    long_px = 768 if a.preview else LONG

    objs = [o for o in scn.objects if o.type == 'MESH']
    head = scn.objects['head']
    Vall = np.vstack([world_verts(o) for o in objs if o.name != 'shaft'] +
                     [world_verts(scn.objects['shaft'])])
    Vhead = world_verts(head)
    # trim the shaft fade-out from the framing
    te = np.array(meta['shaft_end']); ax = np.array(meta['axis_dir'])
    keep = (Vall - te) @ ax < -3.0
    # the shaft lathe has rings only at its ends: frame to a ring 4 mm short of the tip
    e1 = np.cross(ax, [1.0, 0, 0]); e1 /= np.linalg.norm(e1); e2 = np.cross(ax, e1)
    ring = np.array([te - 4.0 * ax + 4.7 * (math.cos(t) * e1 + math.sin(t) * e2) for t in np.linspace(0, 2 * math.pi, 24)])
    Vfr = np.vstack([Vall[keep], ring])
    centre_m = (Vhead.mean(axis=0) / 1000.0)

    cam_data = bpy.data.cameras.new('cam'); cam_data.type = 'ORTHO'
    cam = bpy.data.objects.new('cam', cam_data); scn.collection.objects.link(cam); scn.camera = cam
    cam_data.clip_start = 0.01; cam_data.clip_end = 10.0

    setup_cycles(scn, a.samples, a.preview)
    frames = {}
    for vname in views:
        B = np.array(VIEWS[vname]['B'], float); U = np.array(VIEWS[vname]['U'], float); R = np.cross(U, B)
        pu = Vfr @ R; pv = Vfr @ U
        u0, u1, v0, v1 = pu.min(), pu.max(), pv.min(), pv.max()
        w, h = u1 - u0, v1 - v0
        mg = 0.035 * max(w, h)
        u0 -= mg; u1 += mg; v0 -= mg; v1 += mg; w += 2 * mg; h += 2 * mg
        if w >= h:
            rx = long_px; s = w / rx; ry = int(math.ceil(h / s)); dv = (ry * s - h) / 2; v0 -= dv; v1 += dv
        else:
            ry = long_px; s = h / ry; rx = int(math.ceil(w / s)); du = (rx * s - w) / 2; u0 -= du; u1 += du
        frames[vname] = dict(R=R, U=U, B=B, u0=u0, v1=v1, s=s, rx=rx, ry=ry,
                             cu=(u0 + u1) / 2, cv=(v0 + v1) / 2)

    def place_camera(f):
        c = f['R'] * f['cu'] + f['U'] * f['cv']  # mm, in the image plane through the origin
        c = c + f['B'] * (np.dot(centre_m * 1000, f['B']) + 400.0)
        cam.matrix_world = Matrix(((f['R'][0], f['U'][0], f['B'][0], c[0] / 1000),
                                   (f['R'][1], f['U'][1], f['B'][1], c[1] / 1000),
                                   (f['R'][2], f['U'][2], f['B'][2], c[2] / 1000), (0, 0, 0, 1)))
        cam_data.ortho_scale = max(f['rx'], f['ry']) * f['s'] / 1000.0
        scn.render.resolution_x = f['rx']; scn.render.resolution_y = f['ry']
        scn.render.resolution_percentage = 100

    timings = {}
    for look in looks:
        if look not in ('line', 'zebra', 'curv'):
            cfg = LIGHTS[look + '_steep'] if steep else LIGHTS[look]
            setup_world(scn, cfg['world'], cfg['rot'], soft=meta.get('crown_finish') == 'gloss')
        for vname in views:
            f = frames[vname]
            place_camera(f)
            t = time.time()
            if look == 'curv':
                curv_swap(True)
                c = scn.cycles; ks = (c.samples, c.use_denoising); c.samples = 8; c.use_denoising = False
                clear_lights()
                tag = 'curv'; path = os.path.join(odir, '%s_%s_curv%s.png' % (club, vname, a.suffix))
                scn.render.filepath = path; bpy.ops.render.render(write_still=True)
                curv_swap(False); c.samples, c.use_denoising = ks
            elif look == 'zebra':
                zebra_swap(True)
                c = scn.cycles; ks = (c.samples, c.use_denoising); c.samples = 16; c.use_denoising = False
                clear_lights()
                tag = 'zebra'; path = os.path.join(odir, '%s_%s_zebra%s.png' % (club, vname, a.suffix))
                scn.render.filepath = path; bpy.ops.render.render(write_still=True)
                zebra_swap(False); c.samples, c.use_denoising = ks
            elif look == 'line':
                pb = os.path.join(odir, '%s_%s_line-black%s.png' % (club, vname, a.suffix))
                render_line(scn, f, pb, pb.replace('line-black', 'line-white'), long_px,
                            face_n=np.array(meta['face_normal']))
                tag = 'line-black'; path = pb
            else:
                # a gloss crown mirrors the low front kicker as a blob in the top view, where it has no
                # sole band to light
                gloss_top = meta.get('crown_finish') == 'gloss' and vname == 'top'
                setup_lights(look, f['R'], f['U'], f['B'], centre_m, steep, np.array(meta['face_normal']),
                             skip=DARK_SEPARATION[:1] if gloss_top else (),
                             extra=GLOSS_TOP_DARK if gloss_top and look == 'dark' else ())
                tag = look
                path = os.path.join(odir, '%s_%s_%s%s.png' % (club, vname, tag, a.suffix))
                scn.render.filepath = path
                bpy.ops.render.render(write_still=True)
            timings['%s_%s' % (vname, tag)] = round(time.time() - t, 1)
            print('RENDER %s %.1fs' % (path, time.time() - t), flush=True)

    # anchors ----------------------------------------------------------------------------------
    for vname in views:
        f = frames[vname]
        R, U, B, s = f['R'], f['U'], f['B'], f['s']
        def px(p):
            p = np.asarray(p, float)
            return [round(float((p @ R - f['u0']) / s), 2), round(float((f['v1'] - p @ U) / s), 2)]
        def vec(d):
            d = np.asarray(d, float); x, y = d @ R, -(d @ U)
            n = math.hypot(x, y)
            return None if n < 1e-6 else [round(x / n, 5), round(y / n, 5)]
        FC = np.array(meta['face_centre']); n = np.array(meta['face_normal']); eu = np.array(meta['face_up'])
        ey = np.array([0, 1.0, 0])
        if vname == 'side':
            fp = [FC - eu * 30, FC + eu * 30]
        else:
            fp = [FC - ey * 30, FC + ey * 30]
        hp = Vhead @ R; hv = Vhead @ U
        hb = [round(float((hp.min() - f['u0']) / s), 1), round(float((f['v1'] - hv.max()) / s), 1),
              round(float((hp.max() - f['u0']) / s), 1), round(float((f['v1'] - hv.min()) / s), 1)]
        bmin, bmax = np.array(meta['body_min']), np.array(meta['body_max'])
        corners = np.array([[x, y, z] for x in (bmin[0], bmax[0]) for y in (bmin[1], bmax[1]) for z in (bmin[2], bmax[2])])
        cu_, cv_ = (corners @ R - f['u0']) / s, (f['v1'] - corners @ U) / s
        body_bb = [round(float(cu_.min()), 1), round(float(cv_.min()), 1), round(float(cu_.max()), 1), round(float(cv_.max()), 1)]
        M = [[round(float(R[0] / s), 6), round(float(R[1] / s), 6), round(float(R[2] / s), 6), round(float(-f['u0'] / s), 3)],
             [round(float(-U[0] / s), 6), round(float(-U[1] / s), 6), round(float(-U[2] / s), 6), round(float(f['v1'] / s), 3)]]
        J = dict(club=club, label=meta['label'], view=vname,
                 image=dict(width=f['rx'], height=f['ry']), mm_per_px=round(float(s), 6),
                 world_to_px=M,
                 world_note='world mm: +X target, +Y toward golfer (heel), +Z up, ground z=0; px = M @ [x,y,z,1], y down',
                 loft_deg=meta['loft'], lie_deg=meta['lie'], offset_mm=meta.get('offset'),
                 face_centre=px(FC),
                 leading_edge=dict(heel=px(meta['le_heel']), toe=px(meta['le_toe']), mid=px(meta['le_mid'])),
                 face_plane=[px(fp[0]), px(fp[1])],
                 face_normal=vec(n), face_normal_toward_viewer=bool(abs(n @ B) > 0.5),
                 shaft_axis=[px(meta['axis_point']), px(meta['shaft_end'])],
                 ground_y=(None if vname == 'top' else round(float((f['v1'] - 0.0) / s), 2)),
                 sole_contact=px(meta['contact']),
                 head_bbox=hb, body_bbox=body_bb,
                 pivot=dict(top=px(FC), side=px(meta['le_mid'])).get(vname, px(FC)))
        if vname in ('face', 'back'):
            toe = np.array([0, -1.0, 0])
            J['face_frame'] = dict(
                origin=px(FC),
                x_px_per_mm=[round(float((toe @ R) / s), 5), round(float(-(toe @ U) / s), 5)],
                y_px_per_mm=[round(float((eu @ R) / s), 5), round(float(-(eu @ U) / s), 5)],
                note='impact point px = origin + x_mm*x_px_per_mm + y_mm*y_px_per_mm; +x toward toe, '
                     '+y up the face plane (foreshortened by cos(loft) in this horizontal view)')
        # tight alpha bbox from one rendered look
        for tag in ('light', 'dark', 'line-black'):
            p = os.path.join(odir, '%s_%s_%s%s.png' % (club, vname, tag, a.suffix))
            if os.path.exists(p):
                im = bpy.data.images.load(p)
                pix = np.empty(im.size[0] * im.size[1] * 4, np.float32); im.pixels.foreach_get(pix)
                al = pix.reshape(im.size[1], im.size[0], 4)[::-1, :, 3]
                ys, xs = np.nonzero(al > 0.02)
                if len(xs):
                    J['alpha_bbox'] = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
                bpy.data.images.remove(im)
                break
        jp = os.path.join(odir, '%s_%s%s.json' % (club, vname, a.suffix))
        prev = {}
        if os.path.exists(jp):
            try:
                prev = json.load(open(jp)).get('render_seconds', {})
            except Exception:
                prev = {}
        prev.update({k[len(vname) + 1:]: v for k, v in timings.items() if k.startswith(vname + '_')})
        J['render_seconds'] = prev
        with open(os.path.join(odir, '%s_%s%s.json' % (club, vname, a.suffix)), 'w') as fh:
            json.dump(J, fh, indent=1)
    print('TIMINGS', json.dumps(timings))


main()
