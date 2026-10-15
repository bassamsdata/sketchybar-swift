# Security changes

This edition fixes the concrete issues found at upstream commit
`0de8c10fbb466d38d746dee6e4921e5f04ab2dd3`.

| Reviewed issue | Resolution |
|---|---|
| TSV text could become shell click commands | Removed TSV command transport. JSON objects remain data. Popup callbacks contain random handles into an in-memory typed action registry; stale/unknown handles are rejected. |
| Shell interpolation of names/paths | Child processes receive argv vectors. The only shell strings are fixed SketchyBar callbacks serialized with `shlex.join`; untrusted labels never enter them. Numeric IDs/ports and volume are validated. |
| Background GitHub requests | GitHub/CI/PR integration removed. |
| Browser JavaScript and automatic artwork downloads | Browser helper and curl paths removed. Artwork is embedded media data only, with byte/dimension limits and private temporary files. |
| Nearby networks and popup details written to cache | Wi-Fi helper returns JSON via stdout. Popup actions stay in memory. Rendered rows are temporary private PNGs removed on close. Scanning is opt-in and on demand. |
| Cache permissions inherited from ambient umask | Private owned directory (700), umask 077, socket/lock/log/art (600), symlink rejection at sensitive file paths. |
| Stale PID kills and broad pkill matches | Removed. Only owned live subprocess handles are terminated and reaped. Singleton runtime uses a file lock/private socket. Caffeinate also waits for the runtime PID. |
| Environment-controlled eval restart hook | Removed with the old health script. No eval or arbitrary launchctl matching. |
| Installer replaces config before compilation succeeds | Compile/validate in same-filesystem staging, then atomic directory publish with backup/rollback. No package installation/upgrade or service actions. |
| Unneeded helper permissions | Browser and Rectangle helpers removed; calendar/Wi-Fi permission requests occur on use. Per-feature switches prevent unnecessary runtime queries. |
| Excessive subprocess/animation polling | Consolidated runtime, CLI event streams, coalescing, property deduplication, low-rate recovery and on-demand inventories. Original artwork is generated locally; bounded animations share one owned task and send only changed properties. |

Same-user processes can operate the user's bar/WM and read same-user files; the
IPC socket is not intended to isolate mutually untrusted programs running as
the same macOS account. External dependencies, macOS frameworks, updates and
the user's other configurations are not certified vulnerability-free by this
review. This source contains no remote-code downloader and no runtime credential
upload. Dependency hashes are installation evidence, not vulnerability pins.

The previous upstream `~/.cache/sketchybar` is deliberately not deleted: another
configuration may still use it. If you previously installed upstream, its old
SSID/calendar/popup cache may still exist. Review and remove it yourself once
that configuration is no longer in use. This edition uses a separate private
runtime directory and never reads that old cache.
