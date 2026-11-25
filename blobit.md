# Blob it — short user manual

**What it does.** Blob it turns the masked area of the active Part into a new, sculptable mesh: it extracts a shell from the mask, smooths and rounds it, then remeshes it into clean quads. The result is a separate Part placed beside the source (the source keeps its own undo history).

**Prerequisites.** SculptForge 0.13.8+ with **Enable Python scripts** on (Preferences > Scripts). The script lives in your Scripts folder (`E:\localsculpt\Scripts\blobit.py`); it is listed under **File > Script**.

## Basic workflow

1. Open or sculpt a Part and switch to the **Mask** brush.
2. Paint the area you want to turn into a shell (Ctrl+click to invert the mask).
3. Open the **BlobIt** panel (My Panel) or use the **Blob it** button on the top shelf.
4. Press **Blob it**.

The script prints its progress in the console (extraction, decimation, quad remesh, symmetry).

## Panel controls

| Control | Meaning |
|---|---|
| Shell thickness (% of the longest side) | How far the shell is pushed out from the surface (0.5–10 %). |
| Edge smoothing | Smoothing applied to the extracted shell edges. |
| Shell on both sides | Extracts the shell on both sides of the surface. |
| Decimate (% of triangles kept, 0 = off) | Reduces the extracted mesh before remeshing; 100 keeps everything. |
| Polish | Surface polish pass on the new mesh. |
| Round at extraction (Contrast −100) | Rounds the shell at extraction time. |
| Merge with the Part above | Merges the result back into the source Part instead of creating a new one. |
| Hide the source Part | Hides the original Part once the result exists. |
| Make Symmetric after the quad remesh (X, through the origin) | Mirrors the result across the X plane through the world origin. |
| Quad remesh (quads, 0 = off) | Target quad count for the Quad Remesh passes (first pass, then one after the mirror). |

## Reshape: Balloon buttons

A row of buttons from **−100** to **+100** (in steps of 20) plus **0**. Each button applies its own value to the active mesh as a fixed deformation — pressing the same button twice applies it twice. **0 does nothing.** Each click is one undo step (Ctrl+Z).

## Tips

- The mask must cover a real area; if extraction creates nothing, enlarge the mask.
- If the Part has subdivision levels, they are frozen first (so the extraction works on the base mesh).
- Use **Hide the source Part** to compare the result against the original without z-fighting.
- **Make Symmetric** keeps the half on the + side of the plane and mirrors it; the Part must straddle that plane, otherwise half of it is replaced by a mirrored copy of the other half.
- Every step (extraction, decimation, quad remesh, mirror) is its own undo step.

## Troubleshooting

- *“no mask on the active Part”* — paint a mask first, or invert it with Ctrl+click.
- *“extraction failed”* — make sure the Part is visible and the mask covers a connected area.
- *“Quad remesh … left out”* — the mesh was too coarse or the target too high; lower the quad count or decimate less.
