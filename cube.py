
CUBE_MIN = (-0.5, -0.5, -0.5)   
CUBE_MAX = (0.5, 0.5, 0.5)      
NAME = "cube"                  
FLAT_SHADING = True            
EXPORT = False                  
def cube_mesh(corner_a, corner_b):
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

    triangles = [
        (4, 5, 6), (4, 6, 7),   # +z
        (1, 0, 3), (1, 3, 2),   # -z
        (5, 1, 2), (5, 2, 6),   # +x
        (0, 4, 7), (0, 7, 3),   # -x
        (3, 7, 6), (3, 6, 2),   # +y
        (0, 1, 5), (0, 5, 4),   # -y
    ]
    return vertices, triangles
def main():
    import sculptforge as sf
    doc = sf.document()
    sizes = [abs(b - a) for a, b in zip(CUBE_MIN, CUBE_MAX)]
    if min(sizes) <= 0:
        print("Attention : un côté vaut 0, le cube serait plat.")
    vertices, triangles = cube_mesh(CUBE_MIN, CUBE_MAX)
    sf.run("part_append", type="cube", name=NAME)
    doc.set_mesh(vertices, triangles)
    if FLAT_SHADING:
        sf.run("part_shading", mode="flat")
    part = doc.parts[doc.active_part]
    print("Cube", part["name"], ":", part["triangles"], "triangles,",
          "de", tuple(CUBE_MIN), "à", tuple(CUBE_MAX))
    if EXPORT:
        sf.run("save_obj", path=NAME + ".obj")
        sf.run("export_glb", path=NAME + ".glb")
        sf.run("save_project", path=NAME + ".sfproj")
        print("Exporté :", NAME + ".obj,", NAME + ".glb,", NAME + ".sfproj")
if __name__ == "__main__":
    main()
