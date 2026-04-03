# novel-cad-skill — TODO from Smoke Test (2026-04-03)

Based on 2-part smoke test: Pi 4 case (functional enclosure) + dino desk organizer (decorative/organic).

## High Priority — Breaks Workflow

- [ ] **#3 check_printability.py:333** — Crashes on wall thickness analysis. `'tuple' object has no attribute 'entities'` in `_min_thickness_from_path2d`. trimesh `path2d` returns a tuple in some cross-section topologies instead of a Path2D object. This validator never successfully completed a full run during the entire smoke test.

- [ ] **#4 spec_format.py — Missing feature types** — Rejects `boss`, `standoff`, `rib`, `sweep`, `loft`, `revolve`. SKILL.md documents these as valid, but `_validate_feature()` only accepts `[channel, hole, pattern, pocket, rail, slot]`. Either add the missing types or remove them from the docs.

- [ ] **#7 validate_geometry.py — Slot probe broken for wall features** — `probe_z` scans an XY cross-section at the given Z. For slots through side walls, the probe crosses the interior cavity and measures ~59mm instead of the 13mm slot. Only works for floor/ceiling features. Needs a directional probe or wall-aware detection.

## Medium Priority — Causes Confusion

- [ ] **#1 SKILL.md — `verify_boolean` doesn't exist** — Doc references `verify_boolean` but actual helpers are `verify_result` and `verify_bounds` in `bd_debug_helpers.py`. Update all doc examples.

- [ ] **#2 SKILL.md — `Shell()` API wrong** — Doc uses `Shell(face, thickness=-wall)` but build123d uses `offset(amount=-wall, openings=face)`. Update template and examples.

- [ ] **#5 SKILL.md — `Add()` vs `add()`** — Doc uses uppercase `Add(base)` but build123d uses lowercase `add(base)`. CadQuery uses uppercase. Update all import-STEP examples.

- [ ] **#8 spec_format.py — "polar" arrangement rejected** — Only accepts `grid`, `linear`, `radial`. Also requires `pitch > 0` for radial patterns where pitch is angular, not linear mm. Either accept "polar" as alias for "radial" or document the valid values. Allow pitch=0 or interpret pitch as degrees for radial.

- [ ] **#9 render_cross_sections.py — Wrong plane for radial patterns** — Computes section plane at X=-159mm for a radial pattern at X=-30. Misinterprets the `position` field combined with radial arrangement math. Sections skip gracefully (no crash) but miss the feature entirely.

## Low Priority — Working but Awkward

- [ ] **#6 gate_enforcer.py — Cross-script replay** — Gate state persists in `.gate.json` but each new script must replay the full validation+approval sequence for all prior phases before starting its own. Could add a `resume_from(phase)` method that trusts the persisted state.

## Enhancements (from DeskGuy feedback)

- [ ] **Cross-section renderer: conventional section view** — Currently shows only the cut profile outline. Should render parts beyond the cut plane as shaded solids in a darker color. Would make sections immediately readable without mental 3D reconstruction.

- [ ] **Cross-section renderer: better camera angles** — Angled features near edges can read backwards in orthographic views. Consider adding a slight-above perspective option or labeling lean/angle direction.

- [ ] **Spec height tracking** — Easy to get wrong when importing prior-phase STEP that's taller than current phase's additions. Consider auto-computing bounding box height from STEP file instead of requiring manual spec declaration.

## Lessons Learned (for SKILL.md)

- [ ] Add to docs: **Boolean overlap rule** — Always overlap operands by 0.5-1mm. Touching faces create genus != 0 (topological poison for slicers).

- [ ] Add to docs: **Plane orientation gotcha** — `Plane(z_dir=(0,1,0), x_dir=(1,0,0))` maps sketch Y into world -Z (downward). Use `z_dir=(0,-1,0)` for YZ-plane sketches where Y should map upward. Document the mapping explicitly.

- [ ] Add to docs: **Spec height = tallest feature across ALL phases**, not just current phase additions.
