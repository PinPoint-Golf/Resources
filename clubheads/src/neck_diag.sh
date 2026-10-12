#!/bin/bash
# neck diagnostics for a club: curv + zebra + light face crops around the scoop (scratchpad)
C=${1:-wedge}; YC=${2:-36}; ZC=${3:-18}
cd "$(dirname "$0")/.."
S=${PEEK_DIR:-${TMPDIR:-/tmp}}
src/run_blender.sh src/render.py --club $C --looks curv,zebra --views face 2>&1 | grep -E "rror|run_bl"
src/run_blender.sh src/render.py --club $C --looks light --views face --samples 16 2>&1 | grep -E "rror|run_bl"
python3 - <<PY
import json
from PIL import Image
J=json.load(open('out/$C/${C}_face.json')); M=J['world_to_px']
u=M[0][1]*$YC+M[0][3]; v=M[1][2]*$ZC+M[1][3]
box=(int(u-450),int(v-500),int(u+350),int(v+400))
for lk,bgc in (('curv',(60,60,60,255)),('zebra',(120,120,130,255)),('light',(247,246,242,255))):
    im=Image.open('out/$C/${C}_face_%s.png'%lk); bg=Image.new('RGBA',im.size,bgc); bg.alpha_composite(im)
    bg.crop(box).convert('RGB').save('$S/n_%s.png'%lk)
PY
python3 src/peek.py $S/n.png 777777 $S/n_curv.png $S/n_zebra.png $S/n_light.png
