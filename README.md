![skyblock-infinite-bedrock](/skyblock-infinite-bedrock.png)

# skyblock-infinite-bedrock

A Minecraft Bedrock port of [Skyblock Infinite](https://modrinth.com/datapack/skyblock-infinite) 1.1.18,
Dr.Trog's Java Edition data pack: Skyblock on an infinite void, with all 47 of its islands.

No terrain generates in the overworld, however far you travel. You start on one island, the rest are
scattered out at the distances the data pack puts them, and the Nether and the End are untouched.

See [CREDITS.md](CREDITS.md) for the data pack and its island builders.

## Installation

1. Download the [.mctemplate](https://github.com/kirbycope/skyblock-infinite-bedrock/releases/latest)
1. Double-click the mctemplate file
1. Create a New World using the template
    - "Play" > "Create New" > scroll down to "Imported Templates" (select "See More" if necessary)

The first time you join, a menu asks how to lay the world out. It can be reopened at any time with
`/scriptevent sbi:menu`.

## What it does

| | |
| --- | --- |
| Infinite void | The overworld generates nothing at all, at any distance, with no world border. |
| 26 starting islands | One is placed at spawn, with its chest of starter items. |
| 16 outer islands | The classic rings at 192 and 384 blocks out, at the data pack's own coordinates. |
| 5 nether islands | Off by default; see "What is different on Bedrock" below. |
| Renewable blocks | The data pack's recipes for coral, kelp, netherrack, blackstone, deepslate, tuff and spore blossoms. |
| Extra drops | Husks drop sand, tropical fish drop coral, and the wither drops ancient debris. |
| An end portal | A stronghold portal room, so the End is still reachable. |

### The menu

| Setting | Choices |
| --- | --- |
| Starting island | **Seed**, an island picked by this world's layout seed, or **Classic**, the original plains island |
| Outer islands | **Seed**, the islands this world's seed picks, **Classic**, all sixteen, or **Off** |
| Nether islands | **Off** (the default) or **On** |
| End portal | A portal room **far** out at 1000 60 1000, **near** at 64 60 64, or **off** |

Two more commands, both only useful before the world is generated or for looking around:

```
/scriptevent sbi:seed 12345        set the layout seed, so a layout can be reproduced
/scriptevent sbi:island desert     place a named starting island at spawn
```

## What is different on Bedrock

An add-on cannot replace a dimension's generator the way a Java data pack can, and Bedrock generates no
structures in an empty world. Those two limits are behind every difference here.

**The void is the world's, not the add-on's.** The world is a flat world whose `FlatWorldLayers` has no
block layers at all, which is the recipe in
[void-world-bedrock](https://github.com/kirbycope/void-world-bedrock). That is what makes the overworld
infinite void. It also means the setting travels with the world rather than with the pack: adding this
behavior pack to a normal world gives you the islands on top of ordinary terrain, not a skyblock.

**Seed mode picks differently.** The data pack's seed mode reads the biome you are standing in and gives
you the matching island. A Bedrock flat world is one biome everywhere, so there is no biome to read.
Instead each world mints a layout seed, and that picks the starting island and which outer islands appear,
so the mode still does what it is for: a different island every world. Classic mode is unchanged, and both
`/scriptevent sbi:seed` and `/scriptevent sbi:island` are there if you want a particular one.

**The Nether and the End are normal.** A Bedrock flat world only flattens the overworld, so both other
dimensions generate the way they always do. That is better than the data pack manages, not worse:
fortresses, blazes, wither skeletons, nether wart and end cities are all simply there. It is also why the
five nether islands are off by default - placing them would bury them inside solid netherrack. Turn them on
in the menu if you want them anyway.

**The end portal is built, not found.** The data pack relies on vanilla worldgen putting strongholds in its
void. Bedrock will not generate one in a void world, so the add-on builds a stronghold portal room instead,
with its twelve frames empty, and tells you where it is. Nothing else the data pack leaves to worldgen
(witch huts, villages, monuments) comes across; they would each have to be rebuilt as structures.

**Four extra starting islands.** The data pack ships 26 starting islands but only ever places 22: no
overworld biome maps to its crimson forest, warped forest, soul sand valley or snowy slopes islands. They
are finished islands with a starter chest like the rest, so seed mode here can pick them too.

## Running it here

The add-on is developed against the Bedrock Dedicated Server in `C:\GitHub\bedrock-server`, driven through
the `minecraft-bedrock` MCP server. The packs are junctioned into the world, so an edit here is live on the
next server restart.

```powershell
python tools/build_world.py          # make the world, junction the packs in
# set level-name=skyblock-infinite in bedrock-server/server.properties, then start the bridge and the server
python tools/build_world.py --reset  # throw the terrain away and start the world over
```

Structure files are read when the world loads, so a converted island only appears after a server restart,
not after `/reload`.

## Tools

| | |
| --- | --- |
| `tools/convert_islands.py` | Converts all 47 island templates and writes `scripts/islands.js` |
| `tools/nbt_to_mcstructure.py` | The Java `.nbt` to Bedrock `.mcstructure` converter |
| `tools/validate_blocks.py` | Checks every block name the islands use against a running server |
| `tools/verify_islands.py` | Places every island on a running server and counts what landed |
| `tools/build_world.py` | Makes the development world on the server |
| `tools/build_addon.py` | Builds `build/skyblock-infinite-bedrock.mctemplate` |
| `tools/make_template_level.py` | Rewrites `world_template/level.dat` |
| `tools/write_pack_files.py` | Writes the recipes and loot tables from the data pack's JSON |
| `tools/bridge.py` | Runs commands through the MCP bridge, no client needed |
| `tools/client_drive.py` | Drives the real client on this PC and captures what it shows |

### The original data pack

`java/` holds the extracted `skyblock-infinite-1.1.18.jar` and is git-ignored: the port's source is never
checked in. Download the jar from
[Modrinth](https://modrinth.com/datapack/skyblock-infinite/versions) and extract it there before running
`tools/convert_islands.py`. Everything the conversion produces is committed, so a normal build needs it.

## Tests

```powershell
python -m unittest discover -s tests -v
```

`tests/test_static.py` needs nothing but the repository and runs in CI: the manifests agree, every island
the script can ask for is in the pack, every block in every structure is a name a server has accepted, all
26 starting chests are stocked, and the template world is void. `tests/test_live.py` needs the server and
the bridge, and skips itself when they are not there.

## Releasing

Pushing a tag that starts with `v` (for example `git tag v1.1.18 && git push origin v1.1.18`) runs
[.github/workflows/release.yml](.github/workflows/release.yml), which runs the static tests, builds the
world template and attaches `skyblock-infinite-bedrock.mctemplate` to a GitHub Release.

To build it locally, run `python tools/build_addon.py`; it writes `build/`, which git ignores.

## Licence

Apache-2.0, because the data pack this is a port of is Apache-2.0. That differs from the MIT licence on the
other Bedrock add-ons here, and it has to: the islands, recipes and loot tables are Dr.Trog's work, carried
over under the terms they were published under. See [LICENSE](LICENSE) and [CREDITS.md](CREDITS.md).
