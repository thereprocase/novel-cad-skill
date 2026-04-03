# Pen Organizer — Build Log (novel-cad-skill test)

Test build for validating the novel-cad-skill pipeline end-to-end.
Channel: trio/pen-organizer

## 2026-04-03

### 01:16 UTC — Channel created
- Joined trio channel `pen-organizer` as NovelCAD-Tester
- Repro provided requirements: 6-8 pen holes (12mm), 3x3" Post-It pocket (40mm deep), phone stand (70°), 200x100mm footprint, geometric/angular style, PLA, no supports

### 01:18 UTC — Concept layout posted
- Proposed L-shaped layout: left section (140mm) for pens + sticky notes, right section (60mm) for phone stand
- 2 rows of 4 pen holes, sticky note pocket below, phone stand wall rising to 80mm
- Repro approved concept at ~01:20 UTC

### 01:22 UTC — Phase 1: Base shape

**Attempt 1 — Box union approach:**
- Two boxes (main body + taller phone wall) unioned, then chamfer vertical edges
- FAILED: `ValueError: Failed creating a chamfer, try a smaller length value(s)`
- **Root cause:** Union of two boxes created short internal edges at the intersection. 2mm chamfer exceeded edge length.
- **Skill improvement note:** SKILL.md should warn about chamfering union bodies with short edges. Recommend single-profile extrusion for stepped shapes.

**Attempt 2 — L-profile extrusion:**
- Built side profile as sketch on XZ plane, extruded along Y
- Single solid — no union, no short edges
- Chamfer succeeded on all vertical edges (2mm) and bottom edges (0.5mm)

**Validation results:**
- validate_geometry: PASS (4/4 — 200x100x80mm matches spec)
- check_printability: PASS (flat bottom, 0.4% overhang WARN — acceptable chamfer artifacts)
- validate_manifold: PASS (32 verts, 60 tris, genus 0)
- Cross-sections: 4 rendered (XY lower, XY upper, XZ side, YZ front)

**Preview self-review:**
- L-shape correct: left=55mm, right=80mm
- Chamfers visible on perspective view
- Cross-section renderer axis labels appear rotated in side profile view (shows "200.00mm" on the 80mm dimension) — cosmetic rendering bug, actual geometry correct per bounding box
- **Skill improvement note:** `render_cross_sections.py` may have axis label mapping issue on XZ plane sections

**Status:** Approved by Repro at ~01:24 UTC

### 01:24 UTC — Phase 2: Features

**Attempt 1 — Algebra-mode phone slot:**
- Pen holes (in-context extrude subtract): SUCCESS
- Sticky note pocket (in-context extrude subtract): SUCCESS
- Phone slot (algebra-mode: Box → rotate → move → subtract outside BuildPart): FAILED
  - Bounding box came out 112mm instead of 80mm
  - The rotated cutter box extended 32mm below Z=0
  - validate_geometry caught it immediately: `[FAIL] Overall height: 112.00mm (expected 80.00 +/-0.30mm)`
- **Skill improvement note:** Algebra-mode boolean subtraction with rotated cutters doesn't clip to the target body. The cutter's full extent becomes part of the result. Always use in-context operations for angled cuts.

**Attempt 2 — In-context tilted workplane:**
- Built phone slot using a tilted `Plane(z_dir=..., x_dir=...)` inside BuildPart context
- Extrude subtract bounded correctly by existing solid
- All three features verified with `snapshot()` / `verify_result()` inline checks

**Also hit:** `NameError: name 'part_solid' is not defined` — leftover variable name from attempt 1 refactor. Trivial fix.

**Validation results:**
- validate_geometry: PASS (7/7 — all dims, slot width 10.08mm, pattern declared)
- check_printability: PASS (flat bottom, min wall 7.4mm, 0.2% overhang)
- validate_manifold: PASS (2067 verts, 4130 tris, genus 0)
- Cross-sections: 7 rendered (feature-specific + general)

**Cross-section review:**
- XY at Z=40mm shows all features correctly positioned
- XZ side profile shows angled phone slot cutting cleanly through tall section
- Pen holes visible as gaps in YZ section
- Sticky pocket 78mm wide confirmed

**Status:** Approved by Repro at ~01:28 UTC

### 01:28 UTC — Phase 3: Print Optimization & Final Delivery

- No geometry changes — Phase 1 already had bottom chamfers, Phase 2 had all features
- Re-exported as `pen_organizer_final.step` and `pen_organizer_final.3mf` (37.2 KB)
- All validators re-run on final STEP: 7/7 PASS, manifold genus 0, printability green
- Parameter table presented

**Status:** Approved by Repro at ~01:30 UTC. Build complete.

---

## Skill Improvement Notes (for post-mortem)

### 1. Chamfer on union bodies (Phase 1)
- **Problem:** Unioning two overlapping boxes creates short edges at the intersection. Chamfering those short edges fails with `StdFail_NotDone`.
- **Fix applied:** Used single L-profile extrusion instead of box union.
- **Recommendation for SKILL.md:** Add pitfall warning: "For stepped/L-shaped parts, extrude from a single profile sketch rather than unioning boxes. Box unions create short edges that break chamfer/fillet operations."

### 2. Algebra-mode boolean with rotated cutters (Phase 2)
- **Problem:** `part.part - rotated_box` produced a result where the cutter extended beyond the target body, inflating the bounding box from 80mm to 112mm.
- **Fix applied:** Used in-context tilted `Plane()` with extrude subtract inside BuildPart.
- **Recommendation for SKILL.md:** Add to "Common Pitfalls": "Algebra-mode subtraction with rotated/translated cutters can produce geometry artifacts when the cutter extends beyond the target body. Prefer in-context operations with tilted workplanes for angled cuts."

### 3. Cross-section axis labels (Phase 1)
- **Problem:** XZ plane cross-section showed "200.00mm" label on the 80mm height dimension.
- **Root cause:** Likely axis mapping bug in `render_cross_sections.py` for non-XY plane sections.
- **Recommendation:** Debug axis label assignment in the cross-section renderer for XZ and YZ planes.

### 4. Cross-section visual clarity for angled features (Phase 2)
- **Problem:** Repro noted the phone slot's diagonal cut creates a dark band hard to distinguish from solid body.
- **Recommendation:** Consider hatching or color-coding cut surfaces vs. void in cross-section renders.

### 5. Variable name carryover between refactors (Phase 2)
- **Problem:** After refactoring from algebra-mode to in-context, `part_solid` variable name was left in the export section → NameError.
- **Recommendation:** This is a general code hygiene issue, not skill-specific. But the gate enforcer correctly blocked progress until the script ran clean.

## Files in this directory

| File | Purpose |
|------|---------|
| `phase1_base.py` | Phase 1 script — L-profile extrusion |
| `phase1_base.step` | Phase 1 STEP export |
| `phase1_base.spec.json` | Phase 1 spec |
| `phase1_preview.png` | Phase 1 3D preview |
| `phase2_features.py` | Phase 2 script — pen holes, sticky pocket, phone slot |
| `phase2_features.step` | Phase 2 STEP export |
| `phase2_features.spec.json` | Phase 2 spec |
| `phase2_preview.png` | Phase 2 3D preview |
| `phase3_final.py` | Phase 3 script — final validation + export |
| `pen_organizer_final.step` | Final STEP (archival) |
| `pen_organizer_final.3mf` | Final 3MF (slicer-ready, 37.2 KB) |
| `pen_organizer_final.spec.json` | Final spec |
| `phase3_preview.png` | Final 3D preview |
| `pen_organizer.gates.json` | Gate enforcer state (all 3 phases approved) |
| `section_*.png` | Cross-section images (7 total) |
| `BUILD_LOG.md` | This file |
