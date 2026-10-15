"""Presentation and bounded geometry for the original island design."""

import math
import unicodedata

from runtime import command, text


def text_width(value, size=12):
    # JetBrains Mono 12 has a 7.2pt advance. Reserve extra room for fallback glyphs.
    return (
        size
        / 12
        * sum(
            0
            if unicodedata.combining(c)
            else 15
            if unicodedata.east_asian_width(c) in "WF"
            else 7.3
            for c in value
        )
    )


def fit_text(value, width, size=12):
    value = text(value, 4096)
    if text_width(value, size) <= width:
        return value
    out = ""
    for char in value:
        if text_width(out + char + "…", size) > width:
            break
        out += char
    return out + "…" if width >= 7.3 * size / 12 else ""


def popup_geometry(
    parent_x, parent_width, width, screen_x, screen_width, prefer_right=False
):
    left = parent_x
    right = parent_x + parent_width - width
    if prefer_right and right >= screen_x + 5:
        align, anchor = "right", right
    elif left + width <= screen_x + screen_width - 5:
        align, anchor = "left", left
    elif right >= screen_x + 5:
        align, anchor = "right", right
    else:
        align, anchor = "center", parent_x + (parent_width - width) / 2
    target = max(screen_x + 5, min(anchor, screen_x + screen_width - width - 5))
    return align, round(target - anchor)


def media_geometry(left_end, notch_left, controls_width, gap=5, left_gap=None):
    left_gap = gap if left_gap is None else left_gap
    available = max(0, notch_left - gap - (left_end + left_gap))
    return max(0, math.floor(available - controls_width)), available


def build(bar):
    p, flags = bar.palette, bar.flags
    args, created = [], set()
    height = bar.cfg["height"]
    containers = bar.cfg["containers"]
    bg = f"0x{int(bar.cfg['opacity'] * 255 / 100):02x}" + p["bg"][4:]
    surface = bg[:4] + p["surface"][4:]

    def item(name, position, label="", **props):
        created.add(name)
        args.extend(["--add", "item", name, position, "--set", name, "label=" + label])
        args.extend(k + "=" + str(v) for k, v in props.items())

    def set_props(name, **props):
        args.extend(["--set", name])
        args.extend(k + "=" + str(v) for k, v in props.items())

    def callback(name):
        return command(name if name.startswith("media.") else "popup." + name)

    def plate(name, position, width, color, plate_height, radius=0, **props):
        item(
            name,
            position,
            **{
                "label.width": width,
                "label.drawing": "on",
                "icon.drawing": "off",
                "background.drawing": "on",
                "background.color": color,
                "background.height": plate_height,
                "background.corner_radius": radius,
                **props,
            },
        )

    def spacer(name, position, width):
        item(name, position, width=width, **{"label.drawing": "off"})

    def shape(container, circle=False):
        cfg = containers[container]
        h = cfg["height"] or height
        radius = cfg["corner_radius"]
        if radius == -1:
            radius = bar.cfg["circle_radius" if circle else "corner_radius"]
        return {
            "background.drawing": "on",
            "background.color": bg,
            "background.height": h,
            "background.corner_radius": min(radius, h // 2),
            "background.border_width": cfg["border_width"],
            "background.border_color": p["line"],
            "y_offset": 0,
        }

    def bracket(name, members, container, color=bg, circle=False):
        members = [n for n in members if n in created]
        if members:
            args.extend(["--add", "bracket", name, *members])
            set_props(name, **{**shape(container, circle), "background.color": color})

    args.extend(
        [
            "--bar",
            "position=top",
            f"height={height}",
            f"notch_display_height={height}",
            "color=0x00000000",
            "blur_radius=0",
            "shadow=off",
            "margin=" + str(bar.cfg["margin"]),
            "y_offset=5",
            "padding_left=0",
            "padding_right=0",
            "border_width=0",
            "topmost=window",
            "display=" + str(bar.cfg["display"]),
            "--default",
            "updates=off",
            "icon.font=" + bar.cfg["font"] + ":Regular:" + str(bar.cfg["font_size"]),
            "label.font=" + bar.cfg["font"] + ":Regular:" + str(bar.cfg["font_size"]),
            "icon.drawing=off",
            "label.drawing=on",
            "icon.color=" + p["dim"],
            "label.color=" + p["text"],
            "padding_left=0",
            "padding_right=0",
            "icon.padding_left=0",
            "icon.padding_right=0",
            "label.padding_left=0",
            "label.padding_right=0",
            "y_offset=1",
            "popup.align=left",
            "popup.height=1",
            "popup.y_offset=2",
            "popup.background.drawing=on",
            "popup.background.color=" + surface,
            "popup.background.border_color=" + p["line"],
            "popup.background.border_width=1",
            "popup.background.corner_radius=" + str(bar.cfg["popup_corner_radius"]),
            "popup.blur_radius=" + str(bar.cfg["popup_blur"]),
            "--add",
            "event",
            "shell_cwd",
            "--add",
            "event",
            "theme_change",
            "AppleInterfaceThemeChangedNotification",
        ]
    )
    item("events", "left", drawing="off", updates="on", script=command("event"))
    args.extend(
        [
            "--subscribe",
            "events",
            "front_app_switched",
            "system_woke",
            "display_change",
            "volume_change",
            "wifi_change",
            "power_source_change",
            "theme_change",
            "shell_cwd",
        ]
    )

    spacer("left.pad", "left", containers["left"]["padding"])
    item(
        "wordmark",
        "left",
        fit_text(bar.cfg["wordmark"], 175),
        **{"label.padding_right": 2},
    )
    plate("wordmark.cursor", "left", 6, p["accent"], 11)
    spacer("wordmark.pad", "left", containers["left"]["item_gap"])
    if flags["workspaces"]:
        item(
            "workspaces",
            "left",
            "— ▾",
            **{
                "icon.padding_left": 8,
                "label.padding_right": 8,
                "icon.color": p["text"],
                "label.color": p["muted"],
            },
            click_script=callback("workspaces"),
        )
    if flags["workspaces"]:
        spacer("workspaces.gap", "left", containers["left"]["item_gap"])
    if flags["front_app"]:
        item(
            "front_app",
            "left",
            "—",
            click_script=callback("front_app"),
            **{"label.color": p["muted"]},
        )
    for name in ("folder", "next_event"):
        if flags[name]:
            item(
                name,
                "left",
                drawing="off",
                **{"label.padding_left": containers["left"]["item_gap"]},
                click_script=callback(name),
            )
    spacer("left.end", "left", containers["left"]["padding"])
    left = [n for n in created if n not in ("events", "spaces.cell")]

    # Create progress plates before q items so they stay behind all media text.
    if flags["media"]:
        for name, color, radius in (
            ("media.fill", p["fill"], 11),
            ("media.mask", p["line"], 0),
            ("media.round", p["line"], 11),
        ):
            plate(name, "left", 0, color, height - 4, radius, drawing="off", y_offset=0)
    if flags["media"]:
        spacer("notch.gap", "q", containers["media"]["gap"])
        spacer("media.pad.right", "q", containers["media"]["padding"])
    if flags["media"]:
        for name, label, width in (
            ("media.next", "»", 24),
            ("media.play", "▶", 26),
            ("media.prev", "«", 24),
        ):
            if name != "media.next":
                spacer(name + ".gap", "q", containers["media"]["item_gap"])
            item(
                name,
                "q",
                label,
                click_script=callback(name),
                **{
                    "label.width": width,
                    "label.align": "center",
                    "label.color": p["dim"],
                },
            )
        item(
            "media",
            "q",
            "—",
            click_script=callback("media"),
            **{
                "icon": "media",
                "icon.drawing": "on",
                "icon.padding_right": 8,
                "label.width": 100,
                "label.color": p["dim"],
            },
        )
        for n in (3, 2, 1):
            plate(
                f"media.eq.{n}",
                "q",
                2,
                p["dim"],
                2,
                padding_left=containers["media"]["padding"] if n == 1 else 0,
                padding_right=8 if n == 3 else 2,
                **{"background.y_offset": -4, "click_script": callback("media")},
            )

    main = containers["right"]
    spacer("right.gap", "right", main["gap"])
    spacer("main.pad.right", "right", main["padding"])
    item(
        "clock",
        "right",
        "—",
        click_script=callback("clock"),
        **{"popup.align": "right"},
    )
    for name in ("volume", "wifi", "battery", "usage", "notifications"):
        if not flags[name]:
            continue
        spacer("main.gap." + name, "right", main["item_gap"])
        if name in ("volume", "battery"):
            for n in range(5, 0, -1):
                plate(
                    f"{name}.{n}",
                    "right",
                    4,
                    p["line"],
                    10,
                    **{
                        "label.padding_right": 0 if n == 5 else 2,
                        "click_script": callback(name),
                    },
                )
            props = {
                "icon": "bat",
                "icon.drawing": "on",
                "icon.padding_right": 6,
                "label.drawing": "off",
                "popup.align": "right",
            }
            if name == "volume":
                props.update(
                    {
                        "icon": "\U000f057e",
                        "icon.width": 20,
                        "icon.font": "JetBrainsMono Nerd Font Mono:Regular:12.0",
                    }
                )
            item(name, "right", click_script=callback(name), **props)
        elif name == "wifi":
            item(
                name,
                "right",
                "—",
                click_script=callback(name),
                **{
                    "icon": "wifi",
                    "icon.drawing": "on",
                    "icon.padding_right": 6,
                    "popup.align": "right",
                },
            )
        elif name == "usage":
            for provider, filename in (
                ("codex", "openai.png"),
                ("claude", "claude.png"),
            ):
                if provider == "claude":
                    spacer("usage.gap", "right", main["item_gap"])
                item(
                    "usage." + provider,
                    "right",
                    "—",
                    drawing="off",
                    click_script=callback("usage"),
                    **{
                        "icon.drawing": "on",
                        "icon.padding_right": 6,
                        "icon.width": 18,
                        "icon.background.drawing": "on",
                        "icon.background.image": str(bar.pixels / filename),
                        "icon.background.image.scale": 0.5,
                        "icon.background.image.drawing": "on",
                    },
                )
            # Zero-width popup anchor, without external padding. Fixed-width
            # items with padding make bracket bounds extend into adjacent islands.
            item(
                "usage",
                "right",
                drawing="off",
                click_script=callback("usage"),
                width=0,
                **{"icon.drawing": "off", "label.drawing": "off"},
            )
        else:
            item(
                name,
                "right",
                drawing="off",
                click_script=callback(name),
                **{"icon": "notif", "icon.drawing": "on", "icon.padding_right": 6},
            )
    spacer("main.pad.left", "right", main["padding"])
    right = [
        n
        for n in created
        if n == "clock"
        or n.startswith("main.")
        or n in ("volume", "wifi", "battery", "usage", "notifications")
        or n.startswith(("volume.", "battery.", "usage."))
    ]

    if flags["tailscale"] or flags["ports"]:
        apps = containers["apps"]
        spacer("apps.gap", "right", apps["gap"])
        spacer("apps.pad.right", "right", apps["padding"])
        for index, name in enumerate(n for n in ("tailscale", "ports") if flags[n]):
            if index:
                spacer("apps.item.gap", "right", apps["item_gap"])
            item(
                name,
                "right",
                click_script=callback(name),
                **{
                    "icon.drawing": "on",
                    "icon.width": 12,
                    "icon.background.image": str(
                        bar.pixels
                        / ("ts_off.png" if name == "tailscale" else "port.png")
                    ),
                    "icon.background.image.scale": 0.5,
                    "icon.background.drawing": "on",
                    "icon.background.image.drawing": "on",
                    "label.drawing": "off",
                    "y_offset": 0,
                },
            )
        spacer("apps.pad.left", "right", apps["padding"])
    for name, container in (("system", "cat"), ("settings", "settings")):
        if name == "system" and not flags["system"]:
            continue
        cfg = containers[container]
        h = cfg["height"] or height
        spacer(container + ".gap", "right", cfg["gap"])
        item(
            name,
            "right",
            click_script=callback(name),
            **{
                "icon.drawing": "on",
                "icon.width": h,
                "icon.align": "center",
                "label.drawing": "off",
                "icon": "\U000f062e" if name == "settings" else "",
                "icon.color": p["text"],
                "icon.font": "JetBrainsMono Nerd Font Mono:Regular:14.0",
                **shape(container, circle=True),
            },
        )
        if name == "system":
            set_props(
                name,
                **{
                    "background.image": str(bar.pixels / "cat_1.png"),
                    "background.image.scale": h / 66,
                    "background.image.drawing": "on",
                },
            )

    bracket("island.left", left, "left")
    # Keep the workspace plate above the enclosing island.
    if flags["workspaces"]:
        args.extend(["--add", "bracket", "spaces.background", "workspaces"])
        set_props(
            "spaces.background",
            **{
                **shape("left"),
                "background.color": p["surface"],
                "background.height": max(
                    16, (containers["left"]["height"] or height) - 8
                ),
                "background.corner_radius": 6,
            },
        )
    bracket("island.right", right, "right")
    media = [
        n
        for n in created
        if n.startswith("media.")
        and n not in ("media.fill", "media.mask", "media.round")
    ]
    media += [n for n in ("media",) if n in created]
    bracket("island.media", media, "media", p["line"])
    bracket(
        "apps.cap",
        ["apps.pad.left", "apps.pad.right", "apps.item.gap", "ports", "tailscale"],
        "apps",
        circle=True,
    )
    args.extend(["--add", "bracket", "shield", "wordmark", "clock"])
    set_props(
        "shield",
        **{
            "background.drawing": "on",
            "background.color": "0x00000000",
            "background.height": height,
            "y_offset": 0,
        },
    )
    bar.created = created
    return args
