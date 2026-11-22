# meshops.py - tessellate and decimate the active Part with trimesh, through an
# OBJ round trip (SculptForge 0.13.8+).
#
# SculptForge's own subdivide and decimate run in the app. This script does the
# same work outside it, with the trimesh library (Scripts\site-packages):
#
#   1. save_obj      the visible Parts, one "o" object each;
#   2. trimesh       keeps the active Part's mesh, subdivides it (each level
#                    splits every triangle in four), then simplifies it with
#                    fast-simplification (quadric edge collapse);
#   3. part_append   brings the result back as a new Part beside the source,
#                    which can be hidden to compare the two.
#
# Advantage over the built-in commands: the wanted percentage is reached even on
# very dense meshes (one call to the library can stop short, so it is repeated),
# and the mesh goes through a real file, which another program could read too.
#
# An OBJ holds geometry only: masks, hidden faces, paint colours, UVs of other
# maps and sculpt layers stay in the app, so the new Part starts plain. The
# export covers every visible Part, so a heavy scene writes a heavy file.
#
# Install the libraries once (SculptForge's embedded Python 3.13 has no pip):
#   py -3.13 -m pip install --target "<Documents>\SculptForge\Scripts\site-packages" ^
#       numpy trimesh manifold3d fast-simplification
#
# Launch: File > Script > meshops, then the "Mesh ops" button (top shelf, My
# Panel, F3 palette). Requirement: Enable Python scripts in Preferences.
# One undo step per Part: the source keeps its own, the new Part is one more.

import os
import shutil
import tempfile

import sculptforge as sf

np = None
trimesh = None
LIBS_ERROR = ""


def _add_site_packages():
    """Put the Scripts folder's site-packages on sys.path, if it is missing.

    The app does this itself (the Scripts folder and its site-packages); doing
    it here too covers builds that don't, and running the script from elsewhere.
    """
    import sys
    folders = []
    try:
        folders.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    try:
        folders.append(sf.scripts_folder())
    except Exception:
        pass
    for folder in folders:
        if not folder:
            continue
        candidate = os.path.join(folder, "site-packages")
        if os.path.isdir(candidate) and candidate not in sys.path:
            sys.path.append(candidate)


def _load_libraries():
    global np, trimesh, LIBS_ERROR
    try:
        import numpy
        import trimesh
        np, trimesh = numpy, trimesh
        return
    except Exception as exc:
        LIBS_ERROR = str(exc)
    _add_site_packages()
    try:
        import numpy
        import trimesh
        np, trimesh = numpy, trimesh
        LIBS_ERROR = ""
    except Exception as exc:
        LIBS_ERROR = "%s (tried: %s)" % (exc, sf.scripts_folder())


_load_libraries()

# ---------------------------------------------------------------------------
# Defaults (the panel replaces them when the button is clicked)
# ---------------------------------------------------------------------------
LEVELS = 1        # tessellate levels (0-4): each one multiplies triangles by 4
KEEP = 100        # decimate: percent of triangles kept (1-100; 100 = off)
HIDE_SOURCE = False   # hide the source Part once the new one is there
SUFFIX = "_ops"   # name of the new Part: <source name><suffix>

MAX_LEVELS = 4
MAX_FACES = 40_000_000   # refuse to build a mesh the app would choke on
PASSES = 8               # decimation passes, to reach small targets exactly
UNIT_TOLERANCE = 1.5     # beyond this ratio, the OBJ was read in other units

PRESETS = (
    ("Tessellate x4", 1, 100),
    ("Tessellate x16", 2, 100),
    ("Decimate 50 %", 0, 50),
    ("Decimate 10 %", 0, 10),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _panel_value(control, fallback):
    """Value of a panel control, or the default value."""
    try:
        value = sf.ui.value("meshops." + control)
    except Exception:
        return fallback
    return fallback if value is None else value


def _diagonal(vertices):
    """Length of the bounding box diagonal of a vertex array (0 if empty)."""
    if vertices is None or len(vertices) == 0:
        return 0.0
    if np is not None:
        points = np.asarray(vertices, dtype=float).reshape(-1, 3)
        size = points.max(axis=0) - points.min(axis=0)
        return float(np.sqrt((size ** 2).sum()))
    xs = [p[0] for p in vertices]
    ys = [p[1] for p in vertices]
    zs = [p[2] for p in vertices]
    sx, sy, sz = max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)
    return (sx * sx + sy * sy + sz * sz) ** 0.5


def _find_geometry(geometries, name):
    """Key of the geometry that holds `name`, or None.

    The exporter writes the Part's name as the OBJ object name; some names come
    back with spaces or underscores swapped, so the match is loose.
    """
    if name in geometries:
        return name
    wanted = "".join(ch for ch in name.lower() if ch.isalnum())
    for key in geometries:
        if "".join(ch for ch in str(key).lower() if ch.isalnum()) == wanted:
            return key
    if len(geometries) == 1:
        return next(iter(geometries))
    return None


def _pick_mesh(loaded, name):
    """The Trimesh of `name` in what trimesh.load() returned, or None."""
    if isinstance(loaded, trimesh.Trimesh):
        return loaded
    if isinstance(loaded, trimesh.Scene):
        key = _find_geometry(loaded.geometry, name)
        if key is None:
            return None
        mesh = loaded.geometry[key].copy()
        for node in loaded.graph.nodes_geometry:      # bake the node transform
            transform, geometry_name = loaded.graph[node]
            if geometry_name == key:
                mesh.apply_transform(transform)
                break
        return mesh
    return None


def _decimate(mesh, target):
    """Simplify `mesh` down to `target` faces, in passes.

    One call to the library stops on its own before very small targets (the
    clustering it starts with leaves a floor), so it is repeated while it makes
    progress. Returns the simplified mesh.
    """
    for _ in range(PASSES):
        if len(mesh.faces) <= target:
            break
        before = len(mesh.faces)
        try:
            mesh = mesh.simplify_quadric_decimation(face_count=int(target))
        except Exception as exc:
            print("Mesh ops: decimation stopped (%s)." % exc)
            break
        if len(mesh.faces) >= before:                 # no progress: give up
            break
        mesh = _drop_degenerate(mesh)
    return mesh


def _drop_degenerate(mesh):
    """Remove the zero-area faces a collapse can leave behind.

    They have no normal, so the shading around them breaks (dark specks) and
    the mesh stops being watertight.
    """
    try:
        keep = mesh.nondegenerate_faces()
        if keep is not None and len(keep) == len(mesh.faces) and not keep.all():
            mesh.update_faces(keep)
    except Exception:
        pass
    return mesh


def _unique_name(taken, wanted):
    """`wanted`, made unique against the Part names in `taken`."""
    if wanted not in taken:
        return wanted
    count = 2
    while "%s_%d" % (wanted, count) in taken:
        count += 1
    return "%s_%d" % (wanted, count)


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------
def mesh_ops(levels=LEVELS, keep=KEEP, hide_source=HIDE_SOURCE):
    """Tessellate then decimate the active Part through an OBJ round trip.

    `levels` subdivides the whole mesh (0-4, each level x4 triangles).
    `keep` is the percentage of triangles kept by the decimation (1-100;
    100 leaves the count alone). `hide_source` hides the source Part once the
    new one is in place. Returns the new Part's name, or None on failure.
    """
    if trimesh is None:
        print("Mesh ops: trimesh is missing (%s)." % LIBS_ERROR)
        print("  Scripts folder: %s" % sf.scripts_folder())
        print("  Expected site-packages there: %s" % os.path.join(sf.scripts_folder(), "site-packages"))
        print("  Install with:")
        print('  py -3.13 -m pip install --target "%s" numpy trimesh manifold3d fast-simplification'
              % os.path.join(sf.scripts_folder(), "site-packages"))
        return None

    doc = sf.document()
    if not doc.parts:
        print("Mesh ops: the scene is empty, there is nothing to work on.")
        return None

    part = doc.parts[doc.active_part]
    name = part["name"]
    if not part["visible"]:
        print("Mesh ops: \"%s\" is hidden and save_obj only writes visible "
              "Parts; show it first." % name)
        return None

    before = int(part["triangles"])
    if before <= 0:
        print("Mesh ops: \"%s\" is empty." % name)
        return None
    source_diagonal = _diagonal(doc.vertices)

    levels = max(0, min(MAX_LEVELS, int(round(float(levels)))))
    keep = max(1, min(100, int(round(float(keep)))))
    planned = before * (4 ** levels)
    if levels and planned > MAX_FACES:
        print("Mesh ops: %d levels would make %.1f M triangles, over the %.0f M "
              "limit of this script." % (levels, planned / 1e6, MAX_FACES / 1e6))
        return None
    if not levels and keep >= 100:
        print("Mesh ops: nothing to do (0 levels and 100 % kept).")
        return None

    print("Mesh ops: \"%s\" - %d triangles, %d level%s, keeping %d %%."
          % (name, before, levels, "" if levels == 1 else "s", keep))

    folder = tempfile.mkdtemp(prefix="sculptforge_meshops_")
    source_obj = os.path.join(folder, "source.obj")
    result_obj = os.path.join(folder, "result.obj")
    try:
        # 1. out of the app
        try:
            sf.run("save_obj", path=source_obj)
        except Exception as exc:
            print("Mesh ops: the OBJ export failed (%s)." % exc)
            return None

        # 2. trimesh does the work
        # split_objects: one geometry per OBJ "o", which save_obj writes per
        # Part; without it trimesh merges every Part into a single mesh.
        loaded = trimesh.load(source_obj, process=False, split_objects=True)
        mesh = _pick_mesh(loaded, name)
        if mesh is None or len(mesh.faces) == 0:
            print("Mesh ops: \"%s\" was not found in the exported OBJ "
                  "(the file holds: %s)."
                  % (name, ", ".join(str(k) for k in getattr(loaded, "geometry", {}))
                     if isinstance(loaded, trimesh.Scene) else "one mesh"))
            return None

        exported = len(mesh.faces)
        if levels:
            mesh = mesh.subdivide(iterations=levels)
            print("  tessellate: %d -> %d triangles (x%d)."
                  % (exported, len(mesh.faces), 4 ** levels))

        target = 0
        if keep < 100:
            target = max(1, int(round(len(mesh.faces) * keep / 100.0)))
            shaped = len(mesh.faces)
            mesh = _decimate(mesh, target)
            print("  decimate: %d -> %d triangles (%.1f %%, asked %d)."
                  % (shaped, len(mesh.faces),
                     100.0 * len(mesh.faces) / shaped, target))

        mesh = _drop_degenerate(mesh)
        mesh.export(result_obj)

        # 3. back into the app
        taken = [p["name"] for p in sf.document().parts]
        new_name = _unique_name(taken, name + SUFFIX)
        try:
            sf.run("part_append", path=result_obj, name=new_name)
        except Exception as exc:
            print("Mesh ops: the reimport failed (%s)." % exc)
            return None
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    doc = sf.document()
    new_index = doc.active_part
    new_part = doc.parts[new_index]
    added = int(new_part["triangles"])
    new_diagonal = _diagonal(doc.vertices)

    # The OBJ is unit-less: save_obj writes the scene's own unit, part_append
    # assumes metres. The Part's size says whether the two agreed (decimation
    # moves the bounding box by a few percent, never by half).
    factor = (source_diagonal / new_diagonal) if new_diagonal > 0 else 0.0
    if factor and (factor > UNIT_TOLERANCE or factor < 1.0 / UNIT_TOLERANCE):
        try:
            sf.run("transform", scale="%.10g" % factor, masked=False)
            print("  size fix: the OBJ was read in other units, scaled by %.4g."
                  % factor)
        except Exception as exc:
            print("  size fix failed (%s): check the Part's size." % exc)

    if hide_source:
        try:
            sf.run("part_visibility", name=name, visible=False)
        except Exception as exc:
            print("  could not hide \"%s\" (%s)." % (name, exc))

    print("  new Part \"%s\": %d triangles (%.2f M), source kept at %d."
          % (new_part["name"], added, added / 1e6, before))
    return new_part["name"]


def _run_from_panel():
    try:
        levels = int(_panel_value("levels", LEVELS))
    except (TypeError, ValueError):
        levels = LEVELS
    try:
        keep = int(_panel_value("keep", KEEP))
    except (TypeError, ValueError):
        keep = KEEP
    mesh_ops(
        levels=levels,
        keep=keep,
        hide_source=bool(_panel_value("hide_source", HIDE_SOURCE)),
    )


def _preset_button(levels, keep):
    """Callback of a preset button: its own levels and percentage."""
    return lambda: mesh_ops(
        levels=levels,
        keep=keep,
        hide_source=bool(_panel_value("hide_source", HIDE_SOURCE)))


# ---------------------------------------------------------------------------
# Interface (SculptForge 0.13.8+)
# ---------------------------------------------------------------------------
def _declare_ui():
    sf.ui.action(
        "meshops.run", "Mesh ops", _run_from_panel, icon="wand",
        help="Tessellate then decimate the active Part with trimesh, through an "
             "OBJ round trip, and reimport the result as a new Part")

    panel = sf.ui.panel("meshops", "Mesh ops")
    panel.label("Tessellate and decimate through an OBJ round trip (trimesh)")
    panel.separator()
    panel.slider("levels", "Tessellate levels (x4 triangles each, 0 = off)",
                 LEVELS, 0, MAX_LEVELS, integer=True)
    # A slider label is a printf format, so a literal "%" is written "%%".
    panel.slider("keep", "Decimate - keep (%% of triangles, 100 = off)",
                 KEEP, 1, 100, integer=True)
    panel.checkbox("hide_source", "Hide the source Part", HIDE_SOURCE)
    panel.separator()
    panel.button("meshops.run")
    panel.separator()
    panel.label("Presets (they set both the levels and the percentage)")
    for label, levels, keep in PRESETS:
        aid = "meshops.p_%d_%d" % (levels, keep)
        sf.ui.action(aid, label, _preset_button(levels, keep), icon="wand",
                     help="Mesh ops: %s" % label.lower())
        panel.button(aid, label=label if len(label) <= 14 else label[:14])

    sf.ui.place("meshops.run", "top")
    sf.ui.place("meshops", "my_panel")


if hasattr(sf, "ui"):
    _declare_ui()
    print("Mesh ops: \"Mesh ops\" button added (top shelf, My Panel, F3 palette).")
else:
    print("Mesh ops: sf.ui missing (SculptForge 0.13.8+ required); "
          "call mesh_ops() from the Python console.")
