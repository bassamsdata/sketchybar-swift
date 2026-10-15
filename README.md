# sketchybar-island — personal, hardened edition

A notch-aware SketchyBar configuration for macOS, adapted from
[garamnohhh/sketchybar-island](https://github.com/garamnohhh/sketchybar-island).
The bar keeps the rounded islands, dark/light themes and compact popups, with
AeroSpace/OmniWM virtual workspaces and a quieter runtime.

The upstream screenshots in `screenshots/` are the visual reference. This edition
restores the cursor, original pixel cat/port/Tailscale art, five-cell gauges,
agent glyphs, equalizer and media progress fill within the hardened runtime.
The workspace cell retains the AeroSpace/OmniWM behavior described below.

## Included

- Wordmark, focused workspace and focused app/menu popup.
- Media information and controls via media-control (Apple Music excluded).
- Volume slider, mute and audio/Bluetooth output switching.
- Date/time, month calendar, optional upcoming event and holiday calendar colors.
- Wi-Fi/IP/router; scanning and saved-network switching are opt-in.
- Battery and an owned keep-awake process; this does not override lid-close rules.
- Cached Claude Code/Codex usage, CPU/RAM/SSD, development ports and Tailscale.
- Optional folder/Git branch, Dock badge totals and a settings popup.

Removed: GitHub/gh/CI/PR widgets, Docker/OrbStack integration, Ollama model queries,
Pilo, Apple Music fallback, Rectangle auto-maximize, browser JavaScript and remote
artwork downloads. Visual animation uses one owned task in the existing runtime:
the cat runs at up to four frames/second, cursor at 1 Hz, and equalizer at 2 Hz.
Set `animations: false` for static artwork; macOS Reduce Motion also makes it static.
`wordmark_animation` controls only cursor blinking and defaults to false, leaving
the cat animated when `animations` is true.

## Workspaces

`window_manager` accepts `auto`, `aerospace`, `omniwm` or `off`.
`auto` prefers a responding AeroSpace and falls back to a responding OmniWM.
The OmniWM CLI is also found inside `/Applications/OmniWM.app`.

The cell shows `3 ▾`, or `3 [max] ▾` when maximized. Click to expand a popup of
**occupied workspaces only**, including their app names/window counts. Click a
row to focus it. Occupied workspaces across monitors are included. An empty
current workspace is still shown on the bar but excluded from the popup.

For AeroSpace, `[max]` is its own `fullscreen` state, not native macOS Full Screen.
For OmniWM, it reflects `isFullscreen`. OmniWM Niri column width/maximize is not
the same state and is not inferred from window geometry.

Current CLIs provide subscriptions, so **no WM configuration hooks are required**:

- AeroSpace: `subscribe` focus/workspace/monitor/window/binding events.
- OmniWM: `subscribe` active-workspace/focus/windows/layout channels.

Events coalesce for 150 ms. A 30 s recovery check handles missing events, CLI
commands outside bindings, WM restarts and switching managers. Full window
inventory is queried only while the popup is open. Neither native macOS Spaces
nor Rectangle controls are used. The bar never changes your WM configuration.

OmniWM also requires **Enable IPC** in its status bar menu; IPC is disabled by
default. Its bundled CLI is preferred to prevent client/app protocol mismatches.
The workspace cell distinguishes `omni IPC`, `omni auth`, and `omni version`
errors from an active workspace; click it for the corresponding explanation.
After enabling IPC, the 30-second recovery check connects automatically.

References: [AeroSpace guide](https://nikitabobko.github.io/AeroSpace/guide),
[AeroSpace commands](https://nikitabobko.github.io/AeroSpace/commands),
[OmniWM queries](https://omniwm.app/reference/cli/queries/),
[OmniWM events](https://omniwm.app/reference/cli/events/).

## Prerequisites and installation

macOS 14+, Python 3.9+, Xcode Command Line Tools, SketchyBar, JetBrains Mono
and JetBrainsMono Nerd Font Mono (settings and volume glyphs; Claude/Codex use bundled local artwork).
AeroSpace/OmniWM have their own OS requirements. OmniWM needs macOS 26+.
`media-control` is optional; disable `features.media` if not installed.

Install prerequisites separately using the package sources/versions you trust:

```sh
brew tap FelixKratz/formulae
brew install sketchybar
brew install --cask font-jetbrains-mono font-jetbrains-mono-nerd-font
brew install media-control  # only if keeping the media widget
```

The installer **does not install or upgrade packages**, download scripts, edit
shell/WM configuration, grant permissions or start/restart any service. It
validates the JSON and compiles local Swift sources into a staging directory
before touching the destination. Dependencies remain separately maintained; an
installation records their binary paths and SHA-256 hashes for reference in
`installed-dependencies.json`, not as a vulnerability audit or a package lock.

```sh
make check
bash install.sh
# Alternative isolated destination:
bash install.sh --dest /absolute/path/to/sketchybar
```

An existing real `~/.config/sketchybar` is backed up with a unique timestamp only
after preparation succeeds. A failed directory publish restores the previous
configuration. Symlink destinations are rejected; choose a separate real
destination if your dotfiles use a symlink. Custom destinations require passing
their config to SketchyBar explicitly.

Review `~/.config/sketchybar/config.json`, then start when ready:

```sh
brew services start sketchybar
# If SketchyBar was already running:
sketchybar --reload
```

If a service is already running during installation, it continues using its
existing runtime until you reload/restart it. The installer does not manage
another configuration's processes.

## Configuration and permissions

Edit `config.json`; it is validated data and never sourced as shell code.
The settings popup opens it in the default text editor and provides a validated
reload action. Appearance settings (points, unless noted):

| Setting | Default | Meaning |
|---|---:|---|
| `width` | `0` | Automatic display width; a positive value centers a narrower bar area (minimum 600). |
| `margin` | `5` | Minimum outside horizontal margin. |
| `corner_radius` | `13` | Island corners. |
| `circle_radius` | `16` | Settings/cat circles and the ports/Tailscale capsule. |
| `popup_corner_radius` | `0` | Popup corners; zero matches the reference screenshots. |
| `popup_width` | `0` | Per-popup reference widths; positive values override them (minimum 180). |
| `height` | `30` | Bar and island height; circles and cat artwork scale with it. |
| `font` | `CommitMonoGhostty` | Installed font family for bar text and popup text. |
| `font_size` | `12` | Text size, 9–20; popup rows and reference widths scale with it. |
| `wm_number_bold` | `true` | Bold only the leading workspace number; names, max status, and dropdown arrow remain regular. |
| `cat_grass_color` | `"auto"` | Use a muted version of the theme accent, or set an explicit `"#RRGGBB"`; `"#26795a"` restores the original green. |

`containers` accepts independent overrides for `left` (wordmark/workspaces/app),
`right` (usage/battery/sound/clock), `media`, `apps` (ports/Tailscale), `cat`, and
`settings`. Island defaults: `padding: 12`, `item_gap: 12` (`right: 14`), `gap: 8` (`right: 0`),
`height: 0`, `corner_radius: -1`, `border_width: 1`. `height: 0` inherits the bar
height; positive values must be 16 or greater and no taller than the bar.
`corner_radius: -1` inherits the global island/circle radius. `gap` is the empty
space to the next container on its right. For `right` it adds an inset from the
screen edge, for `left` it separates optional media, and for `media` it separates
the notch. Circles use
`gap`, `height`, `corner_radius`, and `border_width`; padding/item gaps apply to
islands. For example, adjust the capsule and main groups without changing code:

```json
"containers": {
  "apps": {"gap": 10, "padding": 12, "item_gap": 14, "corner_radius": 10},
  "right": {"padding": 12, "item_gap": 14}
}
```

The dev Avra.nvim Appearance module exports its current palette to
`appearance.json` and runs `sketchybar --reload` after explicit colorscheme or
background changes. `:Appearance sketchybar off` restores the configured
SketchyBar theme; `:Appearance refresh` forces synchronization. The generated
file contains only validated color data with an ownership marker and checksum;
it never changes layout or feature settings and makes no network requests.

Reload after editing. A narrow width or larger font can require disabling some
widgets to leave sufficient space around the notch. `features.media` is false;
volume remains independently configurable and sits immediately left of the clock.
`features.wifi` is false. The personal font default matches the installed Ghostty
font; select another installed family if using this configuration elsewhere. Claude/Codex cells remain visible
when the corresponding local tool directory exists; `—` means no fresh cached
usage, and no network request is made to obtain it.

`work_dir` defaults to `~/Repos`. Individual `features` booleans
disable both the item and its work. Clock/settings/wordmark remain available.

`calendar_names: []` reads all calendars; provide an explicit list of calendar
names to restrict access. `holiday_calendar` colors events from that calendar.
`features.calendar=false` keeps the clock/month grid without reading events.
`features.next_event` is separate and off by default. Calendar queries request
Calendars access for **SketchyBar Events** only when that feature is used.

`features.wifi_scan` is off by default. Turning it on lets opening the Wi-Fi popup
request Location for **SketchyBar WifiScan**, scan nearby networks and offer saved
networks for switching. Network names are not written to disk. Without Location,
macOS may hide the current SSID; the cell still shows on/off and the popup IP/router.
No verbose-network logging, sudo command or Shortcuts automation is required.

App-menu control and outside-click observation can require Accessibility for
SketchyBar/helper processes. Grant only what retained features need. Basic
workspace queries use the existing WM CLI; the WM manages its own permissions.

For the optional folder/branch cell, enable `features.folder` and add this to zsh:

```zsh
_sb_cwd() { sketchybar --trigger shell_cwd CWD="$PWD" &! }
precmd_functions+=(_sb_cwd)
```

## Performance and privacy

One Python standard-library process owns the runtime. WM, audio and media
subscriptions stay asleep between events. Media progress-only diffs stay in
memory; they do not launch an extra media CLI query. Popup details are gathered
on demand. Popup rows are rendered with a local AppKit helper, using bundled
SVG icons and your configured font. No runtime icon/font download occurs. Changed properties alone are sent to SketchyBar.

Sleep/wake query failures keep the runtime and click IPC alive. Failed health
queries retry every 5 seconds, returning to the normal 30-second interval on
recovery. Wake/display changes and query recovery clear cached properties,
close stale popups, remeasure the display and refresh enabled widgets. Runtime
start/stop, shutdown reasons and query failure/recovery transitions are logged
without widget contents.

| Work | Frequency |
|---|---|
| WM focus/workspace/maximize | Events + 30 s recovery |
| Occupied workspace/app inventory | On expand / events while open |
| CPU/RAM | 15 s |
| Clock | 30 s (minute-resolution display) |
| Wi-Fi, battery, usage, Dock badges, Tailscale | 60 s + applicable OS events |
| Media | Event stream + 30 s fallback |
| Volume | CoreAudio/SketchyBar events + 60 s fallback |
| Media timeline while its popup is open | 5 s |
| Media progress plate | 2 s while a track is available |
| Cat / cursor / equalizer | Up to 4 / 1 / 2 Hz; changed properties batched |
| Ports, SSD, calendar, app menus, audio device list | On click |

There are **no automatic HTTP requests in this configuration**. It calls local
WM/media/audio/Tailscale utilities; their independently running applications may
have their own networking. Explicit links open localhost services, Tailscale
admin or screen sharing only on a click. Usage is read from local usage caches
and session logs; no credential store or auth-token file is queried.

Runtime IPC/lock/diagnostics live under `~/.cache/sb-island-<config-hash>` with
directory mode 700 and file/socket mode 600. Popup actions stay in memory. Rendered popup rows (which can contain event
names, SSIDs and peer names) are temporary private PNGs, mode 600 under the mode
700 runtime directory. They are removed on popup close or graceful shutdown.
Embedded, size/dimension-limited media artwork follows the same lifecycle. A forced OS/process crash may leave this one private image;
it is cleared on the next runtime start. Diagnostics contain generic failures,
not raw command output or labels. Invalid config leaves the old runtime active.

See [security notes](docs/security.md) and [validation](docs/validation.md).

## Development

```sh
make check                  # configuration, Bash syntax, regression tests
bash helper/build.sh --output /tmp/sketchybar-helpers
python3 plugins/bar.py check
```

Presentation: `plugins/layout.py` (islands, fitting, popup geometry),
`plugins/pixels.py` (original upstream artwork, standard library PNG generation).
Popups use explicit column budgets, adaptive alignment, bounded row counts and
6pt outer padding. Media width follows the left island and measured notch edge,
with 5pt gaps; controls collapse when space is limited.

Core code: `plugins/runtime.py` (process/IPC/config safety), `plugins/wm.py`
(backends), `plugins/bar.py` (events/UI), `plugins/widgets.py` (queries/actions).
No additional Python packages are required. The small Swift helpers use macOS
frameworks and are built locally, never downloaded as binaries.

MIT license for this configuration; SketchyBar and dependencies have their own
licenses. Original design/configuration by garamnohhh; SketchyBar by Felix Kratz;
media-control by ungive; JetBrains Mono by JetBrains.

Bundled `assets/openai.svg` and `assets/claude.svg` are from
[Microsoft VS Code Codicons](https://github.com/microsoft/vscode-codicons),
licensed under CC BY 4.0 (see `assets/LICENSE.codicons`), rendered locally with
colors matching this configuration. Other small SVGs are drawn locally for this
configuration. There are no external SVG references or scripts in these assets.
