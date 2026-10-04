"""Draw the app logo (rounded, glossy "3D" tile with a bold USB symbol and a green check badge).

Writes usb_fixer/data/icon.png (512 px) and usb_fixer/data/icon.ico (16-256 px). The files are committed,
so building the exe does not need Pillow; run this only to change the logo:  python tools/make_icon.py
"""

import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "usb_fixer", "data")
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]

TOP, BOTTOM = (59, 130, 246), (91, 33, 182)  # blue -> violet, the app's primary colour
GREEN_TOP, GREEN_BOTTOM = (74, 222, 128), (21, 128, 61)


def gradient(size, top, bottom, diagonal=True):
    """RGBA gradient from top(-left) to bottom(-right)."""
    w, h = size
    small = Image.new("RGBA", (64, 64))
    px = small.load()
    for y in range(64):
        for x in range(64):
            t = ((x + y) / 126) if diagonal else (y / 63)
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,)
    return small.resize((w, h), Image.BICUBIC)


def rounded_mask(size, box, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle(box, radius=radius, fill=255)
    return m


def usb_symbol(n, scale=1.0):
    """White USB trident on a transparent layer, n x n, as an L mask."""
    m = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(m)
    u = lambda v: v * n  # noqa: E731
    cx = 0.5
    w = u(0.062 * scale)
    # stem + arrow head
    d.line([(u(cx), u(0.30)), (u(cx), u(0.72))], fill=255, width=round(w))
    d.polygon([(u(cx), u(0.17)), (u(cx - 0.085 * scale), u(0.31)), (u(cx + 0.085 * scale), u(0.31))], fill=255)
    # base ball
    r = u(0.078 * scale)
    d.ellipse([u(cx) - r, u(0.745) - r, u(cx) + r, u(0.745) + r], fill=255)
    # left branch with round end
    left = [(u(cx), u(0.60)), (u(0.33), u(0.49)), (u(0.33), u(0.41))]
    d.line(left, fill=255, width=round(w * 0.85), joint="curve")
    r2 = u(0.052 * scale)
    d.ellipse([u(0.33) - r2, u(0.39) - r2, u(0.33) + r2, u(0.39) + r2], fill=255)
    # right branch with square end
    right = [(u(cx), u(0.53)), (u(0.67), u(0.43)), (u(0.67), u(0.36))]
    d.line(right, fill=255, width=round(w * 0.85), joint="curve")
    s = u(0.05 * scale)
    d.rectangle([u(0.67) - s, u(0.33) - s, u(0.67) + s, u(0.33) + s], fill=255)
    return m


def check_badge(n):
    """Green round badge with a white check, n x n RGBA (with its own soft shadow)."""
    layer = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    r = n * 0.40
    c = n / 2
    box = [c - r, c - r, c + r, c + r]
    shadow = Image.new("L", (n, n), 0)
    ImageDraw.Draw(shadow).ellipse([box[0], box[1] + n * 0.05, box[2], box[3] + n * 0.05], fill=150)
    shadow = shadow.filter(ImageFilter.GaussianBlur(n * 0.04))
    layer.paste((0, 0, 0, 255), (0, 0), shadow)
    ring = Image.new("L", (n, n), 0)
    ImageDraw.Draw(ring).ellipse([box[0] - n * 0.05, box[1] - n * 0.05, box[2] + n * 0.05, box[3] + n * 0.05], fill=255)
    layer.paste((255, 255, 255, 255), (0, 0), ring)
    disc = Image.new("L", (n, n), 0)
    ImageDraw.Draw(disc).ellipse(box, fill=255)
    layer.paste(gradient((n, n), GREEN_TOP, GREEN_BOTTOM, diagonal=False), (0, 0), disc)
    # gloss on the badge
    gloss = Image.new("L", (n, n), 0)
    ImageDraw.Draw(gloss).ellipse([c - r * 0.75, c - r * 0.95, c + r * 0.75, c + r * 0.05], fill=90)
    gloss = ImageChops.multiply(gloss.filter(ImageFilter.GaussianBlur(n * 0.03)), disc)
    layer.paste((255, 255, 255, 255), (0, 0), gloss)
    tick = Image.new("L", (n, n), 0)
    ImageDraw.Draw(tick).line([(c - r * 0.45, c + r * 0.02), (c - r * 0.1, c + r * 0.38), (c + r * 0.5, c - r * 0.35)],
                              fill=255, width=round(n * 0.085), joint="curve")
    layer.paste((255, 255, 255, 255), (0, 0), tick)
    return layer


def draw(size=512, badge=True, detail=True):
    n = size * 4  # supersample for smooth edges
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    m = n * 0.06
    box = [m, m * 0.7, n - m, n - m * 1.3]
    radius = n * 0.23

    # drop shadow under the tile
    sh = rounded_mask((n, n), [box[0] + n * 0.01, box[1] + n * 0.035, box[2] - n * 0.01, box[3] + n * 0.035], radius)
    img.paste((10, 15, 40, 255), (0, 0), sh.filter(ImageFilter.GaussianBlur(n * 0.025)).point(lambda v: v * 0.55))

    body = rounded_mask((n, n), box, radius)
    img.paste(gradient((n, n), TOP, BOTTOM), (0, 0), body)

    # bevel: light rim at the top, darker rim at the bottom
    inner = rounded_mask((n, n), [box[0] + n * 0.018, box[1] + n * 0.02, box[2] - n * 0.018, box[3] - n * 0.012], radius * 0.92)
    rim = ImageChops.subtract(body, inner)
    top_fade = Image.linear_gradient("L").rotate(180).resize((n, n))  # 255 at top -> 0 at bottom
    img.paste((255, 255, 255, 255), (0, 0), ImageChops.multiply(rim, top_fade.point(lambda v: v * 0.55)))
    bottom_fade = Image.linear_gradient("L").resize((n, n))
    img.paste((20, 10, 60, 255), (0, 0), ImageChops.multiply(rim, bottom_fade.point(lambda v: v * 0.6)))

    if detail:
        # glass highlight across the upper half
        gloss = Image.new("L", (n, n), 0)
        ImageDraw.Draw(gloss).ellipse([-n * 0.25, -n * 0.62, n * 1.25, n * 0.47], fill=255)
        gloss = ImageChops.multiply(gloss, top_fade.point(lambda v: v * 0.30))
        img.paste((255, 255, 255, 255), (0, 0), ImageChops.multiply(gloss, inner))

    # USB symbol: shadow, then a slightly shaded white face for depth
    sym = usb_symbol(n, 1.0 if detail else 1.6)  # thicker strokes on small icons so they stay readable
    sym_shadow = sym.filter(ImageFilter.GaussianBlur(n * 0.012)).point(lambda v: v * 0.6)
    img.paste((15, 10, 50, 255), (round(n * 0.008), round(n * 0.018)), sym_shadow)
    face = gradient((n, n), (255, 255, 255), (214, 222, 255), diagonal=False)
    img.paste(face, (0, 0), sym)

    if badge:
        b = round(n * 0.40)
        img.alpha_composite(check_badge(b), (round(n * 0.60), round(n * 0.57)))

    return img.resize((size, size), Image.LANCZOS)


def build(out_dir=DATA):
    big = draw(512)
    big.save(os.path.join(out_dir, "icon.png"))
    frames = []
    for s in ICO_SIZES:
        if s <= 24:
            frames.append(draw(s, badge=False, detail=False))
        elif s <= 48:
            frames.append(draw(s, badge=True, detail=False))
        else:
            frames.append(draw(s))
    # Pillow writes one ICO entry per size, taken from the matching frame
    frames[-1].save(os.path.join(out_dir, "icon.ico"), sizes=[(s, s) for s in ICO_SIZES], append_images=frames[:-1])
    return big, frames


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else DATA)
    print("wrote icon.png and icon.ico")
