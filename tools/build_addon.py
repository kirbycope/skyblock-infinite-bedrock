"""Build skyblock-infinite-bedrock.mctemplate from the repository, so nothing is copied into a zip by hand.

    python tools/build_addon.py            writes build/skyblock-infinite-bedrock.mctemplate
    python tools/build_addon.py --check    exits 1 if a build would differ from the archive on disk

The archive is what Minecraft imports when the file is double-clicked: the template's own files at the root
(manifest.json, level.dat, levelname.txt, world_icon.jpeg from world_template/), and the two packs under
behavior_packs/ and resource_packs/. The pack lists are written from the packs' own manifests, so bumping a
manifest version is all a release needs.

There is no db/ in the archive. Every other world template here ships a pre-generated world, but this one is
an infinite void that the server fills in as anyone walks through it, and the islands are placed by
scripts/main.js the first time a player joins. So the template carries only the settings that make the world
void, and Minecraft generates the rest.

What Minecraft requires of the zip, learned from the archives it accepts: entries at the root (no wrapping
folder), forward slashes in entry names, Deflate or Store, no zip64. PowerShell's Compress-Archive writes
backslashes in entry names and Minecraft refuses the result, which is why this is Python's zipfile.
"""
import argparse
import io
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(ROOT, "world_template")
PACKS = {   # folder in the archive -> pack in the repository
    "behavior_packs/skyblock_infinite": os.path.join(ROOT, "development_behavior_packs", "skyblock_infinite"),
    "resource_packs/skyblock_infinite": os.path.join(ROOT, "development_resource_packs", "skyblock_infinite"),
}
OUTPUT = os.path.join(ROOT, "build", "skyblock-infinite-bedrock.mctemplate")
STAMP = (2026, 1, 1, 0, 0, 0)       # a fixed timestamp keeps the archive reproducible, so --check can compare
STORED = {".png", ".jpg", ".jpeg", ".ogg", ".mcstructure"}   # already compressed, or not worth deflating twice
LIMIT = 100 * 1024 * 1024           # GitHub refuses a file over 100 MB
SKIP = {".DS_Store", "Thumbs.db", ".gitkeep"}


def pack_entry(pack_dir):
    with open(os.path.join(pack_dir, "manifest.json"), encoding="utf-8") as handle:
        header = json.load(handle)["header"]
    return {"pack_id": header["uuid"], "version": header["version"]}


def files_under(directory):
    """Every file below `directory` as (relative posix path, absolute path), sorted."""
    for current, dirs, names in os.walk(directory):
        dirs[:] = sorted(d for d in dirs if d not in {".git", "__pycache__"})
        for name in sorted(names):
            if name in SKIP:
                continue
            absolute = os.path.join(current, name)
            yield os.path.relpath(absolute, directory).replace(os.sep, "/"), absolute


def build():
    """The archive bytes."""
    behavior = [pack_entry(PACKS["behavior_packs/skyblock_infinite"])]
    resource = [pack_entry(PACKS["resource_packs/skyblock_infinite"])]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", allowZip64=False) as archive:

        def add(name, data):
            info = zipfile.ZipInfo(name, date_time=STAMP)
            compress = (zipfile.ZIP_STORED if os.path.splitext(name)[1].lower() in STORED
                        else zipfile.ZIP_DEFLATED)
            info.compress_type = compress
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)

        for relative, absolute in files_under(TEMPLATE_DIR):
            with open(absolute, "rb") as handle:
                add(relative, handle.read())
        add("world_behavior_packs.json", json.dumps(behavior, indent="\t") + "\n")
        add("world_resource_packs.json", json.dumps(resource, indent="\t") + "\n")
        for folder in sorted(PACKS):
            for relative, absolute in files_under(PACKS[folder]):
                with open(absolute, "rb") as handle:
                    add(f"{folder}/{relative}", handle.read())
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare with the archive on disk, write nothing")
    args = parser.parse_args()
    data = build()
    if len(data) > LIMIT:
        sys.exit(f"the archive is {len(data) / 1024 / 1024:.1f} MB, over GitHub's 100 MB limit")
    if args.check:
        if not os.path.exists(OUTPUT):
            print(f"{OUTPUT} does not exist")
            return 1
        with open(OUTPUT, "rb") as handle:
            same = handle.read() == data
        print("up to date" if same else f"{OUTPUT} differs from a fresh build")
        return 0 if same else 1
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "wb") as handle:
        handle.write(data)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        print(f"wrote {OUTPUT} ({len(data) / 1024:.0f} KB, {len(archive.namelist())} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
