# Novel CAD Skill — Progress Journal

## 2026-04-02

### INTENT: Reconnaissance — assess state of novel-cad-skill before building

### DONE: Trio channel `novel-cad` established with 4 participants
- Gandalf (Main) — architect, synthesizer
- Legolas (Coordinator) — dep/script audit
- Frodo (NovelCAD-Main) — doc consistency audit
- Sauron (Novel-CAD-Main) — code correctness audit

### DONE: Frodo doc audit (Task #16) — completed
Findings saved to `frodo_doc-audit.md`. Key issues:
- gate_enforcer.py and context_budget.py are built but not integrated into SKILL.md
- fillet()/Fillet() inconsistency between SKILL.md and BUILD123D_REFERENCE.md
- Two SKILL docs with unclear authority (SKILL.md vs SKILL_DRAFT.md)
- warn_wall_mm, 3MF metadata fields missing from SKILL.md examples

### DONE: Gandalf synthesis — full codebase state assessed
- 4,638 lines of Python across 11 files — all functional, no stubs
- All deps install clean: build123d, manifold3d, cadquery, trimesh
- Zero tests, zero fixtures
- Validation pipeline fully implemented but not wired into workflow doc

### DONE: Legolas dep & file audit (Task #14) — completed
Findings saved to `legolas_dep-audit.md`. Key findings:
- 13 implementation files, ~4,779 lines — all real, functional Python
- All deps install on Windows (build123d 0.10.0, manifold3d, cadquery, trimesh, etc.)
- Dual-engine support throughout (build123d primary, CadQuery fallback)
- Zero test files, zero fixtures — the entire gap is testing
- Duplicated mesh-loading code between render_cross_sections.py and check_printability.py

### NOTE: Priority list for shipping
1. Wire gate_enforcer + context_budget into SKILL.md
2. Fix fillet()/Fillet() template bug
3. Resolve SKILL.md vs SKILL_DRAFT.md
4. Write tests
5. End-to-end smoke test on a real part

### DONE: Frodo Task J (#22) — Fix fillet()/Fillet() template bug
- Changed `fillet()` to `Fillet()` with `*` unpacking in all Builder-mode examples
- Fixed in SKILL.md (Phase 1 example) and SKILL_DRAFT.md (Phase 1 example + script template)
- Algebra-mode `fillet()` calls left unchanged (correct for that mode)

### DONE: Frodo Task H (#21) — Integrate gate_enforcer + context_budget into SKILL.md
- Replaced text-only GATE PROTOCOL with programmatic enforcement using GateEnforcer class
- Added full 14-step post-export validation pipeline from ARCHITECTURE.md §11
- Integrated context_budget.estimate_complexity() into Complex Part Management section
- Updated SKILL_DRAFT.md script template with gate_enforcer imports and usage
- Gate enforcement rules documented: begin_phase raises if predecessor not approved, request_approval raises if validations failed or <3 cross-sections

### DONE: Legolas Task D (#23) — Fix cross-section dimension coordinate mismatch
- Fixed Y-coordinate transform in `_draw_dimension_h` and `_draw_dimension_v`
- Changed `y * mm_per_px + y_off` to `y_off - y * mm_per_px` to flip bitmap rows to plot coords
- Report: `legolas_task-d.md`

### DONE: Legolas Task E (#24) — Fix sub-phase skip in gate_enforcer.py
- `_predecessor()` now checks ALL sub-phases of prior major phase, not just latest
- phase_3 requires every phase_2x approved before it can begin
- Limitation: doesn't catch planned-but-never-started sub-phases
- Report: `legolas_task-e.md`

### DONE: Frodo Task K (#25) — Resolve SKILL.md vs SKILL_DRAFT.md
- SKILL.md is now the single authoritative doc
- Merged missing sections from SKILL_DRAFT: Builder vs Algebra table, expanded Export Formats, Preview Rendering, Script Template (with gate_enforcer), Troubleshooting table, build123d code examples, Snap-fit deflection row
- SKILL_DRAFT.md renamed to SKILL_DRAFT.archived.md

### DONE: Frodo Task L (#26) — Add missing spec fields to SKILL.md
- Added warn_wall_mm, export_format, units, description to Phase 1 spec example and script template
- warn_wall_mm creates a WARN band above the FAIL threshold (e.g., WARN < 2.5mm, FAIL < 2.0mm)

### DONE: Legolas Task F — Fix tolerance double-consume in spec_format.py
- Fixed `create_spec()` to pop phantom top-level "tolerance" from `raw` dict
- BUG 3 (LOW) resolved

### DONE: Legolas Task G — Remove dead port/cutout premium from context_budget.py
- Removed `_PORT_CUTOUT_PREMIUM`, deleted "port"/"cutout" from `_FEATURE_COSTS`
- Removed unreachable premium code path in `_feature_cost()`
- CONCERN 2 (LOW) resolved

### DONE: Sauron Task M (#30) — Test suite written
- 5 test files, 53 test cases: spec_format (18), gate_enforcer (12), mesh_utils (12), validate_geometry (5), check_printability (3), conftest
- Results: 52 passed, 1 xfail (known limitation: gate can't enforce un-started sub-phases)
- Zero failures

### DONE: Legolas Task N (#29) — Test fixtures created
- good_box.step + .stl + .spec.json (30x20x15mm filleted box with M4 hole)
- box_with_slots.step + .spec.json (40x30x20mm with 2 parallel slots)
- non_manifold.stl (intentionally broken mesh)
- spec_only.spec.json (PETG spec with pattern features)
- Generator script at generate_fixtures.py
- DISCOVERY: build123d 0.10.0 uses lowercase fillet()/chamfer(), not Fillet()/Chamfer()

### DONE: Frodo Task J-fix — Revert Fillet() back to fillet()
- build123d 0.10.0 confirmed: Fillet is undefined, fillet() is correct
- Reverted all SKILL.md and BUILD123D_REFERENCE.md back to lowercase
- Added version note to reference doc

### COMPLETE: Phases 1-3
- Phase 1 (bugs): 7/7 ✓
- Phase 2 (docs): 5/5 ✓  
- Phase 3 (tests): 6/6 ✓
- Total: 18 tasks completed, 52 tests passing
- Remaining: Phase 4 — end-to-end smoke test

### SESSION CLOSED — 2026-04-02
Channel `novel-cad` ended after 130 messages, 18 tasks completed. Conversation exported to `~/.claude/trio/conversations/novel-cad.md`. Phase 4 (smoke test) deferred to next session.
