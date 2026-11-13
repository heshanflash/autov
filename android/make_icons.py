#!/usr/bin/env python3
"""Generate the AutoV Trader launcher icon (no external assets needed)."""
import os
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "app", "src", "main", "res")

DENSITIES = {  # name -> px
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}


def draw_icon(size: int) -> Image.Image:
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # rounded dark card
    r = max(2, s // 7)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=r, fill=(20, 27, 44, 255),
                        outline=(77, 163, 255, 255), width=max(1, s // 32))

    # candlesticks (mini chart)
    base = int(s * 0.78)
    cw = max(2, s // 10)
    gap = max(2, s // 14)
    xs = [int(s * 0.20), int(s * 0.45), int(s * 0.70)]
    heights = [int(s * 0.18), int(s * 0.30), int(s * 0.44)]
    colors = [(47, 212, 143, 255), (255, 92, 122, 255), (47, 212, 143, 255)]
    for x, h, c in zip(xs, heights, colors):
        # wick
        d.line([(x + cw // 2, base - h - s // 14), (x + cw // 2, base)], fill=c,
               width=max(1, s // 40))
        # body
        top = base - h
        d.rectangle([x, top, x + cw, base], fill=c)

    # blue triangle (AutoV logo mark)
    tri = [
        (int(s * 0.50), int(s * 0.14)),
        (int(s * 0.24), int(s * 0.46)),
        (int(s * 0.76), int(s * 0.46)),
    ]
    d.polygon(tri, fill=(77, 163, 255, 255))
    # inner notch for style
    d.polygon([
        (int(s * 0.50), int(s * 0.24)),
        (int(s * 0.35), int(s * 0.40)),
        (int(s * 0.65), int(s * 0.40)),
    ], fill=(20, 27, 44, 255))
    return img


def main():
    for name, px in DENSITIES.items():
        out_dir = os.path.join(RES, name)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "ic_launcher.png")
        draw_icon(px).save(path, "PNG")
        print("wrote", path)


if __name__ == "__main__":
    main()
