"""layout.py: the generic dimple layout shared by the ball and the impact patch (numpy only).

    python3 layout.py [--freq 6] [--out ../out/dimples.json]

Recipe (our own, no commercial pattern is copied):
  1. an icosahedron with a vertex on each pole, faces subdivided at frequency `freq` (class I
     geodesic), points pushed onto the sphere;
  2. the northern hemisphere is kept; the southern one is its mirror image turned 36 deg about
     the pole axis, so the two halves interleave and the equator stays a dimple-free great
     circle (the parting line of the mould);
  3. a short relaxation (soft repulsion on the sphere, the southern copy acting through the
     symmetry) evens the spacing where the geodesic net meets the parting line;
  4. every dimple is grown to the largest radius its neighbours and the parting line allow, and
     the radii are snapped down to three sizes chosen to maximise surface coverage.

Ball frame: +Z is the pole, the parting line is z = 0.  (The optional print in marks.py puts the
play number at latitude 60, longitude 28 deg and the alignment line along the parting line,
centred on +X.)
"""
import json, math, os, argparse
import numpy as np

R_BALL = 42.67 / 2.0           # mm
SEAM_HALF = 0.42               # mm of land each side of the parting line, to the dimple rim
LAND_MIN = 0.10               # mm, narrowest land between two dimple rims (arc)
DEPTH = {0: 0.24, 1: 0.25, 2: 0.26}  # mm, cap depth by size class (small, medium, large)
ROT_SOUTH = math.radians(36.0)


def icosahedron():
    t = math.atan(0.5)  # latitude of the two pentagonal rings
    V = [(0, 0, 1)]
    for k in range(5):
        a = 2 * math.pi * k / 5
        V.append((math.cos(t) * math.cos(a), math.cos(t) * math.sin(a), math.sin(t)))
    for k in range(5):
        a = 2 * math.pi * (k + 0.5) / 5
        V.append((math.cos(t) * math.cos(a), math.cos(t) * math.sin(a), -math.sin(t)))
    V.append((0, 0, -1))
    V = np.array(V, float)
    F = []
    for k in range(5):
        a, b = 1 + k, 1 + (k + 1) % 5
        c, d = 6 + k, 6 + (k + 1) % 5
        F += [(0, a, b), (a, c, b), (b, c, d), (c, 11, d)]
    return V, F


def geodesic(freq):
    V, F = icosahedron()
    pts = []
    for (i, j, k) in F:
        A, B, C = V[i], V[j], V[k]
        for u in range(freq + 1):
            for v in range(freq + 1 - u):
                w = freq - u - v
                p = (u * A + v * B + w * C) / freq
                pts.append(p / np.linalg.norm(p))
    P = np.array(pts)
    # merge duplicates on shared edges / vertices
    key = np.round(P * 1e6).astype(np.int64)
    _, idx = np.unique(key, axis=0, return_index=True)
    return P[np.sort(idx)]


def south_of(N):
    c, s = math.cos(ROT_SOUTH), math.sin(ROT_SOUTH)
    S = N.copy(); S[:, 2] *= -1
    x, y = S[:, 0].copy(), S[:, 1].copy()
    S[:, 0] = c * x - s * y; S[:, 1] = s * x + c * y
    return S


def arc(a, b):
    return np.arccos(np.clip(a @ b.T, -1, 1)) * R_BALL


def relax(N, iters=400, step=0.02, r_seam=2.3):
    """Soft repulsion among all dimples (south = symmetric copy) plus a wall that keeps centres
    at least r_seam + SEAM_HALF of arc from the parting line.  Pole dimple stays put."""
    N = N.copy()
    pole = np.argmax(N[:, 2])
    lat_min = (r_seam + SEAM_HALF) / R_BALL
    for it in range(iters):
        A = np.vstack([N, south_of(N)])
        D = N[:, None, :] - A[None, :, :]
        d = np.linalg.norm(D, axis=2) + np.eye(len(N), len(A)) * 1e9
        nn = np.sort(d, axis=1)[:, :6].mean()
        w = np.exp(-(d / nn) ** 2 * 3.0)  # short range
        F = (D / d[..., None] * (w / d)[..., None]).sum(axis=1)
        lat = np.arcsin(np.clip(N[:, 2], -1, 1))
        push = np.clip(lat_min - lat, 0, None)
        F[:, 2] += push * 40.0
        F -= (F * N).sum(1, keepdims=True) * N          # tangential
        F[pole] = 0
        N = N + step * nn * F / (np.abs(F).max() + 1e-12) * (1 - it / iters)
        N /= np.linalg.norm(N, axis=1, keepdims=True)
    return N


def grow(P, lat_lim):
    """Largest radii with r_i + r_j + LAND_MIN <= arc_ij and r_i <= lat_lim_i."""
    D = arc(P, P) + np.eye(len(P)) * 1e9
    r = np.minimum(lat_lim, (D.min(1) - LAND_MIN) / 2)
    for _ in range(200):
        r_new = np.minimum(lat_lim, (D - LAND_MIN - r[None, :]).min(1))
        r = 0.5 * r + 0.5 * np.minimum(r_new, r + 0.02)
    return r, D


def quantise(rmax, D, lat_lim, n_sizes=3):
    """Pick n_sizes radii maximising coverage, each dimple taking the largest size it can hold
    given its already-sized neighbours."""
    lo, hi = np.percentile(rmax, 2), rmax.max()
    grid = np.round(np.arange(math.floor(lo * 50) / 50, hi + 1e-9, 0.02), 3)
    best = None
    import itertools
    for sizes in itertools.combinations(grid, n_sizes):
        sizes = np.array(sizes)
        if sizes[0] > rmax.min() + 1e-9:
            continue
        cls = np.searchsorted(sizes, rmax + 1e-9) - 1
        r = sizes[cls]
        # second pass: grow into slack left by snapped neighbours
        order = np.argsort(-rmax)
        for i in order:
            cap = min(lat_lim[i], (D[i] - LAND_MIN - r).min())
            k = np.searchsorted(sizes, cap + 1e-9) - 1
            if k > cls[i]:
                cls[i] = k; r[i] = sizes[k]
        cov = (2 * math.pi * R_BALL ** 2 * (1 - np.cos(r / R_BALL))).sum() / (4 * math.pi * R_BALL ** 2)
        if best is None or cov > best[0]:
            best = (cov, sizes, cls.copy(), r.copy())
    return best


def build(freq=6, relax_iters=400):
    G = geodesic(freq)
    N = G[G[:, 2] > 1e-6]
    N = relax(N, iters=relax_iters)
    P = np.vstack([N, south_of(N)])
    lat_lim = np.abs(np.arcsin(np.clip(P[:, 2], -1, 1))) * R_BALL - SEAM_HALF
    rmax, D = grow(P, lat_lim)
    cov, sizes, cls, r = quantise(rmax, D, lat_lim)
    # land check
    gap = D - r[:, None] - r[None, :]
    seam = lat_lim - r
    return dict(P=P, r=r, cls=cls, sizes=sizes, coverage=cov, min_land=float(gap.min()),
                min_seam=float(seam.min() + SEAM_HALF))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--freq', type=int, default=6)
    ap.add_argument('--out', default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'out', 'dimples.json'))
    a = ap.parse_args()
    L = build(a.freq)
    P, r, cls = L['P'], L['r'], L['cls']
    counts = {int(k): int((cls == k).sum()) for k in range(len(L['sizes']))}
    print('dimples %d  sizes (dia mm) %s  counts %s  coverage %.1f%%  min land %.3f mm  seam half-band %.3f mm'
          % (len(P), [round(2 * float(s), 2) for s in L['sizes']], counts, 100 * L['coverage'], L['min_land'], L['min_seam']))
    J = dict(
        note='Generic icosahedral dimple layout (PinPoint Golf Resources, MIT). Ball frame: +Z pole, '
             'parting line z=0 (dimple-free great circle). '
             'centre = unit vector; radius_mm = rim radius measured as arc on the 42.67 mm sphere; '
             'depth_mm = spherical-cap depth below the land.',
        ball_diameter_mm=42.67, freq=a.freq, count=int(len(P)),
        sizes=[dict(cls=k, radius_mm=float(s), diameter_mm=round(2 * float(s), 3), depth_mm=DEPTH[k], count=counts[k])
               for k, s in enumerate(L['sizes'])],
        coverage=round(float(L['coverage']), 4), min_land_mm=round(L['min_land'], 3),
        parting_line_half_band_mm=round(L['min_seam'], 3),
        dimples=[dict(c=[round(float(x), 6) for x in p], cls=int(k), radius_mm=float(rr), depth_mm=DEPTH[int(k)])
                 for p, k, rr in zip(P, cls, r)])
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, 'w') as f:
        json.dump(J, f, indent=0, separators=(',', ':'))


if __name__ == '__main__':
    main()
