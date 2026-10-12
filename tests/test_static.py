"""Tests that need neither the Java data pack nor a running server, so CI can run them.

    python -m unittest discover -s tests -v

The data pack is git-ignored (see the README), so nothing here reads java/. These check the pack as it is
committed: the manifests agree with each other, every island the script can ask for is really in the pack,
every block in every structure is a name the server has accepted, and the world the template ships is void.

tests/test_live.py covers what only a server can answer.
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from nbt_to_mcstructure import read_nbt

BP = os.path.join(ROOT, "development_behavior_packs", "skyblock_infinite")
RP = os.path.join(ROOT, "development_resource_packs", "skyblock_infinite")
TEMPLATE = os.path.join(ROOT, "world_template")


def load_json(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as file:
        return json.load(file)


def islands_js():
    """The generated scripts/islands.js, read without a JavaScript engine."""
    with open(os.path.join(BP, "scripts", "islands.js"), encoding="utf-8") as file:
        text = file.read()
    out = {}
    for name in ("FALLBACK", "STARTING", "OUTER", "NETHER", "ISLANDS"):
        match = re.search(rf"export const {name} = (.*?);\n", text, re.S)
        out[name] = json.loads(match.group(1))
    return out


class Manifests(unittest.TestCase):
    def test_behavior_pack_depends_on_the_resource_pack(self):
        bp = load_json(BP, "manifest.json")
        rp = load_json(RP, "manifest.json")
        uuids = [d.get("uuid") for d in bp["dependencies"] if "uuid" in d]
        self.assertIn(rp["header"]["uuid"], uuids,
                      "the behavior pack must depend on the resource pack's uuid")

    def test_every_uuid_is_distinct(self):
        seen = []
        for manifest in (load_json(BP, "manifest.json"), load_json(RP, "manifest.json"),
                         load_json(TEMPLATE, "manifest.json")):
            seen.append(manifest["header"]["uuid"])
            seen += [module["uuid"] for module in manifest["modules"]]
        self.assertEqual(len(seen), len(set(seen)), f"a uuid is used twice: {seen}")

    def test_script_module_points_at_the_entry_file(self):
        bp = load_json(BP, "manifest.json")
        script = next(m for m in bp["modules"] if m["type"] == "script")
        self.assertTrue(os.path.exists(os.path.join(BP, script["entry"])), script["entry"])

    def test_script_api_versions_are_pinned(self):
        deps = {d["module_name"]: d["version"] for d in load_json(BP, "manifest.json")["dependencies"]
                if "module_name" in d}
        self.assertIn("@minecraft/server", deps)
        self.assertIn("@minecraft/server-ui", deps)
        for name, version in deps.items():
            self.assertRegex(version, r"^\d+\.\d+\.\d+$", f"{name} must be pinned to an exact version")


class Islands(unittest.TestCase):
    def setUp(self):
        self.table = islands_js()

    def test_the_generated_table_matches_the_structure_files(self):
        for key, island in self.table["ISLANDS"].items():
            name = island["structure"].split(":", 1)[1]
            path = os.path.join(BP, "structures", "skyblock", name + ".mcstructure")
            self.assertTrue(os.path.exists(path), f"{key} names {island['structure']}, but {path} is missing")

    def test_every_structure_file_is_in_the_table(self):
        folder = os.path.join(BP, "structures", "skyblock")
        on_disk = {f[: -len(".mcstructure")] for f in os.listdir(folder) if f.endswith(".mcstructure")}
        named = {i["structure"].split(":", 1)[1] for i in self.table["ISLANDS"].values()}
        self.assertEqual(on_disk, named)

    def test_no_structure_name_has_a_slash(self):
        # /structure load will not parse a slash in a structure name; it is a syntax error on the server
        for island in self.table["ISLANDS"].values():
            self.assertNotIn("/", island["structure"].split(":", 1)[1], island["structure"])

    def test_every_island_has_a_placement(self):
        for key, island in self.table["ISLANDS"].items():
            self.assertIsNotNone(island["offset"], f"{key} has no offset, so nothing can place it")
            self.assertEqual(len(island["offset"]), 3, key)

    def test_the_lists_the_script_picks_from_are_all_in_the_table(self):
        for kind, names in (("starting_islands", self.table["STARTING"]),
                            ("outer_islands", self.table["OUTER"]),
                            ("nether_islands", self.table["NETHER"])):
            for name in names:
                self.assertIn(f"{kind}/{name}", self.table["ISLANDS"])
        self.assertIn(self.table["FALLBACK"], self.table["STARTING"])

    def test_the_table_agrees_with_islands_json(self):
        stored = load_json(ROOT, "tools", "islands.json")
        self.assertEqual(stored["islands"], self.table["ISLANDS"])
        self.assertEqual(stored["fallback"], self.table["FALLBACK"])


class Structures(unittest.TestCase):
    """Every .mcstructure is read back and checked against the block names the server has accepted."""

    @classmethod
    def setUpClass(cls):
        cls.valid = set(load_json(ROOT, "tools", "bedrock_blocks.json")["valid"])
        cls.files = sorted(f for f in os.listdir(os.path.join(BP, "structures", "skyblock"))
                           if f.endswith(".mcstructure"))

    def read(self, name):
        with open(os.path.join(BP, "structures", "skyblock", name), "rb") as file:
            return read_nbt(file.read(), little=True)

    def test_there_are_47_islands(self):
        self.assertEqual(len(self.files), 47)

    def test_each_structure_parses_and_its_size_matches_its_block_count(self):
        for name in self.files:
            with self.subTest(name):
                data = self.read(name)
                sx, sy, sz = data["size"]
                layers = data["structure"]["block_indices"]
                self.assertEqual(len(layers), 2, "a Bedrock structure has two block layers")
                self.assertEqual(len(layers[0]), sx * sy * sz)

    def test_every_block_name_is_one_the_server_accepted(self):
        for name in self.files:
            with self.subTest(name):
                palette = self.read(name)["structure"]["palette"]["default"]["block_palette"]
                for entry in palette:
                    short = entry["name"].split(":", 1)[1]
                    self.assertIn(short, self.valid,
                                  f"{name} uses {entry['name']}, which tools/validate_blocks.py has not "
                                  f"accepted against a server")

    def test_the_starting_islands_each_carry_their_starter_chest(self):
        chests = 0
        for name in self.files:
            if not name.startswith("starting_islands_"):
                continue
            data = self.read(name)
            positions = data["structure"]["palette"]["default"].get("block_position_data", {})
            items = [p for p in positions.values() if p.get("block_entity_data", {}).get("id") == "Chest"]
            self.assertEqual(len(items), 1, f"{name} should hold exactly one starter chest")
            self.assertTrue(items[0]["block_entity_data"]["Items"], f"{name}'s chest is empty")
            chests += 1
        self.assertEqual(chests, 26, "all 26 starting islands carry a chest")


class MenuPreviews(unittest.TestCase):
    """The config menu's buttons are texture buttons, and a texture the resource pack does not have shows as
    a blank button rather than an error, so the pictures are checked rather than trusted."""

    FOLDER = os.path.join(RP, "textures", "ui", "islands")
    # the three pictures that are not an island; see SPECIALS in tools/capture_previews.py
    SPECIALS = ("void", "portal_room", "spawn")

    def test_every_island_has_a_preview(self):
        for key in islands_js()["ISLANDS"]:
            name = key.replace("/", "_") + ".png"
            self.assertTrue(os.path.exists(os.path.join(self.FOLDER, name)),
                            f"{key} has no preview at textures/ui/islands/{name}")

    def test_the_pictures_that_are_not_islands_are_there(self):
        for name in self.SPECIALS:
            self.assertTrue(os.path.exists(os.path.join(self.FOLDER, name + ".png")), name)

    def test_every_texture_the_menu_names_exists(self):
        """Every literal textures/ui/islands/... path in main.js, including the ones built from a template
        literal, which are expanded over the island lists."""
        source = open(os.path.join(BP, "scripts", "main.js"), encoding="utf-8").read()
        table = islands_js()
        names = {n for n in re.findall(r'ICON\("([a-z_]+)"\)', source)}
        for match in re.findall(r'ICON\(`([a-z_]+)_\$\{([A-Za-z]+)\}`\)', source):
            prefix, variable = match
            values = {"seedIsland": table["STARTING"], "name": table["STARTING"],
                      "FALLBACK": [table["FALLBACK"]]}.get(variable)
            self.assertIsNotNone(values, f"main.js builds a texture name from {variable}, which this test "
                                         f"does not know how to expand")
            names |= {f"{prefix}_{value}" for value in values}
        self.assertGreater(len(names), 25, "the menu should name a lot of previews")
        for name in sorted(names):
            self.assertTrue(os.path.exists(os.path.join(self.FOLDER, name + ".png")),
                            f"main.js shows textures/ui/islands/{name}, which the pack does not have")

    def test_the_previews_are_square_and_small(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed; the release workflow installs it")
        for name in sorted(os.listdir(self.FOLDER)):
            if not name.endswith(".png"):
                continue
            with Image.open(os.path.join(self.FOLDER, name)) as image:
                self.assertEqual(image.width, image.height, f"{name} is not square")
                self.assertLessEqual(image.width, 256, f"{name} is bigger than a button needs")


class PackIcons(unittest.TestCase):
    """Minecraft draws pack_icon.png in its pack list. The data pack's own icon was 32 pixels, which is too
    small to make out there, so these are generated by tools/make_pack_icons.py."""

    ICONS = [os.path.join(BP, "pack_icon.png"), os.path.join(RP, "pack_icon.png")]

    def test_both_packs_have_an_icon(self):
        for path in self.ICONS:
            self.assertTrue(os.path.exists(path), path)

    def test_the_icons_are_square_and_big_enough_to_read(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed; the release workflow installs it")
        for path in self.ICONS:
            with self.subTest(os.path.basename(os.path.dirname(path))), Image.open(path) as image:
                self.assertEqual(image.width, image.height, "a pack icon is square")
                self.assertGreaterEqual(image.width, 128, "32 pixels was too small to read in the pack list")
                self.assertLessEqual(image.width, 512)

    def test_the_two_packs_show_the_same_icon(self):
        with open(self.ICONS[0], "rb") as a, open(self.ICONS[1], "rb") as b:
            self.assertEqual(a.read(), b.read(), "both packs should carry the same icon")

    def test_the_world_template_icon_is_sixteen_by_nine(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed; the release workflow installs it")
        with Image.open(os.path.join(TEMPLATE, "world_icon.jpeg")) as image:
            self.assertAlmostEqual(image.width / image.height, 16 / 9, places=2)


class PackData(unittest.TestCase):
    def test_recipes_are_well_formed(self):
        folder = os.path.join(BP, "recipes")
        names = sorted(os.listdir(folder))
        self.assertEqual(len(names), 16)
        for name in names:
            with self.subTest(name):
                body = load_json(folder, name)
                self.assertIn("format_version", body)
                kind = next(k for k in body if k.startswith("minecraft:recipe_"))
                recipe = body[kind]
                self.assertTrue(recipe["description"]["identifier"].startswith("skyblock_infinite:"))
                self.assertIn("crafting_table", recipe["tags"])
                self.assertTrue(recipe["result"]["item"].startswith("minecraft:"))

    def test_shaped_recipe_rows_are_the_same_width(self):
        for name in os.listdir(os.path.join(BP, "recipes")):
            body = load_json(BP, "recipes", name)
            if "minecraft:recipe_shaped" not in body:
                continue
            pattern = body["minecraft:recipe_shaped"]["pattern"]
            self.assertEqual(len({len(row) for row in pattern}), 1, f"{name}: {pattern}")

    def test_loot_tables_keep_the_vanilla_drop_and_add_one(self):
        for name, vanilla in (("tropicalfish.json", "minecraft:clownfish"),
                              ("wither_boss.json", "minecraft:nether_star")):
            with self.subTest(name):
                pools = load_json(BP, "loot_tables", "entities", name)["pools"]
                self.assertGreaterEqual(len(pools), 2, "the vanilla pool plus the data pack's")
                first = json.dumps(pools[0])
                self.assertIn(vanilla, first, "the mob must keep its own drop")


class WorldTemplate(unittest.TestCase):
    def test_the_template_world_is_an_empty_flat_world(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from level_dat import load
        _, root = load(os.path.join(TEMPLATE, "level.dat"))
        fields = {name: tag.value for name, tag in root.value.items()}
        self.assertEqual(fields["Generator"], 2, "2 is the flat generator")
        layers = json.loads(fields["FlatWorldLayers"])
        self.assertEqual(layers["block_layers"], [], "no block layers at all is what makes it void")
        self.assertEqual((fields["SpawnX"], fields["SpawnY"], fields["SpawnZ"]), (6, 64, 6))

    def test_the_template_asks_for_no_experiments(self):
        from level_dat import load
        _, root = load(os.path.join(TEMPLATE, "level.dat"))
        experiments = root.value.get("experiments")
        if experiments is None:
            return
        for name, tag in experiments.value.items():
            self.assertIn(tag.value, (0, False), f"the template should need no experiment, but {name} is on")

    def test_the_template_has_the_files_minecraft_wants(self):
        for name in ("manifest.json", "level.dat", "levelname.txt", "world_icon.jpeg"):
            self.assertTrue(os.path.exists(os.path.join(TEMPLATE, name)), name)
        module = load_json(TEMPLATE, "manifest.json")["modules"][0]
        self.assertEqual(module["type"], "world_template")


class WritingStyle(unittest.TestCase):
    """No emoji anywhere, which is a standing rule for every repository here."""

    def test_no_emoji_in_the_text_this_repository_ships(self):
        # built from escapes and not as a literal, so this file does not match its own pattern
        ranges = ((0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0xFE0F, 0xFE0F), (0x2190, 0x21FF), (0x2B00, 0x2BFF))
        emoji = re.compile("[" + "".join(f"{chr(lo)}-{chr(hi)}" for lo, hi in ranges) + "]")
        checked = 0
        for folder, dirs, names in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in {".git", "java", "build", "__pycache__", ".pytest_cache"}]
            for name in names:
                if not name.endswith((".md", ".json", ".js", ".py", ".yml", ".lang")):
                    continue
                path = os.path.join(folder, name)
                if os.path.samefile(path, __file__):
                    continue
                with open(path, encoding="utf-8", errors="replace") as file:
                    found = emoji.findall(file.read())
                self.assertFalse(found, f"{os.path.relpath(path, ROOT)} has emoji: {found[:5]}")
                checked += 1
        self.assertGreater(checked, 20)


if __name__ == "__main__":
    unittest.main()


class Thumbnail(unittest.TestCase):
    """The project art and everything tools/make_thumbnail.py needs to rebuild it."""

    ASSETS = os.path.join(ROOT, "assets")

    def test_sources_are_committed(self):
        for name in ("background.png", "skin.png"):
            self.assertTrue(os.path.isfile(os.path.join(self.ASSETS, name)),
                            f"assets/{name} is missing, so the thumbnail cannot be rebuilt")
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "tools", "fonts",
                                                    "PassionOne-Black.ttf")),
                        "the title font is missing")

    def test_skin_is_a_64x64_classic_model(self):
        from PIL import Image
        with Image.open(os.path.join(self.ASSETS, "skin.png")) as skin:
            self.assertEqual(skin.size, (64, 64))
            # tools/skin_render.py unwraps the 4px-arm layout, not the slim one
            arm = skin.convert("RGBA").crop((47, 20, 48, 32))
            self.assertTrue(max(p[3] for p in arm.getdata()) > 0,
                            "skin_render.py expects the classic 4px arm")

    def test_master_is_1920x1080(self):
        from PIL import Image
        with Image.open(os.path.join(self.ASSETS, "thumbnail.png")) as img:
            self.assertEqual(img.size, (1920, 1080))

    def test_preview_matches_the_portfolio_size(self):
        from PIL import Image
        with Image.open(os.path.join(ROOT, "skyblock-infinite-bedrock.png")) as img:
            self.assertEqual(img.size, (960, 540))
