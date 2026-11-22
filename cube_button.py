# cube_button.py - ajoute un bouton "Create Cube" à l'interface (SculptForge 0.13.8+)
#
# Script autonome : il ne dépend d'aucun autre fichier. Le dossier Scripts
# n'est pas toujours sur sys.path (d'où l'erreur "No module named 'cube'"),
# donc le maillage du cube est défini ici même.
#
# Lancement : File > Script > cube_button
# Pour l'avoir à chaque démarrage : Edit > Preferences > Scripts >
#   cocher cube_button sous "Run at start-up" (puis Trust this version).
# Prérequis : Edit > Preferences > Scripts > Enable Python scripts.

import sculptforge as sf

# --- Le cube : deux coins opposés, en unités de la scène ---------------------
CUBE_MIN = (-0.5, -0.5, -0.5)
CUBE_MAX = (0.5, 0.5, 0.5)
PART_NAME = "cube"
FLAT_SHADING = True


def cube_mesh(corner_a, corner_b):
    """Sommets et 12 triangles d'un cube entre deux coins opposés.

    Les coins peuvent être donnés dans n'importe quel ordre : les bornes sont
    remises dans l'ordre axe par axe.
    """
    lo = [min(a, b) for a, b in zip(corner_a, corner_b)]
    hi = [max(a, b) for a, b in zip(corner_a, corner_b)]
    x0, y0, z0 = lo
    x1, y1, z1 = hi

    vertices = [
        (x0, y0, z0),  # 0
        (x1, y0, z0),  # 1
        (x1, y1, z0),  # 2
        (x0, y1, z0),  # 3
        (x0, y0, z1),  # 4
        (x1, y0, z1),  # 5
        (x1, y1, z1),  # 6
        (x0, y1, z1),  # 7
    ]

    # 12 triangles, normales vers l'extérieur (sens anti-horaire vu de dehors).
    triangles = [
        (4, 5, 6), (4, 6, 7),   # +z
        (1, 0, 3), (1, 3, 2),   # -z
        (5, 1, 2), (5, 2, 6),   # +x
        (0, 4, 7), (0, 7, 3),   # -x
        (3, 7, 6), (3, 6, 2),   # +y
        (0, 1, 5), (0, 5, 4),   # -y
    ]
    return vertices, triangles


def create_cube():
    """Crée un cube entre CUBE_MIN et CUBE_MAX (une seule étape d'annulation)."""
    vertices, triangles = cube_mesh(CUBE_MIN, CUBE_MAX)

    # Nouveau Part : le maillage en cours n'est pas remplacé.
    sf.run("part_append", type="cube", name=PART_NAME)

    doc = sf.document()
    doc.set_mesh(vertices, triangles)
    if FLAT_SHADING:
        sf.run("part_shading", mode="flat")

    part = doc.parts[doc.active_part]
    print("Cube", part["name"], ":", part["triangles"], "triangles")


# L'action : bouton, palette de commandes (F3), étagère, My Panel, raccourci.
sf.ui.action("cube.create", "Create Cube", create_cube, icon="box",
             help="Crée un cube simple de 12 triangles")

# Un petit panneau sous File > Script, avec le bouton dedans.
panel = sf.ui.panel("cube", "Cube")
panel.label("Cube simple, 12 triangles")
panel.button("cube.create")

# Emplacements visibles : l'étagère du haut et My Panel.
sf.ui.place("cube.create", "top")
sf.ui.place("cube", "my_panel")

print("Bouton Create Cube ajouté : étagère du haut, My Panel, palette F3.")
