#!/bin/bash
# Rebuild the ball and the impact patch from scratch: layout, mesh, one Blender
# process per view and look (under the watchdog in ../clubheads/src/run_blender.sh), line looks,
# patch, @512 copies, sheets and the contrast check.  About 20 minutes on an M4 (CPU Cycles).
set -e
cd "$(dirname "$0")/.."
RB=../clubheads/src/run_blender.sh
rm -rf out work
mkdir -p out work
LOG=work/ball.log; : > $LOG
T0=$(date +%s)
python3 src/layout.py
python3 src/mesh.py
for V in front side three-quarter; do
  for L in light dark; do
    BL_LOG=$LOG $RB src/render.py --views $V --looks $L
  done
done
python3 src/line.py
python3 src/patch.py
python3 src/sheets.py --ball --patch --check
echo "make_all: $(( $(date +%s) - T0 ))s"
