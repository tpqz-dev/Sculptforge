# SPDX-FileCopyrightText: 2026 
# SPDX-License-Identifier: CC0-1.0
#
# Written in 2026. To the extent possible under law, the author(s) have dedicated 
# all copyright and related and neighboring rights to this software to the public 
# domain worldwide. This software is distributed without any warranty.
# You should have received a copy of the CC0 Public Domain Dedication along with this software. 
# If not, see <http://creativecommons.org/publicdomain/zero/1.0/>.

import math

AXIOM = "FFA"
RULES = {"A": "F[&A][/&A][\\A]"}
GENERATIONS = 5

PITCH = 38.0
YAW = 25.0
ROLL = 120.0

START_LENGTH = 0.6
LENGTH_FACTOR = 0.72
START_RADIUS = 0.09
SEGMENT_TAPER = 0.92
BRANCH_TAPER = 0.62
SIDES = 8

PART_NAME = "tree"
SMOOTH = True
EXPORT = False

def vec(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

def mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)

def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])

def unit(a):
    n = math.sqrt(dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)

def rotate(v, axis, angle):
    """Rodrigues : tourne v autour de axis (unitaire) de angle radians."""
    c, s = math.cos(angle), math.sin(angle)
    return vec(vec(mul(v, c), mul(cross(axis, v), s)),
               mul(axis, dot(axis, v) * (1.0 - c)))

def expand(symbols, generations):
    """Développe chaque symbole, récursivement, generations fois."""
    if generations <= 0:
        return symbols
    out = []
    for ch in symbols:
        out.append(expand(RULES.get(ch, ch), generations - 1))
    return "".join(out)

def add_branch(vertices, triangles, p0, p1, r0, r1):
    """Ajoute un cylindre conique fermé de p0 (rayon r0) à p1 (rayon r1)."""
    d = unit(sub(p1, p0))
    ref = (0.0, 0.0, 1.0) if abs(d[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = unit(cross(d, ref))
    v = cross(d, u)

    base = len(vertices)
    for point, radius in ((p0, r0), (p1, r1)):
        for i in range(SIDES):
            a = 2.0 * math.pi * i / SIDES
            off = vec(mul(u, math.cos(a) * radius),
                      mul(v, math.sin(a) * radius))
            vertices.append(vec(point, off))

    for i in range(SIDES):
        j = (i + 1) % SIDES
        a0, b0 = base + i, base + j
        a1, b1 = base + SIDES + i, base + SIDES + j
        triangles.append((a0, b0, b1))
        triangles.append((a0, b1, a1))

    c0 = len(vertices)
    vertices.append(p0)
    c1 = len(vertices)
    vertices.append(p1)
    for i in range(SIDES):
        j = (i + 1) % SIDES
        triangles.append((c0, base + j, base + i))
        triangles.append((c1, base + SIDES + i, base + SIDES + j))

def build_tree():
    vertices, triangles = [], []
    program = expand(AXIOM, GENERATIONS)
    print("L-system :", len(program), "symboles,", GENERATIONS, "générations")

    pos = (0.0, 0.0, 0.0)
    heading = (0.0, 1.0, 0.0)
    up = (0.0, 0.0, 1.0)
    side = unit(cross(up, heading))
    depth = 0
    radius = START_RADIUS
    stack = []

    for ch in program:
        if ch == "F":
            length = START_LENGTH * LENGTH_FACTOR ** depth
            end = vec(pos, mul(heading, length))
            r_end = radius * SEGMENT_TAPER
            add_branch(vertices, triangles, pos, end, radius, r_end)
            pos = end
            radius = r_end
        elif ch == "[":
            stack.append((pos, heading, up, side, depth, radius))
            depth += 1
            radius *= BRANCH_TAPER
        elif ch == "]":
            pos, heading, up, side, depth, radius = stack.pop()
        elif ch in "+-":
            a = math.radians(YAW) * (1.0 if ch == "+" else -1.0)
            heading = rotate(heading, up, a)
            side = rotate(side, up, a)
        elif ch in "&^":
            a = math.radians(PITCH) * (1.0 if ch == "&" else -1.0)
            heading = rotate(heading, side, a)
            up = rotate(up, side, a)
        elif ch in "/\\":
            a = math.radians(ROLL) * (1.0 if ch == "/" else -1.0)
            up = rotate(up, heading, a)
            side = rotate(side, heading, a)

        side = unit(cross(up, heading))
        up = unit(cross(heading, side))

    return vertices, triangles

def main():
    import sculptforge as sf

    vertices, triangles = build_tree()
    print(len(vertices), "sommets,", len(triangles), "triangles")

    sf.run("part_append", type="cube", name=PART_NAME)
    doc = sf.document()
    doc.set_mesh(vertices, triangles)

    if SMOOTH:
        sf.run("part_shading", mode="smooth")

    part = doc.parts[doc.active_part]
    print("Arbre", part["name"], ":", part["triangles"], "triangles")

    if EXPORT:
        sf.run("save_obj", path=PART_NAME + ".obj")
        sf.run("export_glb", path=PART_NAME + ".glb")
        sf.run("save_project", path=PART_NAME + ".sfproj")
        print("Exporté :", PART_NAME + ".obj,", PART_NAME + ".glb,", PART_NAME + ".sfproj")

if __name__ == "__main__":
    main()
