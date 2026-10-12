"""render.py: orthographic renders + anchors of the ball (Blender, headless).

    Blender -b --factory-startup --python render.py -- --views front --looks light [--preview] [--print]

Reads work/ball_mesh.npz (mesh.py), and with --print the print masks (marks.py); writes
out/ball_<view>_<look>.png.  line.py makes the line looks and the anchor JSON (pure geometry,
frame.py), sheets.py the @512 copies and sheets.
"""
import sys, os, math, json, time
import numpy as np
import bpy
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import frame, marks

WORK = os.path.join(ROOT, 'work')
OUT = os.path.join(ROOT, 'out')
# the studio HDRI is shared with the club heads (CC0, see ../clubheads/ref/SOURCE.txt)
HDRI = os.path.join(ROOT, '..', 'clubheads', 'ref', 'studio_small_08_2k.hdr')
CENTRE = np.zeros(3)


def args():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--looks', default='light,dark')
    ap.add_argument('--views', default=','.join(frame.ORDER))
    ap.add_argument('--preview', action='store_true')
    ap.add_argument('--samples', type=int, default=128)
    ap.add_argument('--mesh', default=os.path.join(WORK, 'ball_mesh.npz'))
    ap.add_argument('--suffix', default='')
    ap.add_argument('--outdir', default=OUT)
    ap.add_argument('--print', dest='with_print', action='store_true',
                    help='print the play number and alignment line (off: a plain ball)')
    return ap.parse_args(argv)


# ------------------------------------------------------------------------------------- scene
def build_mesh(path):
    Z = np.load(path)
    V, F, N = Z['V'], Z['F'], Z['N']
    me = bpy.data.meshes.new('ball')
    me.vertices.add(len(V)); me.vertices.foreach_set('co', V.astype(np.float32).ravel())
    nt = len(F)
    me.loops.add(nt * 3); me.loops.foreach_set('vertex_index', F.astype(np.int32).ravel())
    me.polygons.add(nt); me.polygons.foreach_set('loop_start', (np.arange(nt) * 3).astype(np.int32))
    me.update(calc_edges=True)
    me.polygons.foreach_set('use_smooth', np.ones(nt, bool))
    t = time.time()
    me.normals_split_custom_set_from_vertices(N.astype(np.float32))
    print('custom normals %.1fs' % (time.time() - t), flush=True)
    me.validate(verbose=False)
    ob = bpy.data.objects.new('ball', me)
    bpy.context.scene.collection.objects.link(ob)
    ob.scale = (0.001, 0.001, 0.001)          # mesh in mm, scene in m
    return ob


def _in(node, name):
    for s in node.inputs:
        if s.name == name and s.enabled:
            return s
    for s in node.inputs:
        if s.name == name:
            return s
    raise KeyError(name)


def material(with_print=False):
    """Glossy white cover: white paint (diffuse with a little subsurface) under a clear coat;
    the optional print is ink between the paint and the coat."""
    m = bpy.data.materials.new('cover'); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear(); L = nt.links
    def node(t, **kw):
        n = nt.nodes.new(t)
        for k, v in kw.items():
            setattr(n, k, v)
        return n
    def math_(op, a, b=None):
        n = node('ShaderNodeMath', operation=op)
        for i, x in enumerate((a, b)):
            if x is None:
                continue
            if isinstance(x, (int, float)):
                n.inputs[i].default_value = x
            else:
                L.new(x, n.inputs[i])
        return n.outputs[0]
    tc = node('ShaderNodeTexCoord')
    nrm = node('ShaderNodeVectorMath', operation='NORMALIZE'); L.new(tc.outputs['Object'], nrm.inputs[0])
    sep = node('ShaderNodeSeparateXYZ'); L.new(nrm.outputs['Vector'], sep.inputs[0])
    ux, uy, uz = sep.outputs['X'], sep.outputs['Y'], sep.outputs['Z']
    R = marks.R_BALL

    def tex(path, u, v, ext):
        u0, u1, v0, v1 = ext
        cu = math_('DIVIDE', math_('SUBTRACT', u, u0), u1 - u0)
        cv = math_('DIVIDE', math_('SUBTRACT', v, v0), v1 - v0)
        cc = node('ShaderNodeCombineXYZ'); L.new(cu, cc.inputs[0]); L.new(cv, cc.inputs[1])
        im = node('ShaderNodeTexImage'); im.image = bpy.data.images.load(path, check_existing=True)
        im.image.colorspace_settings.name = 'Non-Color'
        im.interpolation = 'Cubic'; im.extension = 'CLIP'
        L.new(cc.outputs[0], im.inputs['Vector'])
        return im.outputs['Color']
    def dot3(e, k=1.0):  # k * (u . e)
        d = math_('ADD', math_('ADD', math_('MULTIPLY', ux, float(e[0])), math_('MULTIPLY', uy, float(e[1]))),
                  math_('MULTIPLY', uz, float(e[2])))
        return math_('MULTIPLY', d, k)
    if with_print:
        num_png, line_png = marks.masks()
        # number: orthographic chart about its axis
        n_ink = tex(num_png, dot3(marks.NUMBER_RIGHT, R), dot3(marks.NUMBER_UP, R), marks.NUMBER_EXT)
        n_ink = math_('MULTIPLY', n_ink, math_('GREATER_THAN', dot3(marks.NUMBER_AXIS), 0.2))
        # line: longitude / latitude chart along the parting line
        lon = math_('ARCTAN2', uy, ux); lat = math_('ARCSINE', uz)
        l_ink = tex(line_png, math_('MULTIPLY', lon, R), math_('MULTIPLY', lat, R), marks.LINE_EXT)
        l_ink = math_('MULTIPLY', l_ink, math_('GREATER_THAN', ux, 0.0))
        ink = math_('MAXIMUM', n_ink, l_ink)
    else:
        ink = math_('MULTIPLY', ux, 0.0)          # no print

    mix = node('ShaderNodeMix', data_type='RGBA')
    L.new(ink, mix.inputs['Factor'])
    for s in mix.inputs:
        if s.name == 'A' and s.type == 'RGBA':
            s.default_value = (0.86, 0.86, 0.845, 1)     # white paint (linear)
        if s.name == 'B' and s.type == 'RGBA':
            s.default_value = (0.012, 0.012, 0.013, 1)   # black ink
    col = [o for o in mix.outputs if o.type == 'RGBA'][0]
    b = node('ShaderNodeBsdfPrincipled')
    L.new(col, _in(b, 'Base Color'))
    _in(b, 'Roughness').default_value = 0.42
    _in(b, 'Specular IOR Level').default_value = 0.5
    try:
        _in(b, 'Subsurface Weight').default_value = 0.12
        _in(b, 'Subsurface Radius').default_value = (1.0, 0.9, 0.8)
        _in(b, 'Subsurface Scale').default_value = 0.0004
        L.new(math_('SUBTRACT', 0.12, math_('MULTIPLY', ink, 0.12)), _in(b, 'Subsurface Weight'))
    except KeyError:
        pass
    _in(b, 'Coat Weight').default_value = 1.0
    _in(b, 'Coat Roughness').default_value = 0.035
    _in(b, 'Coat IOR').default_value = 1.5
    o = node('ShaderNodeOutputMaterial'); L.new(b.outputs[0], o.inputs['Surface'])
    return m


def setup_cycles(scn, samples, preview):
    scn.render.engine = 'CYCLES'
    c = scn.cycles
    c.device = 'CPU'
    c.samples = 24 if preview else samples
    c.use_adaptive_sampling = True; c.adaptive_threshold = 0.01
    c.use_denoising = True
    for k, v in (('denoiser', 'OPENIMAGEDENOISE'), ('denoising_quality', 'BALANCED'),
                 ('denoising_prefilter', 'FAST'), ('denoising_input_passes', 'RGB_ALBEDO_NORMAL')):
        try:
            setattr(c, k, v)
        except Exception as e:
            print('denoise opt', k, e)
    c.max_bounces = 10; c.glossy_bounces = 6; c.diffuse_bounces = 3; c.transparent_max_bounces = 8
    c.filter_width = 1.4
    c.use_auto_tile = True; c.tile_size = 512
    scn.render.film_transparent = True
    vs = scn.view_settings
    vs.view_transform = 'AgX'
    for lk in ('AgX - Medium High Contrast', 'Medium High Contrast'):
        try:
            vs.look = lk; break
        except Exception:
            pass
    im = scn.render.image_settings
    im.file_format = 'PNG'; im.color_mode = 'RGBA'; im.color_depth = '8'; im.compression = 15
    scn.render.use_stamp = False          # no burnt-in stamp
    for k in dir(scn.render):            # and no metadata chunks (file path, date, render stats)
        if k.startswith('use_stamp_'):
            try:
                setattr(scn.render, k, False)
            except Exception:
                pass


def setup_world(scn, strength, rot_z, cam_rot=None):
    """HDRI environment, held fixed relative to the camera (cam_rot = camera rotation matrix) so
    every view of the ball gets the same studio."""
    w = bpy.data.worlds.new('studio'); scn.world = w
    w.use_nodes = True
    nt = w.node_tree; nt.nodes.clear()
    tc = nt.nodes.new('ShaderNodeTexCoord'); mp = nt.nodes.new('ShaderNodeMapping')
    base = Matrix.Rotation(math.radians(rot_z), 3, 'Z')
    # every view sees the studio the way the side view does: lookup = base @ R_side @ R_cam^T @ dir
    R_side = Matrix(((0, 0, 1), (1, 0, 0), (0, 1, 0)))
    M = base @ R_side @ cam_rot.transposed() if cam_rot is not None else base
    mp.inputs['Rotation'].default_value = M.to_euler('XYZ')
    env = nt.nodes.new('ShaderNodeTexEnvironment')
    env.image = bpy.data.images.load(os.path.normpath(HDRI), check_existing=True)
    bg = nt.nodes.new('ShaderNodeBackground'); bg.inputs['Strength'].default_value = strength
    out = nt.nodes.new('ShaderNodeOutputWorld')
    nt.links.new(tc.outputs['Generated'], mp.inputs['Vector'])
    nt.links.new(mp.outputs[0], env.inputs['Vector'])
    nt.links.new(env.outputs['Color'], bg.inputs['Color'])
    nt.links.new(bg.outputs[0], out.inputs['Surface'])


# Lights in camera space: (right, up, toward-camera) direction, distance m, disk size m, power W,
# colour, and which rays see it ('both', 'diffuse' or 'glossy').  Scaled for a 43 mm ball at 0.3 m.
# The shading and the clear-coat highlight are lit separately, the usual product-shot split: a
# diffuse key close to the lens models the dimples and lets the limb fall off, and a glossy-only
# softbox further up and left puts the highlight clear of the number and the line.
# Light look (white ball on near-white #F7F6F2): no back light, a dim world, exposure -0.45 EV,
# so every part of the silhouette keeps dL* >= 12 against the paper.
# Dark look (white ball on #15171A): rims from behind left, right, above and below.
KEY = ((-0.24, 0.28, 0.93), 0.30, 0.20, 3.6, (1.0, 0.985, 0.97), 'diffuse')
SPEC = ((-0.60, 0.62, 0.50), 0.30, 0.10, 3.0, (1.0, 1.0, 1.0), 'glossy')
LIGHTS = {
    'light': dict(world=0.06, rot=250, exposure=-0.45, lights=[
        KEY, SPEC,
        ((0.55, -0.05, 0.83), 0.30, 0.16, 0.9, (0.96, 0.98, 1.0), 'diffuse'),   # fill, right
        ((0.05, -0.50, 0.86), 0.30, 0.20, 0.5, (1.0, 1.0, 1.0), 'diffuse'),     # low front bounce
    ]),
    'dark': dict(world=0.08, rot=250, exposure=-0.55, lights=[
        KEY, SPEC,
        ((0.55, -0.05, 0.83), 0.30, 0.16, 0.6, (0.96, 0.98, 1.0), 'diffuse'),
        ((-1.00, 0.25, -0.70), 0.28, 0.05, 1.6, (0.92, 0.96, 1.0), 'both'),     # rim left
        ((1.00, 0.30, -0.70), 0.28, 0.05, 1.6, (1.0, 0.97, 0.94), 'both'),      # rim right
        ((0.00, -1.00, -0.55), 0.28, 0.05, 1.2, (1.0, 1.0, 1.0), 'both'),       # rim below
        ((0.05, 1.00, -0.60), 0.28, 0.07, 0.8, (1.0, 1.0, 1.0), 'diffuse'),     # rim above (diffuse: keeps glare off the number)
    ]),
}


def setup_lights(look, v):
    for ob in list(bpy.data.objects):
        if ob.type == 'LIGHT':
            bpy.data.objects.remove(ob)
    for i, (d, dist, size, power, col, rays) in enumerate(LIGHTS[look]['lights']):
        w = d[0] * v['R'] + d[1] * v['U'] + d[2] * v['B']; w = w / np.linalg.norm(w)
        Ld = bpy.data.lights.new('L%d' % i, 'AREA'); Ld.shape = 'DISK'; Ld.size = size; Ld.energy = power; Ld.color = col
        ob = bpy.data.objects.new('L%d' % i, Ld); bpy.context.scene.collection.objects.link(ob)
        pos = Vector(CENTRE + w * dist); ob.location = pos
        ob.rotation_euler = (Vector(CENTRE) - pos).to_track_quat('-Z', 'Y').to_euler()
        ob.visible_diffuse = rays in ('both', 'diffuse')
        ob.visible_glossy = rays in ('both', 'glossy')


def main():
    a = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    t0 = time.time()
    ob = build_mesh(a.mesh)
    ob.data.materials.append(material(a.with_print))
    print('scene %.1fs' % (time.time() - t0), flush=True)
    long_px = 768 if a.preview else frame.LONG
    s = frame.scale(long_px)
    cam_d = bpy.data.cameras.new('cam'); cam_d.type = 'ORTHO'
    cam = bpy.data.objects.new('cam', cam_d); scn.collection.objects.link(cam); scn.camera = cam
    cam_d.clip_start = 0.01; cam_d.clip_end = 2.0; cam_d.ortho_scale = long_px * s / 1000.0
    scn.render.resolution_x = scn.render.resolution_y = long_px; scn.render.resolution_percentage = 100
    setup_cycles(scn, a.samples, a.preview)
    os.makedirs(a.outdir, exist_ok=True)
    for look in a.looks.split(','):
        for vname in a.views.split(','):
            v = frame.VIEWS[vname]
            cam_rot = Matrix([[v['R'][i], v['U'][i], v['B'][i]] for i in range(3)])
            setup_world(scn, LIGHTS[look]['world'], LIGHTS[look]['rot'], cam_rot)
            scn.view_settings.exposure = LIGHTS[look].get('exposure', 0.0)
            c = v['B'] * 0.4
            R_, U_, B_ = v['R'], v['U'], v['B']
            cam.matrix_world = Matrix(((R_[0], U_[0], B_[0], c[0]), (R_[1], U_[1], B_[1], c[1]),
                                       (R_[2], U_[2], B_[2], c[2]), (0, 0, 0, 1)))
            setup_lights(look, v)
            path = os.path.join(a.outdir, 'ball_%s_%s%s.png' % (vname, look, a.suffix))
            scn.render.filepath = path
            t = time.time()
            bpy.ops.render.render(write_still=True)
            print('RENDER %s %.1fs' % (os.path.basename(path), time.time() - t), flush=True)


main()
