# tessellate.py - tessellate the whole mesh (SculptForge 0.13.8+).
#
# SculptForge has no "Tessellate" command: the equivalent is "subdivide", a
# Loop subdivision applied to every triangle of the active Part. Each level
# multiplies the triangle count by 4 and keeps the shape (it only rounds it
# very slightly); unlike Divide (subdiv_divide) it keeps no lower levels to
# step back to. Past 4 levels, use "micro_divide" instead (Micro: the surface
# is stored as displacements, so hundreds of millions of triangles stay
# sculptable).
#
# The panel gives a slider to the number of levels and a slider to a target
# triangle count, a Tessellate button, and four quick-level buttons.
#
# Launch: File > Script > tessellate, then the "Tessellate" button (top shelf,
# My Panel, F3 palette). Requirement: Enable Python scripts in Preferences.
# Each tessellation is its own undo step (Ctrl+Z).

import math

import sculptforge as sf

# ---------------------------------------------------------------------------
# Defaults (the panel replaces them when the button is clicked)
# ---------------------------------------------------------------------------
LEVELS = 1        # subdivision levels (1-4): x4 triangles per level
TARGET = 0        # target count, in thousands of triangles (0 = use the levels)
MAX_LEVELS = 4    # subdivide stops at 4; beyond that use micro_divide

QUICK_LEVELS = (1, 2, 3, 4)


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------
def _panel_value(control, fallback):
    """Value of a panel control, or the default value."""
    try:
        value = sf.ui.value("tessellate." + control)
    except Exception:
        return fallback
    return fallback if value is None else value


def tessellate(levels=LEVELS, target=TARGET):
    """Tessellate the active Part: add polygons over the whole mesh.

    `levels` is the number of Loop subdivision levels (1-4, x4 triangles each).
    `target` is a wanted triangle count in thousands; when it is above 0 it
    overrides the levels and the script picks the number of levels needed to
    reach it. Returns the final triangle count, or None if nothing was done.
    """
    doc = sf.document()
    if not doc.parts:
        print("Tessellate: the scene is empty, there is nothing to subdivide.")
        return None

    part = doc.parts[doc.active_part]
    before = int(part["triangles"])

    exact = int(round(float(target) * 1000.0))
    if exact > 0:
        if exact <= before:
            print("Tessellate: \"%s\" already has %d triangles, at or above the "
                  "%d target; nothing to add." % (part["name"], before, exact))
            return before
        needed = int(math.ceil(math.log(float(exact) / before, 4.0)))
        count = max(1, min(MAX_LEVELS, needed))
        print("Tessellate: \"%s\" - %d triangles, target %d (the levels slider "
              "is ignored)." % (part["name"], before, exact))
    else:
        count = int(round(float(levels)))
        count = max(1, min(MAX_LEVELS, count))
        print("Tessellate: \"%s\" - %d triangles, %d level%s."
              % (part["name"], before, count, "" if count == 1 else "s"))

    try:
        sf.run("subdivide", levels=count)
    except Exception as exc:
        print("Tessellate: failed (%s)." % exc)
        return None

    doc = sf.document()
    after = int(doc.parts[doc.active_part]["triangles"])
    print("  %d -> %d triangles (x%d, %.2f M)."
          % (before, after, max(1, after // max(1, before)), after / 1e6))
    if count >= MAX_LEVELS and exact > 0 and after < exact:
        print("  Still under the target: subdivide stops at %d levels, use "
              "Micro (micro_divide) for more." % MAX_LEVELS)
    return after


def _run_from_panel():
    try:
        levels = int(_panel_value("levels", LEVELS))
    except (TypeError, ValueError):
        levels = LEVELS
    try:
        target = int(_panel_value("target", TARGET))
    except (TypeError, ValueError):
        target = TARGET
    tessellate(levels=levels, target=max(0, target))


def _quick_button(count):
    """Callback of a quick-level button (levels only, no target)."""
    return lambda: tessellate(levels=count, target=0)


# ---------------------------------------------------------------------------
# Interface (SculptForge 0.13.8+)
# ---------------------------------------------------------------------------
def _declare_ui():
    sf.ui.action(
        "tessellate.run", "Tessellate", _run_from_panel, icon="wand",
        help="Add polygons over the whole active Part (one undo step)")

    panel = sf.ui.panel("tessellate", "Tessellate")
    panel.label("Add polygons over the whole mesh; the shape is kept")
    panel.separator()
    panel.slider("levels", "Levels (each one multiplies the triangles by 4)",
                 LEVELS, 1, MAX_LEVELS, integer=True)
    panel.slider("target", "Target (thousands of triangles, 0 = use the levels)",
                 TARGET, 0, 4000, integer=True)
    panel.separator()
    panel.button("tessellate.run")
    panel.separator()
    panel.label("Quick levels (they ignore the target above)")
    for count in QUICK_LEVELS:
        aid = "tessellate.n%d" % count
        sf.ui.action(aid, "+%d level%s" % (count, "" if count == 1 else "s"),
                     _quick_button(count), icon="wand",
                     help="Tessellate the whole active Part by %d level%s "
                          "(x%d triangles)" % (count, "" if count == 1 else "s",
                                               4 ** count))
        panel.button(aid, label="+%d" % count)

    sf.ui.place("tessellate.run", "top")
    sf.ui.place("tessellate", "my_panel")


if hasattr(sf, "ui"):
    _declare_ui()
    print("Tessellate: \"Tessellate\" button added (top shelf, My Panel, "
          "F3 palette).")
else:
    print("Tessellate: sf.ui missing (SculptForge 0.13.8+ required); "
          "call tessellate() from the Python console.")
