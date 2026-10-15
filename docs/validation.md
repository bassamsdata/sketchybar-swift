# Validation

Validation is designed to avoid changing the active window manager or granting
macOS permissions during development.

- `make check` runs typed configuration validation, Bash parsing and Python
  regression tests. Tests cover popup text injection, random/stale action
  handling, literal path/workspace/SSID arguments, volume validation, private
  filesystem/IPC permissions, event coalescing/deduplication, cancellation and
  child limits, installer rollback, Apple Music exclusion, and both WM schemas.
- All seven retained Swift helpers compile locally with Xcode Command Line Tools.
  The Calendar and Wi-Fi bundles are ad-hoc signed with their privacy strings.
  Building them does not grant permissions or launch them.
- A read-only AeroSpace query was exercised with installed 0.21.3-Beta. It
  returned the current workspace, its fullscreen flag and seven occupied
  workspaces in about 76 ms on the development Mac. This is one query measurement,
  not a benchmark of steady-state CPU, battery impact or all machines.
- Installed OmniWM CLI help confirmed the query, field, subscribe and focus
  commands. OmniWM was not running, so its response/event schema is tested with
  fixtures matching the official source/docs, not a live OmniWM session.
- On 2026-10-13 the restored configuration was installed with an automatic backup
  and reloaded on SketchyBar 2.24.1, on a 1512×982pt notch display. Live item queries
  confirmed 5pt gaps before media and before the notch, 4pt gauge cells, a 6pt
  cursor, and changing 33pt cat image frames. All twelve enabled popups opened
  and closed without running their actions; their row windows stayed on screen.
  The computer-use capture exposed only Finder's window, so this is geometry
  verification rather than a full-screen screenshot comparison.
- Regression tests now cover Unicode/long text fitting, left/right popup anchors
  including negative display origins, short-screen row limits, optional-feature
  combinations, artwork row height, slider/text width budgets, popup padding
  order, and clamped progress plates. Security regressions continue to pass.
- Sleep/wake regressions simulate repeated empty health replies, recovery and
  stale cached properties. An IPC integration test verifies that a failed
  periodic probe leaves the event socket alive to receive wake and shutdown
  events, and that explicit shutdown still cleans up tasks and the socket.
  On 2026-10-14, the patched runtime was installed with a file backup and
  reloaded while preserving the active config and appearance files. The live
  Settings click callback opened/closed its popup before and after a simulated
  `system_woke` event; that event also closed the stale popup. This checks event
  handling, not a physical sleep/wake cycle.

On additional machines, inspect notch/external-monitor layouts, switch workspaces
and toggle AeroSpace fullscreen, open occupied-workspace/media/volume popups,
exercise calendar permission if desired, and confirm CPU/battery behavior in
Activity Monitor. Enable Wi-Fi scanning only if wanted, then test its Location
prompt and saved-network switching. The runtime's private `runtime.log` records
generic errors if a helper or widget is unavailable.


The second visual revision disables media by default, fixes the disabled icon
backgrounds, and vendors Codicons SVGs with their CC BY 4.0 attribution/license.
A seventh Swift helper renders local SVGs and bounded popup rows from JSON over
stdin; it has no network or shell execution. Reference previews were generated
and inspected for calendar, usage and Wi-Fi. Configuration tests cover width,
corners, font settings, local icon drawing, provider visibility without a fresh
cache, usage gauges, and the colored seven-column calendar. Popup PNGs follow
the private `art-*` cleanup lifecycle.

After the second revision, all eleven enabled popups were opened and closed.
Every content row used a local PNG and stayed within the display bounds. Ports,
Tailscale, Claude and Codex all had visible local image backgrounds; media items
were absent. Closing popups removed all temporary row images. A controlled
reload ended with an empty runtime diagnostic log. The native renderer also
rejected a symlink output without modifying its target.

The third revision disables Wi-Fi, moves volume into the right island beside the
clock, sets height to 30pt, and selects the installed CommitMonoGhostty family
from the user's Ghostty configuration. Circles and cat image scaling now follow
height. OmniWM's CLI is present and the app is running, but the user's OmniWM
settings explicitly contain `ipcEnabled = false`; the socket is absent. This
setting was not changed. Error envelopes are retained for typed diagnostics,
and the bar now explains the missing IPC connection instead of saying `wm off`.
