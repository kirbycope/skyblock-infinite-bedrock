"""Make the Bedrock Dedicated Server world this add-on is developed against, and wire the packs into it.

    python tools/build_world.py                 make (or repair) the world and junction the packs in
    python tools/build_world.py --reset         throw the terrain away and start the world again
    python tools/build_world.py --check         report only, non-zero if anything is missing

Bedrock has no way for an add-on to replace a dimension's generator, so the infinite void is the world's
own: a flat world (`Generator` 2) whose FlatWorldLayers has an empty `block_layers`, which is the recipe
void-world-bedrock documents. Nothing then generates in the overworld no matter how far you travel, which is
the datapack's headline feature; the Nether and the End still generate normally, because a Bedrock flat
world only flattens the overworld.

The level.dat is copied from worlds/mcp-world, the one world on this server made by a client with the Beta
APIs experiment turned on. Only a client can turn that experiment on, and the bridge pack needs it, so every
new world here starts as a copy of that file and is then patched: the generator, the layers, the name, the
spawn and the gamerules. BDS generates fresh terrain around it.

The packs are NTFS junctions into this repository, so an edit here is live on the next server restart with
nothing to copy back. The bedrock-bridge pack is copied rather than junctioned, the way the other add-on
worlds here do it, because it belongs to the MCP server rather than to this repository.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from level_dat import load, patch, save
from nbt_to_mcstructure import BYTE, INT, STRING

BDS = os.environ.get("BDS", r"C:\GitHub\bedrock-server")
WORLD_NAME = "skyblock-infinite"
WORLD = os.path.join(BDS, "worlds", WORLD_NAME)
TEMPLATE_WORLD = os.path.join(BDS, "worlds", "mcp-world")
BRIDGE_PACK = "fa013817-66f2-4a5f-a724-1347f912bd40"
PACKS = [("behavior_packs", os.path.join(REPO, "development_behavior_packs", "skyblock_infinite")),
         ("resource_packs", os.path.join(REPO, "development_resource_packs", "skyblock_infinite"))]
# The client's own development folders. Junctioning the packs in here too is what makes them show up in the
# client's world settings, so a world can be made in the client without going through the server at all.
CLIENT = os.path.join(os.environ.get("APPDATA", ""), "Minecraft Bedrock", "Users", "Shared", "games", "com.mojang")
CLIENT_PACKS = [("development_behavior_packs", PACKS[0][1]), ("development_resource_packs", PACKS[1][1])]
# A flat world with no layers at all: air from bedrock to build limit, forever. biome_id 1 is plains, which
# is what lets grass grow and passive mobs spawn on an island.
VOID_LAYERS = '{"biome_id":1,"block_layers":[],"encoding_version":6,"structure_options":null,"world_version":"version.post_1_18"}\n'
SPAWN = (6, 64, 6)


def manifest(path):
    with open(os.path.join(path, "manifest.json"), encoding="utf-8") as file:
        return json.load(file)


# What this world needs to differ from the one its level.dat is copied from. Every one of these already
# exists in a Bedrock level.dat, so each keeps the NBT type it had; FIELD_KINDS covers the few that an older
# file might not carry yet.
WORLD_FIELDS = {
    "Generator": 2,                          # 2 is flat, and with no layers that means void
    "FlatWorldLayers": VOID_LAYERS,
    "LevelName": WORLD_NAME,
    "SpawnX": SPAWN[0], "SpawnY": SPAWN[1], "SpawnZ": SPAWN[2],
    "GameType": 0, "Difficulty": 2,
    "commandsEnabled": 1, "commandblocksenabled": 1, "sendcommandfeedback": 1, "showcoordinates": 1,
    "LANBroadcast": 1, "LANBroadcastIntent": 1, "MultiplayerGame": 1, "MultiplayerGameIntent": 1,
    # every block in this world is part of someone's island, so nothing gets to break one
    "mobgriefing": 0, "dofiretick": 0,
}
FIELD_KINDS = {"FlatWorldLayers": STRING, "Generator": INT, "showcoordinates": BYTE,
               "mobgriefing": BYTE, "dofiretick": BYTE}


def patch_level_dat(source, target):
    """Copy a level.dat and make it this world: void generator, our name, our spawn, cheats on."""
    header, root = load(source)
    patch(root, WORLD_FIELDS, FIELD_KINDS)
    save(target, header, root)


def junction(link, target):
    if os.path.exists(link):
        # a junction is deleted through the link itself; Remove-Item -Recurse would empty the repository
        subprocess.run(["cmd", "/c", "rmdir", link], check=False, capture_output=True)
    os.makedirs(os.path.dirname(link), exist_ok=True)
    result = subprocess.run(["cmd", "/c", "mklink", "/J", link, target], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"mklink failed for {link}: {result.stdout}{result.stderr}")


def write_pack_list(path, packs):
    with open(path, "w", encoding="utf-8") as file:
        json.dump([{"pack_id": uuid, "version": version} for uuid, version in packs], file, indent=1)


def link_into_client():
    """Junction the packs into the Minecraft client's own development folders, so they appear in its world
    settings. Without this the add-on only exists on the server, which is why it was missing from the
    client's behavior pack list the first time anyone looked."""
    if not os.path.isdir(CLIENT):
        print(f"  no Minecraft client at {CLIENT}; skipping the client junctions")
        return
    for folder, source in CLIENT_PACKS:
        try:
            junction(os.path.join(CLIENT, folder, "skyblock_infinite"), source)
        except RuntimeError as error:
            print(f"  could not link into the client: {error}")
            return
    print(f"  linked into the client at {CLIENT}")


def build(reset=False):
    if reset and os.path.exists(WORLD):
        for folder, _ in PACKS:                      # unlink before deleting, never through a junction
            link = os.path.join(WORLD, folder, "skyblock_infinite")
            if os.path.exists(link):
                subprocess.run(["cmd", "/c", "rmdir", link], check=False, capture_output=True)
        shutil.rmtree(os.path.join(WORLD, "db"), ignore_errors=True)
        print("reset: terrain thrown away")
    os.makedirs(WORLD, exist_ok=True)
    template = os.path.join(TEMPLATE_WORLD, "level.dat")
    if not os.path.exists(template):
        sys.exit(f"no {template}: a world with the Beta APIs experiment has to exist to copy from")
    patch_level_dat(template, os.path.join(WORLD, "level.dat"))
    with open(os.path.join(WORLD, "levelname.txt"), "w", encoding="utf-8") as file:
        file.write(WORLD_NAME)

    behaviors, resources = [], []
    for folder, source in PACKS:
        head = manifest(source)["header"]
        junction(os.path.join(WORLD, folder, "skyblock_infinite"), source)
        (behaviors if folder == "behavior_packs" else resources).append((head["uuid"], head["version"]))
    # the MCP bridge, copied in so the server can be driven from here
    bridge_source = os.path.join(TEMPLATE_WORLD, "behavior_packs", "bedrock-bridge")
    if os.path.isdir(bridge_source):
        bridge_target = os.path.join(WORLD, "behavior_packs", "bedrock-bridge")
        if not os.path.exists(bridge_target):
            shutil.copytree(bridge_source, bridge_target)
        behaviors.append((BRIDGE_PACK, manifest(bridge_target)["header"]["version"]))
    else:
        print(f"WARNING: no bridge pack at {bridge_source}; the MCP server will not reach this world")
    write_pack_list(os.path.join(WORLD, "world_behavior_packs.json"), behaviors)
    write_pack_list(os.path.join(WORLD, "world_resource_packs.json"), resources)
    link_into_client()
    print(f"world ready at {WORLD}")
    print(f"  behavior packs: {[uuid for uuid, _ in behaviors]}")
    print(f"  resource packs: {[uuid for uuid, _ in resources]}")
    print(f"  set level-name={WORLD_NAME} in {os.path.join(BDS, 'server.properties')} and restart the server")
    return 0


def check():
    problems = []
    if not os.path.exists(os.path.join(WORLD, "level.dat")):
        problems.append("no level.dat")
    else:
        _, root = load(os.path.join(WORLD, "level.dat"))
        fields = {name: tag.value for name, tag in root.value.items()}
        if fields.get("Generator") != 2:
            problems.append(f"Generator is {fields.get('Generator')}, not 2 (flat)")
        if json.loads(fields.get("FlatWorldLayers", "{}")).get("block_layers") != []:
            problems.append("FlatWorldLayers still has block layers, so the world is not void")
    for folder, source in PACKS:
        link = os.path.join(WORLD, folder, "skyblock_infinite")
        if not os.path.exists(link): problems.append(f"no junction at {link}")
    for problem in problems:
        print("MISSING:", problem)
    print("world looks right" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(check() if "--check" in sys.argv else build(reset="--reset" in sys.argv))
