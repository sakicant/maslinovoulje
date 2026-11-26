"""Procedural olive tree for the logo concepts.

    python design/logos/make_tree.py

Grows a tree branch by branch (tapered curved limbs, twisted trunk, roots) and
places narrow olive leaves along the twigs. Same seed = same tree, so a chosen
version can be regenerated exactly. Writes SVG files and preview.html next to
this script. Standard library only.
"""
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))

INK = "#24391F"
GREEN = "#2E4A2B"
OLIVE = "#55691F"
OLIVE_LIGHT = "#7A8F3A"
SAGE = "#E3E8D8"
BLUSH = "#8E4467"
FRUIT = "#A3B456"


def f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


class Tree:
    def __init__(self, seed, cx=200, ground=330, crown=(200, 158, 172, 122), depth=6,
                 trunk_len=62, trunk_w=44, limbs=4, spread=38, droop=0.0, hollow=False,
                 leaf_len=12.5, leaf_w=3.3, leaf_gap=10.5, roots=7, olives=0.0):
        self.r = random.Random(seed)
        self.cx, self.ground = cx, ground
        self.ccx, self.ccy, self.crx, self.cry = crown
        self.max_depth = depth
        self.trunk_len, self.trunk_w = trunk_len, trunk_w
        self.limbs, self.spread, self.droop = limbs, spread, droop
        self.hollow = hollow
        self.leaf_len, self.leaf_w, self.leaf_gap = leaf_len, leaf_w, leaf_gap
        self.n_roots = roots
        self.olive_rate = olives
        self.phase = self.r.uniform(0, 6.28)
        self.wood = []      # polygons
        self.leaves = []    # (polygon, tone)
        self.fruit = []     # (x, y, r, colour)
        self.streaks = []   # light lines in the trunk (twist)
        self.grow()

    # ---------------------------------------------------------------- geometry
    @staticmethod
    def dirv(a):
        return math.sin(a), -math.cos(a)

    @staticmethod
    def qbez(p0, p1, p2, t):
        u = 1 - t
        return (u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])

    def ribbon(self, p0, c, p1, w0, w1, n=10):
        pts = [self.qbez(p0, c, p1, i / n) for i in range(n + 1)]
        left, right = [], []
        for i, p in enumerate(pts):
            a = pts[max(i - 1, 0)]
            b = pts[min(i + 1, n)]
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy) or 1
            nx, ny = -dy / L, dx / L
            w = (w0 + (w1 - w0) * (i / n)) / 2
            left.append((p[0] + nx * w, p[1] + ny * w))
            right.append((p[0] - nx * w, p[1] - ny * w))
        return left + right[::-1], pts

    def inside_crown(self, x, y):
        # lumpy outline: radius wobbles with the angle, so the crown reads as clumps
        ang = math.atan2(y - self.ccy, x - self.ccx)
        wob = 1 + 0.10 * math.sin(ang * 5 + self.phase) + 0.06 * math.sin(ang * 9 + self.phase * 2)
        return ((x - self.ccx) / (self.crx * wob)) ** 2 + ((y - self.ccy) / (self.cry * wob)) ** 2 <= 1

    # ---------------------------------------------------------------- growth
    def grow(self):
        r = self.r
        base = (self.cx, self.ground)
        top = (self.cx + r.uniform(-8, 8), self.ground - self.trunk_len)
        ctrl = (self.cx + r.uniform(-16, 16), self.ground - self.trunk_len * 0.5)
        if self.hollow:
            # two strands leaning together leave an arch-shaped hollow at the base
            for side in (-1, 1):
                b = (self.cx + side * self.trunk_w * 0.62, self.ground)
                c = (self.cx + side * self.trunk_w * 0.42 + r.uniform(-3, 3), self.ground - self.trunk_len * 0.5)
                poly, _ = self.ribbon(b, c, top, self.trunk_w * 0.52, self.trunk_w * 0.4)
                self.wood.append(poly)
        else:
            poly, pts = self.ribbon(base, ctrl, top, self.trunk_w * 1.25, self.trunk_w * 0.72)
            self.wood.append(poly)
        # twist: thin light streaks spiralling up the trunk
        for k in range(3):
            off = (k - 1) * self.trunk_w * 0.22
            p0 = (self.cx + off - 6, self.ground - 4)
            c = (self.cx - off * 1.4 + r.uniform(-6, 6), self.ground - self.trunk_len * 0.5)
            p1 = (top[0] + off * 0.6 + 5, top[1] + 10)
            poly, _ = self.ribbon(p0, c, p1, 0.4, 1.6 - k * 0.3)
            self.streaks.append(poly)
        # main limbs
        for i in range(self.limbs):
            a = math.radians(self.spread * (i - (self.limbs - 1) / 2) + r.uniform(-8, 8))
            self.branch(top, a, self.trunk_len * r.uniform(0.95, 1.25), self.trunk_w * r.uniform(0.5, 0.62), 1)
        self.make_roots()

    def branch(self, p0, ang, length, w0, depth):
        r = self.r
        dx, dy = self.dirv(ang)
        p1 = (p0[0] + dx * length, p0[1] + dy * length)
        # keep the crown inside its dome
        tries = 0
        while not self.inside_crown(*p1) and tries < 6 and depth > 1:
            length *= 0.8
            p1 = (p0[0] + dx * length, p0[1] + dy * length)
            tries += 1
        bend = r.gauss(0, length * (0.26 if depth <= 2 else 0.16))
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        c = (mx - dy * bend, my + dx * bend)
        w1 = max(w0 * 0.62, 0.7)
        poly, pts = self.ribbon(p0, c, p1, w0, w1)
        self.wood.append(poly)
        if depth >= self.max_depth - 2:
            self.leaf_twig(pts, depth)
        if depth >= 4:
            for _ in range(r.randint(0, 2)):
                t = r.uniform(0.25, 0.85)
                sp = self.qbez(p0, c, p1, t)
                sa = ang + r.choice((-1, 1)) * math.radians(r.uniform(35, 70))
                sl = length * r.uniform(0.25, 0.4)
                ex, ey = self.dirv(sa)
                se = (sp[0] + ex * sl, sp[1] + ey * sl)
                sc = ((sp[0] + se[0]) / 2 + r.uniform(-3, 3), (sp[1] + se[1]) / 2 + r.uniform(-3, 3))
                spoly, spts = self.ribbon(sp, sc, se, max(w1 * 0.5, 0.8), 0.6, n=5)
                self.wood.append(spoly)
                self.leaf_twig(spts, depth)
                self.leaf_tip(spts[-1], sa)
        if depth >= self.max_depth:
            self.leaf_tip(pts[-1], ang)
            return
        n = 2 if r.random() < 0.6 else 3
        spread = math.radians(r.uniform(24, 40))
        for i in range(n):
            ca = ang + spread * (i - (n - 1) / 2) + math.radians(r.uniform(-10, 10))
            # outer branches bend outward and, with droop, hang down a little
            if self.droop and depth >= 3:
                ca += math.copysign(math.radians(self.droop * depth), ca)
            ca = max(min(ca, math.radians(118)), math.radians(-118))
            t = 1.0 if i != 0 or r.random() < 0.6 else r.uniform(0.55, 0.8)
            start = self.qbez(p0, c, p1, t)
            self.branch(start, ca, length * r.uniform(0.64, 0.82), w1 * r.uniform(0.75, 0.95), depth + 1)

    def leaf(self, x, y, ang, length, width):
        dx, dy = self.dirv(ang)
        nx, ny = -dy, dx
        tip = (x + dx * length, y + dy * length)
        m1 = (x + dx * length * 0.45 + nx * width, y + dy * length * 0.45 + ny * width)
        m2 = (x + dx * length * 0.45 - nx * width, y + dy * length * 0.45 - ny * width)
        return (x, y), m1, tip, m2

    def add_leaf(self, x, y, ang):
        r = self.r
        L = self.leaf_len * r.uniform(0.8, 1.2)
        W = self.leaf_w * r.uniform(0.85, 1.15)
        tone = r.random()
        self.leaves.append((self.leaf(x, y, ang, L, W), tone))
        if self.olive_rate and r.random() < self.olive_rate:
            dx, dy = self.dirv(ang + math.pi * 0.85)
            col = BLUSH if r.random() < 0.4 else FRUIT
            self.fruit.append((x + dx * 5, y + dy * 5 + 3, r.uniform(2.6, 3.4), col))

    def leaf_twig(self, pts, depth):
        r = self.r
        dist = 0.0
        side = 1
        for i in range(1, len(pts)):
            a, b = pts[i - 1], pts[i]
            seg = math.hypot(b[0] - a[0], b[1] - a[1])
            dist += seg
            if dist >= self.leaf_gap:
                dist = 0
                ta = math.atan2(b[0] - a[0], -(b[1] - a[1]))
                la = ta + side * math.radians(r.uniform(35, 62))
                self.add_leaf(b[0], b[1], la)
                side = -side

    def leaf_tip(self, p, ang):
        for k in (-1, 1):
            self.add_leaf(p[0], p[1], ang + k * math.radians(self.r.uniform(18, 30)))

    def make_roots(self):
        r = self.r
        for i in range(self.n_roots):
            side = -1 if i % 2 == 0 else 1
            x0 = self.cx + side * r.uniform(2, self.trunk_w * 0.55)
            a = side * math.radians(r.uniform(68, 104))
            L = r.uniform(18, 58)
            dx, dy = self.dirv(a)
            p1 = (x0 + dx * L, self.ground + dy * L + r.uniform(2, 9))
            c = (x0 + dx * L * 0.4, self.ground + r.uniform(-1, 4))
            poly, _ = self.ribbon((x0, self.ground - 6), c, p1, r.uniform(6, 11), 0.6, n=8)
            self.wood.append(poly)

    # ---------------------------------------------------------------- output
    @staticmethod
    def path(poly):
        return "M" + " ".join(f"{f(x)} {f(y)}" for x, y in poly) + "Z"

    @staticmethod
    def leaf_path(q):
        (b, m1, tip, m2) = q
        return f"M{f(b[0])} {f(b[1])}Q{f(m1[0])} {f(m1[1])} {f(tip[0])} {f(tip[1])}Q{f(m2[0])} {f(m2[1])} {f(b[0])} {f(b[1])}Z"

    def svg_group(self, wood=INK, leaves=(GREEN,), streak="#ffffff", fruit=True):
        out = [f'<path fill="{wood}" d="{"".join(self.path(p) for p in self.wood)}"/>']
        if streak:
            out.append(f'<path fill="{streak}" d="{"".join(self.path(p) for p in self.streaks)}"/>')
        tones = {}
        for q, tone in self.leaves:
            col = leaves[min(int(tone * len(leaves)), len(leaves) - 1)]
            tones.setdefault(col, []).append(self.leaf_path(q))
        for col, ds in tones.items():
            out.append(f'<path fill="{col}" d="{"".join(ds)}"/>')
        if fruit and self.fruit:
            for x, y, rad, col in self.fruit:
                out.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(rad)}" fill="{col}"/>')
        return "\n".join(out)


# ---------------------------------------------------------------- logo layouts
SERIF = "'Playfair Display',Georgia,serif"
SANS = "Inter,Arial,sans-serif"


def word(x, y, size, text="ŠAKIĆ", spacing=8, colour=INK, family=SERIF, weight=700, italic=False):
    st = "font-style:italic;" if italic else ""
    return (f'<text x="{x}" y="{y}" text-anchor="middle" style="fill:{colour};font-family:{family};'
            f'font-weight:{weight};{st}font-size:{size}px;letter-spacing:{spacing}px">{text}</text>')


def svg(inner, w=400, h=480, bg="#ffffff"):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<rect width="{w}" height="{h}" fill="{bg}"/>{inner}</svg>')


def variants():
    out = {}

    # A. Silhouette, single colour, twisted trunk and roots
    t = Tree(seed=14)
    out["A-silhouette"] = svg(t.svg_group(wood=INK, leaves=(INK,), streak="#ffffff", fruit=False)
                              + word(200, 400, 34) + word(200, 428, 12, "MASLINOVO ULJE", 4, OLIVE, SANS, 500))

    # B. Inside a thin double circle, roots resting on the rim
    t = Tree(seed=23, ground=318, crown=(200, 165, 150, 108), trunk_len=56, trunk_w=40)
    ring = (f'<circle cx="200" cy="196" r="176" fill="none" stroke="{GREEN}" stroke-width="3"/>'
            f'<circle cx="200" cy="196" r="168" fill="none" stroke="{GREEN}" stroke-width="1"/>')
    out["B-roundel"] = svg(ring + t.svg_group(wood=GREEN, leaves=(GREEN,), streak="#ffffff", fruit=False)
                           + word(200, 418, 30) + word(200, 446, 12, "MASLINOVO ULJE", 4, OLIVE, SANS, 500))

    # C. Two greens and the family olives (green and blush), like the real harvest
    t = Tree(seed=7, olives=0.07)
    out["C-colour"] = svg(t.svg_group(wood="#3B3A2C", leaves=(GREEN, OLIVE, OLIVE_LIGHT), streak=SAGE, fruit=True)
                          + word(200, 400, 34) + word(200, 428, 12, "MASLINOVO ULJE", 4, OLIVE, SANS, 500))

    # D. Hollow trunk: two strands with an arch at the base, like the family's old trees
    t = Tree(seed=31, hollow=True, trunk_w=50, trunk_len=66)
    out["D-hollow"] = svg(t.svg_group(wood=INK, leaves=(GREEN, OLIVE), streak=None, fruit=False)
                          + word(200, 400, 34) + word(200, 428, 12, "MASLINOVO ULJE", 4, OLIVE, SANS, 500))

    # E. Wide, low, drooping crown (photo 5), on a sage disc
    t = Tree(seed=5, crown=(200, 185, 168, 100), trunk_len=52, trunk_w=50, limbs=5, spread=30, droop=6,
             depth=6, olives=0.05)
    disc = f'<circle cx="200" cy="215" r="180" fill="{SAGE}"/>'
    out["E-wide"] = svg(disc + t.svg_group(wood=INK, leaves=(GREEN, OLIVE), streak=SAGE, fruit=True)
                        + word(200, 430, 30, "Šakić", 1, INK, SERIF, 700, True), h=460)

    # F. Badge: tree cut out of a solid green circle (one colour, prints anywhere)
    t = Tree(seed=19, ground=320, crown=(200, 168, 140, 108), trunk_len=56, trunk_w=40)
    disc = f'<circle cx="200" cy="200" r="178" fill="{GREEN}"/>'
    out["F-badge"] = svg(disc + t.svg_group(wood=SAGE, leaves=(SAGE,), streak=GREEN, fruit=False)
                         + word(200, 420, 30) + word(200, 448, 12, "MASLINOVO ULJE", 4, OLIVE, SANS, 500))
    return out


def main():
    v = variants()
    cards = []
    for name, s in v.items():
        with open(os.path.join(HERE, f"tree-{name}.svg"), "w", encoding="utf-8") as fh:
            fh.write(s)
        cards.append(f'<figure><div class="art">{s}</div><figcaption>{name.replace("-", " · ", 1)}</figcaption></figure>')
    page = ("<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Šakić tree logos</title><style>body{margin:0;padding:16px;background:#f3f5ee;font:15px/1.5 Inter,Arial,sans-serif;color:#24391F}"
            "h1{font:600 20px/1.2 Georgia,serif;margin:0 0 12px}.g{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(280px,1fr))}"
            "figure{margin:0;background:#fff;border:1px solid #cfd7c2;border-radius:8px;padding:12px}.art svg{width:100%;height:auto;display:block}"
            "figcaption{margin-top:6px;font-weight:600}</style>"
            "<h1>Šakić · tree logo concepts</h1><div class='g'>" + "".join(cards) + "</div>")
    with open(os.path.join(HERE, "preview.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    print("wrote", len(v), "variants + preview.html")


if __name__ == "__main__":
    main()
