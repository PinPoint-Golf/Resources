#!/bin/bash
# Build and render one club at final quality: geometry, then one Blender process per view.
set -e
C=$1
cd "$(dirname "$0")/.."
LOG=work/$C.log; mkdir -p work; : > $LOG
T0=$(date +%s)
[ -n "$SKIP_BUILD" ] || BL_LOG=$LOG src/run_blender.sh src/clubs.py --club $C
case $C in iron|wedge) VIEWS="top side face back";; *) VIEWS="top side face";; esac
LOOKS=${LOOKS:-light dark line}
for V in $VIEWS; do
  for L in $LOOKS; do
    BL_LOG=$LOG src/run_blender.sh src/render.py --club $C --views $V --looks $L
  done
done
python3 src/sheets.py --club $C
echo "make_club $C: $(( $(date +%s) - T0 ))s" | tee -a $LOG
