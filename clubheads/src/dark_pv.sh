#!/bin/bash
# preview dark renders (suffix _pv) for all clubs + the silhouette contrast rule
cd "$(dirname "$0")/.."
for C in ${CLUBS:-driver fairway hybrid iron wedge}; do
  src/run_blender.sh src/render.py --club $C --looks dark --preview --suffix _pv 2>&1 | grep -E "rror|KILL"
done
python3 -c "
import sys; sys.path.insert(0,'src'); import sheets
sheets.dark_check(suffix='_pv')" 
