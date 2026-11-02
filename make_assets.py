"""Make the game pictures from raw_art/ with Pillow.

Run on your computer (not in a browser):  python make_assets.py

- every raw_art/*.png becomes assets/<name>.png, 3x bigger, no blurring (NEAREST)
- the demon (the boss) is made 6x so it is drawn twice as big as the others
- two bright crystals are coloured from raw_art/gem.png: blue (XP 1) and pink (XP 2)
- the sand floor tile is coloured into a night blue, so the screen matches the name

raw_art/ itself is never changed.
"""
import os

from PIL import Image, ImageOps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE_DIR, "raw_art")
OUT = os.path.join(BASE_DIR, "assets")

# darkest -> brightest colour of each crystal (see the lecture: dark stays dark)
GEM_TINTS = {
    "gem_blue": ((90, 235, 255), (192, 247, 255)),
    "gem_pink": ((255, 90, 190), (255, 190, 235)),
}

# the Kenney floor tile is sand; this game is called Night Survivors.
# Not too dark: the bats have a near-black outline and would vanish into the floor.
FLOOR_TINT = ((24, 26, 46), (86, 92, 128))


def scale_up(img, factor):
    return img.resize((img.width * factor, img.height * factor), Image.NEAREST)


def tint(img, dark, bright):
    """Keep the shading of the picture, change only its colour."""
    rgba = img.convert("RGBA")
    gray = ImageOps.autocontrast(rgba.convert("L"))
    colored = ImageOps.colorize(gray, black=dark, white=bright).convert("RGBA")
    colored.putalpha(rgba.getchannel("A"))
    return colored


def main():
    os.makedirs(OUT, exist_ok=True)
    for name in sorted(os.listdir(RAW)):
        if not name.endswith(".png"):
            continue
        img = Image.open(os.path.join(RAW, name)).convert("RGBA")
        if name == "floor.png":
            img = tint(img, *FLOOR_TINT)
        factor = 6 if name == "demon.png" else 3
        out = scale_up(img, factor)
        out.save(os.path.join(OUT, name))
        print("assets/%s  %dx%d (%dx%s)" % (name, out.width, out.height, factor,
                                            ", tinted" if name == "floor.png" else ""))
    gem = Image.open(os.path.join(RAW, "gem.png")).convert("RGBA")
    for name, (dark, bright) in GEM_TINTS.items():
        out = scale_up(tint(gem, dark, bright), 3)
        out.save(os.path.join(OUT, name + ".png"))
        print("assets/%s.png  %dx%d (tinted)" % (name, out.width, out.height))


if __name__ == "__main__":
    main()
