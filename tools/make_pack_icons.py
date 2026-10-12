"""Make the packs' icons and the world template's icon from art this repository already has.

    python tools/make_pack_icons.py                  write the icons
    python tools/make_pack_icons.py --preview        write captures/pack_icon_preview.png and nothing else
    python tools/make_pack_icons.py --island plaines which island to put on the icon

Both packs shipped the data pack's own 32 pixel icon, which is too small to read in Minecraft's pack list.
The icon here is the plains island - a tree, a grass island and the starter chest, which is what skyblock
looks like to anyone - lifted out of one of the full size screenshots tools/capture_previews.py took and set
on the thumbnail's blue sky rather than the void's pale one, so it still reads at the size a pack list
draws it.

Lifting it out needs no cutout by hand: the capture tool photographs the empty stage before it photographs
the island, so the island is exactly what differs between the two frames, and that difference is the mask.

The world template's icon is the thumbnail itself, which is already 16:9 and already says what the add-on is.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from PIL import Image, ImageFilter

CAPTURES = os.path.join(REPO, "captures")
THUMBNAIL = os.path.join(REPO, "assets", "thumbnail.png")
ICONS = [os.path.join(REPO, "development_behavior_packs", "skyblock_infinite", "pack_icon.png"),
         os.path.join(REPO, "development_resource_packs", "skyblock_infinite", "pack_icon.png")]
WORLD_ICON = os.path.join(REPO, "world_template", "world_icon.jpeg")
ISLAND = "plaines"
SIZE = 256              # what the pack icon is written at
WORLD_SIZE = (800, 450)
PAD = 0.16              # sky left around the island
THRESHOLD = 16          # how far a pixel has to be from the empty frame to count as island


def sky(height, width):
    """A vertical gradient in the thumbnail's own blues, so the icon matches the rest of the art."""
    thumb = Image.open(THUMBNAIL).convert("RGB")
    top = thumb.getpixel((thumb.width // 2, 30))
    bottom = thumb.getpixel((60, int(thumb.height * 0.62)))
    gradient = Image.new("RGB", (1, height))
    for y in range(height):
        f = y / max(1, height - 1)
        gradient.putpixel((0, y), tuple(int(top[c] + (bottom[c] - top[c]) * f) for c in range(3)))
    return gradient.resize((width, height), Image.BILINEAR)


def island_on_sky(name, size=SIZE):
    """The island cut out of its screenshot and set on the gradient."""
    import numpy as np
    shot = os.path.join(CAPTURES, f"preview_starting_islands_{name}.png")
    empty = os.path.join(CAPTURES, f"preview_starting_islands_{name}_bg.png")
    for path in (shot, empty):
        if not os.path.exists(path):
            sys.exit(f"no {path}; run tools/capture_previews.py first")
    front = Image.open(shot).convert("RGB")
    back = Image.open(empty).convert("RGB")
    mask = (np.abs(np.asarray(front, dtype=np.int16) - np.asarray(back, dtype=np.int16)).max(axis=2)
            > THRESHOLD)
    # Only inside the part of the capture the island can be in. Taking the whole screen instead let the
    # taskbar clock, which ticks over between the two frames, count as part of the island and blew the box
    # up until the island was a speck in the middle of it.
    import capture_previews as cp
    left, top, right, bottom = cp.SEARCH
    outside = np.ones_like(mask)
    outside[top:bottom, left:right] = False
    mask[outside] = False
    rows, columns = np.where(mask)
    if not len(rows):
        sys.exit("the two frames are identical; there is no island to cut out")
    # a square around the island, with sky left around it; percentiles so one stray pixel cannot set the size
    y0, y1 = (int(v) for v in np.percentile(rows, (0.3, 99.7)))
    x0, x1 = (int(v) for v in np.percentile(columns, (0.3, 99.7)))
    side = int(max(x1 - x0, y1 - y0) * (1 + 2 * PAD))
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    box = (cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2)
    alpha = Image.fromarray((mask * 255).astype("uint8")).crop(box)
    cut = front.crop(box)
    # the mask is on or off per pixel, so it would leave a stair-stepped edge; blurring it a little and
    # resizing down from a crop several times the icon's size is what smooths it
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.8))
    icon = sky(cut.height, cut.width)
    icon.paste(cut, (0, 0), alpha)
    return icon.resize((size, size), Image.LANCZOS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--island", default=ISLAND)
    parser.add_argument("--size", type=int, default=SIZE)
    parser.add_argument("--preview", action="store_true", help="write a preview and change nothing else")
    args = parser.parse_args()

    icon = island_on_sky(args.island, args.size)
    if args.preview:
        os.makedirs(CAPTURES, exist_ok=True)
        sheet = Image.new("RGB", (args.size + 160, args.size + 20), (32, 32, 36))
        sheet.paste(icon, (10, 10))
        for i, small in enumerate((128, 64, 32)):
            sheet.paste(icon.resize((small, small), Image.LANCZOS), (args.size + 24, 10 + i * (small + 6)))
        out = os.path.join(CAPTURES, "pack_icon_preview.png")
        sheet.save(out)
        print(f"wrote {out} (the icon, and how it reads at 128, 64 and 32)")
        return 0

    for path in ICONS:
        icon.save(path)
        print(f"wrote {path} ({args.size}x{args.size})")
    thumb = Image.open(THUMBNAIL).convert("RGB").resize(WORLD_SIZE, Image.LANCZOS)
    thumb.save(WORLD_ICON, "JPEG", quality=92)
    print(f"wrote {WORLD_ICON} ({WORLD_SIZE[0]}x{WORLD_SIZE[1]}, from the thumbnail)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
