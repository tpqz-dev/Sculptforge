# SPDX-FileCopyrightText: 2026 
# SPDX-License-Identifier: CC0-1.0
#
# Written in 2026. To the extent possible under law, the author(s) have dedicated 
# all copyright and related and neighboring rights to this software to the public 
# domain worldwide. This software is distributed without any warranty.
# You should have received a copy of the CC0 Public Domain Dedication along with this software. 
# If not, see <http://creativecommons.org/publicdomain/zero/1.0/>.

import sculptforge as sf

THICKNESS = 0.0766
SMOOTH = 24
BOTH_SIDES = True

VOXEL = True
VOXEL_RES = 53
POLISH = 10
ROUND = 0

CONTRAST = 100
FINAL_VOXEL = 32
SYMMETRIC = True
SYMMETRY_AXIS = "x"
SYMMETRY_AXES = ("x", "y", "z", "xy", "xz", "yz")
QUADREMESH = 400

GROUP = True
MERGE = False
HIDE_SOURCE = False
FREEZE_LEVELS = True

RESULT_SUFFIX = "_SB"

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
    except Exception as exc:
        print("  " + command + " skipped: " + str(exc))
        return False

def _quad_remesh(quads, group, stage):
    """Run one Quad Remesh pass (skipped when quads is 0)."""
    if quads <= 0:
        return
    if not _try("qremesh", target=quads, keep_groups=bool(group)):
        print("  Quad remesh (%s) left out; the mesh keeps its current topology."
              % stage)

def shadowbox_it(thickness=THICKNESS, smooth=SMOOTH, both_sides=BOTH_SIDES,
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

    if freeze_levels:
        _try("subdiv_freeze")

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

    result_index = min(source_index + 1, len(doc.parts) - 1)

    sf.run("mask_clear")

    sf.run("part_select", index=result_index)
    sf.run("part_rename", to=target)
    sf.run("mask_clear")

    if voxel:
        sf.run("remesh", resolution=int(round(float(resolution))))
    if polish > 0:
        sf.run("deform_polish", amount=int(round(float(polish))), masked=False)
    if round_form > 0:
        sf.run("deform_balloon", amount=int(round(float(round_form))), masked=False)

    if contrast:
        sf.run("deform_balloon", amount=int(round(float(contrast))), masked=False)

    if final_voxel > 0:
        sf.run("remesh", resolution=int(round(float(final_voxel))))

    if group:
        _try("facegroup_by_connectivity")

    quads = int(round(float(quadremesh)))
    _quad_remesh(quads, group, "first pass")

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

    if merge:
        sf.run("part_select", index=source_index)
        sf.run("part_merge_down")
        final_index = source_index
    else:

        sf.run("part_visibility", index=source_index,
               visible=False if hide_source else source_visible)
        final_index = result_index
        sf.run("part_select", index=final_index)

    part = doc.parts[final_index]
    _reset_balloon()
    print("Ready: \"%s\" (%d triangles) - %s." % (
        part["name"], part["triangles"],
        "merged with the source" if merge else "new sculptable Part"))
    return final_index

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
    if not (0.1 <= thickness <= 100.0):
        print("blobit: thickness read from the panel is invalid (%r), "
              "falling back to %.2f %%." % (thickness, THICKNESS * 100.0))
        thickness = THICKNESS * 100.0
    shadowbox_it(
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

BALLOON_STEPS = tuple(range(-100, 101, 20))
_balloon_state = {"part": None, "amount": 0.0}

def _reset_balloon():
    _balloon_state["part"] = None
    _balloon_state["amount"] = 0.0

def _balloon_apply(value):
    """Apply the difference of the chosen Balloon setting to the active mesh.

    Each button picks a setting from -100 to 100: only the difference with the
    previous setting is applied, so 0 returns to the starting shape (up to
    rounding). Each click is one undo step. A new mesh (or another Part) starts
    from zero.
    """
    doc = sf.document()
    if not doc.parts:
        return

    active = doc.active_part
    part = doc.parts[active]
    key = (active, part["triangles"])
    if key != _balloon_state["part"]:
        _balloon_state["part"] = key
        _balloon_state["amount"] = 0.0

    amount = int(round(float(value)))
    delta = amount - _balloon_state["amount"]
    if delta == 0:
        print("Reshape: Balloon is already at %+d on \"%s\"." % (amount, part["name"]))
        return

    sf.run("deform_balloon", amount=delta)
    _balloon_state["amount"] = amount
    print("Reshape: Balloon %+d on \"%s\" (setting %+d)"
          % (delta, part["name"], amount))

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

    panel = sf.ui.panel("blobit", "blobit")
    panel.label("Mask an area of the active Part, then press Blob it")
    panel.separator()

    panel.slider("thickness", "Shell thickness (%% of the longest side)",
                 THICKNESS * 100.0, 0.5, 10.0)
    panel.slider("smooth", "Edge smoothing", SMOOTH, 0, 30, integer=True)
    panel.checkbox("both_sides", "Shell on both sides", BOTH_SIDES)
    panel.separator()
    panel.checkbox("voxel", "Voxel remesh (ShadowBox / Dynamesh)", VOXEL)
    panel.slider("resolution", "Voxel resolution", VOXEL_RES, 32, 512, integer=True)
    panel.slider("polish", "Polish", POLISH, 0, 100, integer=True)
    panel.slider("round", "Round at extraction (Contrast -100)", ROUND, 0, 100,
                 integer=True)
    panel.separator()
    panel.checkbox("merge", "Merge with the Part above", MERGE)
    panel.checkbox("hide_source", "Hide the source Part (otherwise its visibility is kept)",
                   HIDE_SOURCE)

    panel.checkbox("symmetric", "Make Symmetric after the quad remesh (X, through the origin)",
                   SYMMETRIC)
    panel.slider("qremesh", "Quad remesh (quads, 0 = off)",
                 QUADREMESH, 0, 5000, integer=True)
    panel.button("blobit.run")
    panel.separator()
    panel.label("Reshape: Balloon (cumulative setting; 0 returns to the start)")
    for value in BALLOON_STEPS:
        aid = _balloon_action_id(value)
        label = "0" if value == 0 else ("%+d" % value)
        sf.ui.action(aid, "Balloon " + label, _balloon_button(value),
                     icon="move",
                     help="Inflates (positive) or deflates (negative) the active "
                          "Part by the chosen percentage; the 0 button returns "
                          "to the starting shape.")
        panel.button(aid, label=label)

    sf.ui.place("blobit.run", "top")
    sf.ui.place("blobit", "my_panel")

if hasattr(sf, "ui"):
    _declare_ui()
    print("blobit: \"Blob it\" button added (top shelf, "
          "My Panel, F3 palette).")
else:
    print("blobit: sf.ui missing (SculptForge 0.13.8+ required); "
          "call shadowbox_it() from the Python console.")
