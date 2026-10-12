"""marks.py: the generic print on the ball - a play number and an alignment line (numpy + Pillow).

    python3 marks.py            # writes work/mark_number.png and work/mark_line.png

Both are defined as polygons in mm in a chart on the sphere and rasterised to masks that
render.py (Blender shader) and line.py (line looks) both sample, so every look prints the
same marks.

Ball frame (see layout.py): +Z pole, parting line z = 0.
  * number chart: orthographic projection onto the plane tangent at NUMBER_AXIS (latitude 60,
    longitude 28), x = R u.right, y = R u.up, where up points toward the pole and
    right = up x axis; the front view looks down NUMBER_AXIS with `up` as image up;
  * line chart: u = R * longitude (from +X toward +Y), v = R * latitude, so the line runs
    along the parting line, centred on +X, with its arrow pointing toward +Y.
"""
import os, math, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.join(ROOT, 'work')
R_BALL = 42.67 / 2

# play number "1": 7.0 mm tall, 1.55 mm stem, flag to the upper left.  Our own drawing.
NUMBER = [[(-0.425, -3.5), (1.125, -3.5), (1.125, 3.5), (-0.05, 3.5), (-1.95, 1.85), (-1.95, 0.68), (-0.425, 2.0)]]
NUMBER_EXT = (-4.5, 4.5, -4.5, 4.5)          # chart window, mm
NUMBER_PX = 0.003                              # mm per mask pixel
NUMBER_ROUND = 0.12                            # corner rounding, mm
# the number sits at latitude 60 deg, longitude 28 deg (toward the hero camera), clear of the side
# view's silhouette; it reads upright with its up toward the pole
NUMBER_LAT, NUMBER_LON = 60.0, 28.0
_la, _lo = math.radians(NUMBER_LAT), math.radians(NUMBER_LON)
NUMBER_AXIS = np.array([math.cos(_la) * math.cos(_lo), math.cos(_la) * math.sin(_lo), math.sin(_la)])
NUMBER_UP = np.array([0, 0, 1.0]) - NUMBER_AXIS[2] * NUMBER_AXIS
NUMBER_UP /= np.linalg.norm(NUMBER_UP)
NUMBER_RIGHT = np.cross(NUMBER_UP, NUMBER_AXIS)

# alignment line: 0.7 mm wide (inside the 0.84 mm parting-line land), arc u = -21 .. +18.3 mm,
# then a notched arrowhead 3.4 mm long and 2.6 mm wide that dips into the dimples either side.
LINE_W = 0.70
LINE_U0, LINE_U1 = -21.0, 18.3
ARROW = [(20.6, 0.0), (17.2, 1.3), (18.05, 0.0), (17.2, -1.3)]
LINE = [[(LINE_U0, -LINE_W / 2), (LINE_U1, -LINE_W / 2), (LINE_U1, LINE_W / 2), (LINE_U0, LINE_W / 2)], ARROW]
LINE_EXT = (-22.0, 22.0, -2.0, 2.0)
LINE_PX = 0.004
LINE_ROUND = 0.08
TAIL = (LINE_U0, 0.0)
TIP = (ARROW[0][0], 0.0)


def raster(polys, ext, mmpx, round_mm):
    from PIL import Image, ImageDraw, ImageFilter
    u0, u1, v0, v1 = ext
    W = int(round((u1 - u0) / mmpx)); H = int(round((v1 - v0) / mmpx))
    ss = 4
    im = Image.new('L', (W * ss, H * ss), 0)
    d = ImageDraw.Draw(im)
    for P in polys:
        d.polygon([((u - u0) / mmpx * ss, (v1 - v) / mmpx * ss) for u, v in P], fill=255)
    im = im.resize((W, H), Image.BOX)
    if round_mm > 0:  # round the corners: blur, then re-sharpen to a 1.5 px antialiased edge
        r = round_mm / mmpx
        a = np.asarray(im.filter(ImageFilter.GaussianBlur(r * 0.6)), np.float32) / 255
        a = np.clip((a - 0.5) * (1.0 / 0.5) * (r * 0.6) / 1.5 + 0.5, 0, 1)
        im = Image.fromarray((a * 255 + 0.5).astype(np.uint8))
    return im


def number_uv(U):
    """chart mm coordinates of unit vectors U for the number, and validity (front of the pole)."""
    return R_BALL * (U @ NUMBER_RIGHT), R_BALL * (U @ NUMBER_UP), (U @ NUMBER_AXIS) > 0.2


def line_uv(U):
    lon = np.arctan2(U[..., 1], U[..., 0]); lat = np.arcsin(np.clip(U[..., 2], -1, 1))
    return R_BALL * lon, R_BALL * lat, U[..., 0] > 0.0


def chart_point(kind, u, v):
    """unit vector on the ball for chart coordinates (mm)."""
    if kind == 'number':
        x, y = u / R_BALL, v / R_BALL
        return x * NUMBER_RIGHT + y * NUMBER_UP + math.sqrt(max(0.0, 1 - x * x - y * y)) * NUMBER_AXIS
    lon, lat = u / R_BALL, v / R_BALL
    return np.array([math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)])


def sample(mask, ext, mmpx, u, v):
    """bilinear sample of a mask (float 0..1) at chart mm coordinates."""
    from scipy.ndimage import map_coordinates
    u0, u1, v0, v1 = ext
    x = (u - u0) / mmpx - 0.5; y = (v1 - v) / mmpx - 0.5
    return map_coordinates(mask, [y.ravel(), x.ravel()], order=1, mode='constant', cval=0.0).reshape(np.shape(u))


def masks():
    os.makedirs(WORK, exist_ok=True)
    pn = os.path.join(WORK, 'mark_number.png'); pl = os.path.join(WORK, 'mark_line.png')
    if not os.path.exists(pn):
        from PIL import Image
        raster(NUMBER, NUMBER_EXT, NUMBER_PX, NUMBER_ROUND).save(pn)
    if not os.path.exists(pl):
        raster(LINE, LINE_EXT, LINE_PX, LINE_ROUND).save(pl)
    return pn, pl


if __name__ == '__main__':
    for p in (os.path.join(WORK, 'mark_number.png'), os.path.join(WORK, 'mark_line.png')):
        if os.path.exists(p):
            os.remove(p)
    print(masks())
