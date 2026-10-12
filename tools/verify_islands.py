"""Place every island on the running server and check that each one actually landed.

    python tools/verify_islands.py                  every island, overworld and nether
    python tools/verify_islands.py starting         just the starting islands
    python tools/verify_islands.py --keep            leave them in the world afterwards

A structure that fails to load says `success_count: 0` and leaves the void empty, which is the one failure
this port can produce without anyone noticing: a renamed structure, a palette Bedrock rejects, a chunk that
was never held. So each island is placed at the coordinates islands.json names and then read back - the
blocks in its box are counted, and an island that comes back empty is a failure.

The server has to be running with the add-on's world, and the MCP bridge with it (see the README).
Islands are placed well away from spawn unless --at-home is given, so a verification run does not bulldoze a
world someone is playing.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bridge import Bridge

# Far from anything the datapack places, so a verification run cannot land on a real island.
TEST_ORIGIN = (20000, 60, 20000)
SPACING = 64


def islands():
    with open(os.path.join(HERE, "islands.json"), encoding="utf-8") as file:
        return json.load(file)["islands"]


def wait_for_chunk(bridge, dimension, location, timeout=10.0):
    """Block until the server will actually answer for that location. A ticking area reports success the
    moment it is added, but its chunks are not loaded yet - about a second and a half for a nether chunk -
    and `/structure load` into one of those reports success and places nothing."""
    x, y, z = location
    deadline = time.time() + timeout
    while time.time() < deadline:
        read = bridge.tool("mc_block_get", dimension=dimension, location={"x": x, "y": y, "z": z})
        if "NOT_FOUND" not in read and "unloaded" not in read:
            return True
        time.sleep(0.25)
    return False


def count_blocks(bridge, dimension, origin, size):
    """How many of the island's blocks the server can see in its box, and what the commonest ones are. The
    middle column is no good as a test: several islands are hollow or lopsided there, and a one-column
    sample called four perfectly placed islands empty."""
    x, y, z = origin
    sx, sy, sz = size
    total, kinds, cursor = 0, {}, None
    while True:
        args = {"dimension": dimension, "from": {"x": x, "y": y, "z": z},
                "to": {"x": x + sx - 1, "y": y + sy - 1, "z": z + sz - 1},
                "filter": {"exclude": ["minecraft:air"]}}
        if cursor:
            args["cursor"] = cursor
        page = bridge.tool("mc_block_get_volume", **args)
        for line in page.splitlines():
            if 'type_id: "' in line:
                total += 1
                name = line.split('type_id: "', 1)[1].split('"', 1)[0]
                kinds[name] = kinds.get(name, 0) + 1
        cursor = page.split("cursor:", 1)[1].strip().strip('"') if "cursor:" in page else None
        if not cursor or cursor in ("null", "none", ""):
            break
    return total, kinds


def verify(bridge, only=None, at_home=False, keep=False):
    table = islands()
    results, failures = [], []
    index = 0
    for key in sorted(table):
        island = table[key]
        if only and not key.startswith(only):
            continue
        kind = key.split("/")[0]
        dimension = "nether" if kind == "nether_islands" else "overworld"
        if at_home:
            x, y, z = island["offset"]
        else:
            x = TEST_ORIGIN[0] + (index % 8) * SPACING
            z = TEST_ORIGIN[2] + (index // 8) * SPACING
            y = island["offset"][1]
        index += 1
        area = f"sbi_v{index}"
        bridge.command(f"execute in {dimension} run tickingarea add circle {x} {y} {z} 3 {area}")
        wait_for_chunk(bridge, dimension, (x, y, z))
        loaded = bridge.command(f"execute in {dimension} run structure load {island['structure']} {x} {y} {z}")
        ok = "success_count: 1" in loaded
        solid, kinds = 0, {}
        if ok:
            solid, kinds = count_blocks(bridge, dimension, (x, y, z), island["size"])
        results.append((key, ok, solid, kinds))
        if not ok or solid == 0:
            failures.append((key, loaded.strip()[:90] if not ok else "loaded, but its box came back empty"))
        if not keep:
            bridge.command(f"execute in {dimension} run structure load {island['structure']} {x} {y} {z}")
            sx, sy, sz = island["size"]
            bridge.command(f"execute in {dimension} run fill {x} {y} {z} {x + sx - 1} {y + sy - 1} {z + sz - 1} air")
        bridge.command(f"execute in {dimension} run tickingarea remove {area}")
    return results, failures


if __name__ == "__main__":
    only = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
    bridge = Bridge()
    results, failures = verify(bridge, only=only, at_home="--at-home" in sys.argv, keep="--keep" in sys.argv)
    for key, ok, solid, kinds in results:
        top = ", ".join(f"{n.split(':')[-1]} {c}" for n, c in sorted(kinds.items(), key=lambda i: -i[1])[:3])
        print(f"  {'ok  ' if ok and solid else 'FAIL'} {key:44} {solid:5} blocks  {top}")
    print(f"{len(results) - len(failures)}/{len(results)} islands placed")
    for key, why in failures:
        print(f"  FAILED {key}: {why}")
    sys.exit(1 if failures else 0)
