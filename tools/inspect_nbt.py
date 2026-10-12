"""Print what a Java structure template holds: size, palette, and any block entity data.

    python tools/inspect_nbt.py java/data/skyblock/structures/starting_islands/plaines.nbt
"""
import gzip, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nbt_to_mcstructure import read_nbt

for path in sys.argv[1:]:
    with open(path, "rb") as f:
        java = read_nbt(gzip.decompress(f.read()))
    print(f"=== {os.path.basename(path)} size={java['size']} blocks={len(java.get('blocks', []))} palette={len(java.get('palette', []))}")
    states = {}
    for e in java.get("palette", []):
        if e.get("Properties"):
            states.setdefault(e["Name"], set()).update(e["Properties"].keys())
    for name in sorted(states):
        print("   states", name, sorted(states[name]))
    for b in java.get("blocks", []):
        if b.get("nbt"):
            print("   nbt at", b["pos"], java["palette"][b["state"]]["Name"], json.dumps(b["nbt"])[:400])
