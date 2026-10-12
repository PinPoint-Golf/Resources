#!/bin/bash
# Run one headless Blender job under a watchdog.
#   run_blender.sh <script.py> [script args...]
# Kills Blender if it runs longer than $BL_MAX_SEC (default 900 s) or its memory
# footprint (top -l 1 -pid) exceeds $BL_MAX_MB (default 5120 MB).
BLENDER=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
MAX_SEC=${BL_MAX_SEC:-900}
MAX_MB=${BL_MAX_MB:-5120}
SCRIPT=$1; shift
LOG=${BL_LOG:-/dev/stdout}

if pgrep -x Blender >/dev/null; then
  echo "run_blender: another Blender is running; refusing to start a second one" >&2
  exit 3
fi

"$BLENDER" -b --factory-startup --python-exit-code 1 --python "$SCRIPT" -- "$@" >>"$LOG" 2>&1 &
PID=$!
START=$(date +%s)
PEAK=0
while kill -0 $PID 2>/dev/null; do
  sleep 2
  NOW=$(date +%s); EL=$((NOW-START))
  MEM=$(top -l 1 -pid $PID -stats mem 2>/dev/null | awk 'f{print;exit} /^MEM/{f=1}' | tr -d ' +-')
  MB=0
  case "$MEM" in
    *G) MB=$(echo "${MEM%G}*1024" | bc | cut -d. -f1);;
    *M) MB=$(echo "${MEM%M}" | cut -d. -f1);;
    *K) MB=0;;
  esac
  [ -n "$BL_TRACE" ] && echo "t=${EL}s mem=${MEM}" >&2
  [ -n "$MB" ] && [ "$MB" -gt "$PEAK" ] 2>/dev/null && PEAK=$MB
  if [ "$EL" -gt "$MAX_SEC" ]; then
    echo "run_blender: KILL after ${EL}s (time cap)" >&2; kill -9 $PID; wait $PID 2>/dev/null; exit 124
  fi
  if [ -n "$MB" ] && [ "$MB" -gt "$MAX_MB" ] 2>/dev/null; then
    echo "run_blender: KILL at ${MB} MB (memory cap)" >&2; kill -9 $PID; wait $PID 2>/dev/null; exit 125
  fi
done
wait $PID; RC=$?
echo "run_blender: $(basename "$SCRIPT") $* rc=$RC ${EL}s peak=${PEAK}MB" >&2
exit $RC
