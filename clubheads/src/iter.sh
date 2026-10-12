#!/bin/bash
# quick iteration: build at coarse h, preview renders, composite peeks
C=$1; H=${2:-0.4}; LOOKS=${3:-light,dark}
cd "$(dirname "$0")/.."
src/run_blender.sh src/clubs.py --club $C --h $H 2>&1 | grep -E "measured|rror|run_bl|Trace|line [0-9]"
src/run_blender.sh src/render.py --club $C --preview --looks $LOOKS 2>&1 | grep -E "rror|run_bl|Trace|line [0-9]"
SP=${PEEK_DIR:-${TMPDIR:-/tmp}}
for L in ${LOOKS//,/ }; do
  T=$L; [ $L = line ] && T=line-black
  BG=F7F6F2; [ $L = dark ] && BG=15171A
  python3 src/peek.py $SP/peek_$L.png $BG $(ls out/$C/${C}_{top,side,face,back}_$T.png 2>/dev/null)
done
