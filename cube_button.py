# SPDX-FileCopyrightText: 2026 
# SPDX-License-Identifier: CC0-1.0
#
# Written in 2026. To the extent possible under law, the author(s) have dedicated 
# all copyright and related and neighboring rights to this software to the public 
# domain worldwide. This software is distributed without any warranty.
# You should have received a copy of the CC0 Public Domain Dedication along with this software. 
# If not, see <http://creativecommons.org/publicdomain/zero/1.0/>.

import sculptforge as sf

CUBE_MIN = (-0.5, -0.5, -0.5)
CUBE_MAX = (0.5, 0.5, 0.5)
PART_NAME = "cube"
FLAT_SHADING = True

def cube_mesh(corner_a, corner_b):
    """Vertices and 12 triangles of a cube between two opposite corners.

    Corners can be given in any order: bounds are reordered axis by axis.
    """
    lo = [min(a, b) for a, b in zip(corner_a, corner_b)]
    hi = [max(a, b) for a, b in zip(corner_a, corner_b)]
    x0, y0, z0 = lo
    x1, y1, z1 = hi

    vertices = [
        (x0, y0, z0),
        (x1, y0, z0),
        (x1, y1, z0),
        (x0, y1, z0),
        (x0, y0, z1),
        (x1, y0, z1),
        (x1, y1, z1),
        (x0, y1, z1),
    ]

    triangles = [
        (4, 5, 6), (4, 6, 7),
        (1, 0, 3), (1, 3, 2),
        (5, 1, 2), (5, 2, 6),
        (0, 4, 7), (0, 7, 3),
        (3, 7, 6), (3, 6, 2),
        (0, 1, 5), (0, 5, 4),
    ]
    return vertices, triangles

def create_cube():
    """Creates a cube between CUBE_MIN and CUBE_MAX (single undo step)."""
    vertices, triangles = cube_mesh(CUBE_MIN, CUBE_MAX)

    sf.run("part_append", type="cube", name=PART_NAME)

    doc = sf.document()
    doc.set_mesh(vertices, triangles)
    if FLAT_SHADING:
        sf.run("part_shading", mode="flat")

    part = doc.parts[doc.active_part]
    print("Cube", part["name"], ":", part["triangles"], "triangles")

sf.ui.action("cube.create", "Create Cube", create_cube, icon="box",
             help="Creates a simple cube with 12 triangles")

panel = sf.ui.panel("cube", "Cube")
panel.label("Simple cube, 12 triangles")
panel.button("cube.create")

sf.ui.place("cube.create", "top")
sf.ui.place("cube", "my_panel")

print("Create Cube button added: top shelf, My Panel, F3 palette.")