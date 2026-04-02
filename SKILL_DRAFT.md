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
- **UPDATE THE SPEC** to declare every new feature:
  ```python
  spec = create_spec(
      "Part name", width=W, depth=D, height=H,
      material="PLA", min_wall_mm=2.0,
      features=[
          {"type": "hole", "name": "M4 mount", "diameter": 4.3, "position": [10, 15]},
          {"type": "pocket", "name": "battery slot", "width": 15.1, "depth": 51.0},
          {"type": "slot", "name": "cable channel", "width": 5.0, "probe_z": 8.0},
      ],
      components=[
          {"name": "AA battery", "length": 50.5, "width": 14.5, "height": 14.5, "clearance_mm": 0.3},
      ],
  )
  ```
  **Every measurable feature MUST be declared.** Empty features array at Phase 2 is always wrong.

  **Feature type guide:**
  - `"slot"` — closed gap with material on BOTH sides. Validator probes cross-section width.
  - `"pocket"` — open cavity, trough, recess. Validator checks component fit envelope.
  - `"hole"` — circular through-hole or blind hole. Validator matches by diameter.
  - `"channel"` — long continuous groove. Validator checks cross-section profile.
  - `"pattern"` — array of repeated features (ventilation grid, hole pattern). Declare count, spacing, individual feature dimensions.

- **Use construction-time checks** inline:
  ```python
  from bd_debug_helpers import verify_result
  before_vol = part.part.volume
  with Locations((x, y)):
      Hole(radius=r)
  verify_result(part.part, before_vol, "mounting hole")
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
- Clearance between parts: base exterior dims + 2×clearance = lid interior dims.
- Export each part as a separate 3MF.
- For snap-fit lids: cantilever beam length = 4× beam thickness, deflection 0.5-1.0mm for PLA.

### Complex Part Management
For parts with >6 port cutouts or >10 features:
- Split Phase 2 into sub-phases: 2a (large features), 2b (small ports), 2c (mounting/pattern features).
- Each sub-phase gets its own spec update, validation, and checkpoint.
- This prevents context exhaustion on complex enclosures (e.g., Pi cases with 7+ port cutouts).

## Post-Export Validation (every phase)

Run ALL FOUR tools after every STEP export:
```bash
python scripts/validate_geometry.py part.step        # Spec vs reality
python scripts/check_printability.py part.step       # FDM constraints
python scripts/validate_manifold.py part.step        # Watertight mesh check
python scripts/render_cross_sections.py part.step    # Dimensioned sections
```

- **FAIL** = fix before showing the user.
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

## Export Format: 3MF over STL

Default to **3MF export**. 3MF encodes units (no inches-vs-mm ambiguity), supports color/material metadata, uses compact binary. All major slicers (OrcaSlicer, PrusaSlicer, Bambu Studio) import 3MF natively.

Also export STEP as archival format — retains full B-rep parametric information.

## FDM Print Defaults

| Parameter | PLA | PETG | TPU | ABS |
|-----------|-----|------|-----|-----|
| Wall thickness | 2.0mm | 2.0mm | 3.0mm | 2.0mm |
| Extra clearance | +0.0mm | +0.1mm | +0.2mm | +0.0mm |
| Bottom chamfer | 0.5mm | 0.5mm | 0.5mm | 0.5mm |
| Hole clearance | +0.3mm | +0.4mm | +0.5mm | +0.3mm |
| Max bridge span | 20mm | 15mm | 10mm | 20mm |
| Max overhang | 45° | 45° | 40° | 45° |
| Min feature size | 0.8mm | 0.8mm | 1.0mm | 0.8mm |

## Common Feature Patterns

### Retention slots (cable clips, card holders)
Narrow opening (component width + 0.3mm clearance), wider pocket below (component width + 1.5mm). The narrow opening catches the component; the wider pocket provides clearance for insertion from the side.

### Snap-fit clips (lid attachment)
Cantilever beam: length = 4× thickness, deflection = 0.5-1.0mm for PLA. Catch overhang = 0.3-0.5mm. Print beam along layer lines for maximum flex.

### Screw bosses
Hole diameter = screw + 0.3mm (self-tapping) or screw + 0.5mm (clearance). Boss OD = screw × 2.5. Countersink: 90° included angle, head diameter + 0.5mm.

### Ventilation grids
Declare as `"type": "pattern"` in spec with: slot_width, slot_length, count_x, count_y, spacing. Minimum bar width between slots = 1.2mm for PLA.

### Press-fit holes
Hole diameter = pin diameter - 0.1mm (interference fit for PLA). Test print a single hole first.

## Parameter Table Format

```
┌─────────────────────┬─────────┬──────────────────────┐
│ Parameter           │ Value   │ Notes                │
├─────────────────────┼─────────┼──────────────────────┤
│ Overall width       │ 60mm    │                      │
│ Wall thickness      │ 2.0mm   │ Min 1.2mm            │
│ Corner radius       │ 3.0mm   │                      │
│ Hole diameter       │ 4.3mm   │ M4 + 0.3mm clearance │
└─────────────────────┴─────────┴──────────────────────┘
```

"Want to adjust any of these? Just say 'make it 5mm taller' or 'move the hole left 10mm' and I'll regenerate."
