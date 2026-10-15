"""Locally rendered popup rows, with typed callbacks kept in the runtime."""

import json
import secrets

from runtime import ROOT, run, text

WIDTHS = {
    "clock": 280,
    "wifi": 261,
    "volume": 261,
    "usage": 368,
    "tailscale": 337,
    "system": 261,
    "ports": 337,
    "workspaces": 337,
    "front_app": 300,
    "settings": 300,
    "media": 337,
}


def popup_width(cfg, parent, screen_width):
    scale = cfg["font_size"] / 12
    return int(
        min(cfg["popup_width"] or WIDTHS.get(parent, 300) * scale, screen_width - 10)
    )


async def rows(bar, parent, title, entries, width):
    scale = bar.cfg["font_size"] / 12
    data = [{"label": title, "kind": "title", "height": round(24 * scale)}]
    allowed = {
        "left",
        "label",
        "right",
        "kind",
        "height",
        "color",
        "left_color",
        "right_color",
        "bold",
        "align",
        "key_width",
        "percent",
        "cells",
        "icon",
        "image",
    }
    for entry in entries:
        record = {key: value for key, value in entry.items() if key in allowed}
        for key in ("left", "label", "right"):
            record[key] = text(record.get(key, ""), 4096)
        record["height"] = round(entry.get("height", 24) * scale)
        if entry.get("slider"):
            record.update(kind="slider", right=record["label"], label="")
        if entry.get("image"):
            record["kind"] = "image"
        data.append(record)
    prefix = "art-popup-" + secrets.token_hex(8)
    payload = {
        "width": width,
        "font": bar.cfg["font"],
        "font_size": bar.cfg["font_size"],
        "palette": bar.palette,
        "rows": data,
    }
    result = await run(
        ROOT / "helper/render",
        "rows",
        bar.cache,
        prefix,
        input_data=json.dumps(payload).encode(),
        timeout=5,
    )
    try:
        paths = json.loads(result)
        expected = [str(bar.cache / f"{prefix}-{i}.png") for i in range(len(data))]
        return paths if paths == expected else []
    except (ValueError, TypeError):
        return []
