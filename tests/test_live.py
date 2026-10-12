"""Tests that only a running server can answer.

    python -m unittest discover -s tests -v -k test_live

Needs the Bedrock Dedicated Server up on this add-on's world and the MCP bridge with it, as the README's
"Running it here" section describes. Every test skips rather than fails when the bridge is not answering, so
CI (which has no server) can run the whole tests folder.

What is checked here is what static tests cannot see: that the overworld really generates nothing, that the
Nether and the End still generate normally, that the add-on's recipes are registered, and - once someone has
joined - that the starting island is under the spawn point.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def bridge_or_none():
    try:
        from bridge import Bridge
        return Bridge()
    except Exception:
        return None


BRIDGE = bridge_or_none()
NEEDS_SERVER = unittest.skipIf(BRIDGE is None, "no MCP bridge answering on 127.0.0.1:8765")


def block_at(dimension, x, y, z):
    read = BRIDGE.tool("mc_block_get", dimension=dimension, location={"x": x, "y": y, "z": z})
    if "NOT_FOUND" in read or "type_id" not in read:
        return None
    return read.split('type_id: "', 1)[1].split('"', 1)[0]


@NEEDS_SERVER
class TheWorld(unittest.TestCase):
    def test_the_overworld_generates_nothing(self):
        """The whole point of the data pack: no terrain, however far you go."""
        from verify_islands import wait_for_chunk
        for spot in ((4000, 64, 4000), (-12000, 64, 9000)):
            with self.subTest(spot):
                x, y, z = spot
                area = f"sbi_t{abs(x)}"
                BRIDGE.command(f"tickingarea add circle {x} {y} {z} 2 {area}")
                self.assertTrue(wait_for_chunk(BRIDGE, "overworld", spot, timeout=15),
                                "the chunk never loaded, so this proves nothing")
                for dy in range(-60, 120, 12):
                    self.assertEqual(block_at("overworld", x, y + dy, z), "minecraft:air",
                                     f"something generated at {x} {y + dy} {z}")
                BRIDGE.command(f"tickingarea remove {area}")

    def test_the_nether_still_generates(self):
        """A Bedrock flat world only flattens the overworld, which is why the nether islands are off by
        default: the Nether is whole, with its fortresses, so placing islands would bury them."""
        from verify_islands import wait_for_chunk
        spot = (600, 40, 600)
        BRIDGE.command(f"execute in nether run tickingarea add circle {spot[0]} {spot[1]} {spot[2]} 2 sbi_tn")
        self.assertTrue(wait_for_chunk(BRIDGE, "nether", spot, timeout=15))
        found = {block_at("nether", spot[0], y, spot[2]) for y in range(10, 100, 6)}
        BRIDGE.command("execute in nether run tickingarea remove sbi_tn")
        self.assertTrue(found - {"minecraft:air", None}, f"the Nether looks empty: {found}")

    def test_the_end_still_generates(self):
        from verify_islands import wait_for_chunk
        BRIDGE.command("execute in the_end run tickingarea add circle 0 60 0 3 sbi_te")
        self.assertTrue(wait_for_chunk(BRIDGE, "the_end", (0, 60, 0), timeout=20))
        found = {block_at("the_end", 0, y, 0) for y in range(40, 80, 4)}
        BRIDGE.command("execute in the_end run tickingarea remove sbi_te")
        self.assertIn("minecraft:end_stone", found, f"no end stone under the End's main island: {found}")


@NEEDS_SERVER
class Islands(unittest.TestCase):
    def test_every_island_places(self):
        from verify_islands import verify
        _, failures = verify(BRIDGE)
        self.assertEqual(failures, [], "islands that did not place")


@NEEDS_SERVER
class Recipes(unittest.TestCase):
    def test_the_added_recipes_are_registered(self):
        """`/recipe` is not a Bedrock command, so this asks the server for the crafting result instead: a
        recipe the pack failed to load would leave the item uncraftable, and the cheapest proof the server
        can give is that the result item exists and the pack parsed without a content error."""
        log = os.path.join(os.environ.get("BDS", r"C:\GitHub\bedrock-server"), "bds.out.log")
        if not os.path.exists(log):
            self.skipTest(f"no {log}")
        with open(log, encoding="utf-8", errors="replace") as file:
            text = file.read()
        for bad in ("Error parsing recipe", "Unknown recipe", "failed to load recipe",
                    "skyblock_infinite' is not", "[Scripting] [main] ERROR"):
            self.assertNotIn(bad, text, f"the server log complains: {bad}")
        self.assertIn("Skyblock Infinite", text, "the pack is not in the server's pack stack")


@NEEDS_SERVER
class PlayerStart(unittest.TestCase):
    """Only meaningful once someone has joined, because the add-on waits for a player before generating."""

    def setUp(self):
        players = BRIDGE.tool("mc_player_list")
        if "players: []" in players:
            self.skipTest("nobody is on the server, so no starting island has been generated yet")

    def test_the_spawn_point_has_an_island_under_it(self):
        self.assertEqual(block_at("overworld", 6, 63, 6), "minecraft:grass_block",
                         "the player's spawn at 6 64 6 should stand on the island's grass")

    def test_the_starter_chest_is_stocked(self):
        inventory = BRIDGE.tool("mc_inventory_get",
                                container={"block": {"dimension": "overworld",
                                                     "location": {"x": 10, "y": 64, "z": 6}}})
        self.assertIn("minecraft:obsidian", inventory, "the starter chest should hold its obsidian")
        self.assertIn("minecraft:lava_bucket", inventory)


if __name__ == "__main__":
    unittest.main()
