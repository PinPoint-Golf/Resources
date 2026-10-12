"""sheets.py: @512 copies, contact sheets and the silhouette contrast check for the ball
(system python3 + numpy + Pillow).

    python3 sheets.py --ball           # out/ball_*@512.png, out/contact_ball.png, out/contact_ball_panel.png
    python3 sheets.py --check [dir]    # silhouette dL* of light/dark looks against paper and ink
    python3 sheets.py --patch          # out/dimple-print/contact_patch.png + driver-face scale check

The contrast rule and the sheet layout are imported read-only from ../clubheads/src/sheets.py.
"""
import os, sys, glob, json, argparse
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
import importlib.util as _ilu
sys.dont_write_bytecode = True     # leave no __pycache__ in ../clubheads
_spec = _ilu.spec_from_file_location('club_sheets', os.path.join(ROOT, '..', 'clubheads', 'src', 'sheets.py'))
club_sheets = _ilu.module_from_spec(_spec); _spec.loader.exec_module(club_sheets)   # shared helpers, read-only
sys.path.insert(0, HERE)
import frame                            # noqa: E402

OUT = os.path.join(ROOT, 'out')
PAPER, INK_BG = club_sheets.PAPER, club_sheets.INK_BG
LOOKS = [('light', PAPER), ('dark', INK_BG), ('line-black', PAPER), ('line-white', INK_BG),
         ('line-bold-black', PAPER), ('line-bold-white', INK_BG)]


def strip(p):
    """Re-save a Blender render without its metadata chunks (Cycles render stats, EXIF) and
    with full PNG compression."""
    im = Image.open(p)
    if im.info:
        im.load()
        clean = Image.frombytes(im.mode, im.size, im.tobytes())
        clean.save(p, optimize=True)


def ball_sheets():
    for p in sorted(glob.glob(os.path.join(OUT, 'ball_*.png'))):
        if not p.endswith('@512.png'):
            strip(p)
            club_sheets.downscale(p)
    rows = []
    # one sheet, each look on its own background: stack per-look strips
    strips = []
    for look, bg in LOOKS:
        cells = [(v, os.path.join(OUT, 'ball_%s_%s.png' % (v, look))) for v in frame.ORDER]
        p = os.path.join(OUT, '_strip_%s.png' % look)
        fg = (40, 40, 40) if bg == PAPER else (220, 220, 220)
        club_sheets.sheet([(None, cells)], bg, fg, p, cell_h=440, title='Ball - %s look' % look)
        strips.append(p)
    ims = [Image.open(p) for p in strips]
    c = Image.new('RGB', (max(i.width for i in ims), sum(i.height for i in ims)), PAPER)
    y = 0
    for im in ims:
        c.paste(im, (0, y)); y += im.height
    c.save(os.path.join(OUT, 'contact_ball.png'), optimize=True)
    for p in strips:
        os.remove(p)
    panel_sizes()


def panel_sizes(sizes=(128, 192, 256, 384)):
    """Every look of every view at panel sizes (downscaled from 2048), to judge legibility."""
    pad = 16; f = club_sheets.font(18)
    rows = []
    for look, bg in LOOKS:
        row = []
        for v in frame.ORDER:
            im = Image.open(os.path.join(OUT, 'ball_%s_%s.png' % (v, look))).convert('RGBa')
            for sz in sizes:
                row.append(im.resize((sz, sz), Image.LANCZOS).convert('RGBA'))
        rows.append((look, bg, row))
    W = pad + sum(i.width + pad for i in rows[0][2]) + 200
    H = sum(max(sizes) + 2 * pad for _ in rows) + 50
    c = Image.new('RGB', (W, H), (255, 255, 255)); d = ImageDraw.Draw(c)
    d.text((pad, 12), 'Ball at panel sizes (%s px) - views front, side, three-quarter' % ', '.join(map(str, sizes)),
           fill=(30, 30, 30), font=f)
    y = 50
    for look, bg, row in rows:
        hh = max(sizes) + 2 * pad
        d.rectangle([0, y, W, y + hh], fill=bg)
        d.text((pad, y + 4), look, fill=(40, 40, 40) if bg == PAPER else (220, 220, 220), font=f)
        x = 200
        for im in row:
            c.paste(im, (x, y + pad + (max(sizes) - im.height)), im)
            x += im.width + pad
        y += hh
    c.save(os.path.join(OUT, 'contact_ball_panel.png'), optimize=True)


def check(d=OUT, verbose=True):
    """The club-head silhouette rule (median dL* >= 12 in every 48 px segment of a 4 px band inside
    the alpha edge, at 2048 px), run for each look against both backgrounds."""
    rep = {}
    for v in frame.ORDER:
        for look in ('light', 'dark'):
            p = os.path.join(d, 'ball_%s_%s.png' % (v, look))
            if not os.path.exists(p):
                continue
            for bgn, bg in (('paper', PAPER), ('ink', INK_BG)):
                ok, fails, worst = club_sheets.edge_contrast(p, bg=bg)
                intended = (look == 'light') == (bgn == 'paper')
                rep['%s_%s_on_%s' % (v, look, bgn)] = dict(ok=ok, failing=len(fails), worst=worst, intended=intended)
                if verbose:
                    print('%-14s %-5s on %-5s %s %s  failing segments %3d  worst dL* %5.1f' % (
                        v, look, bgn, 'PASS' if ok else 'FAIL', '' if intended else '(cross)', len(fails), worst))
    return rep


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--ball', action='store_true')
    ap.add_argument('--check', nargs='?', const=OUT)
    ap.add_argument('--patch', action='store_true')
    a = ap.parse_args()
    if a.check:
        check(a.check)
    if a.ball:
        ball_sheets()
    if a.patch:
        import patch
        patch.sheets()
