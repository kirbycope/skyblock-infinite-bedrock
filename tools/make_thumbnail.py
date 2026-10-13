"""Build the 1920x1080 project thumbnail, and the 960x540 repository preview.

Everything it needs is committed: the void screenshot in assets/background.png,
the player skin in assets/skin.png and Passion One in tools/fonts/.

    python tools/make_thumbnail.py
    python tools/make_thumbnail.py --no-preview     # skip the 960x540 rewrite
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

import skin_render

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONT = os.path.join(HERE, "fonts", "PassionOne-Black.ttf")

W, H = 1920, 1080

STYLES = {
    "white": dict(top=(255, 255, 255), bot=(180, 184, 188), side=(138, 142, 146)),
    "gold":  dict(top=(255, 224, 90), bot=(255, 164, 14), side=(184, 105, 12)),
    "yellow": dict(top=(255, 238, 92), bot=(255, 200, 0), side=(190, 140, 0)),
}

# Ragged left, the way One Chunk Challenge and One Block are set. The earlier
# justified block came from Four Sticks alone; across the rest of the author's
# thumbnails each line keeps its natural width.
TITLE = [
    dict(text="SKYBLOCK", style="white",  cap=146, arc=7),
    dict(text="INFINITE", style="white",  cap=146, arc=7),
    dict(text="BEDROCK",  style="yellow", cap=98,  arc=-10),
]

STROKE, DEPTH, EXTRUDE_DEG, TRACK = 13, 8, 90, 5


# --------------------------------------------------------------------------- type

def _cap_ratio(path):
    f = ImageFont.truetype(path, 400)
    box = f.getbbox("H")
    return (box[3] - box[1]) / 400.0


def _layout(font, text, track):
    xs, x = [], 0.0
    for ch in text:
        xs.append(x)
        x += font.getlength(ch) + track
    return xs, max(0.0, x - track)


def _advances(cap, text):
    font = ImageFont.truetype(FONT, int(round(cap / _cap_ratio(FONT))))
    return sum(font.getlength(c) for c in text)


def _track_for(cap, text, width):
    """Letter spacing that makes this word exactly `width` wide. Justifying on
    tracking keeps the letterforms; stretching the bitmap would not."""
    n = len(text)
    if n < 2:
        return TRACK
    return (width - _advances(cap, text)) / (n - 1)


def render_line(text, cap, style, track=TRACK, hscale=1.0, arc=0.0):
    """One word with the outline, extrude, gradient face and drop shadow."""
    pal = STYLES[style]
    size = int(round(cap / _cap_ratio(FONT)))
    font = ImageFont.truetype(FONT, size)
    xs, natural = _layout(font, text, track)

    rad = math.radians(EXTRUDE_DEG)
    dx, dy = math.cos(rad), math.sin(rad)
    pad = STROKE + DEPTH + 60
    cw = int(natural + pad * 2)
    ch = int(cap + size * 0.6 + pad * 2)
    base_y = pad + cap

    def draw_pass(img, fill, stroke_fill, stroke_w, ox, oy):
        d = ImageDraw.Draw(img)
        for ch_, x in zip(text, xs):
            d.text((pad + x + ox, base_y + oy), ch_, font=font, fill=fill,
                   anchor="ls", stroke_width=stroke_w, stroke_fill=stroke_fill)

    # the black shell around the whole extruded solid
    shell = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    for d_ in range(DEPTH, -1, -1):
        draw_pass(shell, (11, 11, 11, 255), (11, 11, 11, 255), STROKE,
                  dx * d_, dy * d_)

    # side faces
    sides = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    for d_ in range(DEPTH, 0, -1):
        draw_pass(sides, pal["side"] + (255,), None, 0, dx * d_, dy * d_)

    # top face, masked so the gradient runs down the cap height
    face_mask = Image.new("L", (cw, ch), 0)
    draw_pass(face_mask, 255, None, 0, 0, 0)
    grad = Image.new("RGB", (1, ch))
    gp = grad.load()
    for y in range(ch):
        t = (y - (base_y - cap)) / max(1.0, cap)
        t = min(1.0, max(0.0, t))
        k = t / 0.78 if t < 0.78 else (1.0 - t) / 0.22
        k = min(1.0, max(0.0, k))
        gp[0, y] = tuple(int(a + (b - a) * k) for a, b in zip(pal["top"], pal["bot"]))
    face = grad.resize((cw, ch), Image.NEAREST).convert("RGBA")
    face.putalpha(face_mask)

    line = Image.alpha_composite(shell, sides)
    line = Image.alpha_composite(line, face)

    # drop shadow, cast off the far face
    sh = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    sh.putalpha(line.split()[3])
    sh = Image.new("RGBA", (cw, ch), (0, 0, 0, 150))
    sh.putalpha(ImageChops.multiply(line.split()[3],
                                    Image.new("L", (cw, ch), 150)))
    sh = sh.filter(ImageFilter.GaussianBlur(11))
    out = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    out.alpha_composite(sh, (9, 13))
    out = Image.alpha_composite(out, line)

    if hscale != 1.0:
        out = out.resize((max(1, int(cw * hscale)), ch), Image.LANCZOS)
    if arc:
        out = _arc(out, arc)
    return out, natural


def _arc(img, bend):
    """Slide every column along a parabola, zero at both ends."""
    w, h = img.size
    pad = int(abs(bend)) + 2
    out = Image.new("RGBA", (w, h + pad * 2), (0, 0, 0, 0))
    for x in range(w):
        t = (x / (w - 1)) * 2 - 1 if w > 1 else 0.0
        off = bend * (1 - t * t)
        out.paste(img.crop((x, 0, x + 1, h)), (x, int(round(pad + off))))
    return out


def render_title():
    """Three lines set left, each at its natural width."""
    pieces, widths = [], []
    for ln in TITLE:
        piece, natural = render_line(ln["text"], ln["cap"], ln["style"],
                                     track=TRACK, arc=ln["arc"])
        pieces.append(piece)
        widths.append(natural)

    gap = 6
    total = sum(ln["cap"] for ln in TITLE) + gap * (len(TITLE) - 1)
    pad = 190
    block = Image.new("RGBA", (int(max(widths)) + pad * 2, int(total) + pad * 2),
                      (0, 0, 0, 0))
    y = pad
    for ln, piece in zip(TITLE, pieces):
        inner_pad = STROKE + DEPTH + 60
        arc_pad = int(abs(ln["arc"])) + 2
        block.alpha_composite(piece, (pad - inner_pad, int(y - inner_pad - arc_pad)))
        y += ln["cap"] + gap
    return block, pad, int(max(widths)), int(total)


# ------------------------------------------------------------------------ scene

def _grade(img, sat=1.5, contrast=1.14, bright=1.03):
    img = ImageEnhance.Color(img).enhance(sat)
    img = ImageEnhance.Contrast(img).enhance(contrast)
    return ImageEnhance.Brightness(img).enhance(bright)


def _sky(size):
    """The saturated blue the reference thumbnails use, fading to the void haze."""
    w, h = size
    col = Image.new("RGB", (1, h))
    p = col.load()
    stops = [(0.00, (0, 92, 255)), (0.38, (64, 160, 252)),
             (0.62, (158, 212, 248)), (1.00, (206, 224, 240))]
    for y in range(h):
        t = y / (h - 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0)
                p[0, y] = tuple(int(a + (b - a) * k) for a, b in zip(c0, c1))
                break
    return col.resize((w, h), Image.BICUBIC)


def _haze(img, amount, blur, lift=(188, 214, 232)):
    """Push a layer back: desaturate toward the void, lighten, soften."""
    img = ImageEnhance.Color(img).enhance(max(0.0, 1.0 - amount * 0.85))
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    veil = Image.new("RGB", img.size, lift)
    base = img.convert("RGB")
    out = Image.blend(base, veil, min(0.85, amount * 0.72))
    if img.mode == "RGBA":
        out = out.convert("RGBA")
        out.putalpha(img.split()[3])
    return out


def _sparkle(size, thickness, tilt, squash=0.72):
    """A tilted yellow frame. The middle stays open, or it reads as a sun
    rather than a glint."""
    s = size * 3
    m = s // 7
    card = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rectangle([m, m, s - m, s - m], outline=(255, 246, 35, 255), width=thickness * 3)

    # a breath of light inside the opening, nowhere near opaque
    inner = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(inner).rectangle(
        [m + thickness * 3, m + thickness * 3, s - m - thickness * 3, s - m - thickness * 3],
        fill=(255, 255, 255, 64))
    inner = inner.filter(ImageFilter.GaussianBlur(s * 0.045))

    card = Image.alpha_composite(inner, card)
    card = card.resize((size, int(size * squash)), Image.LANCZOS)
    glow = card.filter(ImageFilter.GaussianBlur(size * 0.07))
    out = Image.alpha_composite(Image.new("RGBA", card.size, (0, 0, 0, 0)), glow)
    out = Image.alpha_composite(out, card)
    return out.rotate(tilt, expand=True, resample=Image.BICUBIC)


def _vignette(img, strength=0.3):
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w]
    nx = (xx / (w - 1)) * 2 - 1
    ny = (yy / (h - 1)) * 2 - 1
    r = np.sqrt(nx ** 2 + ny ** 2) / math.sqrt(2)
    k = 1.0 - strength * np.clip((r - 0.55) / 0.45, 0, 1) ** 1.6
    arr = np.asarray(img.convert("RGB")).astype(np.float32) * k[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


# Inside the chat overlay's corner and above the Windows taskbar: the only part
# of a capture where the island can be.
SEARCH = (240, 170, 1800, 1120)
SKY_CROP = (0, 60, 1920, 1140)   # 16:9 out of the 1920x1200 client window


def _island(plate, void):
    """The island is whatever differs between the staged shot and the empty one.

    Keying it out of the sky by colour fringed the leaves and ate the grass
    edge. A matching void frame cancels the sky, the clouds and the horizon
    exactly, and keeping only the largest blob drops the chat overlay and any
    stray column left standing outside the staging box."""
    from scipy import ndimage

    a = np.asarray(plate.convert("RGB")).astype(np.int16)
    b = np.asarray(void.convert("RGB")).astype(np.int16)
    diff = np.abs(a - b).max(axis=2)

    mask = np.zeros(diff.shape, bool)
    left, top, right, bottom = SEARCH
    mask[top:bottom, left:right] = diff[top:bottom, left:right] > 14
    mask = ndimage.binary_closing(mask, np.ones((3, 3)))

    labels, count = ndimage.label(mask)
    if not count:
        raise SystemExit("nothing differs between the two plates; re-run tools/capture_thumbnail_plate.py")
    sizes = ndimage.sum(mask, labels, range(1, count + 1))
    keep = labels == (int(np.argmax(sizes)) + 1)

    out = plate.convert("RGBA")
    out.putalpha(Image.fromarray(np.where(keep, 255, 0).astype(np.uint8), "L"))
    ys, xs = np.nonzero(keep)
    return out.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))


def build():
    plate = Image.open(os.path.join(ROOT, "assets", "background.png")).convert("RGB")
    void = Image.open(os.path.join(ROOT, "assets", "background_void.png")).convert("RGB")
    backdrop = void.crop(SKY_CROP).resize((W, H), Image.LANCZOS)

    canvas = _sky((W, H))

    # the void itself, straight off the empty plate, so no island but ours is in it
    far = _haze(backdrop.copy(), amount=0.82, blur=30)
    canvas = Image.blend(canvas, far, 0.28)

    # the screenshot's own cloud deck, kept only across the top of the frame
    clouds = _haze(backdrop.copy(), amount=0.30, blur=1.5)
    ramp = Image.new("L", (1, H))
    rp = ramp.load()
    for y in range(H):
        rp[0, y] = int(255 * max(0.0, 1.0 - y / 430.0) ** 1.2 * 0.88)
    canvas = Image.composite(clouds, canvas, ramp.resize((W, H), Image.BICUBIC))
    canvas = _grade(canvas, sat=1.35, contrast=1.10, bright=1.04).convert("RGBA")

    island = _island(plate, void)

    # One island, and only one. Its own tree carries the height; the void
    # behind it is the point of the add-on, so nothing else floats in it.
    SCALE = 2.40
    GRASS = 252                      # the walkable surface inside the cut-out
    big = island.resize((int(island.width * SCALE), int(island.height * SCALE)),
                        Image.LANCZOS)
    rgb = _grade(big.convert("RGB"), sat=1.46, contrast=1.15, bright=1.02).convert("RGBA")
    rgb.putalpha(big.split()[3])
    island_pos = (700, 700 - int(GRASS * SCALE))
    ground_y = island_pos[1] + int(GRASS * SCALE)
    canvas.alpha_composite(rgb, island_pos)

    # the player, standing on it
    char = skin_render.render(os.path.join(ROOT, "assets", "skin.png"),
                              height=468, yaw=-24, pitch=5, outline=8)
    cx = 1206
    cy = ground_y - char.height + 26
    shadow = Image.new("RGBA", (int(char.width * 0.60), 46), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([0, 0, shadow.width - 1, shadow.height - 1],
                                   fill=(0, 0, 0, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    canvas.alpha_composite(shadow, (cx + int(char.width * 0.21), ground_y - 14))
    canvas.alpha_composite(char, (cx, cy))

    # title
    block, pad, tw, th = render_title()
    tilt = -2.0
    block = block.rotate(tilt, expand=True, resample=Image.BICUBIC)
    canvas.alpha_composite(block, (88 - pad, 72 - pad))

    out = _vignette(canvas.convert("RGB"), 0.30)
    return _grade(out, sat=1.08, contrast=1.04, bright=1.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(ROOT, "assets", "thumbnail.png"))
    ap.add_argument("--no-preview", action="store_true")
    args = ap.parse_args()

    img = build()
    img.save(args.out)
    print(f"wrote {args.out} {img.size[0]}x{img.size[1]}")

    if not args.no_preview:
        # the repository preview is 960x540, written by the project's own tool
        dest = os.path.join(ROOT, "skyblock-infinite-bedrock.png")
        subprocess.check_call([sys.executable,
                               os.path.join(HERE, "make_preview.py"),
                               args.out, dest])


if __name__ == "__main__":
    main()
