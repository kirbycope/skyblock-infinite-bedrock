"""Photograph every island in game and save the shots as resource pack textures.

    python tools/capture_previews.py                  all 47
    python tools/capture_previews.py starting         only the starting islands
    python tools/capture_previews.py --size 160       a different texture size
    python tools/capture_previews.py --keep           leave the staged island in the world

The config menu's buttons show a picture of what they will give you, and the pictures are these: real
screenshots of the real islands, taken once and committed to
development_resource_packs/skyblock_infinite/textures/ui/islands/. This is not run at play time and does not
ship as a tool to anyone; re-run it only when an island changes.

Each island is placed on its own, far from anything, in the overworld void - including the nether ones,
because the Nether's fog makes a muddy backdrop and the void's sky gradient is clean. The camera is put on a
diagonal at a distance taken from the island's own size, facing its middle, so every island is framed the
same way whether it is six blocks across or sixteen. The HUD is hidden and the shot is cropped to a square
around the crosshair.

Needs the server up, the MCP bridge with it, and the Minecraft client joined to the server (see the README).
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from bridge import Bridge
from verify_islands import wait_for_chunk

import client_drive
from PIL import Image

TEXTURES = os.path.join(REPO, "development_resource_packs", "skyblock_infinite", "textures", "ui", "islands")
STAGE = (30000, 100, 30000)     # empty void, nowhere near anything the add-on places
# The part of the capture worth looking at: inside the chat overlay's corner and above the taskbar.
SEARCH = (260, 150, 1800, 1120)
MARGIN = 0.14                   # how much air to leave around the island in the crop
SETTLE = 3.0                    # seconds for the client to stream the chunk in and draw it
CLEAR_MARGIN = 8                # air left around the staging box on every side
FILL_LIMIT = 32768              # blocks /fill will do at once; more than this is refused
# How still the view has to be before a shot counts. Measured rather than guessed: an island appearing
# changes about 5% of the frame, while a drawn island still flickers by 0.006 to 0.012% from one frame to
# the next, because water, lava and portals animate. Asking for two identical frames never came true and
# made every capture run the full retry loop.
STILL = 0.001                   # fraction of the frame that may differ between two frames
APPEARED = 0.003                # fraction that has to change before an island counts as drawn
TAIL = 0.25                     # below the island, a row thinner than this share of its busiest is falling water
TAIL_UP = 0.03                  # above it, a thin row is a tree and is kept
SIZE = 128                      # the texture that gets written


# Pictures that are not an island. Each is a camera position and what to look at, so these are screenshots
# of the real thing too: "off" really is a shot of the empty void, which is what choosing Off gives you.
SPECIALS = {
    "void": {"from": (30000, 100, 30040), "at": (30000, 96, 30000), "needs": None},
    "portal_room": {"from": (1012, 66, 1012), "at": (1000, 60, 1000), "needs": (1000, 60, 1000)},
    "spawn": {"from": (22, 71, 23), "at": (7, 65, 9), "needs": (6, 64, 6)},
}


def capture_special(bridge, name, spot, size=SIZE):
    """A picture of somewhere that already exists in the world rather than a staged structure."""
    fx, fy, fz = spot["from"]
    if spot["needs"]:
        bridge.command(f"tickingarea add circle {spot['needs'][0]} {spot['needs'][1]} {spot['needs'][2]} 3 sbi_special")
        if not wait_for_chunk(bridge, "overworld", spot["needs"], timeout=15):
            return None, "the chunk never loaded"
    else:
        bridge.command(f"tickingarea add circle {fx} {fy} {fz} 2 sbi_special")
        wait_for_chunk(bridge, "overworld", (fx, fy, fz), timeout=15)
        # nothing should be in shot: this is the empty void, which is the point of the picture
        bridge.command(f"fill {fx - 40} {fy - 40} {fz - 60} {fx + 40} {fy + 40} {fz + 40} air")
    bridge.command(f"tp @a {fx} {fy} {fz} facing {spot['at'][0]} {spot['at'][1]} {spot['at'][2]}")
    image = stable_shot(f"preview_{name}")
    os.makedirs(TEXTURES, exist_ok=True)
    out = os.path.join(TEXTURES, name + ".png")
    # these are places that already exist rather than a staged structure, so there is no empty frame to
    # subtract; the picture is the whole view, centred
    width, height = image.size
    half = min(width, height) // 3
    box = (width // 2 - half, height // 2 - half, width // 2 + half, height // 2 + half)
    image.crop(box).resize((size, size), Image.LANCZOS).save(out)
    bridge.command("tickingarea remove sbi_special")
    return out, None


def clear_box():
    """The staging box: big enough for the largest island there is, plus a margin.

    Taken from the island table rather than guessed. A guess of 24 was wrong - the tallest island is 35
    blocks - so eleven blocks of it were left standing and turned up in the background of whichever smaller
    island came next."""
    sizes = [island["size"] for island in islands().values()]
    return [max(s[i] for s in sizes) + CLEAR_MARGIN for i in range(3)]


def clear(bridge, spot):
    """Empty the whole staging box, so nothing of the island before is left to appear behind this one.

    In slabs, because `/fill` refuses more than 32768 blocks in one go and says so only by answering
    `success_count: 0`. The staging box is 45,900 blocks, so every clear this tool ever issued was refused
    and silently did nothing, which is why islands piled up on each other: a tall one would still be
    standing behind the next, smaller one."""
    x, y, z = spot
    bx, by, bz = clear_box()
    x0, y0, z0 = x - CLEAR_MARGIN, y - CLEAR_MARGIN, z - CLEAR_MARGIN
    x1, y1, z1 = x + bx, y + by, z + bz
    layer = (x1 - x0 + 1) * (z1 - z0 + 1)
    slab = max(1, FILL_LIMIT // layer)
    for base in range(y0, y1 + 1, slab):
        top = min(base + slab - 1, y1)
        assert (top - base + 1) * layer <= FILL_LIMIT, "a slab is still over the fill limit"
        # the answer is not checked: `/fill` says success_count 0 both when it refuses the volume and when
        # there was nothing to change, so it cannot tell those apart. Keeping each slab under the limit is
        # the guarantee instead.
        bridge.command(f"fill {x0} {base} {z0} {x1} {top} {z1} air")


def stable_shot(name, differs_from=None, tries=10):
    """Screenshot once the view has settled, and - when `differs_from` is given - once it has actually
    changed from that frame.

    The server changing the world and the client drawing it are a second or two apart, and a fixed wait is a
    guess at that gap. Waiting for the picture to stop moving instead removes the guess, but on its own it
    returns too early: the two frames straight after a `structure load` are identical to each other because
    neither has the island in it yet, which would have saved a picture of empty sky. So a shot that is meant
    to show something new has to differ from the frame before it as well as be still.

    "Still" is a fraction of the frame rather than an exact match, because an island on screen never matches
    itself exactly: its water and lava animate, which costs about 0.01% of the frame."""
    import numpy as np
    left, top, right, bottom = SEARCH
    crop = lambda img: np.asarray(img, dtype=np.int16)[top:bottom, left:right]
    before = crop(differs_from) if differs_from is not None else None
    previous = None
    image = None
    for attempt in range(tries):
        image = Image.open(client_drive.shot(name)).convert("RGB")
        current = crop(image)
        if previous is not None:
            still = (np.abs(current - previous).max(axis=2) > 16).mean() < STILL
            arrived = before is None or (np.abs(current - before).max(axis=2) > 16).mean() > APPEARED
            if still and arrived:
                return image
        previous = current
        time.sleep(0.6)
    return image


def crop_to_island(image, background, size=SIZE):
    """Cut a square around whatever the island added to the frame.

    `background` is the same camera looking at the empty stage, so subtracting it leaves the island and
    nothing else: no clouds, no horizon, no sky gradient, no taskbar. Returns (square image, whether the
    framing looks trustworthy)."""
    import numpy as np
    pixels = np.asarray(image, dtype=np.int16)
    empty = np.asarray(background, dtype=np.int16)
    left, top, right, bottom = SEARCH
    region = pixels[top:bottom, left:right]
    mask = np.abs(region - empty[top:bottom, left:right]).max(axis=2) > 16
    rows, columns = np.where(mask)
    if len(rows) < 50:                                       # the island added nothing: an empty frame
        width, height = image.size
        half = min(width, height) // 4
        box = (width // 2 - half, height // 2 - half, width // 2 + half, height // 2 + half)
        return image.crop(box).resize((size, size), Image.LANCZOS), True
    # The edges of the island, ignoring thin tails. Several islands carry water, which in a void pours off
    # the bottom and falls out of sight, and that column is part of the picture as far as a difference is
    # concerned: it is a few pixels wide and hundreds tall, and it dragged the crop down until the island
    # itself was a detail in the corner. A row or column holding only a trickle of the subject is dropped,
    # and a percentile on what is left shrugs off single stray pixels as well.
    row_counts = mask.sum(axis=1)
    busiest = row_counts.max()
    densest = int(row_counts.argmax())
    # Downwards only, because water falls: from the island's densest row, keep going down while the rows are
    # still substantial, and stop where the trickle begins. Measured on the beach island, whose rows run 80
    # to 320 pixels while its waterfall holds a steady 40, so the cut is nowhere near either.
    below = np.where(row_counts[densest:] >= busiest * TAIL)[0]
    bottom_row = densest + (below.max() if len(below) else 0)
    # Upwards a thin tail is kept: that is a tree, not a leak.
    above = np.where(row_counts[:densest + 1] >= busiest * TAIL_UP)[0]
    top_row = above.min() if len(above) else densest
    keep = (rows >= top_row) & (rows <= bottom_row)
    if keep.any():
        rows, columns = rows[keep], columns[keep]
    x0, x1 = (left + int(v) for v in np.percentile(columns, (0.3, 99.7)))
    y0, y1 = (top + int(v) for v in np.percentile(rows, (0.3, 99.7)))
    # An island filling the search area means the frame is not showing it on its own, or it is too close to
    # fit; either way the shot is retaken from further back.
    touched = x0 <= left + 2 or y0 <= top + 2 or x1 >= right - 3 or y1 >= bottom - 3
    width, height = image.size
    # The crop has to stay inside the game's picture. SEARCH only bounds where the island is looked for; a
    # tall thin island (an oak tree on a small base) makes a tall square that reached past the bottom of the
    # window and took a strip of the Windows taskbar with it.
    safe_top, safe_bottom = 0, min(height, SEARCH[3] + 10)
    side = min(max(x1 - x0, y1 - y0) * (1 + 2 * MARGIN), width, safe_bottom - safe_top)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    half = side / 2
    box = [int(cx - half), int(cy - half), int(cx + half), int(cy + half)]
    # a square that runs off the safe area is pulled back inside rather than letterboxed
    dx = max(0, -box[0]) - max(0, box[2] - width)
    dy = max(0, safe_top - box[1]) - max(0, box[3] - safe_bottom)
    box = (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)
    return image.crop(box).resize((size, size), Image.LANCZOS), not touched


def islands(only=None):
    with open(os.path.join(HERE, "islands.json"), encoding="utf-8") as file:
        table = json.load(file)["islands"]
    return {k: v for k, v in sorted(table.items()) if not only or k.startswith(only)}


def camera_for(size, scale=1.0):
    """Where to stand to frame an island of this size, as an offset from its middle.

    The island is looked at down a diagonal from above, far enough back that its longest side fits the frame
    with room around it. The distance comes from the island's own size so a 6 block island and a 35 block one
    fill the picture by the same amount; `scale` pushes the camera further out when a shot came back with the
    island running off the edge."""
    reach = (max(size) * 1.45 + 5.0) * scale
    return (reach * 0.62, reach * 0.46, reach * 0.62)


def capture(bridge, key, island, size=SIZE, keep=False):
    """Two shots from the same camera - the empty stage, then the island on it - and the island is whatever
    differs between them.

    Finding the island by comparing it with a column of sky does not work: the sky has clouds and a horizon
    in it, and those differ from the sky column too, so the box ended up spanning the whole frame and the
    crop came out as a speck of island between two black bars. A background shot cancels all of it exactly,
    clouds, horizon, gradient and the Windows taskbar alike."""
    x, y, z = STAGE
    sx, sy, sz = island["size"]
    area = "sbi_preview"
    name = key.replace("/", "_")
    bridge.command(f"tickingarea add circle {x} {y} {z} 3 {area}")
    if not wait_for_chunk(bridge, "overworld", STAGE, timeout=15):
        return None, "the staging chunk never loaded"
    middle = (x + sx / 2, y + sy / 2, z + sz / 2)

    picture = None
    for attempt, reach in enumerate((1.0, 1.45, 2.1)):
        dx, dy, dz = camera_for(island["size"], reach)
        bridge.command(f"tp @a {middle[0] + dx:.2f} {middle[1] + dy:.2f} {middle[2] + dz:.2f} "
                       f"facing {middle[0]:.2f} {middle[1]:.2f} {middle[2]:.2f}")
        clear(bridge, STAGE)
        background = stable_shot(f"preview_{name}_bg")
        loaded = bridge.command(f"structure load {island['structure']} {x} {y} {z}")
        if "success_count: 1" not in loaded:
            return None, f"structure load said {loaded.strip()[:60]}"
        shot = stable_shot(f"preview_{name}", differs_from=background)
        picture, framed = crop_to_island(shot, background, size)
        if framed:
            break
        # the island ran off the frame, so stand further back and take it again
        if attempt < 2:
            clear(bridge, STAGE)
    # the kind stays in the file name: starting_islands/jungle and outer_islands/jungle
    # are different islands and would otherwise overwrite each other
    out = os.path.join(TEXTURES, name + ".png")
    os.makedirs(TEXTURES, exist_ok=True)
    picture.save(out)
    if not keep:
        clear(bridge, STAGE)
    bridge.command(f"tickingarea remove {area}")
    return out, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("only", nargs="?", help="starting, outer or nether; all of them by default")
    parser.add_argument("--size", type=int, default=SIZE)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    prefix = {"starting": "starting_islands/", "outer": "outer_islands/",
              "nether": "nether_islands/"}.get(args.only, args.only)

    bridge = Bridge()
    if "players: []" in bridge.tool("mc_player_list"):
        sys.exit("nobody is on the server; the client has to be joined for there to be a camera")
    client_drive.focus()
    # a clean, repeatable picture: no HUD, no weather, no night, and a camera that does not fall
    # The sky has to be the same in every picture, and in the first run it was not: the daylight cycle kept
    # running through a five minute capture, so some islands came out at sunset and some nearly dark. Time
    # and weather are frozen rather than just set.
    for command in ("gamerule sendcommandfeedback false", "gamerule showcoordinates false",
                    "gamerule dodaylightcycle false", "gamerule doweathercycle false",
                    "time set noon", "weather clear", "gamemode spectator @a", "hud @a hide all"):
        bridge.command(command)

    written, failures = [], []
    table = islands(prefix)
    for index, (key, island) in enumerate(table.items(), 1):
        path, error = capture(bridge, key, island, args.size, args.keep)
        if error:
            failures.append((key, error))
            print(f"  {index:3}/{len(table)} FAILED {key}: {error}")
        else:
            written.append(path)
            print(f"  {index:3}/{len(table)} {key:42} -> {os.path.basename(path)}")
    if not prefix:
        for name, spot in SPECIALS.items():
            path, error = capture_special(bridge, name, spot, args.size)
            if error:
                failures.append((name, error))
                print(f"      FAILED {name}: {error}")
            else:
                written.append(path)
                print(f"      {name:42} -> {os.path.basename(path)}")
    for command in ("hud @a reset all", "gamerule dodaylightcycle true", "gamerule doweathercycle true",
                    "gamerule sendcommandfeedback true", "gamerule showcoordinates true"):
        bridge.command(command)
    print(f"\nwrote {len(written)} previews to {TEXTURES}")
    for key, error in failures:
        print(f"  FAILED {key}: {error}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
