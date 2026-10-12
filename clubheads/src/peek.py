# usage: python3 peek.py out.png bg_hex img1 [img2 ...]  -> side-by-side composite on a background
import sys
from PIL import Image
out, bg = sys.argv[1], sys.argv[2]
ims = [Image.open(p).convert('RGBA') for p in sys.argv[3:]]
H = max(i.height for i in ims); W = sum(i.width for i in ims) + 10 * (len(ims) - 1)
c = Image.new('RGBA', (W, H), '#' + bg)
x = 0
for i in ims:
    c.alpha_composite(i, (x, (H - i.height) // 2)); x += i.width + 10
c.convert('RGB').save(out)
