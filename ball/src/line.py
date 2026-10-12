"""line.py: the line looks of the ball, drawn from the analytic geometry, and the anchor JSON
(system python3).

    python3 line.py [--views front,side,three-quarter] [--long 2048] [--print]

The ball is a sphere and every dimple rim is a small circle on it, so the line art is drawn
exactly instead of being traced from a render: the silhouette circle, each visible dimple rim
projected orthographically (an ellipse), and the print (number and alignment line) filled from
the same masks the renders use (only with --print).  Drawn at 3x and box-downsampled.

Two weights:
  line-black / line-white            2.1 px outline, 1.6 px rims at 2048 px (as the club heads)
  line-bold-black / line-bold-white  6 px outline, 4 px rims at 2048 px, for panel sizes
                                     (about 1.5 / 1 px at 512 px)
Rims fade out toward the limb, where foreshortened dimples would pack into a grey band.
"""
import os, sys, json, math, argparse
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import frame, marks

OUT = os.path.join(ROOT, 'out')
WEIGHTS = {
    'line': dict(outline=2.1, rim=1.6, cos_full=0.30, cos_cut=0.14),
    'line-bold': dict(outline=6.0, rim=4.0, cos_full=0.45, cos_cut=0.28),
}


def load_layout():
    J = json.load(open(os.path.join(OUT, 'dimples.json')))
    C = np.array([d['c'] for d in J['dimples']]); C /= np.linalg.norm(C, axis=1, keepdims=True)
    A = np.array([d['radius_mm'] for d in J['dimples']])
    return C, A


def ink_mask(v, long_px, ss):
    """Print coverage per pixel at ss x resolution (float 0..1)."""
    from PIL import Image as I
    nm = np.asarray(I.open(os.path.join(ROOT, 'work', 'mark_number.png')), np.float32) / 255
    lm = np.asarray(I.open(os.path.join(ROOT, 'work', 'mark_line.png')), np.float32) / 255
    W = long_px * ss; s = frame.scale(long_px) / ss
    out = np.zeros((W, W), np.float32)
    xs = (np.arange(W) + 0.5 - W / 2) * s
    for y0 in range(0, W, 512):
        ys = -(np.arange(y0, min(W, y0 + 512)) + 0.5 - W / 2) * s
        X, Y = np.meshgrid(xs, ys)
        r2 = (X * X + Y * Y) / (marks.R_BALL ** 2)
        inside = r2 < 1
        Zc = np.sqrt(np.clip(1 - r2, 0, 1))
        U = (X[..., None] * v['R'] + Y[..., None] * v['U']) / marks.R_BALL + Zc[..., None] * v['B']
        a = np.zeros(X.shape, np.float32)
        u, w, ok = marks.number_uv(U)
        a = np.maximum(a, marks.sample(nm, marks.NUMBER_EXT, marks.NUMBER_PX, u, w) * ok)
        u, w, ok = marks.line_uv(U)
        a = np.maximum(a, marks.sample(lm, marks.LINE_EXT, marks.LINE_PX, u, w) * ok)
        out[y0:y0 + X.shape[0]] = a * inside
    return out


def draw(vname, weight, long_px=frame.LONG, ss=3, with_print=False):
    v = frame.VIEWS[vname]; Wt = WEIGHTS[weight]
    W = long_px * ss; s = frame.scale(long_px) / ss
    C, A = load_layout()
    img = Image.new('L', (W, W), 0); d = ImageDraw.Draw(img)
    cx = cy = W / 2; rp = marks.R_BALL / s
    ow = Wt['outline'] * ss
    d.ellipse([cx - rp + ow / 2, cy - rp + ow / 2, cx + rp - ow / 2, cy + rp - ow / 2], outline=255, width=int(round(ow)))
    # dimple rims, weighted by how squarely they face the camera
    a_ = np.where(np.abs(C[:, 2:3]) < 0.9, [[0, 0, 1.0]], [[1.0, 0, 0]])
    e1 = np.cross(C, a_); e1 /= np.linalg.norm(e1, axis=1, keepdims=True); e2 = np.cross(C, e1)
    t = np.linspace(0, 2 * math.pi, 241)
    layers = {}
    for i in range(len(C)):
        cosv = float(C[i] @ v['B'])
        if cosv < Wt['cos_cut']:
            continue
        f = min(1.0, (cosv - Wt['cos_cut']) / (Wt['cos_full'] - Wt['cos_cut']))
        g = A[i] / marks.R_BALL
        P = (math.cos(g) * C[i][None] + math.sin(g) * (np.cos(t)[:, None] * e1[i] + np.sin(t)[:, None] * e2[i])) * marks.R_BALL
        px = cx + (P @ v['R']) / s; py = cy - (P @ v['U']) / s
        level = int(round(f * 8))  # draw in 9 grey levels, later max-combined
        layers.setdefault(level, []).append(list(zip(px.tolist(), py.tolist())))
    rim = np.zeros((W, W), np.float32)
    rw = int(round(Wt['rim'] * ss))
    for level, polys in layers.items():
        if level == 0:
            continue
        L = Image.new('L', (W, W), 0); dl = ImageDraw.Draw(L)
        for pts in polys:
            dl.line(pts, fill=255, width=rw, joint='curve')
        rim = np.maximum(rim, np.asarray(L, np.float32) / 255 * (level / 8))
    a = np.maximum(np.asarray(img, np.float32) / 255, rim)
    if with_print:
        a = np.maximum(a, ink_mask(v, long_px, ss))
    a = a.reshape(long_px, ss, long_px, ss).mean(axis=(1, 3))
    return a


def save(a, path, col):
    rgba = np.zeros(a.shape + (4,), np.uint8)
    rgba[..., :3] = col; rgba[..., 3] = np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(rgba, 'RGBA').save(path, optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--views', default=','.join(frame.ORDER))
    ap.add_argument('--weights', default='line,line-bold')
    ap.add_argument('--long', type=int, default=frame.LONG)
    ap.add_argument('--outdir', default=OUT)
    ap.add_argument('--print', dest='with_print', action='store_true',
                    help='draw the play number and alignment line (off: a plain ball)')
    a = ap.parse_args()
    for vn in a.views.split(','):
        with open(os.path.join(a.outdir, 'ball_%s.json' % vn), 'w') as fh:
            json.dump(frame.anchors(vn, a.long, a.with_print), fh, indent=1)
        for w in a.weights.split(','):
            al = draw(vn, w, a.long, with_print=a.with_print)
            for ink, col in (('black', (0, 0, 0)), ('white', (255, 255, 255))):
                p = os.path.join(a.outdir, 'ball_%s_%s-%s.png' % (vn, w, ink))
                save(al, p, col)
            print('line', vn, w)


if __name__ == '__main__':
    main()
