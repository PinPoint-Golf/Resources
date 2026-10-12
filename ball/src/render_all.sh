#!/bin/bash
# Re-render the light and dark looks only (needs work/ball_mesh.npz and the print masks):
#   src/render_all.sh [views] [looks]
set -e
cd "$(dirname "$0")/.."
RB=../clubheads/src/run_blender.sh
VIEWS=${1:-"front side three-quarter"}; LOOKS=${2:-"light dark"}
LOG=work/ball.log
for V in $VIEWS; do
  for L in $LOOKS; do
    BL_LOG=$LOG $RB src/render.py --views $V --looks $L
  done
done
