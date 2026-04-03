# Legolas Task D — Fix cross-section dimension coordinate mismatch

**Date:** 2026-04-02
**File:** `scripts/render_cross_sections.py` lines 536-584
**Bug:** BUG 5 (MED)

## Problem

`_draw_dimension_h()` and `_draw_dimension_v()` receive pixel coordinates (bitmap row/col) and convert to mm for matplotlib plotting. The conversion was:

```python
y_mm = y * mm_per_px + y_off    # WRONG
```

where `y_off` = ymax (the top edge of the geometry in mm). Bitmap rows increase downward (row 0 = top = ymax), but matplotlib's Y axis increases upward. Adding `y * mm_per_px` to ymax moves the dimension annotations *above* the geometry instead of placing them at the correct Y position.

## Fix

Changed Y transform in both functions to subtract:

```python
y_mm = y_off - y * mm_per_px    # CORRECT
```

This converts bitmap row positions back to mm coordinates that match the polygon patches drawn on the same axes (lines 644-657, which use raw mm coordinates from shapely polygons).

## Files Changed

- `scripts/render_cross_sections.py` line 541: `_draw_dimension_h` Y transform
- `scripts/render_cross_sections.py` lines 565-566: `_draw_dimension_v` Y1/Y2 transforms

## Note

This file also uses `solid.tessellate(tolerance=0.01)` at line 66 — the same tessellation mismatch as Bug 1. That's Sauron's Task B scope, not fixed here.

## Verification

Needs visual verification with a real STEP file. The dimension arrows and extension lines should now align with the polygon geometry on the plot.
