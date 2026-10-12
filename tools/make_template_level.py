"""Write world_template/level.dat, the void world the released .mctemplate carries.

    python tools/make_template_level.py [source level.dat]

This is not the world tools/build_world.py makes. That one is copied from the server's mcp-world so it
inherits the Beta APIs experiment the MCP bridge needs, and an experimental world is the wrong thing to hand
anyone: the add-on itself only uses the stable @minecraft/server 2.6.0, so the template should ask for no
experiments at all.

So the template's level.dat comes from a plain flat world instead. The default source is the one in
void-world-bedrock, which is already a flat world with no block layers - the infinite void this add-on needs
- and was made by hand in the client with no experiments on. Everything else is patched here: the name, the
spawn on the starting island, and the gamerules.

The result is committed, because a level.dat is not something a build should need another repository for.
Re-run this only to change the world's settings.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from build_world import SPAWN, VOID_LAYERS, WORLD_NAME
from level_dat import load, patch, save
from nbt_to_mcstructure import BYTE, INT, STRING

DEFAULT_SOURCE = r"C:\GitHub\void-world-bedrock\void-world-bedrock.mcworld"
TARGET = os.path.join(REPO, "world_template", "level.dat")

TEMPLATE_FIELDS = {
    "Generator": 2,
    "FlatWorldLayers": VOID_LAYERS,
    "LevelName": "Skyblock Infinite",
    "SpawnX": SPAWN[0], "SpawnY": SPAWN[1], "SpawnZ": SPAWN[2],
    "GameType": 0,          # survival
    "Difficulty": 2,        # normal
    "commandsEnabled": 1,   # the config menu is a script, but /scriptevent sbi:menu reopens it
    "showcoordinates": 1,
    "mobgriefing": 0,       # every block in this world is part of someone's island
    "dofiretick": 0,
    "isFromWorldTemplate": 1,
    "isWorldTemplateOptionLocked": 0,
}
FIELD_KINDS = {"FlatWorldLayers": STRING, "Generator": INT, "showcoordinates": BYTE, "mobgriefing": BYTE,
               "dofiretick": BYTE, "isFromWorldTemplate": BYTE, "isWorldTemplateOptionLocked": BYTE}


def source_level_dat(path):
    """A level.dat on disk, or the one inside an .mcworld archive."""
    if path.endswith(".mcworld"):
        import zipfile
        scratch = os.path.join(HERE, "__level_dat_source")
        with zipfile.ZipFile(path) as archive:
            name = next(n for n in archive.namelist() if n.endswith("level.dat") and "_old" not in n)
            os.makedirs(scratch, exist_ok=True)
            out = os.path.join(scratch, "level.dat")
            with archive.open(name) as src, open(out, "wb") as dst:
                dst.write(src.read())
        return out
    return path


if __name__ == "__main__":
    source = source_level_dat(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SOURCE)
    header, root = load(source)
    before = {name: root.value[name].value for name in ("Generator", "FlatWorldLayers") if name in root.value}
    patch(root, TEMPLATE_FIELDS, FIELD_KINDS)
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    save(TARGET, header, root)
    experiments = root.value.get("experiments")
    print(f"source {source}")
    print(f"  was Generator={before.get('Generator')} layers={json.loads(before.get('FlatWorldLayers', '{}')).get('block_layers')}")
    print(f"  experiments: {({k: v.value for k, v in experiments.value.items()} if experiments else 'none')}")
    print(f"wrote {TARGET}")
