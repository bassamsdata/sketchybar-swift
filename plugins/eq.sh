#!/bin/bash
# EQ bar animation — a 0.5 s loop that runs only while playing. media.sh starts and stops it
# Fixed baseline: a bar of height h is raised by (h-10)/2 so its bottom is always on the same line (center −5). Height and offset move together on the same curve
PID="$HOME/.cache/sketchybar/eq.pid"
kill "$(cat "$PID" 2>/dev/null)" 2>/dev/null
echo $$ > "$PID"
H=("4 8 6" "8 6 10" "6 10 4" "10 6 8" "6 8 10"); k=0   # even numbers only — with odd ones the baseline correction is off by half a pt and the bottom wobbles
while :; do
  set -- ${H[$k]}; a=()
  for i in 1 2 3; do h=${!i}; a+=(--set media.eq.$i background.height=$h background.y_offset=$(( (h - 10) / 2 ))); done
  sketchybar "${a[@]}" 2>/dev/null || exit 0   # no transition animation — in-between frames would have odd heights and the bottom would wobble by 1pt
  k=$(( (k + 1) % 5 )); sleep 0.5
done
