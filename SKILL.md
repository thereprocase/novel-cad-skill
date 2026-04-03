---
name: novel-cad-skill
description: "Parametric 3D-printable part design using build123d with automated validation, dimensioned cross-sections, and Manifold mesh verification. Triggers on: STL, STEP, 3MF, 3D printing, enclosure, bracket, mount, case, holder, stand, or any physical object design request."
---

# Novel CAD Skill — build123d + Manifold Validation Pipeline

## Overview

Design 3D-printable parts from conversational descriptions. Uses **build123d** (Python, OCCT kernel) for geometry, **Manifold** for mesh validation, and a three-layer automated checking pipeline that catches mistakes before the user sees them.

**Key difference from the legacy CadQuery skill:** build123d's context managers make scope explicit, its selectors are Pythonic, and Manifold guarantees every exported mesh is watertight.

## Dependencies

```bash
bash ~/.claude/skills/novel-cad-skill/scripts/setup_env.sh
```

Requires Python 3.10+. Installs build123d, manifold3d, cadquery (fallback), trimesh, matplotlib, shapely, scipy, pillow.

## Workflow — Phased Checkpoints with Mandatory Gates

**NEVER batch the entire model.** Build incrementally. Each phase has a hard gate — do not proceed without user approval.

### Phase 0: Requirements Gathering
- Ask what they're building. Clarify dimensions, tolerances, material, printer.
- If the part interfaces with a real product, **research exact dimensions** from datasheets.
- **Spec-vs-intent self-check:** Before writing any code, re-read the user's words. For each requirement, identify what geometry satisfies it. If "retention slot" → narrow opening with wider pocket below. If "snap-fit" → cantilever beam with catch. Map language to geometry explicitly.
- Confirm understanding before generating any code.

### Pre-flight: Environment Check
```bash
python -c "import build123d; print('build123d OK')"
python -c "import manifold3d; print('manifold3d OK')"
python -c "import trimesh; print('trimesh OK')"
```

### Phase 1: Base Shape
- Generate build123d script creating ONLY the primary form.
- **Choose mode:**
  - **Builder mode** (default) — for parts with multiple features, holes, pockets:
    ```python
    with BuildPart() as part:
        Box(width, depth, height)
        fillet(part.edges().filter_by(Axis.Z), radius=r_ext)
    ```
  - **Algebra mode** — for simple parts or when Builder context gets complex:
    ```python
    base = Box(width, depth, height)
    base = fillet(base.edges().filter_by(Axis.Z), radius=r_ext)
    ```
  - Rule of thumb: if the part has >6 features, use Builder. If it's 1-3 operations, Algebra is cleaner.

- **Spec capture** — immediately after parameters, before geometry:
  ```python
  from spec_format import create_spec, write_spec
  spec = create_spec(
      "Part name",
      width=W, depth=D, height=H,
      material="PLA",
      min_wall_mm=2.0,
      warn_wall_mm=2.5,       # WARN if wall < 2.5mm, FAIL if < 2.0mm
      engine="build123d",
      export_format="3mf",    # default delivery format
      units="millimeter",     # explicit for 3MF header
      description="Brief part description for 3MF metadata",
  )
  write_spec(spec, "part.step")
  ```
  **Spec scope:** Phase 1 spec = overall dimensions only. Features added at Phase 2.

- **Export STEP + run ALL FOUR validation tools:**
  ```bash
  python scripts/validate_geometry.py part.step
  python scripts/check_printability.py part.step
  python scripts/validate_manifold.py part.step
  python scripts/render_cross_sections.py part.step
  ```

- **Show preview, cross-sections, and validator results to the user.**

> **GATE: Do not proceed to Phase 2 until the user explicitly approves Phase 1.** If the user has not responded, wait. If the user rejects, iterate on this phase until approved.

### Phase 1.5: Text & Labeling
If needed, handle text BEFORE mechanical features.
1. Measure text bounding boxes empirically.
2. Use absolute positioning (not face-relative workplanes) to avoid origin drift.
3. For deboss: create text solid, then subtract. For emboss: add then clip.

### Phase 2: Features
- Add internal features: holes, slots, pockets, mounting posts, cable routes, fillets, chamfers.
- **Import the previous phase's STEP** — do NOT carry forward the full script text:
  ```python
  from build123d import *
  base = import_step("phase1_base.step")
  with BuildPart() as part:
      add(base)
      # Phase 2 features only
  ```
- **UPDATE THE SPEC** to declare every new feature:
  ```python
  spec = create_spec(
      "Part name", width=W, depth=D, height=H,
      material="PLA", min_wall_mm=2.0,
      engine="build123d",
      features=[
          {"type": "hole", "name": "M4 mount", "diameter": 4.3, "position": [10, 15]},
          {"type": "pocket", "name": "battery slot", "width": 15.1, "depth": 51.0},
          {"type": "slot", "name": "cable channel", "width": 5.0, "probe_z": 8.0},
          {"type": "pattern", "name": "vent grid",
           "element": {"type": "slot", "width": 2.0, "length": 15.0},
           "arrangement": "linear", "count": 20, "pitch": 3.0,
           "position": [10.0, 20.0, 0.0], "direction": [1.0, 0.0, 0.0]},
      ],
      components=[
          {"name": "AA battery", "length": 50.5, "width": 14.5,
           "height": 14.5, "clearance_mm": 0.3},
      ],
  )
  ```
  **Every measurable feature MUST be declared.** Empty features array at Phase 2 is always wrong.

  **Feature type guide:**
  - `"slot"` — closed gap with material on BOTH sides. Validator probes cross-section width.
  - `"pocket"` — open cavity, trough, recess. Validator checks component fit envelope.
  - `"hole"` — circular through-hole or blind hole. Validator matches by diameter.
  - `"channel"` — long continuous groove. Validator checks cross-section profile.
  - `"rail"` — raised linear feature. Validator checks cross-section profile.
  - `"pattern"` — array of repeated features (ventilation grid, hole pattern). Declare count, spacing, individual feature dimensions.

- **Use construction-time checks** inline:
  ```python
  from bd_debug_helpers import snapshot, verify_result
  before = snapshot(part)
  with Locations((x, y)):
      Hole(radius=r)
  verify_result(part, before, "mounting hole")
  ```

- Export, validate (all 4 tools), render, show cross-sections to user.

> **GATE: Do not proceed to Phase 3 until the user explicitly approves Phase 2.**

> **When the user gives multiple corrections:** Fix functional mismatches first (wrong feature type, missing features, incorrect dimensions) then aesthetic issues (depth, fillet radius, proportions).

### Phase 3: Print Optimization & Delivery
- Chamfer bottom edges (not fillet — fillets need supports).
- Check overhang angles, wall thickness, bridge spans.
- Export final STEP + 3MF (preferred over STL).
- Run ALL FOUR validation tools. Fix any FAILs.
- Run self-review checklist for things scripts can't check.
- Present **parameter table** for quick tweaks.

> **GATE: Do not deliver the final part without user approval of Phase 3.**

### Phase 4: Multi-Part Assemblies (when needed)
For parts with lids, caps, or mating components:
- Design the base FIRST through Phases 1-3.
- Then design the mating part as a separate build with its own Phases 1-3.
- Clearance between parts: base exterior dims + 2x clearance = lid interior dims.
- Export each part as a separate 3MF.
- For snap-fit lids: cantilever beam length = 4x beam thickness, deflection 0.5-1.0mm for PLA.

### Complex Part Management

Before Phase 1, run the complexity estimator:
```python
sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/lib"))
from context_budget import estimate_complexity

estimate = estimate_complexity(spec)
# Returns: feature_count, estimated_phases, sub_phase_split, risk level
```

If risk is "medium" (6-10 features) or "high" (>10):
1. Present the sub-phase split to the user for approval.
2. Split Phase 2 into sub-phases: 2a (large features), 2b (small ports), 2c (mounting/pattern features).
3. Each sub-phase imports the previous sub-phase's STEP — do NOT carry forward script text.
4. Each sub-phase gets its own spec update, validation, and gate checkpoint.
5. This prevents context exhaustion on complex enclosures.

For ALL parts, regardless of complexity:
- Import STEP at the start of each phase (not the script text from the prior phase).
- Keep scripts under 200 lines. If a script exceeds 200 lines, split it.

### GATE PROTOCOL (programmatic enforcement)

The gate enforcer is a state machine persisted to `.gate.json`. It prevents skipping validation or proceeding without user approval. **This is not optional.**

After completing each phase, follow this exact sequence:

```python
from gate_enforcer import GateEnforcer

gate = GateEnforcer("part_name")
gate.begin_phase("phase_1")

# ... build geometry, export STEP ...

# 1. Run all four validators
# 2. Record results
gate.record_validation("validate_geometry", passed=True)
gate.record_validation("check_printability", passed=True)
gate.record_validation("validate_manifold", passed=True)
gate.record_cross_sections(["section_xy.png", "section_xz.png", "section_yz.png", "section_feat.png"])

# 3. Request approval — this prints the gate message
gate.request_approval("phase_1")
```

4. **STOP.** Show the preview, cross-sections, and validator results to the user.
5. **Wait** for the user to say "approved" or give corrections.
6. Only after explicit user approval:

```python
gate.approve("phase_1", approved_by="user")
gate.begin_phase("phase_2")    # only succeeds if phase_1 is approved
```

**Enforcement rules:**
- `begin_phase(N)` raises if phase N-1 is not `"approved"`.
- `request_approval(N)` raises if any required validation has `passed=False`.
- `request_approval(N)` raises if `cross_sections` has fewer than 3 entries.
- Sub-phases follow the same rules: `begin_phase("phase_2b")` requires `"phase_2a"` approved.

Skipping any step raises a RuntimeError. The gate enforcer is not optional.

## Post-Export Validation Pipeline (every phase, every iteration)

The full pipeline after every STEP export, before showing anything to the user:

```
 1. gate.begin_phase(N)                          # start or resume phase
 2. Claude writes build123d script
 3. Script runs, exports STEP
 4. python scripts/validate_geometry.py part.step  # spec vs reality
 5. python scripts/check_printability.py part.step # FDM checks
 6. python scripts/validate_manifold.py part.step  # mesh topology
 7. python scripts/render_cross_sections.py part.step  # visual verification
 8. python scripts/render_preview.py part.step preview.png  # 3D preview
 9. gate.record_validation(...)                   # all four validators
10. gate.record_cross_sections(...)               # all section PNGs
11. gate.request_approval(N)                      # STOP and wait
12. [user reviews and approves]
13. gate.approve(N)
14. [Phase 3 only] python scripts/export_3mf.py part.step final.3mf
```

- **FAIL** = fix before showing the user. The gate enforcer blocks `request_approval()` if any validation failed.
- **WARN** = OK to show. Flag to user.
- **Cross-sections are mandatory every iteration.** Minimum 4 sections (XY lower, XY upper, XZ side, YZ front). Feature-driven cuts on top. Show ALL section PNGs alongside the 3D preview.
- Cross-sections verify internal geometry that 3D renders cannot show. For thin parts, shallow slots, and cavities, **the cross-sections ARE the review**.

## Fallback Chain

If build123d code generation fails after one retry:
1. **Retry with Algebra mode** if Builder mode failed (or vice versa).
2. **Fall back to CadQuery** — same OCCT kernel, different API. Change imports and patterns, keep the validation pipeline.
3. **Fall back to OpenSCAD** — only for pure CSG parts (no fillets/chamfers needed). Use Manifold backend for speed.

The fallback router detects which environment to use:
- If the part needs fillets, chamfers, lofts → must stay on OCCT (build123d or CadQuery)
- If the part is purely additive/subtractive with no rounds → OpenSCAD is viable

## Builder vs. Algebra Mode — When to Use Which

| Scenario | Recommended Mode | Why |
|----------|-----------------|-----|
| Standard enclosure (box + features) | Builder | Context managers group operations cleanly |
| Simple bracket or adapter plate | Algebra | 1-3 operations, context managers are overhead |
| Part with deeply nested features | Algebra | 3+ nested `with` blocks get confusing |
| Pattern operations (hole arrays) | Builder | `with Locations(...)` is natural in Builder |
| Part requiring explicit variable tracking | Algebra | Each operation returns a named result |
| Fallback after Builder mode fails | Algebra | Stateless — easier to debug |

Both modes produce identical OCCT geometry. The choice is purely about code clarity for the LLM.

---

## Self-Review Checklist

After every preview render, check ALL:

1. **Shape match** — does it look like what was requested? *(visual — human review)*
2. **Feature completeness** — all holes, slots, cutouts present? *(visual — human review)*
3. **Flat bottom** — *(automated by check_printability.py)*
4. **Overhang check** — *(automated by check_printability.py)* (prefer chamfer over fillet at bed contact)
5. **Wall thickness** — *(automated by both validators)* WARN if within 0.3mm of minimum.
6. **Corner wall thinning** — set inner radius = outer radius - wall thickness.
7. **Boolean integrity** — *(automated by bd_debug_helpers.py at construction time)*
8. **Printability** — bridge spans <20mm *(automated by check_printability.py)*
9. **Clearance** — hole diameters include +0.3mm for FDM *(automated by validate_geometry.py)*
10. **Manifold mesh** — *(automated by validate_manifold.py)*

## Export Formats

### 3MF (primary delivery format)
Default to **3MF export**. 3MF encodes units (no inches-vs-mm ambiguity), supports color and material metadata, and uses compact binary. OrcaSlicer, PrusaSlicer, Bambu Studio all import 3MF natively.

```bash
python ~/.claude/skills/novel-cad-skill/scripts/export_3mf.py part.step part.3mf
```

### STEP (archival format)
Always export STEP alongside 3MF. STEP retains full B-rep parametric information — arcs are arcs, circles are circles. This enables downstream editing in any CAD tool.

### STL (fallback only)
Export STL only if the slicer explicitly requires it or for plate packing of many parts. STL loses precision and produces ugly preview renders (visible triangle mesh on flat surfaces).

---

## Preview Rendering

```bash
python ~/.claude/skills/novel-cad-skill/scripts/render_preview.py part.step preview.png
```

- **Always render from STEP** — per-face shading gives clean surfaces. STL renders show triangle mesh artifacts.
- Produces 2x2 grid: front, right, top, perspective.
- Read the resulting image to self-review before showing to the user.
- Check for: missing geometry (unexpected flat areas), z-fighting (flickering overlapping faces), features too small to evaluate visually (flag these for slicer verification).

## FDM Print Defaults

| Parameter | PLA | PETG | TPU | ABS |
|-----------|-----|------|-----|-----|
| Wall thickness | 2.0mm | 2.0mm | 3.0mm | 2.0mm |
| Extra clearance | +0.0mm | +0.1mm | +0.2mm | +0.0mm |
| Bottom chamfer | 0.5mm | 0.5mm | 0.5mm | 0.5mm |
| Hole clearance | +0.3mm | +0.4mm | +0.5mm | +0.3mm |
| Max bridge span | 20mm | 15mm | 10mm | 20mm |
| Max overhang | 45deg | 45deg | 40deg | 45deg |
| Min feature size | 0.8mm | 0.8mm | 1.0mm | 0.8mm |
| Snap-fit deflection | 0.5-1.0mm | 0.5-1.0mm | 1.0-2.0mm | 0.5-1.0mm |

## Common Feature Patterns

### Retention slots (cable clips, card holders)
Narrow opening (component width + 0.3mm clearance), wider pocket below (component width + 1.5mm). The narrow opening catches the component; the wider pocket provides clearance for insertion. In build123d:
```python
with BuildSketch(Plane.XZ) as slot_profile:
    with BuildLine():
        Line((0, top), (opening_w/2, top))
        Line((opening_w/2, top), (opening_w/2, top - lip_h))
        Line((opening_w/2, top - lip_h), (pocket_w/2, top - lip_h))
        Line((pocket_w/2, top - lip_h), (pocket_w/2, bottom))
    make_face()
```

### Snap-fit clips (lid attachment)
Cantilever beam: length = 4x thickness, deflection = 0.5-1.0mm for PLA. Catch overhang = 0.3-0.5mm. Print beam along layer lines for maximum flex.

### Screw bosses
Hole diameter = screw + 0.3mm (self-tapping) or screw + 0.5mm (clearance). Boss OD = screw x 2.5. In build123d:
```python
with BuildPart() as boss:
    Cylinder(radius=screw_d * 1.25, height=boss_h)
    Hole(radius=(screw_d + 0.3) / 2)
```

### Ventilation grids
Declare as `"type": "pattern"` in spec. Minimum bar width between slots = 1.2mm for PLA. In build123d:
```python
with BuildPart() as part:
    # ... base geometry ...
    vent_locs = GridLocations(pitch_x, pitch_y, count_x, count_y)
    with Locations(vent_locs):
        Box(slot_length, slot_width, wall + 0.02, mode=Mode.SUBTRACT)
```

### Hole arrays (mounting patterns)
```python
with BuildPart() as part:
    # NEMA 17 mounting pattern: 31mm square
    hole_locs = [(-15.5, -15.5), (-15.5, 15.5), (15.5, -15.5), (15.5, 15.5)]
    with Locations(hole_locs):
        CounterBoreHole(radius=1.65, counter_bore_radius=3.0,
                        counter_bore_depth=3.5, depth=wall + 0.02)
```

### Press-fit holes
Hole diameter = pin diameter - 0.1mm (interference fit for PLA). Test print a single hole first.

## Parameter Table Format

```
+---------------------+---------+----------------------+
| Parameter           | Value   | Notes                |
+---------------------+---------+----------------------+
| Overall width       | 60mm    |                      |
| Wall thickness      | 2.0mm   | Min 1.2mm            |
| Corner radius       | 3.0mm   |                      |
| Hole diameter       | 4.3mm   | M4 + 0.3mm clearance |
+---------------------+---------+----------------------+
```

"Want to adjust any of these? Just say 'make it 5mm taller' or 'move the hole left 10mm' and I'll regenerate."

---

## build123d Script Template

Every generated script should follow this structure:

```python
from build123d import *
import sys
from pathlib import Path

# Construction-time checks
sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/scripts"))
from bd_debug_helpers import snapshot, verify_result, verify_bounds

# Spec capture + gate enforcement
sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/lib"))
from spec_format import create_spec, write_spec
from gate_enforcer import GateEnforcer

# ============================================================
# PARAMETERS — edit these to customize the part
# ============================================================
width = 60.0        # mm
depth = 40.0        # mm
height = 25.0       # mm
wall = 2.0          # mm — wall thickness
r_ext = 3.0         # mm — exterior corner fillet radius
r_int = r_ext - wall  # mm — interior radius (concentric = uniform wall)
clearance = 0.3     # mm — FDM clearance for mating parts

# ============================================================
# SPEC — declare what you're building (validators read this)
# ============================================================
spec = create_spec("Example box", width=width, depth=depth, height=height,
                   material="PLA", min_wall_mm=wall, warn_wall_mm=wall + 0.5,
                   engine="build123d", export_format="3mf",
                   units="millimeter", description="Example parametric box")
write_spec(spec, "phase1_base.step")

# ============================================================
# GATE — begin phase before building geometry
# ============================================================
gate = GateEnforcer("example_box")
gate.begin_phase("phase_1")

# ============================================================
# MODEL
# ============================================================
with BuildPart() as part:
    Box(width, depth, height)
    fillet(part.edges().filter_by(Axis.Z), radius=r_ext)
    offset(amount=-wall, openings=part.faces().sort_by(Axis.Z)[-1])

result = part.part

# Inline boolean verification — use after every subtraction
# before = snapshot(part)
# with Locations((x, y)):
#     Hole(radius=r)
# verify_result(part, before, "mounting hole")

# ============================================================
# EXPORT — STEP primary, 3MF for slicer
# ============================================================
export_step(result, "phase1_base.step")
print(f"Exported: {width}x{depth}x{height}mm")

# ============================================================
# POST-EXPORT — run validators, record results, request approval
# ============================================================
# Run all 4 validators via CLI, then record:
# gate.record_validation("validate_geometry", passed=True)
# gate.record_validation("check_printability", passed=True)
# gate.record_validation("validate_manifold", passed=True)
# gate.record_cross_sections(["section_xy.png", "section_xz.png", ...])
# gate.request_approval("phase_1")
# --- STOP: show preview + cross-sections to user, wait for approval ---
# gate.approve("phase_1", approved_by="user")
```

---

## Common Pitfalls

### Boolean overlap rule
Always overlap boolean operands by 0.5-1mm. Bodies that merely *touch* at a face create degenerate topology (genus != 0) that confuses slicers. When adding a feature that sits on a surface, extend it 0.5-1mm into the base body.

### Plane orientation in build123d
`Plane(z_dir=(0,1,0), x_dir=(1,0,0))` maps sketch Y into world **-Z** (downward). This is because the sketch Y axis is `cross(z_dir, x_dir)` = `(0, 0, -1)`. Use `z_dir=(0,-1,0)` for YZ-plane sketches where sketch Y should map upward in world Z.

### Spec height across phases
When importing a prior-phase STEP that contains features taller than the current phase's additions, the spec `height` must reflect the **tallest feature across all phases**, not just what you're adding now. The validator compares spec height to the actual bounding box.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Builder context boolean fails silently | Use `snapshot(part)` before, then `verify_result(part, before, name)` after every subtraction. |
| Fillet fails on edge | Try smaller radius or chamfer instead. Some edge combinations confuse OCCT. |
| Shell fails | Reduce fillet radii before shelling. Or: fillet exterior, then shell — shell propagates fillet inward. |
| Two fillet types on same solid fail | Apply one fillet type, then add the second after a cut/union using `.filter_by()` to isolate target edges. |
| Text offset after boolean operations | Use absolute positioning for text, not face-relative workplanes. |
| `import_step()` returns wrong type | Wrap in `add()` inside a `BuildPart()` context. |
| Manifold validation fails | Check for coincident faces after booleans. Add 0.01mm extra depth to through-cuts. |
| Context exhaustion on complex part | Split Phase 2 into sub-phases. Import STEP between sub-phases. |
| Spec file not found by validator | You forgot `write_spec(spec, "part.step")`. Add it before geometry generation. |
| Feature dimensions mismatch in validator | Check that spec values match parameter values. A mismatch means spec was written with different values than the geometry used. |
| 3MF export fails | Run `export_3mf.py` on the STEP file. If STEP is valid but 3MF fails, this is a tessellation issue — check Manifold validation. |
| Preview has triangle mesh lines | You're rendering from STL. Render from STEP instead. |
