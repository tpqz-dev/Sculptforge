# SPDX-FileCopyrightText: 2026 
# SPDX-License-Identifier: CC0-1.0
#
# Written in 2026. To the extent possible under law, the author(s) have dedicated 
# all copyright and related and neighboring rights to this software to the public 
# domain worldwide. This software is distributed without any warranty.
# You should have received a copy of the CC0 Public Domain Dedication along with this software. 
# If not, see <http://creativecommons.org/publicdomain/zero/1.0/>.

import sculptforge as sf

doc = sf.document()

sf.run("part_append", type="cube", name="squircle")
part = doc.parts[doc.active_part]
print("Part ajoutée :", part["name"], "-", part["triangles"], "triangles")

sf.run("center_on_origin")

sf.run("deform_round", amount=40, axes="xyz")

sf.run("subdivide", levels=1)

sf.run("deform_round", amount=12, axes="xyz")

sf.run("deform_smooth", amount=12, keep_volume=True)

sf.run("part_shading", mode="smooth")

for _ in range(5):
    sf.run("subdiv_reconstruct")

sf.run("subdiv_delete_higher")

print(sf.run("scene_overview"))
print(sf.run("subdiv_info"))

part = doc.parts[doc.active_part]
if part["triangles"] == 108:
    print("Squircle prêt : cage de base de", part["triangles"], "triangles.")
else:
    print("Attention : la cage fait", part["triangles"], "triangles au lieu de 108.")

EXPORT = False
if EXPORT:
    sf.run("save_obj", path="squircle.obj")
    sf.run("export_glb", path="squircle.glb")
    sf.run("save_project", path="squircle.sfproj")
    print("Exporté : squircle.obj, squircle.glb, squircle.sfproj")
