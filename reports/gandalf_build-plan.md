# Gandalf Build Plan — novel-cad-skill
**Date:** 2026-04-02
**Based on:** Frodo doc audit, Sauron code audit, Legolas dep audit, Gandalf synthesis

## Phase 1: Fix confirmed bugs (no new features)

### Task A: Fix pattern validation (BUG 2 — HIGH)
- File: `scripts/validate_geometry.py` lines 376-389
- Fix: Change `feat.get("element_width")` to `feat["element"]["width"]` (and same for other nested keys)
- Verify: Write a test with a pattern feature and confirm it PASS/FAILs correctly

### Task B: Unify tessellation paths (BUG 1 — HIGH)
- Extract shared `_load_mesh_occ()` into `lib/mesh_utils.py` using `BRepMesh_IncrementalMesh` at 0.05mm
- Update `validate_manifold.py`, `check_printability.py`, `export_3mf.py`, `render_preview.py` to use it
- Also addresses CONCERN 3 (duplicated tessellation code)

### Task C: Fix mutable `_results` (BUG 4 — MED)
- File: `scripts/check_printability.py` line 63
- Move `_results = []` into `main()` or accept as parameter
- Verify: Call `main()` twice in same process, confirm no bleed

### Task D: Fix cross-section dimension coords (BUG 5 — MED)
- File: `scripts/render_cross_sections.py`
- Audit `_draw_dimension_h/v` coordinate transform chain
- Fix pixel-vs-mm mismatch with margin/offset/Y-flip

### Task E: Fix sub-phase skip (CONCERN 1 — MED)
- File: `lib/gate_enforcer.py`
- `_predecessor()` must check ALL sub-phases of the prior major phase, not just the latest
- e.g., phase_3 requires both phase_2a AND phase_2b approved

### Task F: Fix tolerance double-consume (BUG 3 — LOW)
- File: `lib/spec_format.py` line 282
- Remove phantom top-level "tolerance" key

### Task G: Add "port"/"cutout" to valid feature types OR remove dead premium (CONCERN 2 — LOW)
- Either add to `_VALID_FEATURE_TYPES` or delete the premium code path

## Phase 2: Wire SKILL.md (doc gap — critical for deployment)

### Task H: Integrate gate_enforcer into SKILL.md
- Add gate_enforcer imports to script template
- Replace text-only gate protocol with programmatic gate protocol from ARCHITECTURE.md S8
- Show the full 14-step pipeline from ARCHITECTURE.md S11

### Task I: Integrate context_budget into SKILL.md
- Add complexity estimation step before Phase 1
- Reference `estimate_complexity(spec)` with example output

### Task J: Fix fillet()/Fillet() template bug
- SKILL.md Phase 1 example: change `fillet()` to `Fillet()`, add `*` unpacking

### Task K: Resolve SKILL.md vs SKILL_DRAFT.md
- Determine which is authoritative
- Merge or delete the other

### Task L: Add missing spec fields to SKILL.md examples
- `warn_wall_mm`, `export_format`, `color`, `units`, `description`

## Phase 3: Tests

### Task M: Write test suite
- test_spec_format.py — create_spec, validate_spec, write/load round-trip
- test_gate_enforcer.py — phase ordering, sub-phase enforcement, validation recording
- test_context_budget.py — complexity estimation, sub-phase splitting
- test_validate_manifold.py — manifold pass/fail with fixtures
- test_validate_geometry.py — pattern validation, bounding box checks

### Task N: Create test fixtures
- good_box.step — simple valid part
- good_box.spec.json — matching spec
- non_manifold.stl — intentionally broken mesh
- complex_enclosure.step — multi-feature part

## Phase 4: Smoke test

### Task O: End-to-end build
- Pick a simple part (e.g., the DIMM tray from spec_format examples)
- Run the full pipeline: build123d script → STEP → all 4 validators → cross-sections → 3MF
- Document results

## Assignment Recommendations
- **Sauron** → Tasks A, B, C (bugs he found, knows the code paths)
- **Legolas** → Tasks D, E, F, G (lower-severity fixes, dep expertise)
- **Frodo** → Tasks H, I, J, K, L (doc issues he found)
- **Gandalf** → Tasks M, N, O (tests + smoke, needs architectural view)
