# squircle.py - crée un squircle dans SculptForge (scripting Python, 0.13.7+)
#
# Où le lancer :
#   - File > Script > squircle          (il est dans le dossier Scripts)
#   - File > Run script file...          (depuis n'importe où)
#   - console (`) en mode Python : exec(open(r"...\squircle.py", encoding="utf-8").read())
#
# Prérequis : Edit > Preferences > Scripts > Enable Python scripts.
# Tout le script ne fait qu'une seule étape d'annulation (Ctrl+Z).
#
# Mêmes étapes que l'ancien squircle.txt, mais en Python : les boucles et les
# conditions sont maintenant possibles dans l'application.

import sculptforge as sf

doc = sf.document()

# --- 1. Cube de départ -------------------------------------------------------
sf.run("part_append", type="cube", name="squircle")
part = doc.parts[doc.active_part]
print("Part ajoutée :", part["name"], "-", part["triangles"], "triangles")

# --- 2. Centrage sur l'origine -----------------------------------------------
# D'après le centre de la boîte englobante du Part, pas par rapport au reste
# de la scène.
sf.run("center_on_origin")

# --- 3. Arrondi principal ----------------------------------------------------
# Les composantes des 3 axes se rapprochent d'une sphère de 40 % :
# coins et arêtes s'arrondissent, les faces restent plates.
sf.run("deform_round", amount=40, axes="xyz")

# --- 4. Subdivision Loop -----------------------------------------------------
# Une silhouette lisse : 27 648 -> 110 592 triangles.
sf.run("subdivide", levels=1)

# --- 5. Rayon de coin plus ouvert --------------------------------------------
sf.run("deform_round", amount=12, axes="xyz")

# --- 6. Nettoyage de la surface ----------------------------------------------
# Taubin (keep_volume=True) : lisse sans faire rétrécir le volume.
sf.run("deform_smooth", amount=12, keep_volume=True)

# --- 7. Ombrage lissé --------------------------------------------------------
sf.run("part_shading", mode="smooth")

# --- 8. Réduction au minimum de niveaux --------------------------------------
# Rebuild Lower Levels, cinq fois : 110 592 -> 27 648 -> 6 912 -> 1 728 ->
# 432 -> 108 triangles. C'est ici qu'une boucle sert : on répète la commande
# au lieu de la recopier.
for _ in range(5):
    sf.run("subdiv_reconstruct")

# Remove Above : supprime tous les niveaux au-dessus du niveau courant.
sf.run("subdiv_delete_higher")

# --- 9. Vérification ---------------------------------------------------------
print(sf.run("scene_overview"))
print(sf.run("subdiv_info"))

# Une condition, pour contrôler le résultat au lieu de le supposer.
part = doc.parts[doc.active_part]
if part["triangles"] == 108:
    print("Squircle prêt : cage de base de", part["triangles"], "triangles.")
else:
    print("Attention : la cage fait", part["triangles"], "triangles au lieu de 108.")

# --- 10. Exports (passer EXPORT à True pour les écrire) ----------------------
# Les chemins relatifs partent du dossier du projet.
EXPORT = False
if EXPORT:
    sf.run("save_obj", path="squircle.obj")
    sf.run("export_glb", path="squircle.glb")
    sf.run("save_project", path="squircle.sfproj")
    print("Exporté : squircle.obj, squircle.glb, squircle.sfproj")
