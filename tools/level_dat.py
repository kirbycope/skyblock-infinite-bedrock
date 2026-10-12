"""Read and write a Bedrock level.dat without losing a tag's type.

    python tools/level_dat.py <world>/level.dat              print every field with its NBT type

nbt_to_mcstructure.read_nbt returns plain Python, which is all a structure needs but not enough for a
level.dat: Bedrock cares that `Generator` is an int, `LastPlayed` a long and `mobgriefing` a byte, and a
value read back as the Python int 2 could be written as any of the three. Guessing from the value corrupts
the file, so this reader keeps each tag's type beside its value and patch() changes only the values.

A level.dat is 8 bytes of header - a storage version and the length of what follows - and then one
little-endian NBT compound.
"""
import io
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from nbt_to_mcstructure import (BYTE, BYTE_ARRAY, COMPOUND, DOUBLE, END, FLOAT, INT, INT_ARRAY, LIST, LONG,
                                LONG_ARRAY, SHORT, STRING, Tag, write_nbt)


def read_typed(data, little=True):
    """The compound in `data` as a dict of name -> Tag, recursively."""
    stream = io.BytesIO(data)
    order = "<" if little else ">"

    def unpack(fmt, size): return struct.unpack(order + fmt, stream.read(size))[0]
    def read_string(): return stream.read(unpack("H", 2)).decode("utf-8", "replace")

    def payload(kind):
        if kind == BYTE: return Tag(kind, unpack("b", 1))
        if kind == SHORT: return Tag(kind, unpack("h", 2))
        if kind == INT: return Tag(kind, unpack("i", 4))
        if kind == LONG: return Tag(kind, unpack("q", 8))
        if kind == FLOAT: return Tag(kind, unpack("f", 4))
        if kind == DOUBLE: return Tag(kind, unpack("d", 8))
        if kind == BYTE_ARRAY: return Tag(kind, list(stream.read(unpack("i", 4))))
        if kind == STRING: return Tag(kind, read_string())
        if kind == LIST:
            item_kind = unpack("b", 1); count = unpack("i", 4)
            return Tag(kind, [payload(item_kind) for _ in range(count)], item_kind)
        if kind == COMPOUND:
            result = {}
            while True:
                child = unpack("b", 1)
                if child == END: return Tag(kind, result)
                name = read_string(); result[name] = payload(child)
        if kind == INT_ARRAY: return Tag(kind, [unpack("i", 4) for _ in range(unpack("i", 4))])
        if kind == LONG_ARRAY: return Tag(kind, [unpack("q", 8) for _ in range(unpack("i", 4))])
        raise ValueError(f"unknown NBT tag {kind}")

    kind = unpack("b", 1); read_string()
    return payload(kind)


def load(path):
    """(header, root tag) for a level.dat."""
    with open(path, "rb") as file:
        raw = file.read()
    return raw[:8], read_typed(raw[8:])


def save(path, header, root):
    body = write_nbt(root, little=True)
    with open(path, "wb") as file:
        file.write(header[:4] + len(body).to_bytes(4, "little") + body)


def patch(root, values, kinds=None):
    """Set each field to a new value, keeping the type it already had. A field the file does not have yet
    needs its type in `kinds`."""
    kinds = kinds or {}
    for key, value in values.items():
        if key in root.value:
            root.value[key].value = value
        elif key in kinds:
            root.value[key] = Tag(kinds[key], value)
        else:
            raise KeyError(f"{key} is not in this level.dat and no type was given for it")
    return root


KIND_NAMES = {BYTE: "byte", SHORT: "short", INT: "int", LONG: "long", FLOAT: "float", DOUBLE: "double",
              BYTE_ARRAY: "bytes", STRING: "string", LIST: "list", COMPOUND: "compound",
              INT_ARRAY: "ints", LONG_ARRAY: "longs"}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    _, root = load(sys.argv[1])
    for name in sorted(root.value):
        tag = root.value[name]
        shown = tag.value if tag.kind not in (COMPOUND, LIST) else f"<{KIND_NAMES[tag.kind]}>"
        print(f"{name:40} {KIND_NAMES[tag.kind]:9} {json.dumps(shown)[:90] if not isinstance(shown, str) or tag.kind == STRING else shown}")
