#!/bin/bash
# Rebuild every club head from scratch: geometry, renders, anchors, @512 copies, contact sheets.
# One Blender at a time, each under the watchdog in run_blender.sh.  About 50 minutes on an M4 (CPU Cycles).
set -e
cd "$(dirname "$0")/.."
rm -rf out work
mkdir -p out work
T0=$(date +%s)
for C in driver fairway hybrid iron wedge; do
  src/make_club.sh $C
done
python3 src/sheets.py --all
echo "make_all: $(( $(date +%s) - T0 ))s"
