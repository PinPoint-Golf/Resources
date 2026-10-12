"""frame.py: the views, the image framing and the anchor geometry, shared by render.py (Blender)
and line.py / sheets.py (system python).  numpy only.

Pixel coordinates: origin top left, y down, continuous (pixel i spans i .. i+1).
"""
import math
import numpy as np
import marks

R_BALL = 42.67 / 2
LONG = 2048
MARGIN = 0.035                     # of the ball diameter, each side (as the club heads)


def _view(B, U):
    B = np.array(B, float); B /= np.linalg.norm(B)
    U = np.array(U, float); U = U - B * (U @ B); U /= np.linalg.norm(U)
    return dict(B=B, U=U, R=np.cross(U, B))


def _azel(az, el):
    a, e = math.radians(az), math.radians(el)
    return (math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e))


# B points from the ball toward the camera, U is image up, R = U x B is image right.
VIEWS = {
    'front': _view(marks.NUMBER_AXIS, marks.NUMBER_UP),  # looking down latitude 60 / longitude 28 (where the
                                                         # optional number sits), pole up
    'side': _view((1, 0, 0), (0, 0, 1)),                # at the parting line: alignment line horizontal, arrow right
    'three-quarter': _view(_azel(28, 42), (0, 0, 1)),   # hero
}
ORDER = ['front', 'side', 'three-quarter']


def scale(long_px=LONG):
    return 2 * R_BALL * (1 + 2 * MARGIN) / long_px   # mm per px


def to_px(p, v, long_px=LONG):
    """world mm (ball centre at origin) -> px."""
    s = scale(long_px)
    p = np.asarray(p, float)
    return np.stack([p @ v['R'] / s + long_px / 2, -(p @ v['U']) / s + long_px / 2], -1)


def dir_px(d, v):
    d = np.asarray(d, float)
    x, y = d @ v['R'], -(d @ v['U'])
    n = math.hypot(x, y)
    return None if n < 1e-9 else [x / n, y / n]


def anchors(vname, long_px=LONG, with_print=False):
    """Anchor JSON for one view (see README).  The print fields appear only with_print."""
    v = VIEWS[vname]; s = scale(long_px)
    r2 = lambda a: [round(float(a[0]), 2), round(float(a[1]), 2)]
    r5 = lambda a: None if a is None else [round(float(a[0]), 5), round(float(a[1]), 5)]
    vis = lambda p: bool((p / R_BALL) @ v['B'] > 0.0)
    axes = {k: r5(dir_px(e, v)) for k, e in (('x', (1, 0, 0)), ('y', (0, 1, 0)), ('z', (0, 0, 1)))}
    seam = []
    for lon in np.radians(np.arange(0, 360, 10)):
        p = R_BALL * np.array([math.cos(lon), math.sin(lon), 0.0])
        seam.append(r2(to_px(p, v, long_px)) + [vis(p)])
    J = dict(
        view=vname,
        image=dict(width=long_px, height=long_px),
        mm_per_px=round(s, 6),
        ball_diameter_mm=42.67,
        centre=[long_px / 2, long_px / 2],
        radius_px=round(R_BALL / s, 3),
        camera=dict(toward_camera=[round(float(x), 5) for x in v['B']], image_up=[round(float(x), 5) for x in v['U']],
                    image_right=[round(float(x), 5) for x in v['R']]),
        pole_axis=r5(dir_px((0, 0, 1), v)),
        parting_line=dict(polyline=seam, land_width_mm=0.84),
        ball_axes_px=axes,
        note='px: origin top left, y down. Ball frame: +Z pole, parting line z=0 (the dimple-free great '
             'circle). pole_axis = image direction of +Z, the axis normal to the parting line. '
             'parting_line.polyline = 36 points every 10 deg of longitude from +X toward +Y, as [x, y, visible]. '
             'ball_axes_px = image direction of each ball axis (null when it points at the camera).')
    if with_print:
        def onball(kind, u, w):
            return marks.chart_point(kind, u, w) * R_BALL
        tail = onball('line', *marks.TAIL); tip = onball('line', *marks.TIP); mid = onball('line', 0.0, 0.0)
        num = onball('number', 0.0, 0.0)
        J['alignment_line'] = dict(
            tail=r2(to_px(tail, v, long_px)), tip=r2(to_px(tip, v, long_px)), centre=r2(to_px(mid, v, long_px)),
            direction=r5(dir_px((0.0, 1.0, 0.0), v)), tail_visible=vis(tail), tip_visible=vis(tip),
            arc_mm=round(marks.TIP[0] - marks.TAIL[0], 2), width_mm=marks.LINE_W,
            polyline=[r2(to_px(onball('line', u, 0.0), v, long_px)) + [vis(onball('line', u, 0.0))]
                      for u in np.linspace(marks.TAIL[0], marks.TIP[0], 17)])
        J['number'] = dict(text='1', centre=r2(to_px(num, v, long_px)), up=r5(dir_px(marks.NUMBER_UP, v)),
                           visible=vis(num), height_mm=7.0)
    return J
