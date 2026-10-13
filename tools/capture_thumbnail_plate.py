"""Photograph the starting island for the thumbnail, and the empty void behind it.

Two frames from one camera: the bare stage, then the island standing on it. What
differs between them is the island exactly - leaves, grass fringe and all - so
the thumbnail needs no colour keying and nothing fringes.

The island is staged far out in the void rather than photographed at spawn, so
this neither needs the world to have been started nor changes it. Writes
assets/background.png and assets/background_void.png, which
tools/make_thumbnail.py reads.

Needs the server up, the MCP bridge with it, and the client joined (see README).

    python tools/capture_thumbnail_plate.py
    python tools/capture_thumbnail_plate.py --island starting_islands/cherry_grove
"""

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import client_drive
from bridge import Bridge
from capture_previews import STAGE, clear, islands, stable_shot
from verify_islands import wait_for_chunk

ASSETS = os.path.join(REPO, "assets")

# Lower and closer than the menu previews' camera: the thumbnail wants the
# island near eye level, the way One Chunk Challenge frames its chunk.
LIFT, REACH = 0.30, 1.22


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--island", default="starting_islands/plaines")
    ap.add_argument("--reach", type=float, default=REACH,
                    help="pull the camera back if the island runs off frame")
    args = ap.parse_args()

    table = islands()
    if args.island not in table:
        sys.exit(f"no such island: {args.island}\n" + "\n".join(sorted(table)[:10]) + " ...")
    island = table[args.island]

    client_drive.focus()        # the shot grabs the screen, so the game must be in front
    bridge = Bridge()
    # command feedback prints into chat, and chat is drawn over the shot; turning
    # it off is what keeps the plates clean, not hiding the HUD
    for command in ("gamerule sendcommandfeedback false", "gamerule dodaylightcycle false",
                    "gamerule doweathercycle false", "time set noon", "weather clear",
                    "gamemode spectator @a", "hud @a hide all"):
        bridge.command(command)

    x, y, z = STAGE
    bridge.command(f"tickingarea add circle {x} {y} {z} 3 sbi_thumb")
    if not wait_for_chunk(bridge, "overworld", STAGE, timeout=20):
        sys.exit("the staging chunk never loaded")

    sx, sy, sz = island["size"]
    middle = (x + sx / 2, y + sy / 2, z + sz / 2)
    span = (max(island["size"]) * 1.45 + 5.0) * args.reach
    dx, dy, dz = span * 0.66, span * LIFT, span * 0.66
    bridge.command(f"tp @a {middle[0] + dx:.2f} {middle[1] + dy:.2f} {middle[2] + dz:.2f} "
                   f"facing {middle[0]:.2f} {middle[1]:.2f} {middle[2]:.2f}")

    os.makedirs(ASSETS, exist_ok=True)
    clear(bridge, STAGE)
    void = stable_shot("thumb_void")
    void.save(os.path.join(ASSETS, "background_void.png"))
    print(f"wrote assets/background_void.png {void.size[0]}x{void.size[1]}")

    loaded = bridge.command(f"structure load {island['structure']} {x} {y} {z}")
    if "success_count: 1" not in loaded:
        sys.exit(f"structure load said {loaded.strip()[:80]}")
    shot = stable_shot("thumb_island", differs_from=void)
    shot.save(os.path.join(ASSETS, "background.png"))
    print(f"wrote assets/background.png {shot.size[0]}x{shot.size[1]}")

    clear(bridge, STAGE)
    for command in ("tickingarea remove sbi_thumb", "hud @a reset all",
                    "gamerule dodaylightcycle true", "gamerule doweathercycle true",
                    "gamerule sendcommandfeedback true", "gamemode creative @a"):
        bridge.command(command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
