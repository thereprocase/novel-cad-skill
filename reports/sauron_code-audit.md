# Sauron Code Correctness Audit — Task #17
**Date:** 2026-04-02
**Auditor:** Sauron (Novel-CAD-Main, member 8p589s)
**Scope:** All 13 Python files in scripts/ and lib/ checked against ARCHITECTURE.md S1-14

## Confirmed Bugs

### BUG 1: validate_manifold.py — tessellation path mismatch
`_load_mesh_from_step()` uses `solid.tessellate(tolerance=0.01)` for build123d path. But `check_printability.py` and `export_3mf.py` use OCC `BRepMesh_IncrementalMesh` at 0.05mm. Different tessellations produce different topology — a mesh can pass manifold check but fail in the export path.
**Severity:** High — the manifold guarantee is only as good as the tessellation it validates.

### BUG 2: validate_geometry.py — pattern validation broken (lines 376-389)
Code checks `feat.get("element_width")` but spec format puts width at `feat["element"]["width"]`. `element_width` is never a top-level key in a validated pattern spec. ALL pattern features silently fall to the WARN path.
**Severity:** High — pattern validation is effectively disabled.

### BUG 3: spec_format.py — tolerance double-consume (line 282)
`raw.update(kwargs)` copies tolerance to `raw["tolerance"]`, then `kwargs.pop("tolerance")` removes from kwargs but raw already has it. Phantom top-level "tolerance" key persists in written JSON.
**Severity:** Low — harmless but wrong.

### BUG 4: check_printability.py — module-level mutable `_results = []` (line 63)
Accumulates across multiple calls in the same process. FAIL check at line 775 sees failures from previous runs. Only affects library usage, not CLI.
**Severity:** Medium — will bite when used from gate_enforcer or test harness.

### BUG 5: render_cross_sections.py — dimension annotation coordinate mismatch
`_draw_dimension_h/v` takes pixel coords but converts to mm, while polygon patches use polygon mm coords. Bitmap has margins, offsets, and flipped Y. Dimension arrows may appear at wrong positions relative to geometry.
**Severity:** Medium — cross-section images may have misplaced dimension annotations.

## Concerns (lower severity)

### CONCERN 1: gate_enforcer.py — sub-phase skip vulnerability
`_predecessor("phase_3")` returns the latest phase < phase_3 from state dict. If phase_2a is approved but phase_2b never started, phase_3 can begin — skipping 2b entirely. ARCHITECTURE.md S8 implies ALL sub-phases must complete before the next major phase.
**Severity:** Medium — logic hole in the enforcement layer.

### CONCERN 2: context_budget.py — unreachable port premium (dead code)
`_feature_cost()` adds `_PORT_CUTOUT_PREMIUM` for type "port" or "cutout". But `spec_format._VALID_FEATURE_TYPES` = {slot, hole, pocket, rail, channel, pattern}. "port" and "cutout" aren't valid types. The premium path is dead code.
**Severity:** Low — dead code, no runtime impact.

### CONCERN 3: Duplicated OCC tessellation across 3 files
`check_printability.py`, `export_3mf.py`, `render_preview.py` each have identical ~30-line OCC `BRepMesh_IncrementalMesh` + `TopExp_Explorer` loops. Should be a shared `_load_mesh_occ()` util in lib/ or bd_debug_helpers.
**Severity:** Low — maintenance burden, not a correctness issue.

## Clean Files
spec_format.py, gate_enforcer.py (minus Concern 1), bd_debug_helpers.py, fallback_router.py, export_3mf.py, render_preview.py, check_printability.py (minus Bug 4), render_cross_sections.py (minus Bug 5)

## Sauron's Priority Ranking
Bug 2 > Bug 1 > Bug 5 > Concern 1 > Concern 2 > Concern 3

## Status
Complete. Both parts delivered. Confirmed by Legolas independently on Bugs 1, 2, 4.
