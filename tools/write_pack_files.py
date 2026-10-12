"""Write the behavior pack's recipes and loot tables from the Java datapack's own JSON.

    python tools/write_pack_files.py

The datapack makes a handful of otherwise dead-end blocks renewable (java/data/skyblock/recipes and
java/data/minecraft/recipes) and adds a drop to three mobs (java/data/minecraft/loot_tables/entities). Those
are the rules that make the progression work, so they are ported rather than reinvented: the recipes become
Bedrock recipe JSON one for one, and the loot tables become overrides of the Bedrock tables the mobs use.

Two things differ, and both are forced by Bedrock:
  * Java can say "roll the vanilla table, then roll mine". Bedrock cannot include another table, so each
    override repeats the vanilla pool, copied from the server's own behavior_packs/vanilla.
  * A Bedrock husk has no loot table of its own: it rolls loot_tables/entities/zombie.json, the same file a
    zombie rolls. Overriding that would give every zombie sand, so the husk's sand is dropped from
    scripts/main.js instead, on the entityDie event.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PACK = os.path.join(REPO, "development_behavior_packs", "skyblock_infinite")

CORALS = ("tube", "brain", "bubble", "fire", "horn")


def shapeless(name, ingredients, result, count=1, unlock=None):
    recipe = {"format_version": "1.20.10", "minecraft:recipe_shapeless": {
        "description": {"identifier": f"skyblock_infinite:{name}"},
        "tags": ["crafting_table"],
        "ingredients": [{"item": f"minecraft:{item}"} for item in ingredients],
        "result": {"item": f"minecraft:{result}", "count": count},
        "unlock": [{"item": f"minecraft:{item}"} for item in sorted(set(unlock or ingredients))]}}
    return recipe


def shaped(name, pattern, key, result, count=1):
    return {"format_version": "1.20.10", "minecraft:recipe_shaped": {
        "description": {"identifier": f"skyblock_infinite:{name}"},
        "tags": ["crafting_table"],
        "pattern": pattern,
        "key": {symbol: {"item": f"minecraft:{item}"} for symbol, item in key.items()},
        "result": {"item": f"minecraft:{result}", "count": count},
        "unlock": [{"item": f"minecraft:{item}"} for item in sorted(set(key.values()))]}}


def recipes():
    out = {}
    # the stone cycle: basalt and cobblestone into deepslate, deepslate and basalt into blackstone,
    # andesite and iron nuggets into tuff
    out["cobbled_deepslate"] = shapeless("cobbled_deepslate", ["basalt", "basalt", "cobblestone", "cobblestone"],
                                         "cobbled_deepslate", 4)
    out["blackstone"] = shapeless("blackstone", ["cobbled_deepslate", "cobbled_deepslate", "basalt", "basalt"],
                                  "blackstone")
    out["tuff"] = shapeless("tuff", ["andesite", "andesite", "iron_nugget", "iron_nugget"], "tuff", 4)
    # the nether and the ocean, which a skyblock has no other way to reach
    out["netherrack"] = shapeless("netherrack", ["weeping_vines"] * 4, "netherrack")
    out["kelp"] = shapeless("kelp", ["seagrass"] * 4, "kelp")
    out["spore_blossom"] = shaped("spore_blossom", ["#  ", "#F#", "#  "],
                                  {"#": "moss_block", "F": "flowering_azalea"}, "spore_blossom")
    # a coral block from four of either the coral or its fan, so a tropical fish drop is enough to farm them
    for coral in CORALS:
        out[f"{coral}_coral_block"] = shapeless(f"{coral}_coral_block", [f"{coral}_coral"] * 4, f"{coral}_coral_block")
        out[f"{coral}_coral_block_fan"] = shapeless(f"{coral}_coral_block_fan", [f"{coral}_coral_fan"] * 4,
                                                    f"{coral}_coral_block")
    return out


def loot_tables():
    """The two overrides. Each starts with the pool the server's own vanilla pack rolls, so the mob keeps its
    normal drops, then adds the datapack's."""
    tropical = {"pools": [
        # vanilla: behavior_packs/vanilla/loot_tables/entities/tropicalfish.json
        {"rolls": 1, "entries": [{"type": "item", "name": "minecraft:clownfish", "weight": 1}]},
        {"rolls": 1, "conditions": [{"condition": "random_chance_with_looting", "chance": 0.25, "looting_multiplier": 0.01}],
         "entries": [{"type": "item", "name": "minecraft:bone", "weight": 1,
                      "functions": [{"function": "looting_enchant", "count": {"min": 1, "max": 2}}]}]},
        # the datapack's: one coral or coral fan, so coral is renewable
        {"rolls": 1, "conditions": [{"condition": "random_chance", "chance": 0.25}],
         "entries": [{"type": "item", "name": f"minecraft:{coral}_coral{suffix}", "weight": 1}
                     for coral in CORALS for suffix in ("", "_fan")]},
    ]}
    wither = {"pools": [
        # vanilla: behavior_packs/vanilla/loot_tables/entities/wither_boss.json
        {"rolls": 1, "entries": [{"type": "item", "name": "minecraft:nether_star", "weight": 1}]},
        # the datapack's: ancient debris, so netherite is reachable without a nether fortress chest
        {"rolls": 1, "conditions": [{"condition": "killed_by_player"},
                                    {"condition": "random_chance_with_looting", "chance": 0.5, "looting_multiplier": 0.01}],
         "entries": [{"type": "item", "name": "minecraft:ancient_debris", "weight": 1}]},
    ]}
    return {"tropicalfish": tropical, "wither_boss": wither}


def write(folder, files):
    os.makedirs(folder, exist_ok=True)
    for name, body in files.items():
        with open(os.path.join(folder, name + ".json"), "w", encoding="utf-8") as file:
            json.dump(body, file, indent=2)
            file.write("\n")
    return len(files)


if __name__ == "__main__":
    count = write(os.path.join(PACK, "recipes"), recipes())
    count += write(os.path.join(PACK, "loot_tables", "entities"), loot_tables())
    print(f"wrote {count} files")
