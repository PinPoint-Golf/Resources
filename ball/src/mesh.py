"""mesh.py: the dimpled ball surface as a conforming triangle mesh (system python3: numpy + scipy).

    python3 mesh.py [--layout ../out/dimples.json] [--out ../work/ball_mesh.npz] [--scale 1.0]

Why a mesh and not an SDF: a dimple is only 0.24-0.26 mm deep and its rim is the detail that
reads, so an SDF would need voxels of about 0.01 mm to keep the rim crisp (a 4000^3 grid).
Here every vertex sits exactly on the analytic surface instead:
  * each dimple gets concentric rings of vertices around its centre, coarse on the floor and
    packed at 0.012 mm across a 0.1 mm-wide rim fillet, so the rim is a smooth circle of
    vertices rather than a staircase;
  * the land between dimples is filled with an even Fibonacci point set;
  * all points (as unit vectors) are triangulated by their convex hull, which on a sphere is the
    spherical Delaunay triangulation, and then pushed to radius R - depth(direction);
  * per-vertex normals are the analytic normals of that radial surface, so shading has no
    facets anywhere.
Depth profile: a spherical cap of depth d and rim radius a, joined to the land by a polynomial
smooth-max of width k (a soft 0.04 mm edge, the way paint and clear coat round a moulded rim).
"""
import os, json, math, time, argparse
import numpy as np
from scipy.spatial import ConvexHull, cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
K_EDGE = 0.010    # mm of depth: rim smooth-max width (about 0.04 mm of arc)


def tangent_basis(c):
    a = np.where(np.abs(c[:, 2:3]) < 0.9, np.array([[0, 0, 1.0]]), np.array([[1.0, 0, 0]]))
    e1 = np.cross(c, a); e1 /= np.linalg.norm(e1, axis=1, keepdims=True)
    e2 = np.cross(c, e1)
    return e1, e2


def cap_depth(s, a, d):
    """Spherical-cap depth (mm, + into the ball) at arc distance s from the dimple centre, and
    its derivative d(depth)/ds.  Negative outside the rim (the smooth-max clips it)."""
    rho = (a * a + d * d) / (2 * d)
    s = np.minimum(s, 0.999 * rho)
    q = np.sqrt(rho * rho - s * s)
    return d - (rho - q), -s / q


def smax0(x, dx, k=K_EDGE):
    """Polynomial smooth max(x, 0) and its derivative."""
    h = np.clip((k - np.abs(x)) / k, 0, 1)
    m = np.maximum(x, 0)
    y = m + h * h * k / 4
    dm = (x > 0).astype(float)
    dh = np.where(np.abs(x) < k, -np.sign(x) / k, 0.0)
    dy = dm + 2 * h * dh * k / 4
    return y, dy * dx


def depth_field(U, C, A, D, Rb, tree):
    """Depth (mm) and its surface gradient direction for unit vectors U.  Takes the deepest of
    the 3 nearest dimples (the fillets of neighbours never overlap: land >= 0.1 mm)."""
    _, idx = tree.query(U, k=3)
    best = np.zeros(len(U)); slope = np.zeros(len(U)); sdir = np.zeros_like(U)
    for j in range(3):
        i = idx[:, j]
        c = C[i]
        cosang = np.clip((U * c).sum(1), -1, 1)
        ang = np.arccos(cosang)
        s = ang * Rb
        x, dx = cap_depth(s, A[i], D[i])
        y, dy = smax0(x, dx)
        t = c - U * cosang[:, None]           # toward the centre, tangent
        tn = np.linalg.norm(t, axis=1, keepdims=True)
        away = -t / np.maximum(tn, 1e-12)
        take = y > best
        best = np.where(take, y, best); slope = np.where(take, dy, slope)
        sdir = np.where(take[:, None], away, sdir)
    return best, slope, sdir


def build(layout, scale=1.0):
    J = json.load(open(layout))
    Rb = J['ball_diameter_mm'] / 2
    C = np.array([d['c'] for d in J['dimples']]); C /= np.linalg.norm(C, axis=1, keepdims=True)
    A = np.array([d['radius_mm'] for d in J['dimples']]); D = np.array([d['depth_mm'] for d in J['dimples']])
    e1s, e2s = tangent_basis(C)
    ds_in, ds_rim, ds_land = 0.085 * scale, 0.030 * scale, 0.085 * scale
    rim_half, rim_step = 0.06, 0.012 * scale
    pts = []
    for i in range(len(C)):
        a = A[i]
        rings = list(np.arange(0.0, a - rim_half, ds_in)) + list(np.arange(a - rim_half, a + rim_half + 1e-9, rim_step))
        for kr, s in enumerate(rings):
            if s < 1e-9:
                pts.append(C[i][None]); continue
            n = max(6, int(math.ceil(2 * math.pi * s / (ds_in if s < a - rim_half else ds_rim))))
            t = (np.arange(n) + 0.5 * (kr % 2)) * 2 * math.pi / n + 0.37 * i
            g = s / Rb
            P = math.cos(g) * C[i][None] + math.sin(g) * (np.cos(t)[:, None] * e1s[i] + np.sin(t)[:, None] * e2s[i])
            pts.append(P)
    Pd = np.vstack(pts)
    # land: Fibonacci sphere, minus everything inside rim + margin of any dimple
    area = 4 * math.pi * Rb * Rb
    N = int(area / (ds_land * ds_land * 0.866))
    k = np.arange(N) + 0.5
    z = 1 - 2 * k / N; r = np.sqrt(1 - z * z); ph = math.pi * (3 - math.sqrt(5)) * k
    L = np.stack([r * np.cos(ph), r * np.sin(ph), z], 1)
    tree = cKDTree(C)
    dd, ii = tree.query(L, k=3)
    keep = np.ones(N, bool)
    for j in range(3):
        ang = np.arccos(np.clip((L * C[ii[:, j]]).sum(1), -1, 1)) * Rb
        keep &= ang > A[ii[:, j]] + rim_half + 0.5 * ds_land
    L = L[keep]
    U = np.vstack([Pd, L])
    U /= np.linalg.norm(U, axis=1, keepdims=True)
    print('points: dimples %d, land %d, total %d' % (len(Pd), len(L), len(U)), flush=True)
    t0 = time.time()
    hull = ConvexHull(U)
    F = hull.simplices.astype(np.int32)
    print('hull %.1fs, %d triangles' % (time.time() - t0, len(F)), flush=True)
    # orient outward
    a_, b_, c_ = U[F[:, 0]], U[F[:, 1]], U[F[:, 2]]
    flip = (np.cross(b_ - a_, c_ - a_) * (a_ + b_ + c_)).sum(1) < 0
    F[flip] = F[flip][:, ::-1]
    # unreferenced points (coplanar duplicates) are harmless; report
    used = np.zeros(len(U), bool); used[F.ravel()] = True
    dep, slope, sdir = depth_field(U, C, A, D, Rb, tree)
    rad = Rb - dep
    V = U * rad[:, None]
    # analytic normal of x = r(u) u: n ~ u - grad_S r / r, grad_S r = -slope * Rb * sdir
    Nn = U + (slope * Rb / rad)[:, None] * sdir
    Nn /= np.linalg.norm(Nn, axis=1, keepdims=True)
    # mean edge length check
    e = np.linalg.norm(V[F[:, 0]] - V[F[:, 1]], axis=1)
    print('edges: median %.3f mm, max %.3f mm; unused points %d; depth max %.3f' % (np.median(e), e.max(), (~used).sum(), dep.max()))
    return V.astype(np.float32), F, Nn.astype(np.float32), dep.astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--layout', default=os.path.join(ROOT, 'out', 'dimples.json'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'work', 'ball_mesh.npz'))
    ap.add_argument('--scale', type=float, default=1.0, help='point spacing multiplier (2 = quick preview)')
    a = ap.parse_args()
    V, F, N, dep = build(a.layout, a.scale)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    np.savez(a.out, V=V, F=F, N=N, depth=dep)
    print('wrote %s (%.0f MB)' % (os.path.basename(a.out), os.path.getsize(a.out) / 1e6))


if __name__ == '__main__':
    main()
