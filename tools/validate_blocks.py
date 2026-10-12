"""Check every Bedrock block name the converted islands use against a running server.

    python tools/validate_blocks.py              check, and rewrite tools/bedrock_blocks.json
    python tools/validate_blocks.py --report     check and print, change nothing

A name the converter invents is only a guess until the server has taken it. This places each one at a
scratch spot in the void and reads the block back: a name the server does not know fails to place, and a
name it silently substitutes reads back as something else. Both end up in the `invalid` list, which
nbt_to_mcstructure turns into air rather than letting a whole structure fail to load.

The server has to be running with the add-on's world, and the MCP bridge with it (see the README).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bridge import Bridge
from nbt_to_mcstructure import bedrock_name, read_nbt

SCRATCH = (0, 100, 0)          # empty void, well clear of any island
# What a block wants underneath it. A plant with nothing below pops straight off and reads back as air,
# which says nothing about whether the name is good, so each gets the ground it grows on.
SUPPORT = {
    "soul_fire": "soul_soil", "crimson_roots": "crimson_nylium", "crimson_fungus": "crimson_nylium",
    "warped_roots": "warped_nylium", "warped_fungus": "warped_nylium", "nether_sprouts": "warped_nylium",
    "cactus": "sand", "twisting_vines": "warped_nylium", "frog_spawn": "water",
    "sweet_berry_bush": "grass_block", "spore_blossom": "moss_block", "waterlily": "water",
    "reeds": "grass_block", "pink_petals": "grass_block",
}
DEFAULT_SUPPORT = "dirt"


def island_names():
    """Every Bedrock name the converter would produce for the datapack's structures."""
    import gzip
    source = os.path.join(os.path.dirname(HERE), "java", "data", "skyblock", "structures")
    found = set()
    for folder, _, files in os.walk(source):
        for file in files:
            if not file.endswith(".nbt"):
                continue
            with open(os.path.join(folder, file), "rb") as handle:
                java = read_nbt(gzip.decompress(handle.read()))
            for entry in java.get("palette", []):
                name = bedrock_name(entry["Name"], entry.get("Properties", {}))
                if name:
                    found.add(name)
    return sorted(found)


def check(bridge, names):
    """A name is invalid only when the server will not take it. Bedrock's command parser treats block names
    as an enum, so a name it does not know comes back as a syntax error rather than placing anything; that is
    the test. A name that parses but does not stay (a plant whose support is still wrong, a vine that wants a
    block above) is reported separately, because the name itself was accepted."""
    x, y, z = SCRATCH
    valid, invalid, loose = [], {}, {}
    bridge.command(f"tickingarea add circle {x} {y} {z} 2 sbi_validate")
    for name in names:
        if name == "air":
            valid.append(name)
            continue
        bridge.command(f"setblock {x} {y} {z} air")
        bridge.command(f"setblock {x} {y - 1} {z} {SUPPORT.get(name, DEFAULT_SUPPORT)}")
        result = bridge.command(f"setblock {x} {y} {z} {name}")
        if "Syntax error" in result or "Unexpected" in result:
            invalid[name] = "the server does not know this block name"
            continue
        valid.append(name)
        if "success_count: 1" not in result:
            loose[name] = f"parsed, but did not place here: {result.strip()[:60]}"
            continue
        read = bridge.tool("mc_block_get", location={"x": x, "y": y, "z": z}, dimension="overworld")
        got = read.split('type_id: "minecraft:', 1)[-1].split('"', 1)[0] if "type_id" in read else "?"
        if got != name:
            loose[name] = f"placed, then read back as {got}"
    bridge.command(f"fill {x} {y - 1} {z} {x} {y} {z} air")
    bridge.command("tickingarea remove sbi_validate")
    return valid, invalid, loose


if __name__ == "__main__":
    names = island_names()
    bridge = Bridge()
    valid, invalid, loose = check(bridge, names)
    print(f"{len(valid)}/{len(names)} names the server accepts")
    for name, why in sorted(invalid.items()):
        print(f"  INVALID {name}: {why}")
    for name, why in sorted(loose.items()):
        print(f"  note    {name}: {why}")
    if "--report" not in sys.argv:
        path = os.path.join(HERE, "bedrock_blocks.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump({"note": "Every Bedrock name the island converter produces, checked against a running "
                               "server by tools/validate_blocks.py. An invalid name becomes air.",
                       "valid": sorted(valid), "invalid": sorted(invalid)}, file, indent=1)
        print(f"wrote {path}")
    sys.exit(1 if invalid else 0)
