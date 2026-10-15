"""Original upstream pixel artwork, generated locally without dependencies."""

import struct
import zlib

from runtime import private_dir, private_file


def rgba(value):
    value = int(value, 16)
    return ((value >> 16) & 255, (value >> 8) & 255, value & 255, value >> 24)


def png(path, rows):
    height, width = len(rows), len(rows[0])
    raw = b"".join(
        b"\0" + b"".join(bytes(c or (0, 0, 0, 0)) for c in row) for row in rows
    )

    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    import os

    fd = private_file(path, truncate=True)
    with os.fdopen(fd, "wb") as file:
        file.write(data)


def generate(cache, palette, grass_color="#26795a"):
    output = private_dir(cache / "pixels")
    foreground = rgba(palette["text"])
    muted = rgba(palette["dim"])
    warning = rgba(palette["warn"])

    def bitmap(name, lines):
        rows = [[foreground if c == "#" else None for c in line] for line in lines]
        rows = [[c for c in row for _ in range(2)] for row in rows for _ in range(2)]
        png(output / name, rows)

    bitmap(
        "port.png",
        [
            "...........",
            "###########",
            "#.........#",
            "#.#.#.#.#.#",
            "#.........#",
            "#.........#",
            "#.........#",
            "###.....###",
            "..#.....#..",
            "..#######..",
            "...........",
        ],
    )
    for enabled in (False, True):
        lit = {(1, 0), (1, 1), (1, 2), (2, 1)} if enabled else set()
        rows = [[None] * 22 for _ in range(22)]
        for r in range(3):
            for c in range(3):
                color = foreground if (r, c) in lit else muted
                for y in range(6):
                    for x in range(6):
                        rows[r * 8 + y][c * 8 + x] = color
        png(output / ("ts_on.png" if enabled else "ts_off.png"), rows)

    top = [
        "...........#..#.",
        "#..........####.",
        "#..........#.##.",
        ".#.........####.",
        "..#############.",
        "..############..",
        "..###########...",
    ]
    legs = [
        [".##.........##..", "#.............#.", "................"],
        ["..#.#.....#.#...", "..#..#...#..#...", "................"],
        ["...##.....##....", "....#.....#.....", "....#.....#....."],
        ["..#.#.....#.#...", "..#..#...#..#...", "................"],
    ]
    blade = rgba(palette["fill"] if grass_color == "auto" else "0xff" + grass_color[1:])
    pattern = [0, 2, 1, 0, 2, 0, 1, 2, 0]
    for frame, feet in enumerate(legs, 1):
        for suffix, color in (("", foreground), ("_warn", warning)):
            rows = [[None] * 66 for _ in range(66)]
            for x in range(66):
                for y in range(52, 66):
                    rows[y][x] = blade
                h = pattern[(x // 2) % 9]
                if h >= 1:
                    rows[50][x] = rows[51][x] = blade
                if h == 2:
                    rows[48][x] = rows[49][x] = blade
            for r, line in enumerate(top + feet):
                for c, mark in enumerate(line):
                    if mark == "#":
                        for y in range(25 + int(r * 2.5), 25 + int((r + 1) * 2.5)):
                            for x in range(13 + int(c * 2.5), 13 + int((c + 1) * 2.5)):
                                rows[y][x] = color
            rows = [
                [
                    color
                    if (x + 0.5 - 33) ** 2 + (y + 0.5 - 33) ** 2 <= 31**2
                    else None
                    for x, color in enumerate(row)
                ]
                for y, row in enumerate(rows)
            ]
            png(output / f"cat_{frame}{suffix}.png", rows)
    return output
