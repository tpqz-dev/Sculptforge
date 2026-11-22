
import sculptforge as sf

# ---------------------------------------------------------------------------
# Defaults (the panel replaces them when the button is clicked)
# ---------------------------------------------------------------------------
THICKNESS = 0.0766    # shell thickness: fraction of the longest side (0.0766 = 7.66 %)
SMOOTH = 24           # edge smoothing of the extraction (0-50)
BOTH_SIDES = True     # shell on both sides of the surface (extract "double")

VOXEL = True          # voxel remesh: approximates Blob / Dynamesh
VOXEL_RES = 53        # voxels across the longest side (32-512)
POLISH = 10           # surface polish after the remesh (0-100)
ROUND = 0             # rounding, the plugin's Contrast -100 equivalent (0-100)

CONTRAST = 100        # Contrast pass on the new mesh (0 = off)
FINAL_VOXEL = 32      # coarse voxel remesh before the quad remesh (0 = off)
SYMMETRIC = True      # Make Symmetric just before the quad remesh
SYMMETRY_AXIS = "x"   # mirror plane through the world origin: x, y, z or xz
SYMMETRY_AXES = ("x", "y", "z", "xy", "xz", "yz")
QUADREMESH = 400      # final Quad Remesh target polygon count (0 = off)

GROUP = True          # one face group per piece (GroupVisible)
MERGE = False         # merge with the Part above (automerge)
HIDE_SOURCE = False   # False = the source Part keeps its original visibility
FREEZE_LEVELS = True  # delete the subdivision levels (Del Lower/Higher)

RESULT_SUFFIX = "_SB"  # name of the shell: "<source Part>_SB"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mask_stats(mask):
    """(masked vertices, total), with or without NumPy."""
    if mask is None:
        return 0, 0
    try:
        return int((mask > 0.5).sum()), int(mask.size)
    except (AttributeError, TypeError):
        return sum(1 for v in mask if float(v) > 0.5), len(mask)


def _try(command, **params):
    """Run a command without stopping the script if it fails."""
    try:
        message = sf.run(command, **params)
        if message:
            print("  " + str(message))
        return True
    except Exception as exc:                       # sf.CommandError, ValueError...
        print("  " + command + " skipped: " + str(exc))
        return False


def _quad_remesh(quads, group, stage):
    """Run one Quad Remesh pass (skipped when quads is 0)."""
    if quads <= 0:
        return
    if not _try("qremesh", target=quads, keep_groups=bool(group)):
        print("  Quad remesh (%s) left out; the mesh keeps its current topology."
              % stage)


def blob_it(thickness=THICKNESS, smooth=SMOOTH, both_sides=BOTH_SIDES,
                 voxel=VOXEL, resolution=VOXEL_RES, polish=POLISH,
                 round_form=ROUND, contrast=CONTRAST,
                 final_voxel=FINAL_VOXEL, symmetric=SYMMETRIC,
                 symmetry_axis=SYMMETRY_AXIS, quadremesh=QUADREMESH,
                 group=GROUP, merge=MERGE, hide_source=HIDE_SOURCE,
                 freeze_levels=FREEZE_LEVELS, name=""):
    """Turn the masked area of the active Part into a sculptable mesh.

    Steps: subdivision levels deleted, shell extracted from the mask,
    optional voxel remesh, polish, rounding, Contrast pass, coarse voxel
    remesh, face groups, Quad Remesh, then Make Symmetric and a second Quad
    Remesh, then the source Part is hidden (or merged).

    Returns the index of the final Part, or None if nothing was done.
    """
    doc = sf.document()
    parts = doc.parts
    if not parts:
        print("Blob it: the scene is empty, there is nothing to mask.")
        return None

    masked, total = _mask_stats(doc.mask)
    if masked == 0:
        print("Blob it: no mask on the active Part, nothing to extract.")
        print("  Paint the mask (Mask brush, or Ctrl+click to invert it),")
        print("  then press Blob it again.")
        return None

    source_index = doc.active_part
    source_name = parts[source_index]["name"]
    source_visible = bool(parts[source_index].get("visible", True))
    target = name or (source_name + RESULT_SUFFIX)
    count_before = len(parts)

    print("Blob it: \"%s\" - %d/%d vertices masked" % (source_name, masked, total))
    print("  Thickness: %.2f %% of the longest side (%.4f)."
          % (float(thickness) * 100.0, float(thickness)))

    # 1. Del Lower / Del Higher from the plugin: a mesh without levels.
    if freeze_levels:
        _try("subdiv_freeze")

    # 2. s.Dynamic + s.Thickness + s.Apply: the closed shell.
    try:
        sf.run("extract",
               thickness=float(thickness),
               smooth=int(round(float(smooth))),
               double=bool(both_sides),
               accept=True)
    except Exception as exc:
        print("Blob it: extraction failed (%s)." % exc)
        print("  Check that the Part is visible and that the mask covers an area.")
        return None

    if len(doc.parts) != count_before + 1:
        print("Blob it: the extraction created nothing "
              "(masked area too small, or entirely hidden?).")
        return None

    # extract inserts the shell just below the source Part.
    result_index = min(source_index + 1, len(doc.parts) - 1)

    # 3. The plugin's mask is cleared after the operation.
    sf.run("mask_clear")                       # the source is still active here

    sf.run("part_select", index=result_index)
    sf.run("part_rename", to=target)
    sf.run("mask_clear")                       # in case the shell inherited the mask

    # 4. Blob / Dynamesh: voxel remesh, then finishing.
    if voxel:
        sf.run("remesh", resolution=int(round(float(resolution))))
    if polish > 0:
        sf.run("deform_polish", amount=int(round(float(polish))), masked=False)
    if round_form > 0:
        sf.run("deform_balloon", amount=int(round(float(round_form))), masked=False)

    # 5. Contrast pass. ZBrush's Tool > Deformation > Contrast has no
    #    equivalent command in SculptForge: like the plugin's Contrast -100
    #    ("rounder form", mapped to Balloon above), +100 goes through Balloon,
    #    which fills the form out.
    if contrast:
        sf.run("deform_balloon", amount=int(round(float(contrast))), masked=False)

    # 6. Coarse voxel remesh: evens the surface out before retopology.
    if final_voxel > 0:
        sf.run("remesh", resolution=int(round(float(final_voxel))))

    # 7. GroupVisible: one group per connected piece (after the last remesh,
    #    so the groups match the geometry the quad remesh works on).
    if group:
        _try("facegroup_by_connectivity")

    # 8. Quad Remesh: clean all-quad topology.
    quads = int(round(float(quadremesh)))
    _quad_remesh(quads, group, "first pass")

    # 9. Make Symmetric (Tool > Geometry > Symmetry): keeps the half on the +
    #    side of the plane through the world origin, mirrors it and welds the
    #    seam. The Part must straddle that plane, otherwise half of it is
    #    replaced by a mirrored copy of the other half. The mirror cuts the
    #    quads, so a second Quad Remesh rebuilds clean topology afterwards.
    if symmetric:
        axis = symmetry_axis if symmetry_axis in SYMMETRY_AXES else "x"
        if axis != symmetry_axis:
            print("  Make Symmetric: unknown axis %r, using x." % (symmetry_axis,))
        if _try("mirror_and_weld", axis=axis):
            print("  Make Symmetric: mirrored across the %s plane through the origin."
                  % axis)
            _quad_remesh(quads, group, "after the mirror")
        else:
            print("  Make Symmetric left out; the mesh keeps its own symmetry.")

    # 10. automerge from the plugin (SelectUp + MergeDown), or kept visibility.
    if merge:
        sf.run("part_select", index=source_index)
        sf.run("part_merge_down")              # not undoable: see the header
        final_index = source_index
    else:
        # The source Part keeps exactly the visibility it had before the
        # operation; only the "Hide the source Part" checkbox hides it.
        sf.run("part_visibility", index=source_index,
               visible=False if hide_source else source_visible)
        final_index = result_index
        sf.run("part_select", index=final_index)

    part = doc.parts[final_index]
    print("Ready: \"%s\" (%d triangles) - %s." % (
        part["name"], part["triangles"],
        "merged with the source" if merge else "new sculptable Part"))
    return final_index


# ---------------------------------------------------------------------------
# Interface (SculptForge 0.13.8+)
# ---------------------------------------------------------------------------
def _panel_value(control, fallback):
    """Value of a panel control, or the default value."""
    try:
        value = sf.ui.value("blobit." + control)
    except Exception:
        return fallback
    return fallback if value is None else value


def _run_from_panel():
    try:
        thickness = float(_panel_value("thickness", THICKNESS * 100.0))
    except (TypeError, ValueError):
        thickness = THICKNESS * 100.0
    if not (0.1 <= thickness <= 100.0):   # 0, NaN or denormal: unreadable value
        print("BlobIt: thickness read from the panel is invalid (%r), "
              "falling back to %.2f %%." % (thickness, THICKNESS * 100.0))
        thickness = THICKNESS * 100.0
    blob_it(
        thickness=thickness / 100.0,
        smooth=int(_panel_value("smooth", SMOOTH)),
        both_sides=bool(_panel_value("both_sides", BOTH_SIDES)),
        voxel=bool(_panel_value("voxel", VOXEL)),
        resolution=int(_panel_value("resolution", VOXEL_RES)),
        polish=int(_panel_value("polish", POLISH)),
        round_form=int(_panel_value("round", ROUND)),
        symmetric=bool(_panel_value("symmetric", SYMMETRIC)),
        quadremesh=int(_panel_value("qremesh", QUADREMESH)),
        merge=bool(_panel_value("merge", MERGE)),
        hide_source=bool(_panel_value("hide_source", HIDE_SOURCE)),
    )


# Reshape: Balloon - buttons from -100 to 100 in steps of 20. Each button
# applies its own amount straight away: nothing is remembered between clicks,
# so pressing +40 twice inflates twice as much, and 0 changes nothing.
BALLOON_STEPS = tuple(range(-100, 101, 20))


def _balloon_apply(value):
    """Apply this Balloon amount to the active mesh.

    The amount is applied as given, not as a difference with a previous
    setting: pressing the same button twice applies it twice. The 0 button
    changes nothing. Each click is one undo step.
    """
    doc = sf.document()
    if not doc.parts:
        return

    part = doc.parts[doc.active_part]
    amount = int(round(float(value)))
    if amount == 0:
        print("Reshape: Balloon 0 on \"%s\": nothing to change." % part["name"])
        return

    sf.run("deform_balloon", amount=amount)
    print("Reshape: Balloon %+d on \"%s\"" % (amount, part["name"]))


def _balloon_button(value):
    """Callback of a Balloon button (one function per value)."""
    return lambda: _balloon_apply(value)


def _balloon_action_id(value):
    """Stable, unique action id: blobit.balloon.m20 / z0 / p20."""
    if value < 0:
        return "blobit.balloon.m%d" % -value
    if value > 0:
        return "blobit.balloon.p%d" % value
    return "blobit.balloon.z0"


def _declare_ui():
    sf.ui.action(
        "blobit.run", "Blob it", _run_from_panel, icon="wand",
        help="Turn the masked area into a sculptable mesh (merging cannot be undone)")

    panel = sf.ui.panel("blobit", "BlobIt")
    panel.label("Mask an area of the active Part, then press Blob it")
    panel.separator()
    # A slider label is a printf format - SculptForge appends " %.3g" for the
    # value - so a literal "%" must be written "%%"; otherwise "% d" swallows
    # the argument and the displayed number becomes garbage.
    panel.slider("thickness", "Shell thickness (%% of the longest side)",
                 THICKNESS * 100.0, 0.5, 10.0)
    panel.slider("smooth", "Edge smoothing", SMOOTH, 0, 30, integer=True)
    panel.checkbox("both_sides", "Shell on both sides", BOTH_SIDES)
    panel.separator()
    panel.checkbox("voxel", "Voxel remesh (Blob / Dynamesh)", VOXEL)
    panel.slider("resolution", "Voxel resolution", VOXEL_RES, 32, 512, integer=True)
    panel.slider("polish", "Polish", POLISH, 0, 100, integer=True)
    panel.slider("round", "Round at extraction (Contrast -100)", ROUND, 0, 100,
                 integer=True)
    panel.separator()
    panel.checkbox("merge", "Merge with the Part above", MERGE)
    panel.checkbox("hide_source", "Hide the source Part (otherwise its visibility is kept)",
                   HIDE_SOURCE)
    # Symmetry after the first Quad Remesh; the slider value is reused for the
    # second pass that cleans up the mirror cut. 0 turns both passes off.
    panel.checkbox("symmetric", "Make Symmetric after the quad remesh (X, through the origin)",
                   SYMMETRIC)
    panel.slider("qremesh", "Quad remesh (quads, 0 = off)",
                 QUADREMESH, 0, 5000, integer=True)
    panel.button("blobit.run")
    panel.separator()
    panel.label("Reshape: Balloon (each button applies its own value; 0 does nothing)")
    for value in BALLOON_STEPS:
        aid = _balloon_action_id(value)
        label = "0" if value == 0 else ("%+d" % value)
        sf.ui.action(aid, "Balloon " + label, _balloon_button(value),
                     icon="move",
                     help="Inflates (positive) or deflates (negative) the active "
                          "Part by this percentage, applied as it is; pressing it "
                          "again applies it again, and 0 changes nothing.")
        panel.button(aid, label=label)

    sf.ui.place("blobit.run", "top")
    sf.ui.place("blobit", "my_panel")


if hasattr(sf, "ui"):
    _declare_ui()
    print("BlobIt: \"Blob it\" button added (top shelf, "
          "My Panel, F3 palette).")
else:
    print("BlobIt: sf.ui missing (SculptForge 0.13.8+ required); "
          "call blob_it() from the Python console.")
