# decimate.py - expose the SculptForge "decimate" command as a panel
# (SculptForge 0.13.8+).
#
# Decimate reduces the triangle count of the active Part while preserving its
# shape (quadric edge collapse; sculpt layers are kept). Three parameters:
#   - ratio       fraction of triangles to keep (0.01-1);
#   - triangles   exact target count, which overrides the ratio;
#   - keep_masked masked vertices are not moved or removed.
#
# The panel gives a slider to each of them, a Decimate button, and a few quick
# ratio buttons. The sliders are read when a button is pressed, so every button
# uses the values shown in the panel.
#
# Launch: File > Script > decimate, then the "Decimate" button (top shelf,
# My Panel, F3 palette). Requirement: Enable Python scripts in Preferences.
# Each decimate is its own undo step (Ctrl+Z).

import sculptforge as sf

# ---------------------------------------------------------------------------
# Defaults (the panel replaces them when the button is clicked)
# ---------------------------------------------------------------------------
RATIO = 50            # percent of triangles kept (1-100)
TARGET = 0            # exact count, in thousands of triangles (0 = use the ratio)
KEEP_MASKED = False   # leave masked areas untouched

PRESETS = (90, 75, 50, 25, 10)   # quick percentage buttons


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------
def _panel_value(control, fallback):
    """Value of a panel control, or the default value."""
    try:
        value = sf.ui.value("decimate." + control)
    except Exception:
        return fallback
    return fallback if value is None else value


def decimate_part(ratio=RATIO, target=TARGET, keep_masked=KEEP_MASKED):
    """Decimate the active Part.

    `ratio` is the percentage of triangles kept (1-100). `target` is an exact
    triangle count in thousands; when it is above 0 it overrides the ratio.
    Returns the final triangle count, or None if nothing was done.
    """
    doc = sf.document()
    if not doc.parts:
        print("Decimate: the scene is empty, there is nothing to reduce.")
        return None

    part = doc.parts[doc.active_part]
    before = int(part["triangles"])

    params = {"keep_masked": bool(keep_masked)}
    exact = int(round(float(target) * 1000.0))
    if exact > 0:
        params["triangles"] = exact
        print("Decimate: \"%s\" - %d triangles, target %d (the percentage is ignored)."
              % (part["name"], before, exact))
    else:
        kept = max(0.01, min(1.0, float(ratio) / 100.0))
        if kept >= 1.0:
            print("Decimate: keeping 100 %% leaves \"%s\" unchanged."
                  % part["name"])
            return before
        params["ratio"] = kept
        print("Decimate: \"%s\" - %d triangles, keeping %.0f %%."
              % (part["name"], before, kept * 100.0))

    try:
        sf.run("decimate", **params)
    except Exception as exc:
        print("Decimate: failed (%s)." % exc)
        return None

    doc = sf.document()
    after = int(doc.parts[doc.active_part]["triangles"])
    print("  %d -> %d triangles (%s %%)."
          % (before, after, ("%.1f" % (100.0 * after / before)) if before else "-"))
    return after


def _run_from_panel():
    try:
        ratio = int(_panel_value("ratio", RATIO))
    except (TypeError, ValueError):
        ratio = RATIO
    try:
        target = int(_panel_value("target", TARGET))
    except (TypeError, ValueError):
        target = TARGET
    if ratio <= 0:                       # unreadable slider: back to the default
        ratio = RATIO
    decimate_part(
        ratio=ratio,
        target=max(0, target),
        keep_masked=bool(_panel_value("keep_masked", KEEP_MASKED)),
    )


def _preset_button(percent):
    """Callback of a quick-ratio button (ratio only, no exact count)."""
    return lambda: decimate_part(
        ratio=percent,
        target=0,
        keep_masked=bool(_panel_value("keep_masked", KEEP_MASKED)))


# ---------------------------------------------------------------------------
# Interface (SculptForge 0.13.8+)
# ---------------------------------------------------------------------------
def _declare_ui():
    sf.ui.action(
        "decimate.run", "Decimate", _run_from_panel, icon="wand",
        help="Reduce the triangles of the active Part with the panel settings "
             "(one undo step)")

    panel = sf.ui.panel("decimate", "Decimate")
    panel.label("Reduce the triangles of the active Part; the shape is kept")
    panel.separator()
    # A slider label is a printf format - SculptForge appends " %.3g" for the
    # value - so a literal "%" must be written "%%".
    panel.slider("ratio", "Keep (%% of triangles)", RATIO, 1, 100, integer=True)
    panel.slider("target", "Exact count (thousands of triangles, 0 = use the percentage)",
                 TARGET, 0, 2000, integer=True)
    panel.checkbox("keep_masked", "Keep masked areas untouched", KEEP_MASKED)
    panel.separator()
    panel.button("decimate.run")
    panel.separator()
    panel.label("Quick ratios (the kept percentage; masked setting is kept)")
    for percent in PRESETS:
        aid = "decimate.pct%d" % percent
        sf.ui.action(aid, "Keep %d %%" % percent, _preset_button(percent),
                     icon="wand",
                     help="Decimate the active Part to %d %% of its triangles"
                          % percent)
        panel.button(aid, label="%d %%" % percent)

    sf.ui.place("decimate.run", "top")
    sf.ui.place("decimate", "my_panel")


if hasattr(sf, "ui"):
    _declare_ui()
    print("Decimate: \"Decimate\" button added (top shelf, My Panel, F3 palette).")
else:
    print("Decimate: sf.ui missing (SculptForge 0.13.8+ required); "
          "call decimate_part() from the Python console.")
