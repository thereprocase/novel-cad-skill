---
name: novel-cad-skill
description: "Parametric 3D-printable part design using build123d with automated validation, dimensioned cross-sections, and Manifold mesh verification. Triggers on: STL, STEP, 3MF, 3D printing, enclosure, bracket, mount, case, holder, stand, or any physical object design request."
---

# Novel CAD Skill — build123d + Manifold Validation Pipeline

## Overview

Design 3D-printable parts from conversational descriptions. Uses **build123d** (Python, OCCT kernel) for geometry, **Manifold** for mesh validation, and a four-tool automated checking pipeline that catches mistakes before the user sees them.

**Key difference from the legacy CadQuery skill:** build123d's context managers make scope explicit, its selectors are Pythonic, and Manifold guarantees every exported mesh is watertight. Export format is 3MF (not STL).

## Dependencies

```bash
bash ~/.claude/skills/novel-cad-skill/scripts/setup_env.sh
```

Requires Python 3.10+. Installs build123d, manifold3d, cadquery (fallback), trimesh, matplotlib, shapely, scipy, pillow.

To run any build123d script:
```bash
python <script.py>
```

---

## Workflow — Phased Checkpoints with Mandatory Gates

**NEVER batch the entire model.** Build incrementally. Each phase has a hard gate — do not proceed without explicit user approval.

### Phase 0: Requirements Gathering

- Ask what they're building. Clarify dimensions, tolerances, material (PLA/PETG/TPU/ABS), and printer if known.
- If the part interfaces with a real product (phone, PCB, sensor, connector), **research exact dimensions** from datasheets or manufacturer specs before designing.
- **Spec-vs-intent self-check:** Before writing any code, re-read the user's words. For each requirement, identify what geometry satisfies it:
  - "retention slot" -> narrow opening with wider pocket below
  - "snap-fit" -> cantilever beam with catch
  - "cable clip" -> not an open trough — needs a retention feature
  - "ventilation" -> pattern of slots or holes
  - Map every conversational term to a specific geometric feature. If anything is ambiguous, ask.
- Confirm understanding before generating any code.

### Pre-flight: Environment Check

```bash
python -c "import build123d; print('build123d OK')"
python -c "import manifold3d; print('manifold3d OK')"
python -c "import trimesh; print('trimesh OK')"
python -c "import matplotlib; print('matplotlib OK')"
```
If any fail, run: `bash ~/.claude/skills/novel-cad-skill/scripts/setup_env.sh`

### Phase 1: Base Shape

- Generate a build123d script creating ONLY the primary form — outer shell, main body, base plate.

- **Choose mode** based on part complexity:
  - **Builder mode** (default for most parts) — explicit scope via context managers:
    ```python
    with BuildPart() as part:
        Box(width, depth, height)
        Fillet(*part.edges().filter_by(Axis.Z), radius=r_ext)
    ```
  - **Algebra mode** — for simple parts (1-3 operations) or when Builder context nesting gets unwieldy:
    ```python
    base = Box(width, depth, height)
    base = fillet(base.edges().filter_by(Axis.Z), radius=r_ext)
    ```
  - **Rule of thumb:** >6 features -> Builder mode. 1-3 operations -> Algebra. Complex nested geometry where Builder contexts would be 3+ deep -> Algebra with explicit variables.

- **Spec capture** — immediately after the parameters block, before any geometry:
  ```python
  import sys
  from pathlib import Path
  sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/lib"))
  from spec_format import create_spec, write_spec

  spec = create_spec(
      "Part name",
      width=W, depth=D, height=H,
      material="PLA",
      min_wall_mm=2.0,
      engine="build123d",
  )
  write_spec(spec, "part.step")
  ```
  **Spec scope per phase:** The spec describes ONLY the geometry present in the current phase's export. Phase 1 spec = overall dimensions and material only — no features. Features are added at Phase 2 as they're built.

- Export STEP and run **all four validation tools** (see Post-Export Validation below).
- Render 4-view preview and **mandatory cross-sections** (minimum 4).
- **Show preview, cross-sections, and validator results to the user.** Ask: "Does this base shape and proportion look right?"

> **GATE: Do not proceed to Phase 2 until the user explicitly approves Phase 1.** If the user has not responded, wait. If the user rejects, iterate on this phase until approved. Delivering a finished part without intermediate checkpoint approvals violates the workflow.

### Phase 1.5: Text & Labeling

If the part needs text labels, handle them BEFORE mechanical features (holes, chamfers) because those operations pollute workplane references.

1. **Measure text bounding boxes** empirically — generate text at reference size, measure, compute width/height ratios.
2. **Use absolute positioning** — not face-relative workplanes that drift after operations.
3. **For deboss:** create text solid on a fresh reference plane, then subtract from body.
4. **For emboss:** create text solid, union with body, then intersect with body profile to clip overflow.
5. Render close-up preview and verify text is within bounds before proceeding.

### Phase 2: Features

- Add internal features: holes, slots, pockets, mounting posts, cable routes, fillets, chamfers.

- **Import the previous phase's STEP** — do NOT carry forward the full script text from Phase 1. This keeps context lean:
  ```python
  from build123d import *
  base = import_step("phase1_base.step")
  with BuildPart() as part:
      Add(base)
      # Phase 2 features only
  ```

- **UPDATE THE SPEC** to declare every new feature:
  ```python
  spec = create_spec(
      "Part name", width=W, depth=D, height=H,
      material="PLA", min_wall_mm=2.0,
      engine="build123d",
      features=[
          {"type": "hole", "name": "M4 mount", "diameter": 4.3,
           "position": [10, 15]},
          {"type": "pocket", "name": "battery slot", "width": 15.1,
           "depth": 51.0},
          {"type": "slot", "name": "cable channel", "width": 5.0,
           "probe_z": 8.0, "tolerance": 0.3},
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

  **Every measurable feature MUST be declared.** An empty `features` array at Phase 2 is always wrong — you just added features, declare them. An undeclared hole is an unvalidated hole.

  **Feature type guide:**
  - `"slot"` — closed gap with material on BOTH sides. Validator probes cross-section gap width. Use when the feature has walls on all sides.
  - `"pocket"` — open cavity, trough, or recess. Validator checks component fit envelope. Use for open-top channels, blind pockets, recesses where one side is open.
  - `"hole"` — circular through-hole or blind hole. Validator matches by diameter.
  - `"channel"` — long continuous groove. Validator checks cross-section profile.
  - `"rail"` — raised linear feature. Validator checks cross-section profile.
  - `"pattern"` — array of repeated features. Declare the element type, count, pitch, and individual feature dimensions. See Ventilation Grids below.
  - When in doubt: open on top or one side -> `"pocket"`. Walls on all sides -> `"slot"`.

- **Use construction-time checks** inline after every boolean:
  ```python
  sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/scripts"))
  from bd_debug_helpers import verify_boolean

  before_vol = part.part.volume
  with Locations((x, y)):
      Hole(radius=r)
  verify_boolean(before_vol, part.part.volume, "mounting hole")
  ```

- Export STEP, run all four validation tools, render preview + cross-sections.
- **Show everything to the user.** Ask: "Are the features positioned correctly? Anything to add or move?"
- Iterate until features are approved.

> **GATE: Do not proceed to Phase 3 until the user explicitly approves Phase 2.** If the user has not responded, wait. If the user rejects, iterate on this phase until approved.

> **Revision priority:** When the user gives multiple corrections, fix **functional mismatches first** (wrong feature type, missing features, incorrect dimensions for interfacing parts), then **aesthetic issues** (depth, fillet radius, proportions). A part with the right features at wrong proportions is closer to done than a part with wrong features at right proportions.

### Phase 3: Print Optimization & Delivery

- Apply print-friendly adjustments: chamfer bottom edges (not fillet — fillets need supports), check overhang angles, ensure wall thickness meets material minimums.
- Export final **STEP + 3MF** (3MF preferred over STL).
- Run all four validation tools. Fix any FAILs.
- Run the self-review checklist for anything scripts can't check.
- Show final preview, cross-sections, and validator results to the user.
- Present a **parameter table** listing all key dimensions (see format below).

> **GATE: Do not deliver the final part without user approval of Phase 3.** If the user has not responded, wait. If the user rejects, iterate on this phase until approved.

---

## Complex Part Management

For parts with >6 port cutouts or >10 total features (e.g., Raspberry Pi case with 7+ ports, standoffs, ventilation):

1. **Split Phase 2 into sub-phases:**
   - **Phase 2a:** Large structural features (main cavities, large port cutouts)
   - **Phase 2b:** Small ports and holes (connectors, screw holes)
   - **Phase 2c:** Pattern features (ventilation grids, mounting arrays)

2. **Each sub-phase imports the previous sub-phase's STEP:**
   ```python
   base = import_step("phase2a_large_ports.step")
   with BuildPart() as part:
       Add(base)
       # Phase 2b small ports only
   export_step(part.part, "phase2b_small_ports.step")
   ```

3. **Each sub-phase gets its own validation and user checkpoint.** The gate protocol applies to each sub-phase, not just the full phase.

4. **Why:** The Pi case (Round 6) exhausted agent context before completing Phase 3. A 12.8KB script with 7+ port cutouts is too much state to carry. Importing STEP between sub-phases resets the script context while preserving geometry.

---

## Multi-Part Assemblies (Base + Lid)

For parts with lids, caps, or mating components:

1. **Design the base FIRST** through full Phases 1-3. Get user approval.
2. **Then design the mating part** as a separate build with its own Phase 1-3 cycle.
3. **Dimensional relationships:**
   - Lid interior width = base exterior width + 2 x clearance
   - Lid interior depth = base exterior depth + 2 x clearance
   - Lid interior corner radius = base exterior corner radius + clearance (so lid slides over base corners)
   - Lid exterior corner radius = lid interior corner radius + lid wall thickness (concentric arcs)
4. **Export each part as a separate 3MF file.** Do not combine into one file.
5. **For snap-fit lids:**
   - Cantilever beam length = 4x beam thickness
   - Deflection = 0.5-1.0mm for PLA
   - Catch overhang = 0.3-0.5mm
   - Print beams along layer lines for maximum flex

---

## Post-Export Validation (every phase, every iteration)

Run ALL FOUR tools after every STEP export, before showing anything to the user:

```bash
python ~/.claude/skills/novel-cad-skill/scripts/validate_geometry.py part.step
python ~/.claude/skills/novel-cad-skill/scripts/check_printability.py part.step
python ~/.claude/skills/novel-cad-skill/scripts/validate_manifold.py part.step
python ~/.claude/skills/novel-cad-skill/scripts/render_cross_sections.py part.step
```

### Validator behavior

- **FAIL = fix before showing the user.** The whole point is Claude catches its own mistakes.
- **WARN = OK to show.** Flag warnings to the user so they can decide.
- `validate_geometry.py` reads `.spec.json` written during spec capture. If there's no spec file, it errors — that's the reminder to write one.
- `check_printability.py` works with or without a spec (falls back to FDM defaults).
- `validate_manifold.py` tessellates the STEP and passes the mesh through Manifold. If the mesh isn't watertight, it fails.
- `render_cross_sections.py` reads the spec for smart cut locations but always produces at least 4 sections even with an empty spec.

### Cross-sections

**Cross-sections are mandatory at every checkpoint, not optional.** This is the most important validation tool for internal geometry.

- **Minimum 4 sections per checkpoint:** XY lower, XY upper, XZ side, YZ front.
- Feature-driven cuts are added on top of the baseline 4 — the renderer uses the spec to place cuts through declared features.
- Show ALL section PNGs to the user alongside the 3D preview.
- For thin parts, shallow slots, and internal cavities, **the cross-sections ARE the review** — the 3D preview only shows the outside.
- Round 3 (headphone hook) had zero cross-sections because the spec declared no features. The renderer's fallback (4 sections at 25/50/75% of each axis) prevents this from happening again.

---

## Fallback Chain

If build123d code generation fails after one retry:

1. **Retry with the other mode** — if Builder mode failed, try Algebra (or vice versa). Same geometry intent, different API style.
2. **Fall back to CadQuery** — same OCCT kernel, different API surface. Change imports and method calls; the entire validation pipeline works unchanged because it operates on STEP files.
3. **Fall back to OpenSCAD** — only for pure CSG parts that need no fillets, chamfers, or B-rep operations. Use Manifold backend (`--backend manifold`) for speed.

**The fallback router** (`scripts/fallback_router.py`) classifies the part:
- Needs fillets, chamfers, lofts, sweeps -> must stay on OCCT (build123d or CadQuery)
- Purely additive/subtractive with no rounds -> OpenSCAD is viable

When falling back, carry the spec and validation pipeline forward. Only the code generation changes.

---

## Builder vs. Algebra Mode — When to Use Which

| Scenario | Recommended Mode | Why |
|----------|-----------------|-----|
| Standard enclosure (box + features) | Builder | Context managers group operations cleanly |
| Simple bracket or adapter plate | Algebra | 1-3 operations, context managers are overhead |
| Part with deeply nested features | Algebra | 3+ nested `with` blocks get confusing |
| Pattern operations (hole arrays) | Builder | `with Locations(...)` is natural in Builder |
| Part requiring explicit variable tracking | Algebra | Each operation returns a named result |
| Fallback after Builder mode fails | Algebra | Stateless — easier to debug |

**Builder mode** uses `with BuildPart() as part:` context. Operations inside the context implicitly contribute to `part`. Good for parts where you want to say "add a box, then on the top face add holes."

**Algebra mode** is stateless. Every operation takes explicit inputs and returns explicit outputs: `result = base - Pos(x,y) * Hole(r)`. Good when you need to name intermediate geometry or the Builder context nesting would exceed 3 levels.

Both modes produce identical OCCT geometry. The choice is purely about code clarity for the LLM.

---

## Self-Review Checklist

After every preview render, check ALL items before showing to the user:

### Automated checks (scripts handle these)
- **Flat bottom** — `check_printability.py`
- **Overhang angles** — `check_printability.py` (prefer chamfer over fillet at bed contact)
- **Wall thickness** — `check_printability.py` + `validate_geometry.py`
- **Bridge spans** — `check_printability.py` (<20mm for PLA)
- **Hole clearance** — `validate_geometry.py` (+0.3mm for FDM)
- **Boolean integrity** — `bd_debug_helpers.py` at construction time
- **Manifold mesh** — `validate_manifold.py`

### Manual checks (visual review of renders/cross-sections)
- **Shape match** — does the geometry match what was requested?
- **Feature completeness** — all holes, slots, cutouts present and visible?
- **Corner wall thinning** — at filleted corners, set `r_int = r_ext - wall` for concentric arcs (uniform wall thickness). If using `shell()`, fillet exterior edges first — shell propagates the radius inward automatically.

If any automated check FAILed, fix it BEFORE showing the preview. If any manual check fails, fix it before proceeding.

---

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

---

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

---

## Common Feature Patterns

### Retention slots (cable clips, card holders)
Narrow opening (component width + 0.3mm clearance), wider pocket below (component width + 1.5mm). The narrow opening catches the component; the wider pocket provides clearance for insertion. In build123d:
```python
# Retention slot profile: narrow opening, wider pocket
with BuildSketch(Plane.XZ) as slot_profile:
    with BuildLine():
        # Narrow opening at top
        Line((0, top), (opening_w/2, top))
        Line((opening_w/2, top), (opening_w/2, top - lip_h))
        # Wider pocket below
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

### Press-fit holes
Hole diameter = pin diameter - 0.1mm (interference fit for PLA). Test print a single hole first.

### Ventilation grids
Declare as `"type": "pattern"` in spec. Minimum bar width between slots = 1.2mm for PLA. In build123d:
```python
with BuildPart() as part:
    # ... base geometry ...
    vent_locs = GridLocations(pitch_x, pitch_y, count_x, count_y)
    with Locations(vent_locs):
        Box(slot_length, slot_width, wall + 0.02, mode=Mode.SUBTRACT)
```
Spec declaration:
```python
{"type": "pattern", "name": "vent grid",
 "element": {"type": "slot", "width": 2.0, "length": 15.0},
 "arrangement": "grid", "count_x": 5, "count_y": 4,
 "pitch_x": 4.0, "pitch_y": 4.0,
 "position": [0.0, 0.0, 0.0]}
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

---

## build123d Script Template

Every generated script should follow this structure:

```python
from build123d import *
import sys
from pathlib import Path

# Construction-time checks
sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/scripts"))
from bd_debug_helpers import verify_boolean

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
                   material="PLA", min_wall_mm=wall, engine="build123d")
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
    Fillet(*part.edges().filter_by(Axis.Z), radius=r_ext)

# Inline boolean verification — use after every subtraction
# before_vol = part.part.volume
# with Locations((x, y)):
#     Hole(radius=r)
# verify_boolean(before_vol, part.part.volume, "mounting hole")

# ============================================================
# EXPORT — STEP primary, 3MF for slicer
# ============================================================
export_step(part.part, "phase1_base.step")
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

## GATE PROTOCOL (summary)

This is the most important section. Round 1 failed because gates were skipped. Rounds 4-6 succeeded because they weren't.

After completing each phase:
1. Run all four validators (validate_geometry, check_printability, validate_manifold, render_cross_sections).
2. Fix any FAILs before proceeding.
3. **STOP.** Show the preview, cross-sections, and validator results to the user.
4. **Wait** for the user to say "approved" or give corrections.
5. Only then proceed to the next phase.

**Showing a "final" part without intermediate checkpoint approvals is never acceptable.** The user must see and approve Phase 1 before Phase 2 begins, and Phase 2 before Phase 3 begins. No exceptions.

---

## Parameter Table Format

After final delivery, present parameters:

```
+---------------------+---------+----------------------+
| Parameter           | Value   | Notes                |
+---------------------+---------+----------------------+
| Overall width       | 60mm    |                      |
| Overall depth       | 40mm    |                      |
| Overall height      | 25mm    |                      |
| Wall thickness      | 2.0mm   | Min 1.2mm            |
| Corner radius       | 3.0mm   |                      |
| Hole diameter       | 4.3mm   | M4 + 0.3mm clearance |
+---------------------+---------+----------------------+
```

"Want to adjust any of these? Just say 'make it 5mm taller' or 'move the hole left 10mm' and I'll regenerate."

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Builder context boolean fails silently | Use `verify_boolean(before_vol, after_vol, name)` after every subtraction. |
| Fillet fails on edge | Try smaller radius or chamfer instead. Some edge combinations confuse OCCT. |
| Shell fails | Reduce fillet radii before shelling. Or: fillet exterior, then shell — shell propagates fillet inward. |
| Two fillet types on same solid fail | Apply one fillet type, then add the second after a cut/union using `.filter_by()` to isolate target edges. |
| Text offset after boolean operations | Use absolute positioning for text, not face-relative workplanes. |
| `import_step()` returns wrong type | Wrap in `Add()` inside a `BuildPart()` context. |
| Manifold validation fails | Check for coincident faces after booleans. Add 0.01mm extra depth to through-cuts. |
| Context exhaustion on complex part | Split Phase 2 into sub-phases. Import STEP between sub-phases. |
| Spec file not found by validator | You forgot `write_spec(spec, "part.step")`. Add it before geometry generation. |
| Feature dimensions mismatch in validator | Check that spec values match parameter values. A mismatch means spec was written with different values than the geometry used. |
| 3MF export fails | Run `export_3mf.py` on the STEP file. If STEP is valid but 3MF fails, this is a tessellation issue — check Manifold validation. |
| Preview has triangle mesh lines | You're rendering from STL. Render from STEP instead. |
