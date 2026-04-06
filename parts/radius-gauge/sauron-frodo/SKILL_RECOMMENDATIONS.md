# Skill Recommendations — Lessons from the Radius Gauge Build

Maintained by Sauron during the review pass. Updated at each step.

---

## 1. The validation pipeline was never run

The novel-cad skill specifies a mandatory four-tool validation pipeline after every STEP export: `validate_geometry.py`, `check_printability.py`, `validate_manifold.py`, `render_cross_sections.py`. Plus gate enforcement via `GateEnforcer`.

**None of these were used during the radius gauge build.** Not once across 15 commits and 78 leaves. All quality review was done by visual inspection of low-resolution preview renders. The cross-section tool failed on first attempt (missing spec sidecar) and was abandoned in favor of ad-hoc matplotlib slicing.

**Recommendation:** The skill should detect when it's being used for a multi-leaf parametric set (not a single enclosure) and adapt the pipeline accordingly. The current pipeline assumes one part, one spec, one gate sequence. A 78-leaf batch needs:
- A batch validation mode that runs validators on N samples, not all N leaves
- Spec sidecars generated per-leaf automatically by the batch script
- A summary report ("78 built, 78 manifold, 3 printability warnings")

## 2. RadiusArc sign convention is a landmine

Five separate commits were burned fixing RadiusArc direction. The sign convention (positive = short/minor arc, negative = long/major arc) is not intuitive for concave-into-body vs convex-outward operations. The skill's BUILD123D_REFERENCE.md does not document this.

**Recommendation:** Add a "Common Gotchas" section to BUILD123D_REFERENCE.md:
- `RadiusArc(A, B, +r)`: minor arc (shorter path). For two points on a vertical line, curves LEFT of the A→B direction.
- `RadiusArc(A, B, -r)`: major arc (longer path). Curves RIGHT.
- Always build a 2-point test before committing to a sign in production geometry.

## 3. The skill doesn't handle parametric families

The entire skill workflow (phases, gates, spec, validation) is designed for one part. The radius gauge is 78 parts that share a parametric generator. The skill had no guidance for:
- When to use a parameter table vs a single spec
- How to validate a parametric family (sample-based vs exhaustive)
- How to structure batch output (folder conventions, naming)
- How to handle two architectures (dual-ended + talon) in one generator

**Recommendation:** Add a "Parametric Families" section to SKILL.md covering:
- Generator script pattern (parameter table → loop → export)
- Sample-based validation (pick 1-2 per ring, not all 78)
- Output folder conventions (step/, png/, separate)
- When to split architectures into separate generators vs one function with a switch

## 4. G1 continuity should be a first-class concept

The biggest time sink in this build was the arc-to-body transition — G0 (position match) vs G1 (tangent match). The skill mentions "tangent blend" in the spec format (`arc_tangent_blend: true`) but provides no implementation guidance. Five rewrites and a war council were needed to get this right.

**Recommendation:** Add to BUILD123D_REFERENCE.md:
- Definition of G0 vs G1 vs G2 continuity
- How to compute tangent direction at a RadiusArc endpoint
- Pattern: "follow the tangent for N mm, then transition to straight"
- Warning: "vertical body sides meeting curved arcs always produce a visible kink unless the sweep is exactly 180°"

## 5. The Sauron/Frodo review loop should be a documented pattern

The most effective quality process in this build was the Sauron+Frodo iteration loop: code a fix, render, review the image, iterate. This caught bugs that the validation pipeline would have missed (visual artifacts, wrong proportions, cat ears). It also caught bugs faster than running the full pipeline would have.

**Recommendation:** Document this as a "Visual Review Loop" pattern in the skill:
- Build → render → read image → judge → iterate
- Use for shape validation (does it look like what was asked for?)
- Complement, don't replace, the automated pipeline
- The automated pipeline catches dimensional/manifold/printability issues; the visual loop catches "this doesn't look right"

---

## 6. Missing dependency: networkx

`validate_manifold.py` calls `trimesh.repair.fix_normals()` which requires `networkx`. This is not in `requirements.txt` and not installed by `setup_env.sh`. First-time users will hit `ModuleNotFoundError: No module named 'networkx'` on their first manifold validation.

**Recommendation:** Add `networkx>=3.0` to `requirements.txt`.

## 7. Genus 1 is correct for parts with through-holes

`validate_manifold.py` reports genus but doesn't explain what it means. A through-hole (like a string hole) creates genus 1 topology. Users seeing "genus 1" may think their mesh is broken.

**Recommendation:** Add a note to the manifold output: "genus 1 = 1 through-hole (expected)" or similar context-aware explanation.

## 8. Hole edge treatment should be standard practice

Frodo's review caught that raw cylinder holes (no chamfer) cause string wear and stress cracking. This applies to any FDM-printed through-hole, not just gauge string holes. A 0.2-0.3mm chamfer on hole edges should be a default recommendation in the FDM Print Defaults table.

**Recommendation:** Add to SKILL.md's FDM Print Defaults: "Through-holes: chamfer both faces 0.2-0.3mm for stress relief and deburring."

## 9. Tip fillet failure handling

Silent `try/except pass` on fillet operations is a quality risk. The v1 code silently shipped sharp tips when fillets failed. Frodo correctly identified this as a cut-your-fingers hazard.

**Recommendation:** The skill template's fillet section should include a fallback chain with logging:
1. Try requested radius
2. Fall back to half radius
3. Print WARNING if both fail — don't silently pass

## 10. Non-gauging geometry should default to straight lines

The biggest time sink in this project was perfecting the back profile of the talon — arcs, G1 splines, tangent constraints. The user's eventual rule: "straight lines are fine anywhere we're not describing the target radius of measure." This should have been the starting assumption.

**Recommendation:** Add to SKILL.md: "For measurement tools, only the measurement surfaces need precision geometry. All non-measurement surfaces (body, handles, transitions) should default to straight lines or simple chamfers. Don't optimize what doesn't need optimizing."

## 11. Workpiece clearance is a first-class design constraint

The user pointed out that body material must never project into the space where the workpiece sits during measurement. This is obvious in retrospect but the skill has no guidance on clearance envelopes for measurement tools.

**Recommendation:** For measurement tool designs, require a "workpiece mating zone" analysis: imagine the workpiece against each gauging surface and verify no other body material intrudes.

## 12. `trimesh.to_2D()` returns a tuple in v4.x

The skill's `render_cross_sections.py` uses `to_planar()` (deprecated) and may break with trimesh 5.x. The correct call is `path2d, transform = section.to_2D()` — must unpack the tuple.

**Recommendation:** Update `render_cross_sections.py` and document the API change.

## 13. Manifold validator doesn't handle multi-body STEP files

The `validate_manifold.py` script loads the entire STEP as one merged mesh. Multi-body assemblies (like our 3-body gauge leaves where text inlays sit inside deboss pockets) create self-intersecting meshes by design. The validator reports FAIL on assemblies that are correct.

**Recommendation:** Add a `--per-body` flag to `validate_manifold.py` that loads each body separately and validates independently. Report per-body results.

## 14. build123d "unable to clean" warnings are common with Text booleans

Large text deboss operations on thin bodies frequently trigger `UserWarning: Unable to clean` from build123d. These appear to be cosmetic — the geometry exports and slices correctly. But they add noise to the build log and make it hard to spot real errors.

**Recommendation:** Document in the skill that text boolean warnings are expected and don't indicate failure. Consider suppressing them with `warnings.filterwarnings` in batch generation scripts.

*Last updated: after Phase 3 batch generation of 78 leaves.*
