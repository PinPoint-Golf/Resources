"""patch.py: the impact patch - what face tape or face spray shows after a strike (system python3).

    python3 patch.py [--sizes 20,25,30] [--default 25] [--reach 0.10]

The patch is made from the ball's own dimple layout (out/dimples.json): the ball is pressed
flat against the face around a contact point and seen straight on (orthographic projection along
the contact normal).  Inside the contact disc the land prints; each dimple leaves a hole, except
for its shallow outer rim, which a compliant tape or spray still reaches (`--reach`, the depth
in mm below the land that still marks).  Holes that cross the contact circle scallop its edge.

Outputs, in out/dimple-print/:
  patch_<d>mm.svg                 one evenodd path, fill = currentColor (tint by setting `color`)
  patch_<d>mm_ink-dark.png        dark ink, for light faces       1024 px + @256
  patch_<d>mm_ink-light.png       light ink, for dark faces       1024 px + @256
  patch_<d>mm.json                anchors
Every size shares one canvas (32 x 32 mm), so they swap without rescaling.
"""
import os, sys, json, math, argparse
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, 'out', 'dimple-print')
CANVAS_MM = 32.0
PX = 1024
UNIT = 0.01                    # mm per SVG user unit
INK_DARK = (27, 29, 33)
INK_LIGHT = (238, 236, 230)
REACH = 0.09                   # mm: tape/spray marks a dimple down to this depth below the land;
#   0.09 gives marked / apparent area = 0.50, inside the 0.38-0.52 measured with pressure film at
#   50 m/s (US 6,416,426 B1, Table 1)


def load():
    J = json.load(open(os.path.join(ROOT, 'out', 'dimples.json')))
    C = np.array([d['c'] for d in J['dimples']]); C /= np.linalg.norm(C, axis=1, keepdims=True)
    A = np.array([d['radius_mm'] for d in J['dimples']]); D = np.array([d['depth_mm'] for d in J['dimples']])
    cls = np.array([d['cls'] for d in J['dimples']])
    return J['ball_diameter_mm'] / 2, C, A, D, cls


def pick_centre(C, A, cls, Rb, max_patch_mm=30.0):
    """A large dimple with six even neighbours, far enough from the parting line that the
    largest patch never reaches it.  Deterministic."""
    clear = math.degrees(math.asin(min(1.0, (max_patch_mm / 2 + 1.0) / Rb)))
    lat = np.degrees(np.arcsin(C[:, 2]))
    ang = np.arccos(np.clip(C @ C.T, -1, 1)) * Rb + np.eye(len(C)) * 1e9
    best = None
    for i in range(len(C)):
        if cls[i] != cls.max() or lat[i] < clear:
            continue
        nn = np.sort(ang[i])[:7]
        six = nn[5] < 1.12 * nn[0] and nn[6] > 1.2 * nn[0]
        if not six:
            continue
        score = np.std(nn[:6]) + 0.01 * abs(lat[i] - 62)
        if best is None or score < best[0]:
            best = (score, i)
    return best[1]


def hole_radius(a, d, reach):
    """Arc radius (mm) at which the spherical-cap dimple is `reach` deep."""
    rho = (a * a + d * d) / (2 * d)
    z = rho - d + reach
    return math.sqrt(max(0.0, rho * rho - z * z))


def ellipses(diam, reach=REACH, centre=None):
    """Hole ellipses in the patch plane (mm, x right, y up) for a contact disc of `diam` mm."""
    Rb, C, A, D, cls = load()
    i0 = pick_centre(C, A, cls, Rb) if centre is None else centre
    k = C[i0]
    up = np.array([0, 0, 1.0]) - k[2] * k; up /= np.linalg.norm(up)
    right = np.cross(up, k)
    rc = diam / 2
    E = []
    for j in range(len(C)):
        ck = float(C[j] @ k)
        if ck <= 0.05:
            continue
        b = hole_radius(A[j], D[j], reach) / Rb          # angular radius of the hole
        cen3 = Rb * math.cos(b) * (C[j] - ck * k)
        cx, cy = float(cen3 @ right), float(cen3 @ up)
        rr = math.hypot(cx, cy)
        major = Rb * math.sin(b); minor = major * ck
        if rr - major > rc:
            continue
        rad = (cx / rr, cy / rr) if rr > 1e-9 else (1.0, 0.0)
        E.append(dict(cx=cx, cy=cy, a=major, b=minor, ux=-rad[1], uy=rad[0], j=j))  # u = tangential (major)
    return E, i0


def ell_pt(e, t):
    return (e['cx'] + e['a'] * math.cos(t) * e['ux'] - e['b'] * math.sin(t) * e['uy'],
            e['cy'] + e['a'] * math.cos(t) * e['uy'] + e['b'] * math.sin(t) * e['ux'])


def raster(E, rc, px=PX, ss=4):
    """Coverage (0..1) of the ink at px x px over the 32 mm canvas, y down."""
    W = px * ss; s = CANVAS_MM / W
    xs = (np.arange(W) + 0.5 - W / 2) * s
    X, Y = np.meshgrid(xs, -xs)
    ink = (X * X + Y * Y) <= rc * rc
    for e in E:
        x0, x1 = e['cx'] - e['a'], e['cx'] + e['a']; y0, y1 = e['cy'] - e['a'], e['cy'] + e['a']
        i0, i1 = max(0, int((x0 + CANVAS_MM / 2) / s) - 1), min(W, int((x1 + CANVAS_MM / 2) / s) + 2)
        j0, j1 = max(0, int((CANVAS_MM / 2 - y1) / s) - 1), min(W, int((CANVAS_MM / 2 - y0) / s) + 2)
        if i0 >= i1 or j0 >= j1:
            continue
        dx = X[j0:j1, i0:i1] - e['cx']; dy = Y[j0:j1, i0:i1] - e['cy']
        u = dx * e['ux'] + dy * e['uy']; v = -dx * e['uy'] + dy * e['ux']
        ink[j0:j1, i0:i1] &= (u / e['a']) ** 2 + (v / e['b']) ** 2 > 1
    return ink.reshape(px, ss, px, ss).mean(axis=(1, 3))


def svg_path(E, rc):
    """One path: the scalloped outer boundary (circle arcs + elliptical notch arcs) and every
    interior hole as a closed ellipse, for fill-rule evenodd.  Coordinates in UNIT, y down."""
    f = lambda v: ('%.1f' % (v / UNIT)).rstrip('0').rstrip('.')
    P = lambda p: '%s %s' % (f(p[0]), f(-p[1]))
    R = f(rc)
    inner, notches = [], []
    for e in E:
        ts = np.linspace(0, 2 * math.pi, 1441)
        pts = np.array([ell_pt(e, t) for t in ts])
        r = np.hypot(pts[:, 0], pts[:, 1]) - rc
        if r.max() < 0:
            inner.append(e); continue
        if r.min() > 0:
            continue
        # crossings
        cr = []
        for i in range(len(ts) - 1):
            if (r[i] < 0) != (r[i + 1] < 0):
                lo, hi = ts[i], ts[i + 1]
                for _ in range(50):
                    mid = 0.5 * (lo + hi); q = ell_pt(e, mid)
                    if (math.hypot(*q) - rc < 0) == (r[i] < 0):
                        lo = mid
                    else:
                        hi = mid
                cr.append((0.5 * (lo + hi), r[i] < 0))  # (t, was_inside_before)
        if len(cr) != 2:
            raise RuntimeError('ellipse crosses the contact circle %d times' % len(cr))
        t_in0 = [t for t, ins in cr if not ins][0]       # outside -> inside
        t_in1 = [t for t, ins in cr if ins][0]           # inside -> outside
        span = (t_in1 - t_in0) % (2 * math.pi)
        p0, p1 = ell_pt(e, t_in0), ell_pt(e, t_in1)
        # polar angles in SVG coordinates (y down): increasing = clockwise on screen = sweep 1
        a0, a1 = math.atan2(-p0[1], p0[0]), math.atan2(-p1[1], p1[0])
        d = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        if d > 0:
            pa, pb, dirn, aa, ab = p0, p1, +1, a0, a1
        else:
            pa, pb, dirn, aa, ab = p1, p0, -1, a1, a0
        # orientation of the ellipse parametrisation in SVG coordinates
        ux, uy = e['ux'], -e['uy']; vx, vy = -e['uy'], -e['ux']
        s_uv = 1 if (ux * vy - uy * vx) > 0 else -1
        sweep = 1 if dirn * s_uv > 0 else 0
        rot = math.degrees(math.atan2(uy, ux))
        notches.append(dict(aa=aa % (2 * math.pi), ab=ab % (2 * math.pi), pa=pa, pb=pb, e=e, span=span,
                            sweep=sweep, rot=rot))
    parts = []
    if not notches:
        parts.append('M %s 0 A %s %s 0 1 1 -%s 0 A %s %s 0 1 1 %s 0 Z' % (R, R, R, R, R, R, R))
    else:
        notches.sort(key=lambda n: n['aa'])
        n0 = notches[-1]
        parts.append('M %s' % P(n0['pb']))
        prev_ab = n0['ab']
        for n in notches:
            dphi = (n['aa'] - prev_ab) % (2 * math.pi)
            parts.append('A %s %s 0 %d 1 %s' % (R, R, 1 if dphi > math.pi else 0, P(n['pa'])))
            e = n['e']
            parts.append('A %s %s %.3f %d %d %s' % (f(e['a']), f(e['b']), n['rot'], 1 if n['span'] > math.pi else 0,
                                                     n['sweep'], P(n['pb'])))
            prev_ab = n['ab']
        parts[-1] += ' Z'
    for e in inner:
        rot = math.degrees(math.atan2(-e['uy'], e['ux']))
        # three 120 deg arcs: an arc between opposite ends of an axis is degenerate, and renderers
        # rescale its radii when rounding puts the end points a hair too far apart
        q = [ell_pt(e, k * 2 * math.pi / 3) for k in range(3)]
        ux, uy = e['ux'], -e['uy']; vx, vy = -e['uy'], -e['ux']
        sweep = 1 if (ux * vy - uy * vx) > 0 else 0
        arcs = ' '.join('A %s %s %.3f 0 %d %s' % (f(e['a']), f(e['b']), rot, sweep, P(q[(k + 1) % 3])) for k in range(3))
        parts.append('M %s %s Z' % (P(q[0]), arcs))
    return ' '.join(parts), len(inner), len(notches)


def write_png(cov, path, col):
    from PIL import Image
    rgba = np.zeros(cov.shape + (4,), np.uint8); rgba[..., :3] = col
    rgba[..., 3] = np.clip(cov * 255 + 0.5, 0, 255).astype(np.uint8)
    im = Image.fromarray(rgba, 'RGBA'); im.save(path, optimize=True)
    sm = im.convert('RGBa').resize((PX // 4, PX // 4), Image.LANCZOS).convert('RGBA')
    sm.save(path[:-4] + '@256.png', optimize=True)


def build(sizes, default, reach):
    os.makedirs(OUT, exist_ok=True)
    half = CANVAS_MM / 2 / UNIT
    for dmm in sizes:
        E, i0 = ellipses(dmm, reach)
        rc = dmm / 2
        d, n_in, n_notch = svg_path(E, rc)
        tag = 'patch_%gmm' % dmm
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="%gmm" height="%gmm" '
               'viewBox="%g %g %g %g" color="#1B1D21">\n'
               '  <!-- Impact patch, %g mm contact, generic dimple layout. 1 unit = %g mm, origin = ball '
               'contact centre, y down. Tint by changing color. MIT, PinPoint Golf Resources. -->\n'
               '  <path fill="currentColor" fill-rule="evenodd" d="%s"/>\n</svg>\n') % (
            CANVAS_MM, CANVAS_MM, -half, -half, 2 * half, 2 * half, dmm, UNIT, d)
        with open(os.path.join(OUT, tag + '.svg'), 'w') as fh:
            fh.write(svg)
        cov = raster(E, rc)
        write_png(cov, os.path.join(OUT, tag + '_ink-dark.png'), INK_DARK)
        write_png(cov, os.path.join(OUT, tag + '_ink-light.png'), INK_LIGHT)
        Rb, C, A, Dp, cls = load()
        centre_hole = [e for e in E if e['j'] == i0][0]
        J = dict(
            contact_diameter_mm=dmm, default=(dmm == default),
            image=dict(width=PX, height=PX), centre=[PX / 2, PX / 2], mm_per_px=CANVAS_MM / PX,
            image_256=dict(width=PX // 4, height=PX // 4, centre=[PX / 8, PX / 8], mm_per_px=CANVAS_MM / (PX // 4)),
            svg=dict(file=tag + '.svg', viewBox=[-half, -half, 2 * half, 2 * half], unit_mm=UNIT, origin='centre',
                     size_mm=[CANVAS_MM, CANVAS_MM]),
            centred_on='dimple', centre_hole_diameter_mm=round(2 * centre_hole['a'], 3),
            holes_inside=n_in, holes_on_edge=n_notch, ink_reach_mm=reach, projection='orthographic',
            marked_fraction=round(float(cov.sum() * (CANVAS_MM / PX) ** 2 / (math.pi * rc * rc)), 3),
            ball_diameter_mm=2 * Rb, contact_dimple=dict(index=int(i0), c=[round(float(x), 6) for x in C[i0]]),
            note='px: origin top left, y down; centre = the ball contact point (the middle of a dimple '
                 'hole). Same 32 mm canvas for every size. SVG: one evenodd path filled with currentColor.')
        with open(os.path.join(OUT, tag + '.json'), 'w') as fh:
            json.dump(J, fh, indent=1)
        print('%s: %d holes inside, %d on the edge, centre hole %.2f mm' % (tag, n_in, n_notch, 2 * centre_hole['a']))


# ------------------------------------------------------------------------------------- sheets
FACE_LIGHT = (212, 214, 217)
FACE_DARK = (40, 43, 48)


def _font(sz):
    for f in ('/System/Library/Fonts/Helvetica.ttc', '/Library/Fonts/Arial.ttf'):
        if os.path.exists(f):
            from PIL import ImageFont
            return ImageFont.truetype(f, sz)
    from PIL import ImageFont
    return ImageFont.load_default()


def _marker(d, cx, cy, r, col, halo):
    d.ellipse([cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2], fill=halo)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)


def sheets():
    from PIL import Image, ImageDraw
    sizes = sorted(json.load(open(p))['contact_diameter_mm'] for p in
                   [os.path.join(OUT, f) for f in os.listdir(OUT) if f.startswith('patch_') and f.endswith('.json')])
    cell = 560; pad = 28; ft = _font(30); fs = _font(22)
    W = pad + len(sizes) * (cell + pad); H = 70 + 2 * (cell + 50 + pad)
    c = Image.new('RGB', (W, H), (255, 255, 255)); d = ImageDraw.Draw(c)
    d.text((pad, 18), 'Impact patch - contact diameters %s mm, on light and dark faces (same scale; '
           'grey ring = 30 mm)' % ', '.join('%g' % s for s in sizes), fill=(30, 30, 30), font=ft)
    y = 70
    for face, ink, mk in ((FACE_LIGHT, 'ink-dark', (27, 29, 33)), (FACE_DARK, 'ink-light', (238, 236, 230))):
        x = pad
        for s in sizes:
            tile = Image.new('RGBA', (cell, cell), face + (255,))
            im = Image.open(os.path.join(OUT, 'patch_%gmm_%s.png' % (s, ink))).convert('RGBa').resize(
                (cell, cell), Image.LANCZOS).convert('RGBA')
            tile.alpha_composite(im)
            td = ImageDraw.Draw(tile)
            k = cell / CANVAS_MM; r30 = 15 * k
            td.ellipse([cell / 2 - r30, cell / 2 - r30, cell / 2 + r30, cell / 2 + r30], outline=(128, 128, 128), width=1)
            c.paste(tile.convert('RGB'), (x, y))
            d.text((x, y + cell + 8), '%g mm  (%s on %s face)' % (s, ink, 'light' if face == FACE_LIGHT else 'dark'),
                   fill=(30, 30, 30), font=fs)
            x += cell + pad
        y += cell + 50 + pad
    c.save(os.path.join(OUT, 'contact_patch.png'), optimize=True)
    driver_check()


def driver_check(dmm=25):
    """The patch at true scale on the driver face render (driver_face.json face_frame), with a
    neutral centre marker."""
    from PIL import Image, ImageDraw
    cd = os.path.join(ROOT, '..', 'clubheads', 'out', 'driver')
    J = json.load(open(os.path.join(cd, 'driver_face.json')))
    ff = J['face_frame']; o = ff['origin']
    sx = abs(ff['x_px_per_mm'][0]) * CANVAS_MM / PX; sy = abs(ff['y_px_per_mm'][1]) * CANVAS_MM / PX
    base = Image.open(os.path.join(cd, 'driver_face_light.png')).convert('RGBA')
    panels = []
    # the driver's face is dark, so the centre marker is light ink (with a dark keyline) on both
    for ink, mk, halo in (('ink-light', (238, 236, 230), (27, 29, 33)), ('ink-dark', (238, 236, 230), (27, 29, 33))):
        bg = Image.new('RGBA', base.size, (247, 246, 242, 255)); bg.alpha_composite(base)
        p = Image.open(os.path.join(OUT, 'patch_%gmm_%s.png' % (dmm, ink))).convert('RGBa')
        w, h = round(PX * sx), round(PX * sy)
        p = p.resize((w, h), Image.LANCZOS).convert('RGBA')
        bg.alpha_composite(p, (round(o[0] - w / 2), round(o[1] - h / 2)))
        _marker(ImageDraw.Draw(bg), o[0], o[1], 7, mk, halo)
        panels.append(bg.crop((280, 900, 1340, 1680)))
    pad = 20; ft = _font(26)
    W = sum(p.width for p in panels) + pad * 3; H = panels[0].height + 90
    c = Image.new('RGB', (W, H), (255, 255, 255)); d = ImageDraw.Draw(c)
    d.text((pad, 14), 'Scale check: %g mm impact patch at the driver face centre (face_frame scale, %.2f px/mm; '
           'vertical foreshortened by cos(loft)). Left: light ink, right: dark ink; light dot = centre marker (neutral ink, the app themes its own).' % (
               dmm, abs(ff['x_px_per_mm'][0])), fill=(30, 30, 30), font=_font(22))
    x = pad
    for p in panels:
        c.paste(p.convert('RGB'), (x, 70)); x += p.width + pad
    c.save(os.path.join(OUT, 'scale_check_driver_%gmm.png' % dmm), optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sizes', default='20,25,30')
    ap.add_argument('--default', type=float, default=25)
    ap.add_argument('--reach', type=float, default=REACH)
    a = ap.parse_args()
    build([float(s) for s in a.sizes.split(',')], a.default, a.reach)


if __name__ == '__main__':
    main()
