"""
Procedural blocky anime-style pixel avatars.

Every sprite is generated from a seed, so the art is original and yours to use
(treat it as CC0). Each avatar is a 16x20 pixel grid rendered as crisp SVG.

To swap in a third-party open-source pack instead (for example Kenney's CC0
assets or a CC-BY set from OpenGameArt), drop PNGs in static/sprites/ and point
the <img> tags in static/app.js at them.
"""
import random

W, H = 16, 20

SKIN = ["#FCE3D0", "#F6D2B8", "#EBB98F", "#D49A6A", "#A8714A", "#7A4E33"]
HAIR = [
    "#2B2B3A", "#4A3222", "#7B4B2A", "#E9C46A", "#F4A6C6", "#6FA8DC",
    "#B4A7D6", "#C0C4CC", "#E06666", "#76C893", "#F6B26B", "#3D5A99",
]
EYES = ["#3D5A99", "#6B3E26", "#2E7D32", "#8E44AD", "#C0392B", "#1F6F8B", "#B7950B"]
STUDENT_UNIFORMS = ["blazer", "sailor", "gakuran", "hoodie", "sweater"]
TEACHER_OUTFITS = ["suit", "cardigan", "labcoat", "tracksuit", "blouse"]
STUDENT_HAIR = ["short", "spiky", "long", "twintails", "ponytail", "bob", "messy"]
TEACHER_HAIR = ["short", "long", "bob", "bun", "ponytail", "messy", "bald"]


def _shade(hex_color, factor):
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    if factor < 1:
        r, g, b = (int(c * factor) for c in (r, g, b))
    else:
        r, g, b = (int(c + (255 - c) * (factor - 1)) for c in (r, g, b))
    return "#{:02X}{:02X}{:02X}".format(max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


class Canvas:
    def __init__(self):
        self.px = [[None] * W for _ in range(H)]

    def set(self, x, y, c):
        if 0 <= x < W and 0 <= y < H and c:
            self.px[y][x] = c

    def fill(self, x0, y0, x1, y1, c):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.set(x, y, c)

    def to_svg(self, scale=4, bg=None):
        rects = []
        if bg:
            rects.append(f'<rect width="{W}" height="{H}" fill="{bg}"/>')
        for y, row in enumerate(self.px):
            x = 0
            while x < W:  # merge horizontal runs to keep the SVG small
                c = row[x]
                if c is None:
                    x += 1
                    continue
                start = x
                while x < W and row[x] == c:
                    x += 1
                rects.append(f'<rect x="{start}" y="{y}" width="{x - start}" height="1" fill="{c}"/>')
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'width="{W * scale}" height="{H * scale}" shape-rendering="crispEdges">'
            + "".join(rects) + "</svg>"
        )


def appearance(seed, role="student"):
    rng = random.Random(f"{role}:{seed}")
    return {
        "skin": rng.choice(SKIN),
        "hair": rng.choice(HAIR if role == "student" else HAIR[:4] + HAIR[7:8] + HAIR[8:9]),
        "eyes": rng.choice(EYES),
        "hairstyle": rng.choice(STUDENT_HAIR if role == "student" else TEACHER_HAIR),
        "outfit": rng.choice(STUDENT_UNIFORMS if role == "student" else TEACHER_OUTFITS),
        "glasses": rng.random() < (0.18 if role == "student" else 0.45),
        "ahoge": rng.random() < 0.25,
        "accent": rng.choice(["#D7263D", "#2F6B4F", "#3D5A99", "#E9A23B", "#8E44AD"]),
    }


def _hair_back(cv, a):
    hc, dk = a["hair"], _shade(a["hair"], 0.72)
    s = a["hairstyle"]
    if s == "long":
        cv.fill(2, 4, 13, 15, dk)
    elif s == "twintails":
        cv.fill(0, 5, 1, 13, hc)
        cv.fill(14, 5, 15, 13, hc)
        cv.set(0, 13, None); cv.set(15, 13, None)
        cv.set(1, 5, a["accent"]); cv.set(14, 5, a["accent"])
    elif s == "ponytail":
        cv.fill(13, 2, 15, 10, dk)
        cv.set(13, 3, a["accent"])
    elif s == "bun":
        cv.fill(6, 0, 9, 1, hc)


def _body(cv, a):
    skin = a["skin"]
    o = a["outfit"]
    cv.fill(7, 13, 8, 13, _shade(skin, 0.85))  # neck
    palettes = {
        "blazer": ("#27325A", "#F5F7FA", "#D7263D"),
        "sailor": ("#F5F7FA", "#27325A", "#D7263D"),
        "gakuran": ("#1C1F2B", "#1C1F2B", "#E9C46A"),
        "hoodie": (a["accent"], _shade(a["accent"], 0.7), "#F5F7FA"),
        "sweater": ("#6B8F71", "#F5F7FA", "#27325A"),
        "suit": ("#3A3F4B", "#F5F7FA", a["accent"]),
        "cardigan": ("#A0522D", "#F0E6D8", "#6B4226"),
        "labcoat": ("#F5F7FA", "#6FA8DC", "#27325A"),
        "tracksuit": ("#2F6B4F", "#F5F7FA", "#F5F7FA"),
        "blouse": ("#B4A7D6", "#F5F7FA", "#8E44AD"),
    }
    main, trim, detail = palettes[o]
    cv.fill(4, 14, 11, 18, main)
    cv.fill(3, 15, 3, 17, main)
    cv.fill(12, 15, 12, 17, main)
    cv.set(3, 18, skin); cv.set(12, 18, skin)
    if o in ("blazer", "suit", "cardigan", "labcoat"):
        cv.fill(7, 14, 8, 16, trim)
        if o in ("blazer", "suit"):
            cv.set(7, 15, detail); cv.set(7, 16, detail)
    elif o == "sailor":
        cv.fill(4, 14, 11, 14, trim)
        cv.set(5, 15, trim); cv.set(10, 15, trim)
        cv.fill(7, 15, 8, 15, detail)
    elif o == "gakuran":
        for y in (15, 16, 17):
            cv.set(7, y, detail)
        cv.fill(6, 14, 9, 14, "#2E3345")
    elif o in ("hoodie", "tracksuit"):
        cv.fill(6, 14, 9, 14, trim)
        cv.set(6, 15, detail); cv.set(9, 15, detail)
    else:
        cv.fill(6, 14, 9, 14, trim)
        cv.set(7, 15, detail); cv.set(8, 15, detail)
    cv.fill(5, 19, 6, 19, "#2B2B3A")
    cv.fill(9, 19, 10, 19, "#2B2B3A")


def _head(cv, a):
    skin = a["skin"]
    cv.fill(3, 3, 12, 12, skin)
    for (x, y) in ((3, 3), (12, 3), (3, 12), (12, 12)):
        cv.set(x, y, None)
    cv.set(2, 8, skin); cv.set(13, 8, skin)  # ears
    cv.fill(4, 12, 11, 12, _shade(skin, 0.93))


def _face(cv, a, mood):
    eye, dark, white = a["eyes"], "#1C1F2B", "#FFFFFF"
    blush = "#F29CA3"
    if mood == "sleepy":
        cv.fill(5, 8, 6, 8, dark); cv.fill(9, 8, 10, 8, dark)
    else:
        for ex in (5, 9):
            cv.set(ex, 6, dark); cv.set(ex + 1, 6, dark)   # lash line
            cv.set(ex, 7, white); cv.set(ex + 1, 7, dark)  # highlight
            cv.set(ex, 8, eye); cv.set(ex + 1, 8, eye)
    if mood in ("happy", "stressed", "neutral") or mood == "sleepy":
        cv.set(4, 9, blush); cv.set(11, 9, blush)
    m = "#8C3B3B"
    if mood == "happy":
        cv.set(6, 10, m); cv.set(9, 10, m); cv.fill(7, 11, 8, 11, m)
    elif mood == "sad":
        cv.fill(7, 10, 8, 10, m); cv.set(6, 11, m); cv.set(9, 11, m)
    elif mood == "angry":
        cv.fill(6, 11, 9, 11, m)
        cv.set(5, 5, dark); cv.set(6, 6, dark); cv.set(10, 5, dark); cv.set(9, 6, dark)
    elif mood == "stressed":
        cv.fill(7, 11, 8, 11, m)
        cv.set(13, 6, "#9BD3F2"); cv.set(13, 7, "#6FA8DC")
    else:
        cv.fill(7, 11, 8, 11, m)
    if a["glasses"]:
        g = "#7A8294"
        for x in (4, 7, 8, 11):
            cv.set(x, 7, g); cv.set(x, 8, g)
        for x in (5, 6, 9, 10):
            cv.set(x, 9, g)


def _hair_front(cv, a):
    hc = a["hair"]
    dk, lt = _shade(hc, 0.72), _shade(hc, 1.35)
    s = a["hairstyle"]
    if s == "bald":
        cv.set(3, 6, dk); cv.set(12, 6, dk); cv.set(3, 7, dk); cv.set(12, 7, dk)
        cv.fill(6, 3, 9, 3, _shade(a["skin"], 1.15))
        return
    cv.fill(4, 1, 11, 2, hc)
    cv.fill(3, 2, 12, 4, hc)
    cv.fill(2, 3, 13, 5, hc)
    for x in (3, 4, 7, 8, 11, 12):  # jagged anime bangs
        cv.set(x, 6 if x not in (7, 8) else 5, hc)
    cv.set(5, 5, hc); cv.set(10, 5, hc)
    cv.fill(5, 2, 7, 2, lt)  # shine
    cv.set(8, 3, lt)
    cv.fill(2, 6, 2, 9, dk); cv.fill(13, 6, 13, 9, dk)
    if s == "spiky":
        for x in (3, 6, 9, 12):
            cv.set(x, 0, hc)
        cv.set(1, 3, hc); cv.set(14, 3, hc); cv.set(1, 4, hc); cv.set(14, 4, hc)
    elif s == "long":
        cv.fill(2, 6, 2, 13, hc); cv.fill(13, 6, 13, 13, hc)
    elif s == "bob":
        cv.fill(2, 6, 3, 11, hc); cv.fill(12, 6, 13, 11, hc)
        cv.set(3, 11, dk); cv.set(12, 11, dk)
    elif s == "messy":
        cv.set(1, 4, hc); cv.set(14, 5, hc); cv.set(6, 0, hc); cv.set(10, 0, hc)
        cv.set(6, 6, hc); cv.set(9, 6, hc)
    elif s == "bun":
        cv.fill(6, 0, 9, 1, hc); cv.set(7, 0, lt)
    if a["ahoge"] and s not in ("bun",):
        cv.set(8, 0, hc); cv.set(9, 0, dk)


def render(seed, role="student", mood="neutral", scale=4, bg=None):
    a = appearance(seed, role)
    cv = Canvas()
    _hair_back(cv, a)
    _body(cv, a)
    _head(cv, a)
    _face(cv, a, mood)
    _hair_front(cv, a)
    return cv.to_svg(scale=scale, bg=bg)
