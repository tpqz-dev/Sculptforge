# SPDX-FileCopyrightText: 2026 
# SPDX-License-Identifier: CC0-1.0
#
# Written in 2026. To the extent possible under law, the author(s) have dedicated 
# all copyright and related and neighboring rights to this software to the public 
# domain worldwide. This software is distributed without any warranty. 
# You should have received a copy of the CC0 Public Domain Dedication along with this software. 
# If not, see <http://creativecommons.org/publicdomain/zero/1.0/>.

import sculptforge as sf

SOLIDIFY = 0.151
DECIMATE = 25
QUADREMESH = 400
BALLOON = 80
SMOOTH = 30
SMOOTH_REPEAT = 1
SYMMETRIC = True
SYMMETRY_AXIS = "x"
SYMMETRY_AXES = ("x", "y", "z", "xy", "xz", "yz")
KEEP_GROUPS = True
HIDE_SOURCE = False

RESULT_SUFFIX = "_B02"


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


def _decimate(percent, stage):
    """Decimate to this percentage of triangles kept (skipped when 0)."""
    value = float(percent)
    if value <= 0.0:
        return
    if value >= 100.0:
        print("  Decimate (%s): %.0f %% keeps every triangle, skipped."
              % (stage, value))
        return
    if not _try("decimate", ratio=max(0.01, min(1.0, value / 100.0))):
        print("  Decimate left out; the mesh keeps its triangle count.")


def _quad_remesh(quads, group):
    """Run one Quad Remesh pass (skipped when quads is 0)."""
    target = int(round(float(quads)))
    if target <= 0:
        return
    target = max(16, target)
    if not _try("qremesh", target=target, keep_groups=bool(group)):
        print("  Quad remesh left out; the mesh keeps its current topology.")


def blob_it_02(thickness=SOLIDIFY, decimate=DECIMATE, quadremesh=QUADREMESH,
               balloon=BALLOON, symmetric=SYMMETRIC,
               symmetry_axis=SYMMETRY_AXIS, keep_groups=KEEP_GROUPS,
               hide_source=HIDE_SOURCE, name=""):
    """Turn the unmasked area of the active Part into a solid, sculptable mesh.

    The Part must be masked: the mask is copied with the duplicate, inverted,
    the masked part deleted (so only the unmasked area stays), the leftover
    mask cleared, then the surface is solidified, decimated, quad remeshed,
    made symmetric (with a second quad remesh) and inflated with Balloon.

    `thickness` is Solidify's value: a fraction of the largest side (0.151 is
    15.1 %, negative grows in front of the surface, 0 leaves it single-sided).

    Returns the index of the final Part, or None if nothing was done.
    """
    doc = sf.document()
    parts = doc.parts
    if not parts:
        print("Blob it 02: the scene is empty, there is nothing to mask.")
        return None

    masked, total = _mask_stats(doc.mask)
    if masked == 0:
        print("Blob it 02: no mask on the active Part, nothing to build from.")
        print("  Paint the mask (Mask brush) on the area to keep,")
        print("  then press Blob it 02 again.")
        return None

    if masked == total:
        print("Blob it 02: the whole Part is masked, so deleting the masked")
        print("  part would leave nothing. Unmask the area to keep first.")
        return None

    source_index = doc.active_part
    source_name = parts[source_index]["name"]
    target = name or (source_name + RESULT_SUFFIX)
    count_before = len(parts)

    print("Blob it 02: \"%s\" - %d/%d vertices masked, %d kept"
          % (source_name, masked, total, total - masked))
    print("  Solidify: %.3f of the longest side (%.1f %%)."
          % (float(thickness), float(thickness) * 100.0))
    print("  Decimate: %.0f %% of the triangles kept." % float(decimate))

    if not _try("part_duplicate"):
        print("Blob it 02: could not duplicate the Part.")
        return None
    if len(doc.parts) != count_before + 1:
        print("Blob it 02: the duplicate created nothing, stopping.")
        return None

    result_index = doc.active_part
    sf.run("part_rename", to=target)

    sf.run("mask_invert")
    if not _try("delete_masked"):
        print("Blob it 02: deleting the masked part failed, stopping.")
        return None
    sf.run("mask_clear")

    if float(thickness) != 0.0:
        if not _try("solidify", thickness=float(thickness)):
            print("  Solidify left out; the surface stays single-sided.")
    else:
        print("  Solidify: thickness 0, the surface stays single-sided.")

    _decimate(decimate, "before the quad remesh")

    _quad_remesh(quadremesh, keep_groups)

    if symmetric:
        axis = symmetry_axis if symmetry_axis in SYMMETRY_AXES else "x"
        if axis != symmetry_axis:
            print("  Make Symmetric: unknown axis %r, using x." % (symmetry_axis,))
        if _try("mirror_and_weld", axis=axis):
            print("  Make Symmetric: mirrored across the %s plane through the origin."
                  % axis)
            _quad_remesh(quadremesh, keep_groups)
        else:
            print("  Make Symmetric left out; the mesh keeps its own symmetry.")

    amount = int(round(float(balloon)))
    if amount != 0:
        _balloon_apply(amount)

    if hide_source:
        sf.run("part_visibility", index=source_index, visible=False)
        sf.run("part_select", index=result_index)

    part = doc.parts[result_index]
    print("Ready: \"%s\" (%d triangles), from \"%s\"."
          % (part["name"], part["triangles"], source_name))
    return result_index


def _panel_value(control, fallback):
    """Value of a panel control, or the default value."""
    try:
        value = sf.ui.value("blobit02." + control)
    except Exception:
        return fallback
    return fallback if value is None else value


def _run_from_panel():
    try:
        thickness = float(_panel_value("solidify", SOLIDIFY))
    except (TypeError, ValueError):
        thickness = SOLIDIFY
    if not (-1.0 <= thickness <= 1.0):
        print("Blob it 02: Solidify %r is out of range, using %.3f."
              % (thickness, SOLIDIFY))
        thickness = SOLIDIFY
    blob_it_02(
        thickness=thickness,
        decimate=int(_panel_value("decimate", DECIMATE)),
        quadremesh=int(_panel_value("quadremesh", QUADREMESH)),
        symmetric=bool(_panel_value("symmetric", SYMMETRIC)),
        keep_groups=bool(_panel_value("keep_groups", KEEP_GROUPS)),
        hide_source=bool(_panel_value("hide_source", HIDE_SOURCE)),
    )


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


def _balloon_from_panel():
    _balloon_apply(_panel_value("balloon", BALLOON))


def _balloon_action_id(value):
    """Stable, unique action id: blobit02.balloon.m20 / z0 / p20."""
    if value < 0:
        return "blobit02.balloon.m%d" % -value
    if value > 0:
        return "blobit02.balloon.p%d" % value
    return "blobit02.balloon.z0"


def _smooth_apply(amount, repeat):
    """Smooth the active Part `repeat` times with this amount (one undo step per pass)."""
    doc = sf.document()
    if not doc.parts:
        return

    part = doc.parts[doc.active_part]
    strength = int(round(float(amount)))
    times = int(round(float(repeat)))
    if strength <= 0:
        print("Reshape: Smooth 0 on \"%s\": nothing to change." % part["name"])
        return
    if times <= 0:
        print("Reshape: Smooth repeat 0 on \"%s\": nothing to change." % part["name"])
        return

    sf.run("deform_smooth", amount=strength)
    for _ in range(times - 1):
        sf.run("deform_smooth", amount=strength)
    print("Reshape: Smooth %d x%d on \"%s\""
          % (strength, times, part["name"]))


def _smooth_from_panel():
    _smooth_apply(_panel_value("smooth", SMOOTH),
                  _panel_value("smooth_repeat", SMOOTH_REPEAT))


def _declare_ui():
    sf.ui.action(
        "blobit02.run", "Blob it 02", _run_from_panel, icon="wand",
        help="Build a solid Part from the unmasked area of a masked Part: "
             "duplicate, invert the mask, delete the masked part, solidify, "
             "decimate, quad remesh, Balloon")
    sf.ui.action(
        "blobit02.balloon.run", "Balloon !", _balloon_from_panel, icon="move",
        help="Apply the Balloon amount from the slider to the active Part")
    sf.ui.action(
        "blobit02.smooth.run", "Execute smooth", _smooth_from_panel,
        icon="sparkles",
        help="Smooth the active Part with the slider's amount, repeated as "
             "many times as the Repeat slider says")

    panel = sf.ui.panel("blobit02", "Blob it 02")
    panel.label("Mask the area to keep, then press Blob it 02")
    panel.separator()

    panel.label("Solidify thickness: a fraction of the longest side "
                "(0.151 = 15.1 %; 0 keeps the surface single-sided)")
    panel.slider("solidify", "Solidify thickness (of the side)", SOLIDIFY, -1.0, 1.0)
    panel.slider("decimate", "Decimate (% kept, 0 = off)",
                 DECIMATE, 0, 100, integer=True)
    panel.slider("quadremesh", "Quad remesh (quads, 0 = off)",
                 QUADREMESH, 0, 20000, integer=True)
    panel.checkbox("keep_groups", "Quad remesh follows Face Groups", KEEP_GROUPS)
    panel.checkbox("symmetric",
                   "Make Symmetric after the remesh (X)",
                   SYMMETRIC)
    panel.separator()

    panel.checkbox("hide_source", "Hide the source Part", HIDE_SOURCE)
    panel.button("blobit02.run")
    panel.separator()

    panel.label("After the remesh")
    panel.slider("balloon", "Balloon amount (-100 to +100)", BALLOON, -100, 100,
                 integer=True)
    panel.button("blobit02.balloon.run", label="Balloon !")
    panel.separator()
    panel.slider("smooth", "Smooth amount (0-100)", SMOOTH, 0, 100,
                 integer=True)
    panel.slider("smooth_repeat", "Repeat (0 = off)", SMOOTH_REPEAT, 0, 10,
                 integer=True)
    panel.button("blobit02.smooth.run", label="Execute smooth")
    panel.separator()
    panel.label("Presets: each applies its own value (0 does nothing)")
    for value in BALLOON_STEPS:
        aid = _balloon_action_id(value)
        label = "0" if value == 0 else ("%+d" % value)
        sf.ui.action(aid, "Balloon " + label, _balloon_button(value),
                     icon="move",
                     help="Inflates (positive) or deflates (negative) the active "
                          "Part by this percentage, applied as it is; pressing it "
                          "again applies it again, and 0 changes nothing.")
        panel.button(aid, label=label)

    sf.ui.place("blobit02.run", "top")
    sf.ui.place("blobit02", "my_panel")


if hasattr(sf, "ui"):
    _declare_ui()
    print("Blob it 02: \"Blob it 02\" button added (top shelf, "
          "My Panel, F3 palette).")
else:
    print("Blob it 02: sf.ui missing (SculptForge 0.13.8+ required); "
          "call blob_it_02() from the Python console.")
