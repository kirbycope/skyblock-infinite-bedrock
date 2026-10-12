"""Convert Skyblock Infinite's Java structure templates (.nbt) to Bedrock structures (.mcstructure).

    python tools/nbt_to_mcstructure.py <in.nbt> <out.mcstructure>   one file
    python tools/nbt_to_mcstructure.py --names <folder>             every Bedrock block name the folder's
                                                                      structures would use, as JSON

tools/convert_islands.py imports convert() and runs it over java/data/skyblock/structures. A Java template is
gzipped big-endian NBT: a size, a palette of block states and a list of blocks by position. A Bedrock
structure is little-endian NBT: the same size, two layers of palette indices in x, y, z order (-1 for
structure void), and a palette of Bedrock block names and states. Java names become Bedrock names through
BLOCK_NAMES, and the states Bedrock spells differently (log axis, slab half, a huge mushroom's cap faces
packed into one integer, a vine's sides packed into bit flags, leaves that must not decay) through
convert_states(); any other state is dropped and Bedrock uses the block's default. Names listed in
tools/bedrock_blocks.json as invalid (found by placing each one on the server) become air. The starting
islands each hold a chest of starter items, written out as a Bedrock Chest block entity so the items survive.

The NBT reader and writer come from cobblemon-bedrock's tools/nbt_to_mcstructure.py.
"""
import gzip
import io
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# NBT
# ---------------------------------------------------------------------------

END, BYTE, SHORT, INT, LONG, FLOAT, DOUBLE, BYTE_ARRAY, STRING, LIST, COMPOUND, INT_ARRAY, LONG_ARRAY = range(13)


class Tag:
    """A value with its NBT type, for writing; reading returns plain Python values."""
    def __init__(self, kind, value, item_kind=None):
        self.kind, self.value, self.item_kind = kind, value, item_kind


def read_nbt(data, little=False):
    stream = io.BytesIO(data)
    order = "<" if little else ">"

    def unpack(fmt, size): return struct.unpack(order + fmt, stream.read(size))[0]

    def read_string(): return stream.read(unpack("H", 2)).decode("utf-8", "replace")

    def payload(kind):
        if kind == BYTE: return unpack("b", 1)
        if kind == SHORT: return unpack("h", 2)
        if kind == INT: return unpack("i", 4)
        if kind == LONG: return unpack("q", 8)
        if kind == FLOAT: return unpack("f", 4)
        if kind == DOUBLE: return unpack("d", 8)
        if kind == BYTE_ARRAY: return list(stream.read(unpack("i", 4)))
        if kind == STRING: return read_string()
        if kind == LIST:
            item_kind = unpack("b", 1); count = unpack("i", 4)
            return [payload(item_kind) for _ in range(count)]
        if kind == COMPOUND:
            result = {}
            while True:
                child = unpack("b", 1)
                if child == END: return result
                name = read_string(); result[name] = payload(child)
        if kind == INT_ARRAY: return [unpack("i", 4) for _ in range(unpack("i", 4))]
        if kind == LONG_ARRAY: return [unpack("q", 8) for _ in range(unpack("i", 4))]
        raise ValueError(f"unknown NBT tag {kind}")

    kind = unpack("b", 1); read_string()
    return payload(kind)


def write_nbt(root, little=True):
    out = io.BytesIO()
    order = "<" if little else ">"

    def pack(fmt, value): out.write(struct.pack(order + fmt, value))

    def write_string(text):
        data = text.encode("utf-8"); pack("H", len(data)); out.write(data)

    def payload(tag):
        kind, value = tag.kind, tag.value
        if kind == BYTE: pack("b", value)
        elif kind == SHORT: pack("h", value)
        elif kind == INT: pack("i", value)
        elif kind == LONG: pack("q", value)
        elif kind == FLOAT: pack("f", value)
        elif kind == DOUBLE: pack("d", value)
        elif kind == STRING: write_string(value)
        elif kind == BYTE_ARRAY: pack("i", len(value)); out.write(bytes(value))
        elif kind == INT_ARRAY:
            pack("i", len(value))
            for item in value: pack("i", item)
        elif kind == LONG_ARRAY:
            pack("i", len(value))
            for item in value: pack("q", item)
        elif kind == LIST:
            pack("b", tag.item_kind if value else (tag.item_kind or END)); pack("i", len(value))
            for item in value: payload(item)
        elif kind == COMPOUND:
            for name, child in value.items():
                pack("b", child.kind); write_string(name); payload(child)
            pack("b", END)
        else: raise ValueError(f"cannot write NBT tag {kind}")

    pack("b", COMPOUND); write_string(""); payload(root)
    return out.getvalue()


def compound(**children): return Tag(COMPOUND, dict(children))


def int_list(values): return Tag(LIST, [Tag(INT, v) for v in values], INT)


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------

# Java name -> Bedrock name, where they differ
BLOCK_NAMES = {
    "cave_air": "air", "void_air": "air", "grass": "short_grass", "snow_block": "snow", "snow": "snow_layer",
    "terracotta": "hardened_clay", "melon": "melon_block", "sugar_cane": "reeds", "lily_pad": "waterlily",
    "tripwire": "trip_wire", "nether_portal": "portal", "frogspawn": "frog_spawn",
    "mushroom_stem": "brown_mushroom_block", "bubble_column": "water",
    # three Bedrock spells differently enough that its command parser rejects the Java name outright
    "dead_bush": "deadbush", "rooted_dirt": "dirt_with_roots",
    "flowering_azalea_leaves": "azalea_leaves_flowered",
    # a vine with a plant half: Bedrock has the one block and reads its own age state
    "twisting_vines_plant": "twisting_vines", "weeping_vines_plant": "weeping_vines",
    "cave_vines_plant": "cave_vines",
}
# the berry-bearing halves of a glow berry vine are their own blocks on Bedrock
CAVE_VINES_BERRIES = {"cave_vines": "cave_vines_head_with_berries", "cave_vines_plant": "cave_vines_body_with_berries"}

CARDINAL = ("north", "south", "east", "west")
# Bedrock packs a huge mushroom's cap faces into one integer; Java keeps a boolean per face
MUSHROOM_BITS = {("north", "west"): 1, ("north",): 2, ("east", "north"): 3, ("west",): 4, (): 5,
                 ("east",): 6, ("south", "west"): 7, ("south",): 8, ("east", "south"): 9}
VINE_BITS = {"south": 1, "west": 2, "north": 4, "east": 8}
# Java spells a double plant as two halves of one block; so does Bedrock, under another state name
DOUBLE_PLANTS = ("sunflower", "lilac", "peony", "rose_bush", "tall_grass", "large_fern")


def bedrock_name(java, props=None):
    name = java.split(":", 1)[1] if ":" in java else java
    if name in CAVE_VINES_BERRIES and (props or {}).get("berries") == "true": return CAVE_VINES_BERRIES[name]
    if name.startswith("potted_"): return "flower_pot"
    return BLOCK_NAMES.get(name, name)


def truthy(props, keys):
    return tuple(sorted(k for k in keys if props.get(k) == "true"))


def convert_states(java_name, name, props):
    """The Bedrock states for the Java properties that matter to how an island looks."""
    states = {}
    java = java_name.split(":", 1)[1] if ":" in java_name else java_name
    if "axis" in props: states["pillar_axis"] = Tag(STRING, props["axis"])
    # leaves placed into the void have no log to decay towards, so every leaf is pinned
    if name.endswith("_leaves") or name == "leaves": states["persistent_bit"] = Tag(BYTE, 1)
    if name.endswith("_slab") and props.get("type") in ("top", "bottom"):
        states["minecraft:vertical_half"] = Tag(STRING, props["type"])
    if name == "snow_layer" and "layers" in props: states["height"] = Tag(INT, int(props["layers"]) - 1)
    if name in ("water", "lava") and "level" in props: states["liquid_depth"] = Tag(INT, int(props["level"]))
    if name in ("cactus", "cocoa") and "age" in props: states["age"] = Tag(INT, int(props["age"]))
    if name == "portal": states["portal_axis"] = Tag(STRING, props.get("axis", "x"))
    if name == "sweet_berry_bush" and "age" in props: states["growth"] = Tag(INT, int(props["age"]))
    if name == "twisting_vines" and "age" in props: states["twisting_vines_age"] = Tag(INT, int(props["age"]))
    if name == "weeping_vines" and "age" in props: states["weeping_vines_age"] = Tag(INT, int(props["age"]))
    if name == "cave_vines" and "age" in props: states["growing_plant_age"] = Tag(INT, min(int(props["age"]), 25))
    if java in DOUBLE_PLANTS and "half" in props:
        states["upper_block_bit"] = Tag(BYTE, 1 if props["half"] == "upper" else 0)
    if name in ("chest", "carved_pumpkin", "lit_pumpkin") and "facing" in props:
        states["minecraft:cardinal_direction"] = Tag(STRING, props["facing"])
    if name == "pink_petals":
        states["growth"] = Tag(INT, int(props.get("flower_amount", 1)) - 1)
        states["minecraft:cardinal_direction"] = Tag(STRING, props.get("facing", "north"))
    if name in ("brown_mushroom_block", "red_mushroom_block"):
        # Java's stem has no cap face at all; Bedrock spells that 10, and 14 is cap on every side
        states["huge_mushroom_bits"] = Tag(INT, 10 if props.get("up") != "true" else MUSHROOM_BITS.get(truthy(props, CARDINAL), 14))
    if name == "vine":
        states["vine_direction_bits"] = Tag(INT, sum(VINE_BITS[k] for k in truthy(props, CARDINAL)))
    if name == "pointed_dripstone":
        states["dripstone_thickness"] = Tag(STRING, props.get("thickness", "tip"))
        states["hanging"] = Tag(BYTE, 1 if props.get("vertical_direction") == "down" else 0)
    if name == "mangrove_propagule":
        states["propagule_stage"] = Tag(INT, int(props.get("stage", 0)))
        states["hanging"] = Tag(BYTE, 1 if props.get("hanging") == "true" else 0)
    return states


def load_invalid():
    path = os.path.join(HERE, "bedrock_blocks.json")
    if not os.path.exists(path): return set()
    with open(path, encoding="utf-8") as file: return set(json.load(file).get("invalid", []))


def chest(items):
    """A Bedrock Chest block entity holding a starting island's items. Java writes an item's name in `id` and
    its slot in `Slot`; Bedrock wants `Name`, a byte `Count` and a `Damage` of 0."""
    return compound(block_entity_data=compound(
        id=Tag(STRING, "Chest"), isMovable=Tag(BYTE, 1),
        Items=Tag(LIST, [compound(Count=Tag(BYTE, item.get("Count", 1)), Damage=Tag(SHORT, 0),
                                  Name=Tag(STRING, item["id"]), Slot=Tag(BYTE, item.get("Slot", 0)),
                                  WasPickedUp=Tag(BYTE, 0)) for item in items], COMPOUND)))


def convert(src, dst, invalid=None, unmapped=None):
    """Write one .mcstructure; returns the set of Bedrock names it uses. Unmapped Java names are counted into
    `unmapped` (a dict) when given, and become air."""
    invalid = load_invalid() if invalid is None else invalid
    with open(src, "rb") as file: java = read_nbt(gzip.decompress(file.read()))
    sx, sy, sz = java["size"]
    palette, names, keys, position_data = [], set(), [], {}

    def block_key(java_name, props):
        if java_name == "minecraft:structure_void": return -1
        name = bedrock_name(java_name, props)
        if name is None or name in invalid:
            if unmapped is not None: unmapped[java_name] = unmapped.get(java_name, 0) + 1
            name = "air"
        names.add(name)
        return (name, json.dumps({k: (t.kind, t.value) for k, t in convert_states(java_name, name, props).items()}, sort_keys=True))

    def palette_index(key):
        if key not in keys:
            keys.append(key)
            name, states = key
            palette.append(compound(name=Tag(STRING, name if ":" in name else f"minecraft:{name}"),
                                    states=Tag(COMPOUND, {k: Tag(kind, value) for k, (kind, value) in json.loads(states).items()}),
                                    version=Tag(INT, 18168865)))
        return keys.index(key)

    source_palette = [(entry["Name"], entry.get("Properties", {})) for entry in java.get("palette", [])]
    palette_index(("air", "{}"))
    layer = [-1] * (sx * sy * sz)
    for block in java.get("blocks", []):
        x, y, z = block["pos"]
        java_name, props = source_palette[block["state"]]
        key = block_key(java_name, props)
        if key == -1: continue
        index = (x * sy + y) * sz + z
        layer[index] = palette_index(key)
        items = (block.get("nbt") or {}).get("Items")
        if items and key[0] == "chest": position_data[str(index)] = chest(items)
    root = compound(
        format_version=Tag(INT, 1),
        size=int_list([sx, sy, sz]),
        structure=compound(
            block_indices=Tag(LIST, [int_list(layer), int_list([-1] * len(layer))], LIST),
            entities=Tag(LIST, [], COMPOUND),
            palette=compound(default=compound(block_palette=Tag(LIST, palette, COMPOUND), block_position_data=Tag(COMPOUND, position_data)))),
        structure_world_origin=int_list([0, 0, 0]))
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    with open(dst, "wb") as file: file.write(write_nbt(root))
    return names


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--names":
        found = {}
        for root_dir, _, files in os.walk(args[1]):
            for f in files:
                if not f.endswith(".nbt"): continue
                with open(os.path.join(root_dir, f), "rb") as file: java = read_nbt(gzip.decompress(file.read()))
                for entry in java.get("palette", []):
                    name = bedrock_name(entry["Name"], entry.get("Properties", {}))
                    if name: found[name] = found.get(name, 0) + 1
        print(json.dumps(sorted(found), indent=0))
    elif len(args) == 2:
        print(sorted(convert(args[0], args[1])))
    else:
        print(__doc__)
