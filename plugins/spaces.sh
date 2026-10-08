#!/bin/bash
# space dots = only the spaces of the display showing the bar (BAR_DISPLAY → sketchybarrc writes it to bar_uuid; the main display is "Main") (10-07).
#   no rebuild when another display's space count changes (external connected/disconnected). space= is a global index → skip the space counts of earlier displays in prefs order (connected ones only)
#   spaces of detached monitors remain in the prefs, so only connected displays are counted (2026-10-01, helper/displays).
# Adding or removing spaces rebuilds on space_change or the 5s refresh. If unchanged, does nothing.
CONFIG_DIR="${CONFIG_DIR:-$HOME/.config/sketchybar}"
source "$CONFIG_DIR/colors.sh"
read -r S0 N <<<"$(defaults export com.apple.spaces - 2>/dev/null | plutil -extract SpacesDisplayConfiguration."Management Data".Monitors json -o - - 2>/dev/null \
  | python3 -c '
import json,sys
me=sys.argv[1]; on=set(sys.argv[2:])|{"Main",me}; s0=0
for m in json.load(sys.stdin):
    i=m.get("Display Identifier"); k=len(m.get("Spaces",[]))
    if i==me: print(s0,k); break
    if i in on: s0+=k' "$(cat "$HOME/.cache/sketchybar/bar_uuid" 2>/dev/null || echo Main)" $("$CONFIG_DIR/helper/displays") 2>/dev/null)"
[ -n "$N" ] && [ "$N" -gt 0 ] || exit 0
C="$HOME/.cache/sketchybar/spaces.n"
[ "$S0:$N" = "$(cat "$C" 2>/dev/null)" ] && exit 0

a=(); old=$(sketchybar --query bar | grep -c '"space\.[0-9]*"')   # number of dots present now (actual, not the cache) — regex --remove does not work, so remove by name
for ((i = 1; i <= old; i++)); do a+=(--remove space.$i); done
sketchybar --remove spaces.seg 2>/dev/null   # remove the bracket first — removing items first crashes SketchyBar in the bracket size calculation (3 crashes on 2026-09-30)
sketchybar "${a[@]}" 2>/dev/null; a=()
for ((i = 1; i <= N; i++)); do
  a+=(--add space space.$i left
      --set space.$i space=$(( S0 + i )) icon.drawing=off label="" label.width=8
            background.color=$TEXT3 background.height=8 background.drawing=on
            padding_right=6 y_offset=0 script="$CONFIG_DIR/plugins/space.sh"   # island: dots (shapes) are centered vertically in the island, unlike text. When 8pt in 31pt leaves half a pt, it goes down (top 12 · bottom 11, by request)
      --move space.$i before space.padr)
  # the key-press emulation (⌃number) that switched to the clicked space was removed — that shortcut is disabled, so it gets typed into the front window
done
sketchybar "${a[@]}" \
  --add bracket spaces.seg '/space\..*/' --set spaces.seg background.color=$LINE background.height=$((NOTCH_H - 2)) background.drawing=on   # without a height the bracket background is not drawn. Color is the --line token, opaque — so only this cell stands out on the bar
echo "$S0:$N" > "$C"
sketchybar --trigger space_change   # apply the selected state to the new dots
