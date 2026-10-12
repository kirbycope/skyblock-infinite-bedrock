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
}

TITLE = [
    dict(text="SKYBLOCK", style="white", cap=150, arc=9),
    dict(text="INFINITE", style="white", cap=150, arc=9),
    dict(text="BEDROCK",  style="gold",  cap=104, arc=-18),
]

STROKE, DEPTH, EXTRUDE_DEG, TRACK = 13, 8, 90, -12


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
    """Justify the two white lines to one width on tracking, then size the
    accent line so it lands at 82 per cent of that and centre it, which is the
    proportion the reference thumbnails use."""
    white = [ln for ln in TITLE if ln["style"] != "gold"]
    target = max(_advances(ln["cap"], ln["text"]) for ln in white)

    plan = []
    for ln in TITLE:
        if ln["style"] != "gold":
            w = target
            cap = ln["cap"]
        else:
            w = target * 0.82
            # width scales with cap height, so solve for the cap that fits
            cap = ln["cap"] * w / max(1.0, _advances(ln["cap"], ln["text"]))
            cap = int(round(cap))
            w = min(w, _advances(cap, ln["text"]) + 0.08 * cap * (len(ln["text"]) - 1))
        tr = _track_for(cap, ln["text"], w)
        tr = max(-0.20 * cap, min(0.06 * cap, tr))
        plan.append((ln, cap, tr, w))

    pieces = [(ln, cap, render_line(ln["text"], cap, ln["style"], track=tr,
                                    arc=ln["arc"])[0])
              for ln, cap, tr, w in plan]

    gap = 4
    total = sum(cap for _, cap, _ in pieces) + gap * (len(pieces) - 1)
    pad = 190
    block = Image.new("RGBA", (int(target) + pad * 2, int(total) + pad * 2),
                      (0, 0, 0, 0))
    y = pad
    for (ln, cap, piece), (_, _, _, w) in zip(pieces, plan):
        inner_pad = STROKE + DEPTH + 60
        arc_pad = int(abs(ln["arc"])) + 2
        x = pad + int((target - w) / 2)
        block.alpha_composite(piece, (x - inner_pad, int(y - inner_pad - arc_pad)))
        y += cap + gap
    return block, pad, int(target), int(total)


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
    stops = [(0.00, (3, 72, 253)), (0.34, (74, 155, 249)),
             (0.56, (168, 214, 245)), (1.00, (214, 224, 236))]
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


def _island(plate):
    """Cut the spawn island out of the screenshot, keyed off the flat void."""
    crop = plate.crop((690, 330, 1230, 820)).convert("RGBA")
    arr = np.asarray(crop).astype(np.int16)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    # the void is pale, blue-leaning and low contrast; the island is neither
    void = (b > r + 6) & (b > 180) & (g > 170)
    alpha = np.where(void, 0, 255).astype(np.uint8)
    out = crop.copy()
    out.putalpha(Image.fromarray(alpha, "L").filter(ImageFilter.MedianFilter(5)))
    bbox = out.split()[3].getbbox()
    return out.crop(bbox) if bbox else out


def build():
    plate = Image.open(os.path.join(ROOT, "assets", "background.png")).convert("RGB")

    canvas = _sky((W, H))

    # the void itself, pulled from the screenshot and pushed right back
    far = _haze(plate.copy(), amount=0.72, blur=7)
    canvas = Image.blend(canvas, far, 0.42)

    # the screenshot's own cloud deck, kept only across the top of the frame
    clouds = _haze(plate.copy(), amount=0.30, blur=1.5)
    ramp = Image.new("L", (1, H))
    rp = ramp.load()
    for y in range(H):
        rp[0, y] = int(255 * max(0.0, 1.0 - y / 340.0) ** 1.3 * 0.72)
    canvas = Image.composite(clouds, canvas, ramp.resize((W, H), Image.BICUBIC))
    canvas = _grade(canvas, sat=1.35, contrast=1.10, bright=1.04).convert("RGBA")

    island = _island(plate)

    # far islands, specks of the forty-seven out in the void
    for x, y, scale, amount, blur in [
        (74, 884, 0.26, 0.52, 1.6),
        (596, 928, 0.18, 0.64, 2.2),
        (1796, 300, 0.20, 0.50, 1.4),
        (352, 158, 0.12, 0.76, 3.0),
    ]:
        s_ = island.resize((max(1, int(island.width * scale)),
                            max(1, int(island.height * scale))), Image.LANCZOS)
        canvas.alpha_composite(_haze(s_, amount, blur), (x, y))

    # a whole island behind the player, for the tree and a sense of depth
    mid = island.resize((int(island.width * 0.74), int(island.height * 0.74)),
                        Image.LANCZOS)
    canvas.alpha_composite(_haze(mid, 0.28, 1.1), (1596, 74))

    # sparkle frames
    canvas.alpha_composite(_sparkle(132, 5, 22), (902, 128))
    canvas.alpha_composite(_sparkle(84, 4, -15), (1352, 76))

    # The foreground platform: the island's grass and dirt only, blown up so a
    # block reads at roughly 150px and the player sits at a believable height
    # against it. The canopy is left out; the island behind carries the tree.
    slab = island.crop((108, 272, island.width, island.height))
    SCALE = 3.0
    slab = slab.resize((int(slab.width * SCALE), int(slab.height * SCALE)), Image.LANCZOS)
    rgb = _grade(slab.convert("RGB"), sat=1.5, contrast=1.16, bright=1.02).convert("RGBA")
    rgb.putalpha(slab.split()[3])
    slab_pos = (742, 672)
    ground_y = slab_pos[1] + int((302 - 272) * SCALE)   # the walkable surface
    canvas.alpha_composite(rgb, slab_pos)

    # the player, four blocks tall against that platform
    char = skin_render.render(os.path.join(ROOT, "assets", "skin.png"),
                              height=604, yaw=-24, pitch=5, outline=9)
    cx = 1196
    cy = ground_y - char.height + 32
    shadow = Image.new("RGBA", (int(char.width * 0.66), 58), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([0, 0, shadow.width - 1, shadow.height - 1],
                                   fill=(0, 0, 0, 105))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    canvas.alpha_composite(shadow, (cx + int(char.width * 0.19), ground_y - 16))
    canvas.alpha_composite(char, (cx, cy))

    # title
    block, pad, tw, th = render_title()
    tilt = -2.0
    block = block.rotate(tilt, expand=True, resample=Image.BICUBIC)
    canvas.alpha_composite(block, (104 - pad, 352 - pad))

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
