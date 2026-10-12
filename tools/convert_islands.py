"""Convert every island in the Java datapack to a Bedrock structure in the behavior pack.

    python tools/convert_islands.py            convert, and write tools/islands.json
    python tools/convert_islands.py --check     report only, non-zero if a structure is missing or stale

The datapack keeps 47 templates under java/data/skyblock/structures: 26 starting islands, 16 outer islands
and 5 nether islands. Each becomes development_behavior_packs/skyblock_infinite/structures/skyblock/
<kind>_<name>.mcstructure, which the server names `skyblock:<kind>_<name>` for `/structure load`. The kind is
part of the file name rather than a folder because `/structure load` will not parse a `/` in a structure
name: a nested folder gives `Syntax error: Unexpected "/"` on the server.

tools/islands.json is what scripts/main.js reads: for every island its structure name, its size, and the
offset the datapack placed it at, so the Bedrock port puts each island exactly where the Java one did. The
offsets come from PLACEMENTS below, read out of the datapack's own .mcfunction files.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nbt_to_mcstructure import convert, load_invalid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SOURCE = os.path.join(REPO, "java", "data", "skyblock", "structures")
TARGET = os.path.join(REPO, "development_behavior_packs", "skyblock_infinite", "structures", "skyblock")

# Where the datapack places a starting island, from
# java/data/skyblock/functions/main_island_generation/seed/island_place/*.mcfunction. The island is placed at
# this offset and the player spawns at 6 64 6, so the same pair on Bedrock puts the player in the same spot.
STARTING = {
    "badlands": (3, 61, 5), "beach": (3, 61, 5), "birch": (3, 61, 5), "cherry_grove": (0, 61, 5),
    "dark_forest": (3, 61, 5), "deep_frozen_ocean": (4, 61, 5), "desert": (5, 61, 5),
    "flower_forest": (3, 61, 5), "ice_spikes": (5, 61, 5), "jungle": (3, 61, 5), "lush_caves": (4, 59, 5),
    "mangrove": (2, 61, 5), "mountains": (5, 61, 5), "mushroom_fields": (2, 61, 5), "plaines": (0, 57, 2),
    "savanna": (2, 61, 5), "stony_shore": (3, 61, 5), "sunflower_forest": (3, 61, 5), "swamp": (3, 61, 5),
    "taiga": (3, 61, 4), "taiga_snow": (3, 61, 4), "windswept_gravel_hills": (3, 61, 5),
    # Four islands the datapack ships but never places: its biome search has no overworld biome that maps to
    # them. They are finished islands with a starter chest like the rest, so the port offers them too, at the
    # offset the other islands of their size use.
    "crimpson_forest": (3, 61, 5), "snowy_slopes": (3, 61, 5), "soul_sand_valley": (3, 61, 5),
    "warped_forest": (3, 61, 5),
}
# The classic ring, from outer_island_seed_generation/classic/place_island/*.mcfunction. Eight islands at
# +-192, eight at +-384, each at the exact block the datapack names.
OUTER = {
    "jungle": (1, 61, -191), "savanna": (195, 61, -192), "mushroom_island": (197, 61, 5),
    "desert": (198, 61, 198), "taiga": (4, 61, 196), "birch": (-188, 61, 197), "mangrove": (-188, 61, 1),
    "roofed_forest": (-189, 61, -190), "cherry_grove": (-383, 62, 4), "jagged_peaks": (389, 61, 6),
    "deep_frozen_ocean": (6, 60, 389), "flower_forest": (6, 62, -379), "dripstone_cave": (390, 62, 392),
    "ice_spikes": (-381, 62, -381), "sunflower_forest": (389, 62, -379), "lush_cave": (-379, 57, 389),
}
# The nether ring, from nether_islands/classic/place_island/*.mcfunction.
NETHER = {
    "portal": (6, 62, 6), "crimson_forest": (5, 55, -187), "warped_forest": (198, 62, 6),
    "basalt_delta": (4, 62, 197), "soulsand_valley": (-186, 62, 6),
}
PLACEMENTS = {"starting_islands": STARTING, "outer_islands": OUTER, "nether_islands": NETHER}
# The datapack's starting island list names two biomes that have no island of their own and fall back
# to another: the seed search returns mountains for both jagged_peaks and the #skyblock:mountain tag.
FALLBACK = "plaines"


def sources():
    """Every (kind, name, path) template the datapack ships."""
    for kind in sorted(PLACEMENTS):
        folder = os.path.join(SOURCE, kind)
        for file in sorted(os.listdir(folder)):
            if file.endswith(".nbt"):
                yield kind, file[: -len(".nbt")], os.path.join(folder, file)


def write_islands_js(islands):
    """scripts/islands.js, which main.js imports. A behavior pack script cannot read a file, so the island
    table is generated into the pack instead of loaded at run time."""
    path = os.path.join(REPO, "development_behavior_packs", "skyblock_infinite", "scripts", "islands.js")
    lists = {"STARTING": sorted(STARTING), "OUTER": sorted(OUTER), "NETHER": sorted(NETHER)}
    with open(path, "w", encoding="utf-8") as file:
        file.write("/**\n * Every island the behavior pack ships, written by tools/convert_islands.py.\n"
                   " * Do not edit by hand; the offsets come from the Java datapack's own placement functions.\n */\n")
        file.write(f"export const FALLBACK = {json.dumps(FALLBACK)};\n")
        for name, values in lists.items():
            file.write(f"export const {name} = {json.dumps(values)};\n")
        file.write("export const ISLANDS = " + json.dumps(islands, indent=1, sort_keys=True) + ";\n")


def run(check=False):
    invalid = load_invalid()
    islands, unmapped, missing, names = {}, {}, [], set()
    from nbt_to_mcstructure import read_nbt
    import gzip
    for kind, name, path in sources():
        out = os.path.join(TARGET, f"{kind}_{name}.mcstructure")
        if check:
            if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(path):
                missing.append(f"{kind}/{name}")
        else:
            names |= convert(path, out, invalid=invalid, unmapped=unmapped)
        with open(path, "rb") as file:
            size = read_nbt(gzip.decompress(file.read()))["size"]
        offset = PLACEMENTS[kind].get(name)
        islands[f"{kind}/{name}"] = {"structure": f"skyblock:{kind}_{name}", "size": size,
                                     "offset": list(offset) if offset else None}
    if check:
        for island in missing:
            print("MISSING or STALE:", island)
        print(f"{len(islands) - len(missing)}/{len(islands)} structures up to date")
        return 1 if missing else 0
    placed = sum(1 for i in islands.values() if i["offset"])
    with open(os.path.join(HERE, "islands.json"), "w", encoding="utf-8") as file:
        json.dump({"fallback": FALLBACK, "islands": islands}, file, indent=1, sort_keys=True)
    write_islands_js(islands)
    print(f"converted {len(islands)} structures, {placed} with a placement, {len(names)} block names")
    if unmapped:
        print("UNMAPPED Java blocks became air:", json.dumps(unmapped, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(run(check="--check" in sys.argv))
