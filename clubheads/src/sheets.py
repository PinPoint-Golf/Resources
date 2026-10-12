"""sheets.py: @512 downscales, per-club and combined contact sheets, anchors check (system python3 + Pillow).

    python3 sheets.py --club driver      # out/driver/*@512.png + out/driver/contact_{light,dark,line}.png
    python3 sheets.py --all              # out/contact_{light,dark,line}.png + out/anchors_check.png
"""
import os, sys, json, glob, argparse
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'out')
ORDER = ['driver', 'fairway', 'hybrid', 'iron', 'wedge']
VIEWS = ['top', 'side', 'face', 'back']
PAPER, INK_BG = (247, 246, 242), (21, 23, 26)


def font(sz):
    for f in ('/System/Library/Fonts/Helvetica.ttc', '/System/Library/Fonts/SFNS.ttf', '/Library/Fonts/Arial.ttf'):
        if os.path.exists(f):
            return ImageFont.truetype(f, sz)
    return ImageFont.load_default()


def downscale(path, long=512):
    im = Image.open(path).convert('RGBA')
    s = long / max(im.size)
    sz = (max(1, round(im.width * s)), max(1, round(im.height * s)))
    sm = im.convert('RGBa').resize(sz, Image.LANCZOS).convert('RGBA')  # premultiplied resample: no fringes
    sm.save(path[:-4] + '@512.png', optimize=True)


def fit(im, h):
    s = h / im.height
    return im.convert('RGBa').resize((max(1, round(im.width * s)), h), Image.LANCZOS).convert('RGBA')


def views_of(club):
    return [v for v in VIEWS if os.path.exists(os.path.join(OUT, club, '%s_%s.json' % (club, v)))]


def sheet(rows, bg, fg, path, cell_h=420, title=None):
    """rows: list of (row label, [(cell label, image path)])"""
    pad = 24; lab_h = 34; f = font(22); ft = font(30)
    cells = [[(l, fit(Image.open(p), cell_h)) for l, p in r if os.path.exists(p)] for _, r in rows]
    W = max(sum(im.width for _, im in r) + pad * (len(r) + 1) for r in cells)
    top = 60 if title else 0
    rl_h = 30 if any(rl for rl, _ in rows) else 0
    H = top + len(rows) * (cell_h + lab_h + pad + rl_h) + pad
    c = Image.new('RGBA', (W, H), bg + (255,))
    d = ImageDraw.Draw(c)
    if title:
        d.text((pad, 16), title, fill=fg, font=ft)
    y = top + pad
    for (rl, _), r in zip(rows, cells):
        if rl:
            d.text((pad, y), rl, fill=fg, font=ft)
            y += rl_h
        x = pad
        for l, im in r:
            c.alpha_composite(im, (x, y))
            d.text((x, y + cell_h + 6), l, fill=fg, font=f)
            x += im.width + pad
        y += cell_h + lab_h + pad
    c.convert('RGB').save(path, optimize=True)


def club_sheets(club, rows_out=None):
    d = os.path.join(OUT, club)
    for p in sorted(glob.glob(os.path.join(d, '%s_*.png' % club))):
        if not p.endswith('@512.png'):
            downscale(p)
    vs = views_of(club)
    lab = json.load(open(os.path.join(d, '%s_%s.json' % (club, vs[0]))))['label'] if vs else club
    for look, bg, fg in (('light', PAPER, (40, 40, 40)), ('dark', INK_BG, (220, 220, 220))):
        sheet([(None, [(v, os.path.join(d, '%s_%s_%s.png' % (club, v, look))) for v in vs])], bg, fg,
              os.path.join(d, 'contact_%s.png' % look), title='%s - %s look' % (lab, look))
    # line: black ink on paper above white ink on dark
    pb = [(v, os.path.join(d, '%s_%s_line-black.png' % (club, v))) for v in vs]
    pw = [(v, os.path.join(d, '%s_%s_line-white.png' % (club, v))) for v in vs]
    a = os.path.join(d, '_a.png'); b = os.path.join(d, '_b.png')
    sheet([(None, pb)], PAPER, (40, 40, 40), a, title='%s - line look, black ink' % lab)
    sheet([(None, pw)], INK_BG, (220, 220, 220), b, title='white ink')
    A, B = Image.open(a), Image.open(b)
    c = Image.new('RGB', (max(A.width, B.width), A.height + B.height), PAPER)
    c.paste(A, (0, 0)); c.paste(B, (0, A.height))
    c.save(os.path.join(d, 'contact_line.png'), optimize=True)
    os.remove(a); os.remove(b)


def draw_anchors(club, view, cell_h=520):
    d = os.path.join(OUT, club)
    J = json.load(open(os.path.join(d, '%s_%s.json' % (club, view))))
    im = Image.open(os.path.join(d, '%s_%s_light.png' % (club, view))).convert('RGBA')
    base = Image.new('RGBA', im.size, PAPER + (255,)); base.alpha_composite(im)
    g = ImageDraw.Draw(base)
    s = J['image']['width'] / 2048.0 * 2.5
    w = max(2, int(3 * s))
    def P(p): return (p[0], p[1])
    def dot(p, col, r=9):
        r = r * s; g.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=col, outline=(255, 255, 255), width=max(1, w // 2))
    if J.get('ground_y') is not None:
        y = J['ground_y']; x = 0
        while x < im.width:
            g.line([(x, y), (x + 24 * s, y)], fill=(90, 90, 90), width=w); x += 40 * s
    hb = J['head_bbox']; g.rectangle(hb, outline=(0, 170, 200), width=w)
    sa = J['shaft_axis']; g.line([P(sa[0]), P(sa[1])], fill=(240, 140, 0), width=w)
    fp = J['face_plane']; g.line([P(fp[0]), P(fp[1])], fill=(20, 160, 60), width=w)
    le = J['leading_edge']; g.line([P(le['heel']), P(le['toe'])], fill=(40, 90, 230), width=w)
    dot(le['heel'], (40, 90, 230)); dot(le['toe'], (40, 90, 230)); dot(le['mid'], (40, 90, 230), 6)
    dot(J['sole_contact'], (200, 0, 200))
    fc = J['face_centre']
    if J.get('face_normal'):
        n = J['face_normal']; L = 140 * s
        g.line([P(fc), (fc[0] + n[0] * L, fc[1] + n[1] * L)], fill=(220, 30, 30), width=w)
    if J.get('face_frame'):
        ff = J['face_frame']; o = ff['origin']
        for k, col in (('x_px_per_mm', (220, 30, 30)), ('y_px_per_mm', (20, 160, 60))):
            v = ff[k]
            g.line([P(o), (o[0] + v[0] * 20, o[1] + v[1] * 20)], fill=col, width=w)
            for t in range(-20, 21, 10):
                q = (o[0] + v[0] * t, o[1] + v[1] * t); g.ellipse([q[0] - 3 * s, q[1] - 3 * s, q[0] + 3 * s, q[1] + 3 * s], fill=col)
    dot(fc, (220, 30, 30), 11)
    return fit(base, cell_h)


def _lstar(rgb):
    c = rgb / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    Y = lin[..., 0] * 0.2126 + lin[..., 1] * 0.7152 + lin[..., 2] * 0.0722
    return np.where(Y > 216 / 24389, 116 * np.cbrt(Y) - 16, Y * 24389 / 27)


def edge_contrast(path, bg=INK_BG, band=4, cell=48, thresh=12.0, min_px=40, anchors=None):
    """Dark-look rule: along the silhouette (a band `band` px inside the alpha edge) every
    `cell`-px segment must have median luminance contrast dL* >= thresh against `bg`.
    Returns (ok, failures[(x, y, dL)], worst).  The shaft's alpha fade is excluded."""
    im = np.asarray(Image.open(path).convert('RGBA')).astype(np.float64)
    sc = max(im.shape[:2]) / 2048.0                       # scale the rule with image size
    cell = max(12, int(round(cell * sc))); band = max(2, int(round(band * sc))); min_px = max(8, int(min_px * sc))
    a = im[..., 3] / 255.0
    solid = a > 0.95
    er = solid.copy()
    for _ in range(band):
        e = er.copy()
        e[1:, :] &= er[:-1, :]; e[:-1, :] &= er[1:, :]; e[:, 1:] &= er[:, :-1]; e[:, :-1] &= er[:, 1:]
        er = e
    edge = solid & ~er
    comp = im[..., :3] * a[..., None] + np.array(bg, float) * (1 - a[..., None])
    dL = np.abs(_lstar(comp) - _lstar(np.array(bg, float)))
    H, W = a.shape
    skip = None
    if anchors and os.path.exists(anchors):  # the shaft stub's deliberate fade-out is not silhouette
        J = json.load(open(anchors)); k = W / J['image']['width']
        se = np.array(J['shaft_axis'][1]) * k; skip = (se, 45.0 / J['mm_per_px'] * k)
    fails = []; worst = 999.0
    for y0 in range(0, H, cell):
        for x0 in range(0, W, cell):
            m = edge[y0:y0 + cell, x0:x0 + cell]
            if m.sum() < min_px:
                continue
            if skip is not None and np.hypot(x0 + cell / 2 - skip[0][0], y0 + cell / 2 - skip[0][1]) < skip[1]:
                continue
            med = float(np.median(dL[y0:y0 + cell, x0:x0 + cell][m]))
            worst = min(worst, med)
            if med < thresh:
                fails.append((x0 + cell // 2, y0 + cell // 2, round(med, 1)))
    return (len(fails) == 0, fails, round(worst, 1))


def dark_check(clubs=None, tag='dark', suffix=''):
    rep = {}
    for c in clubs or ORDER:
        for v in views_of(c):
            p = os.path.join(OUT, c, '%s_%s_%s%s.png' % (c, v, tag, suffix))
            if os.path.exists(p):
                ok, fails, worst = edge_contrast(p, bg=INK_BG if tag == 'dark' else PAPER,
                                                 anchors=os.path.join(OUT, c, '%s_%s.json' % (c, v)))
                rep['%s_%s' % (c, v)] = (ok, len(fails), worst, fails[:6])
                print('%-14s %-5s %s  failing segments %3d  worst dL* %5.1f %s' % (
                    c + '_' + v, tag, 'PASS' if ok else 'FAIL', len(fails), worst, fails[:4]))
    return rep


def combined():
    clubs = [c for c in ORDER if views_of(c)]
    labels = {c: json.load(open(os.path.join(OUT, c, '%s_%s.json' % (c, views_of(c)[0]))))['label'] for c in clubs}
    for look, bg, fg in (('light', PAPER, (40, 40, 40)), ('dark', INK_BG, (220, 220, 220))):
        rows = [(labels[c], [(v, os.path.join(OUT, c, '%s_%s_%s.png' % (c, v, look))) for v in views_of(c)]) for c in clubs]
        sheet(rows, bg, fg, os.path.join(OUT, 'contact_%s.png' % look), cell_h=380, title='Club heads - %s look' % look)
    rows = [(labels[c], [(v, os.path.join(OUT, c, '%s_%s_line-black.png' % (c, v))) for v in views_of(c)]) for c in clubs]
    sheet(rows, PAPER, (40, 40, 40), os.path.join(OUT, 'contact_line.png'), cell_h=380, title='Club heads - line look (black ink)')
    # anchors check
    pad = 20; f = font(22)
    cells = [[draw_anchors(c, v) for v in views_of(c)] for c in clubs]
    W = max(sum(i.width for i in r) + pad * (len(r) + 1) for r in cells)
    H = len(cells) * (520 + 40 + pad) + pad + 70
    out = Image.new('RGBA', (W, H), (255, 255, 255, 255)); g = ImageDraw.Draw(out)
    g.text((pad, 14), 'Anchors: red = face centre + normal (+x toe ticks 10 mm in face view), green = face plane '
           '(+y up-face ticks), blue = leading edge, orange = shaft axis, magenta = sole contact, cyan = head bbox, '
           'grey dashes = ground', fill=(30, 30, 30), font=f)
    y = 60
    for c, r in zip(clubs, cells):
        x = pad
        for v, im in zip(views_of(c), r):
            out.alpha_composite(im, (x, y)); g.text((x, y + 522), '%s  %s' % (labels[c], v), fill=(30, 30, 30), font=f)
            x += im.width + pad
        y += 520 + 40 + pad
    out.convert('RGB').save(os.path.join(OUT, 'anchors_check.png'), optimize=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--club'); ap.add_argument('--all', action='store_true')
    ap.add_argument('--check', action='store_true', help='dark-look silhouette contrast rule (all clubs)')
    a = ap.parse_args()
    if a.check:
        dark_check(); dark_check(tag='light')
    if a.club:
        club_sheets(a.club)
    if a.all:
        for c in ORDER:
            if views_of(c):
                club_sheets(c)
        combined()
