#!/bin/bash
# pilo circle (optional) - the state of your Pilo agents as a round face with two arms: pose, expression and color. Popup PILO: character · name · one line (question / progress) per agent
# Data: `pilo api GET /api/agents` (at once on the pilo_change event + every 30s, ~0.05s). No pilo command or no answer → the circle is not drawn at all, so it never shows on a Mac without Pilo
# States = the pilo agentstate ladder: limited · gaveUp · stalled · blocked · failed · unbound · running · idle
# The circle shows the most urgent state among all agents: blocked (waiting on a decision) > failed > gaveUp > stalled > running > limited > unbound > idle
source "$CONFIG_DIR/colors.sh"; source "$CONFIG_DIR/config.sh"; source "$CONFIG_DIR/plugins/popup.sh"
PX="$HOME/.cache/sketchybar/px"
# A burst of pilo_change events runs once: only the last one continues, 0.15s after it arrived (earlier ones stop here)
if [ "$SENDER" = pilo_change ]; then E="$HOME/.cache/sketchybar/pilo_evt"; echo $$ > "$E"; sleep 0.15; [ "$(cat "$E" 2>/dev/null)" = $$ ] || exit 0; fi
FAILS="$HOME/.cache/sketchybar/pilo_fail"
hide() { rm -f "$FAILS"; echo off > "$HOME/.cache/sketchybar/pilo"; sketchybar --set pilo drawing=off --set pilo.ul drawing=off; exit 0; }   # writing "off" also ends pilo_anim.sh
# No answer: keep the circle as it is for up to 3 failures in a row so a short outage such as a server restart does not make it vanish. If it was hidden it stays hidden
miss() { local n=$(( $(cat "$FAILS" 2>/dev/null || echo 0) + 1 )); echo $n > "$FAILS"
  [ $n -lt 3 ] && [ "$(cat "$HOME/.cache/sketchybar/pilo" 2>/dev/null || echo off)" != off ] && exit 0; hide; }
[ "${PILO_ISLAND:-1}" = 1 ] || hide
PILO="${PILO_CMD:-$(command -v pilo || echo "$HOME/.local/bin/pilo")}"
[ -x "$PILO" ] || hide
J=$(perl -e 'alarm 3; exec @ARGV' "$PILO" api GET /api/agents 2>/dev/null) || miss
OUT=$(/usr/bin/python3 -c '
import json, sys, datetime as D
try: A = [a for a in json.loads(sys.argv[1]) if a.get("role") != "system"]
except Exception: sys.exit(1)
if not isinstance(A, list) or not A: sys.exit(1)
now = D.datetime.now(D.timezone.utc)
def t(s):
    try: return D.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception: return None
def state(a):   # same order as pilo src/agentstate.js
    lim = t(a.get("limitedUntil") or "")
    if lim and lim > now: return "limited"
    if (a.get("gaveUp") or 0) > 0: return "gaveUp"
    st, ss, sig = a.get("status"), a.get("sessionStatus"), t(a.get("lastSignal") or "")
    if st == "running" and sig and ss != "working" and (now - sig).total_seconds() > 600: return "stalled"
    if st in ("blocked", "failed", "unbound"): return st
    return "running" if st == "running" or ss == "working" else "idle"
def line(a, s):
    def one(x, n=48):   # one line, cut at n display columns (wide characters count 2)
        import unicodedata as U
        o, w = "", 0
        for ch in " ".join(str(x or "").split()):
            w += 2 if U.east_asian_width(ch) in "WF" else 1
            if w > n: return o + "…"
            o += ch
        return o
    if s == "blocked": return one(a.get("blockedQuestion")) or "waiting on a decision"
    if s == "limited": return "limited · until " + t(a["limitedUntil"]).astimezone().strftime("%m.%d %H:%M")
    w = {"gaveUp": "wake failed", "stalled": "stalled", "failed": "failed", "unbound": "no session", "running": "running", "idle": "idle"}[s]
    p = one(a.get("progress") or a.get("activity"))
    return p if s == "running" and p else (one(w + " · " + p) if p and s != "idle" else w)
S = {a["id"]: state(a) for a in A}
RANK = ["blocked", "failed", "gaveUp", "stalled", "running", "limited", "unbound", "idle"]
print(min(S.values(), key=RANK.index), sum(1 for v in S.values() if v == "blocked"), sep="\t")
ids = {a["id"] for a in A}
def walk(parent, seen):   # desk → PM → its workers (worker rows start with "· ")
    kids = [a for a in A if (a.get("parentAgentId") if a.get("parentAgentId") in ids else None) == parent and a["id"] not in seen]
    for a in sorted(kids, key=lambda a: (a.get("role") != "pilo", a["name"])):
        seen.add(a["id"])
        print(("· " if a.get("role") == "worker" else "") + a["name"], line(a, S[a["id"]]), S[a["id"]], sep="\t")
        walk(a["id"], seen)
walk(None, set())
' "$J") || miss
rm -f "$FAILS"

IFS=$'\t' read -r TOP NB <<<"$(head -1 <<<"$OUT")"
ST="$HOME/.cache/sketchybar/pilo"   # current state - pilo_anim.sh reads it and swaps frames. On a state change the first frame is drawn here right away
[ "$(cat "$ST" 2>/dev/null)" = "$TOP" ] || { echo "$TOP" > "$ST"; sketchybar --set pilo background.image="$PX/pilo_${TOP}_1.png"; }
sketchybar --set pilo drawing=on --set pilo.ul drawing=on
pgrep -qf '^/bin/bash .*/plugins/pilo_anim.sh$' || (CONFIG_DIR="$CONFIG_DIR" nohup /bin/bash "$CONFIG_DIR/plugins/pilo_anim.sh" >/dev/null 2>&1 &)

# Popup: the title carries the number of pending decisions. Row = character (row background image, 16×12pt) · name · one line. Text color = state color. Click opens the dashboard (inbox for pending decisions, agents otherwise)
PORT=$(cat "${PILO_HOME:-$HOME}/.pilo/port" 2>/dev/null || echo 48888)
scol() { case "$1" in blocked|stalled) echo $WARN ;; failed|gaveUp) echo $ERR ;; running) echo $TEXT ;; *) echo $TEXT3 ;; esac; }
i=0; a=(); rows=""; sts=""
while IFS=$'\t' read -r name text st; do
  tab=agents; [ "$st" = blocked ] && tab=inbox
  rows+="$name"$'\t'"$text"$'\t'"$(scol "$st")"$'\t'"open 'http://localhost:$PORT/#$tab'"$'\n'
  a+=(--set pilo.ul.p.$i background.image="$PX/pilo_s_${st}_1.png" background.image.scale=0.5 background.image.drawing=on
      background.image.padding_left=12 icon.padding_left=36 icon.color=$TEXT2)
  sts+="$st"$'\n'; i=$((i + 1))
done <<<"$(tail -n +2 <<<"$OUT")"
# Legend: one divider line at the bottom, then all 8 states as face · name · meaning. The faces move like the agent rows (their states are appended to pilo_rows; rows without a face are "-")
pad="icon.drawing=off label.drawing=off background.height=6"
a+=(--set pilo.ul.p.$i $pad --set pilo.ul.p.$((i + 1)) $pad background.height=1 background.color=$LINE background.padding_left=12 background.padding_right=12
    --set pilo.ul.p.$((i + 2)) $pad --set pilo.ul.p.$((i + 3)) label.font="$FONT:Bold:11.0" label.color=$TEXT2)
rows+=$'_\t-\t\t\n_\t-\t\t\n_\t-\t\t\n_\tLEGEND\t\t\n'; sts+=$'-\n-\n-\n-\n'; i=$((i + 4))
while IFS='|' read -r st text; do
  rows+="$st"$'\t'"$text"$'\t'"$(scol "$st")"$'\t\n'; sts+="$st"$'\n'
  a+=(--set pilo.ul.p.$i background.image="$PX/pilo_s_${st}_1.png" background.image.scale=0.5 background.image.drawing=on
      background.image.padding_left=12 icon.padding_left=36 icon.color=$TEXT2)
  i=$((i + 1))
done <<'LEGEND'
running|working
blocked|waiting on you - needs your answer
stalled|looks stuck - no signal for 10+ min
failed|failed - the task ended in an error
gaveUp|wake failed - the session did not respond
limited|usage limit - resting until it resets
unbound|no session - no window attached
idle|idle
LEGEND
# Divider width = text width of the longest row (name column 137 + columns × 6.9; the 12 on each side comes from the background padding - rounded down so it never widens the popup). An item with no text has zero width, so it is set here
LW=$(printf '%s' "$rows" | perl -CS -Mutf8 -F'\t' -lane '$_ = $F[1]; $w = length($_) + (() = /[\p{EastAsianWidth=W}\p{EastAsianWidth=F}]/g); $m = $w if $w > $m; END { printf "%d", 137 + $m * 6.9 }')
a+=(--set pilo.ul.p.$((i - 11)) width=${LW:-400})
printf '%s' "$sts" > "$HOME/.cache/sketchybar/pilo_rows"   # state per row - while the popup is open pilo_anim.sh moves the row faces too
# Popup placement: left edge = left end of the underline (like the other circles). If there is no room on the right, the right edge goes to the underline's right end and the popup grows leftwards:
#   underline left x + max popup width (PW) > display right edge − 5 → right, else left.  PW 500 = 12 padding each side + 137 name column + 48 text columns (7.2 each), rounded up
for _ in 1 2 3; do Q=$(sketchybar --query pilo.ul 2>/dev/null); [ -n "$Q" ] && break; sleep 0.1; done   # the query sometimes comes back empty - ask again
AL=$(printf '%s' "$Q" | PW="${PILO_POPUP_W:-500}" DISP="$(sketchybar --query displays 2>/dev/null)" /usr/bin/python3 -c '
import json, os, sys
try:
    k, r = next(iter(json.load(sys.stdin)["bounding_rects"].items())); x = r["origin"][0]
    f = next(d["frame"] for d in json.loads(os.environ["DISP"]) if d["arrangement-id"] == int(k.split("-")[1]))
    print("right" if x + int(os.environ["PW"]) > f["w"] - 5 else "left")   # item x is relative to the left edge of that display
except Exception: pass')
[ -n "$AL" ] && a+=(--set pilo.ul popup.align=$AL)   # unknown → keep the current alignment
POPUP_XA=("${a[@]}"); printf '%s' "$rows" | awk -F'\t' -v OFS='\t' '{ gsub(/ /, "\302\240", $2) } 1' | POPUP_KW=137 popup_rows pilo.ul "PILO$([ "$NB" -gt 0 ] && echo " · $NB waiting")"
