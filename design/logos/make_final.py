"""Final logo set from concept B (tree in a double ring).

    python design/logos/make_final.py

Writes design/logos/final/*.svg and copies the web versions to static/img/.
The mark (tree + ring) is pure paths. The wordmark stays live text until the
brand name is final; outline it then with the licensed font.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from make_tree import Tree, GREEN, INK, OLIVE, SAGE  # noqa: E402

OUT = os.path.join(HERE, "final")
SERIF = "'Playfair Display',Georgia,'Times New Roman',serif"
SANS = "Inter,'Segoe UI',Arial,sans-serif"
BRAND = "ŠAKIĆ"          # OPEN: working title. Also set in config/site.toml.
DESCRIPTOR = "MASLINOVO ULJE"

SEED = 23  # the tree the owner picked (concept B)


def tree_full():
    # identical settings to concept B (roots are grown last, so longer roots keep the same tree)
    return Tree(seed=SEED, ground=318, crown=(200, 165, 150, 108), trunk_len=56, trunk_w=40,
                roots=9, root_len=(40, 95))


def tree_small():
    # fewer, bigger leaves and thicker wood: stays readable at 32 to 64 px
    return Tree(seed=SEED, ground=316, crown=(200, 152, 150, 108), trunk_len=62, trunk_w=58, depth=4,
                leaf_len=30, leaf_w=8.5, leaf_gap=15, roots=5, root_len=(40, 80))


def mark(colour=GREEN, bg=None, small=False, cid="c"):
    """Tree in a double ring, 400 x 400 units, centred on (200, 200)."""
    t = tree_small() if small else tree_full()
    hole = "#ffffff" if bg is None else bg
    inner = t.svg_group(wood=colour, leaves=(colour,), streak=None if small else hole, fruit=False)
    if small:
        ring = f'<circle cx="200" cy="200" r="186" fill="none" stroke="{colour}" stroke-width="16"/>'
        clip_r = 172
    else:
        ring = (f'<circle cx="200" cy="200" r="192" fill="none" stroke="{colour}" stroke-width="7"/>'
                f'<circle cx="200" cy="200" r="181" fill="none" stroke="{colour}" stroke-width="2"/>')
        clip_r = 176
    back = f'<circle cx="200" cy="200" r="196" fill="{bg}"/>' if bg else ""
    return (f'{back}<clipPath id="{cid}"><circle cx="200" cy="200" r="{clip_r}"/></clipPath>'
            f'<g clip-path="url(#{cid})"><g transform="translate(0,{0 if small else 6})">{inner}</g></g>{ring}')


def text(x, y, size, s, spacing, colour, family, weight, anchor="middle"):
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" style="fill:{colour};font-family:{family};'
            f'font-weight:{weight};font-size:{size}px;letter-spacing:{spacing}px">{s}</text>')


def doc(w, h, body, bg=None):
    b = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">{b}{body}</svg>'


def build():
    files = {}
    files["mark.svg"] = doc(400, 400, mark())
    files["mark-small.svg"] = doc(400, 400, mark(small=True))
    files["mark-white.svg"] = doc(400, 400, mark(colour="#ffffff", bg=GREEN, cid="w"))
    files["mark-small-white.svg"] = doc(400, 400, mark(colour="#ffffff", bg=GREEN, small=True, cid="w"))
    files["mark-black.svg"] = doc(400, 400, mark(colour="#141414"))
    stacked = (f'<g transform="translate(40,0)">{mark()}</g>'
               + text(240, 462, 46, BRAND, 12, INK, SERIF, 700)
               + text(240, 500, 16, DESCRIPTOR, 6, OLIVE, SANS, 400))
    files["logo-stacked.svg"] = doc(480, 530, stacked)
    files["logo-stacked-white.svg"] = doc(480, 530, stacked.replace(mark(), mark(colour="#ffffff", bg=GREEN, cid="w"))
                                          .replace(f"fill:{INK}", "fill:#ffffff").replace(f"fill:{OLIVE}", f"fill:{SAGE}"), bg=GREEN)
    horiz = (f'<g transform="translate(0,0) scale(0.5)">{mark()}</g>'
             + text(384, 104, 50, BRAND, 10, INK, SERIF, 700)
             + text(384, 140, 15, DESCRIPTOR, 5.5, OLIVE, SANS, 400))
    files["logo-horizontal.svg"] = doc(560, 200, horiz)
    files["og-image.svg"] = doc(1200, 630,
                                f'<g transform="translate(165,115) scale(1)">{mark()}</g>'
                                + text(836, 300, 96, BRAND, 22, INK, SERIF, 700)
                                + text(836, 360, 26, DESCRIPTOR, 9, OLIVE, SANS, 400), bg=SAGE)
    os.makedirs(OUT, exist_ok=True)
    for name, s in files.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(s)
    # web copies
    img = os.path.join(ROOT, "static", "img")
    shutil.copy(os.path.join(OUT, "mark-small.svg"), os.path.join(img, "logo-mark.svg"))
    shutil.copy(os.path.join(OUT, "mark-small-white.svg"), os.path.join(img, "logo-mark-white.svg"))
    shutil.copy(os.path.join(OUT, "mark.svg"), os.path.join(img, "logo-mark-detailed.svg"))
    shutil.copy(os.path.join(OUT, "mark-small.svg"), os.path.join(img, "favicon.svg"))
    print("wrote", len(files), "files to design/logos/final and web copies to static/img")


if __name__ == "__main__":
    build()
