# Credits

## Skyblock Infinite, the Java data pack

Everything this add-on places was built for the Java Edition data pack **Skyblock Infinite**, by
**Dr.Trog**, and is used here under the Apache License 2.0.

- Project: <https://modrinth.com/datapack/skyblock-infinite>
- Version ported: 1.1.18
- Licence: Apache-2.0
- In this tree: the 47 island templates in
  [development_behavior_packs/skyblock_infinite/structures/skyblock/](development_behavior_packs/skyblock_infinite/structures/skyblock/),
  converted from the data pack's `.nbt` templates, and the recipes and loot tables in
  [recipes/](development_behavior_packs/skyblock_infinite/recipes/) and
  [loot_tables/](development_behavior_packs/skyblock_infinite/loot_tables/), ported from its JSON.

## Island builders

The data pack's Modrinth page credits these builders for individual islands. Their work is what the
`.mcstructure` files in this repository contain.

| Builder | Islands |
| --- | --- |
| Doovid | Jagged Peaks, Swamp, Badlands, Dark Forest |
| PandaX | Mangrove, Lush Cave, Windswept Gravelly Hills, Desert, Savanna, Birch, Dripstone Cave |
| Porg Collector | Deep Frozen Ocean |
| Andergamez | Beach |
| MrAmericanMike | Mushroom Fields |
| WolfButterCup | Ice Spikes |
| Anathra | Sulfur Caves |

## Pack icon

`development_behavior_packs/skyblock_infinite/pack_icon.png` and the resource pack's copy are this
project's own, written by [tools/make_pack_icons.py](tools/make_pack_icons.py): the plains island cut out
of one of the screenshots `tools/capture_previews.py` took, set on a gradient in the thumbnail's blues. The
island itself is Dr.Trog's build, Apache-2.0, like the rest of them.

They used to be the data pack's own 32 pixel `skyblock-infinite_pack.png`, which was too small to read in
Minecraft's pack list.

`world_template/world_icon.jpeg` is `assets/thumbnail.png` resized, so see the next section for what is in
it.

## Thumbnail

The title on `assets/thumbnail.png` is set in **Passion One** (Black), by **Dario Manuel Muhafara**,
under the SIL Open Font License 1.1.

- Project: <https://fonts.google.com/specimen/Passion+One>
- Licence: OFL-1.1
- In this tree: [tools/fonts/PassionOne-Black.ttf](tools/fonts/PassionOne-Black.ttf)

Everything else in the thumbnail is this project's own: `assets/background.png` is a screenshot of the
world the add-on generates, and `assets/skin.png` is the author's player skin.

## Code reused from this author's other repositories

- The NBT reader and writer in [tools/nbt_to_mcstructure.py](tools/nbt_to_mcstructure.py) come from
  `cobblemon-bedrock`, as do [tools/bridge.py](tools/bridge.py) and [tools/bds_host.py](tools/bds_host.py).
- The void world recipe — a flat world whose `FlatWorldLayers` has no block layers — is the one documented
  in `void-world-bedrock`, and [world_template/level.dat](world_template/) is derived from that world's own
  `level.dat`.
