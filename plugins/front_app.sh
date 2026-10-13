#!/bin/bash
# Front app name. Width animates over 0.2s. With the media island present (island), ordering keeps the islands from overlapping:
#   growing — shrink the media island first (0.2s), then widen the name / shrinking — narrow the name first and the media island grows after
case "$SENDER" in   # app name hover: --text-2 → --text (rev 10)
  mouse.entered) source "${CONFIG_DIR:-$HOME/.config/sketchybar}/colors.sh"; sketchybar --set "$NAME" label.color=$TEXT; exit 0 ;;
  mouse.exited) source "${CONFIG_DIR:-$HOME/.config/sketchybar}/colors.sh"; sketchybar --set "$NAME" label.color=$TEXT2; exit 0 ;;
esac
[ "$SENDER" = "front_app_switched" ] || exit 0
# one at a time: when the app changes twice quickly, two runs compute from the same 'previous width' and the progress fill and island jump (10-06 capture) → wait for the earlier run to finish (max 2s)
LK="$HOME/.cache/sketchybar/front_app.lock"; for _ in $(seq 40); do mkdir "$LK" 2>/dev/null && break; sleep 0.05; done; trap 'rmdir "$LK" 2>/dev/null' EXIT
CONFIG_DIR="${CONFIG_DIR:-$HOME/.config/sketchybar}"; P="$CONFIG_DIR/plugins"
case "$INFO" in
  "Visual Studio Code"|"Code") n=code ;;
  "Google Chrome") n=chrome ;;
  *) n=$(tr '[:upper:]' '[:lower:]' <<<"$INFO") ;;
esac
# previous name and fill position come from the cache (written by this script and media.sh). Under an event burst sketchybar --query sometimes returns empty → previous width computed as 0 and the island jumps a lot (measured 10-06)
FA="$HOME/.cache/sketchybar/front_app.last"; MP="$HOME/.cache/sketchybar/media_pl"
old=$(cat "$FA" 2>/dev/null); [ -n "$old" ] || old=$(sketchybar --query "$NAME" 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin)['label']['value'])" 2>/dev/null)
[ -n "$SB_BOOT" ] && { sketchybar --set "$NAME" label="$n" label.width=$(perl "$P/width.pl" "$n"); echo "$n" > "$FA"; exit 0; }   # at startup (bar still off screen): apply at once, no animation or island ordering. sketchybarrc fits the media island right after
wo=$(perl "$P/width.pl" "$old"); wn=$(perl "$P/width.pl" "$n")   # text width only (padding is item padding)
MEDIA=1   # the media island is always present (checking by query returns empty under an event burst, giving 0 and skipping the fill correction)
if [ "$wn" -gt "$wo" ] && [ $MEDIA = 1 ]; then
  LE_GROW=$(( wn - wo )) SENDER=media_layout bash "$P/media.sh"; sleep 0.22
fi
# the progress fill (media.fill) is an item attached after the left island — move its padding the opposite way in the same command to keep it in place on the media island
F=(); if [ $MEDIA = 1 ]; then mp=$(cat "$MP" 2>/dev/null) || mp=; [ -n "$mp" ] || mp=$(sketchybar --query media.fill | python3 -c "import json,sys;print(json.load(sys.stdin)['geometry']['padding_left'])" 2>/dev/null)
  [ -n "$mp" ] && { F=(--set media.fill padding_left=$(( mp - (wn - wo) ))); echo $(( mp - (wn - wo) )) > "$MP"; }; fi
sketchybar --set "$NAME" label="$n" label.width=$wo --animate tanh 12 --set "$NAME" label.width=$wn "${F[@]}"
echo "$n" > "$FA"
[ $MEDIA = 1 ] && { sleep 0.22; sketchybar --trigger media_layout; }
