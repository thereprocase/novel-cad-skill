# Novel CAD Skill Architecture

## 1. Design Rationale

The current `cad-skill` works. Six rounds of testing proved the checkpoint/validator/cross-section pipeline catches real bugs. But it's built on CadQuery, which has three structural problems that get worse as parts get more complex:

1. **Implicit workplane state** — `.center()` permanently mutates the origin. `.faces(">Z").workplane()` inherits the shifted origin via `ProjectedOrigin`. This causes feature drift that `debug_workplane()` can detect but not prevent. build123d's context managers (`BuildPart`, `BuildSketch`, `BuildLine`) scope state explicitly. When the `with` block ends, the context is gone.

2. **String selectors** — CadQuery's `.faces(">Z")`, `.edges("|Z")` are opaque strings parsed at runtime. Typos fail silently or select wrong geometry. build123d's `.faces().sort_by(Axis.Z).last` is Python attribute access — the IDE catches typos, and `.filter_by()` chains are composable.

3. **Silent boolean failures** — CadQuery's `.cut()` returns unchanged geometry when the tool doesn't intersect the body. We built `verify_boolean()` as a bandaid. build123d raises exceptions on degenerate booleans, and its algebra mode (`part + feature`, `part - cut`) makes the operation intent explicit.

The novel skill keeps everything that works (checkpoint gates, spec capture, cross-section rendering, printability checks) and replaces the geometry engine underneath.

---

## 2. File Structure

```
~/.claude/skills/novel-cad-skill/
├── SKILL.md                          # Workflow doc (Claude reads this)
├── BUILD123D_REFERENCE.md            # API patterns, gotchas, migration guide
├── requirements.txt                  # build123d, manifold3d, trimesh, etc.
├── scripts/
│   ├── setup_env.sh                  # pip install + verify imports
│   ├── render_preview.py             # Port from cad-skill (STEP renderer)
│   ├── render_cross_sections.py      # Port from cad-skill (spec-driven slicing)
│   ├── validate_geometry.py          # Spec-vs-reality checker (adapted for build123d)
│   ├── check_printability.py         # FDM printability (mostly unchanged)
│   ├── validate_manifold.py          # NEW — Manifold mesh validation layer
│   ├── export_3mf.py                 # NEW — 3MF export with metadata
│   ├── bd_debug_helpers.py           # NEW — build123d equivalents of cq_debug_helpers
│   └── fallback_router.py            # NEW — build123d → CadQuery → OpenSCAD chain
├── lib/
│   ├── spec_format.py                # Intent capture (evolved from cad-skill)
│   ├── context_budget.py             # NEW — complexity estimator for context management
│   └── gate_enforcer.py              # NEW — programmatic checkpoint enforcement
└── tests/
    ├── test_manifold_validation.py
    ├── test_export_3mf.py
    ├── test_fallback_router.py
    └── fixtures/
        ├── good_box.step
        ├── good_box.spec.json
        ├── non_manifold.stl
        └── complex_enclosure.step
```

### What moves, what's new, what's gone

| Current cad-skill file | Novel skill disposition |
|------------------------|----------------------|
| `SKILL.md` | Rewrite. Same checkpoint structure, new engine, new gate enforcement |
| `CADQUERY_REFERENCE.md` | Replace with `BUILD123D_REFERENCE.md` |
| `lib/spec_format.py` | Evolve. Add `"pattern"` feature type, `"sub_phase"` field, 3MF metadata |
| `lib/cq_text_utils.py` | Drop. build123d text handling is different enough to warrant inline patterns |
| `scripts/render_preview.py` | Port. The OCC tessellation path is engine-agnostic (both use OCCT underneath) |
| `scripts/render_cross_sections.py` | Port. Same trimesh slicing pipeline; STEP loading is unchanged |
| `scripts/validate_geometry.py` | Adapt. Replace CadQuery import/intersection calls with build123d equivalents |
| `scripts/check_printability.py` | Mostly unchanged. Mesh-based analysis doesn't care about the modeling engine |
| `scripts/cq_debug_helpers.py` | Replace with `bd_debug_helpers.py`. build123d needs different checks |
| `scripts/test_validators.py` | Port to pytest, add manifold/3MF/fallback tests |

---

## 3. build123d Integration

### Why build123d over CadQuery

Both sit on the same OpenCASCADE kernel (OCP). build123d is a higher-level wrapper with three modes:

1. **Builder mode** (recommended for complex parts):
   ```python
   from build123d import *

   with BuildPart() as part:
       with BuildSketch() as sk:
           Rectangle(width, depth)
       Extrude(amount=height)
       Fillet(*part.edges().filter_by(Axis.Z), radius=r_ext)
       Shell(*part.faces().sort_by(Axis.Z).last, thickness=-wall)
   ```
   The `with` block scopes all state. When it exits, the sketch/part context is finalized. No origin drift.

2. **Algebra mode** (recommended for simple parts and boolean clarity):
   ```python
   from build123d import *

   box = Box(width, depth, height)
   pocket = Pos(x, y, z) * Box(pw, pd, ph)
   result = box - pocket
   ```
   Fully stateless. Each expression produces a new object. `Pos()`, `Rot()`, `Loc()` are explicit transforms.

3. **Sketch mode** (for 2D profiles):
   ```python
   with BuildSketch() as profile:
       with BuildLine():
           Line((0, 0), (10, 0))
           Line((10, 0), (10, 20))
           Line((10, 20), (0, 20))
       MakeFace()
   ```

### BUILD123D_REFERENCE.md scope

The reference doc should cover:

- **Mode selection guide**: Builder for enclosures/trays (>3 features). Algebra for brackets/mounts (<3 features). Never mix modes in the same part.
- **Selector API**: `.faces().sort_by(Axis.Z)`, `.edges().filter_by(Axis.Z)`, `.filter_by(GeomType.CIRCLE)`. Show CadQuery equivalents for migration.
- **Location transforms**: `Pos(x, y, z)`, `Rot(rx, ry, rz)`, `Loc(pos, rot)`. Replaces CadQuery's `.transformed(offset=..., rotate=...)`.
- **Text handling**: `Text("label", font_size, align=(Align.CENTER, Align.CENTER))` in a BuildSketch context. Deboss via `Extrude(amount=-depth, mode=Mode.SUBTRACT)`.
- **Shell gotchas**: Same OCCT kernel = same shell-before-fillet ordering issues. Document the same workarounds.
- **Export**: `export_step(part, "file.step")`, `export_stl(part, "file.stl")`. Note: build123d export functions are module-level, not method calls.
- **OCP interop**: build123d objects expose `.wrapped` for raw OCC access. CadQuery code can coexist via `cq.Shape(bd_part.wrapped)`.
- **Known traps**:
  - `Extrude` direction defaults to sketch normal, not always +Z. Always verify with bounding box after first extrude.
  - `Fillet` and `Chamfer` take edge lists, not selector strings. Build the list explicitly.
  - `Mode.SUBTRACT` inside a `BuildPart` context is equivalent to CadQuery's `.cut()` — but it applies immediately within the context, not lazily.
  - Revolve on non-XY planes: same OCCT coordinate mapping trap as CadQuery. The reference must carry forward the warning from rounds 5-6.

### CadQuery coexistence

build123d and CadQuery share OCP. A build123d part can be wrapped in a CadQuery Workplane for operations where CadQuery has better support (plate packing with `BRep_Builder`, compound assembly). The bridge:

```python
import cadquery as cq
from build123d import *

bd_part = Box(50, 30, 10)
cq_shape = cq.Shape(bd_part.wrapped)
```

This is the escape hatch, not the primary path. The reference should document it but discourage routine use.

---

## 4. Manifold Validation Layer

### Purpose

A mesh can export as valid STL (all triangles present, normals consistent) and still be non-manifold (self-intersecting faces, T-junctions, inverted normals on internal surfaces). Non-manifold meshes cause slicer failures, infill leaks, and unprintable geometry. The current skill has no mesh topology validation beyond trimesh's `is_watertight` check.

### Implementation: `validate_manifold.py`

```
validate_manifold.py <input.step|stl> [--fix] [--output fixed.stl]
```

**Pipeline:**

1. Load geometry (STEP via OCC tessellation, or STL direct).
2. Pass to Manifold's `from_mesh()` constructor. If the constructor succeeds, the mesh is manifold. If it raises, the mesh has topology errors.
3. On success: report PASS with vertex/face count and genus.
4. On failure with `--fix`: attempt Manifold's `as_original()` repair. Re-validate. Report PASS/FAIL with repair delta (vertices added/removed, faces modified).
5. On failure without `--fix`: report FAIL with error description.

**Where it fits in the pipeline:**

```
[build123d generates STEP]
    → validate_geometry.py (spec vs. reality)
    → check_printability.py (FDM checks)
    → validate_manifold.py (mesh topology)     ← NEW
    → export_3mf.py (final export)             ← NEW
    → render_cross_sections.py (visual review)
    → render_preview.py (3D preview)
```

Manifold validation runs AFTER printability (which needs a mesh anyway — share the tessellation) and BEFORE 3MF export (don't package a broken mesh).

**Dependency:** `manifold3d` (pip installable, has Windows wheels). Falls back to trimesh's `is_watertight` + `is_volume` if manifold3d is unavailable.

### Integration with spec

Add a `"manifold_check"` field to the spec (default: `true`). For parts with intentional non-manifold geometry (e.g., zero-thickness alignment planes used as slicer color-change markers), set to `false` with a reason string.

---

## 5. Fallback Chain

### When build123d fails

build123d and CadQuery share the same OCCT kernel, so kernel-level failures (degenerate fillets, shell failures on complex topology) affect both equally. The fallback chain is for API-level failures:

```
build123d (primary)
    ↓ on ImportError or API failure
CadQuery (fallback 1 — same kernel, different API)
    ↓ on kernel-level failure
OpenSCAD (fallback 2 — CSG-only, different kernel)
```

### Implementation: `fallback_router.py`

The router doesn't run automatically. It's a decision tool Claude consults when a build123d script fails:

```python
from fallback_router import diagnose_failure, suggest_fallback

diagnosis = diagnose_failure(error, script_source)
# Returns: {"engine": "build123d", "failure_type": "fillet_topology",
#           "recommendation": "cadquery", "reason": "CadQuery's edge selector
#           may handle this edge case differently"}
```

**Failure classification:**

| Failure type | Recommendation | Reason |
|---|---|---|
| `ImportError` (build123d not installed) | CadQuery | Same kernel, different wrapper |
| Fillet/chamfer topology error | CadQuery | Different edge selection may avoid the degenerate case |
| Shell failure | CadQuery | Try different face selection order |
| Boolean kernel crash (SIGSEGV) | OpenSCAD | Different kernel entirely |
| Loft/sweep failure | CadQuery | build123d loft API is less mature |
| CSG-only geometry (no fillets, no shell) | OpenSCAD | Simpler, faster, no OCC overhead |

**OpenSCAD integration:**

OpenSCAD scripts are text-based CSG. Claude generates `.scad` files, runs `openscad -o part.stl part.scad` for export. No Python API needed. The fallback_router generates a template `.scad` from the spec's dimensions and feature list.

**Key constraint:** The fallback chain does NOT auto-retry. Claude reads the diagnosis, decides whether to try a different engine, and writes a new script in the fallback engine's language. The router provides the diagnosis and template — not automatic re-execution.

---

## 6. Spec Capture 2.0

### What to keep from current `spec_format.py`

The core structure works:

- `part_name`, `overall_dimensions`, `material`, `min_wall_mm` — unchanged
- `components` with `length/width/height/clearance_mm` — unchanged
- `features` with type-specific validation — keep and extend
- `validate_spec()` / `write_spec()` / `load_spec()` API — unchanged
- Material-specific clearance defaults (`_EXTRA_CLEARANCE`) — unchanged

### What to change

**1. New feature type: `"pattern"`**

Round 6 (Pi case) exposed the gap: arrays of identical features (ventilation slots, screw hole grids) have no spec representation. Each slot in a 20-slot vent grid would need its own feature entry.

```python
{"type": "pattern", "name": "ventilation grid",
 "element": {"type": "slot", "width": 2.0, "length": 15.0},
 "arrangement": "linear",  # or "grid", "radial"
 "count": 20, "pitch": 3.0,
 "position": [10.0, 20.0, 0.0],
 "direction": [1.0, 0.0, 0.0]}
```

The validator checks one representative element, then verifies count by detecting repeated geometry at the expected pitch.

**2. Sub-phase support**

Round 6 died from context exhaustion on a 12.8KB CadQuery script with 7+ port cutouts. The spec needs to support phase splitting:

```python
spec = create_spec("Pi 4 Case", ...,
    sub_phases={
        "2a": ["usb_c_cutout", "hdmi_cutout_1", "hdmi_cutout_2"],
        "2b": ["usb_a_cutout", "ethernet_cutout", "audio_cutout"],
        "2c": ["mounting_standoff_1", "mounting_standoff_2",
               "mounting_standoff_3", "mounting_standoff_4"],
    }
)
```

Each sub-phase gets its own script, export, and validation cycle. The spec tracks which features belong to which sub-phase. Gate enforcement (section 8) checks that only the current sub-phase's features are present.

**3. 3MF metadata fields**

```python
spec = create_spec("Pi 4 Case", ...,
    export_format="3mf",           # default changes from "step" to "3mf"
    color=[0.2, 0.6, 0.8, 1.0],   # RGBA for 3MF color
    units="millimeter",            # explicit for 3MF header
    description="Raspberry Pi 4 Model B snap-fit case, PETG",
)
```

**4. Engine field**

```python
spec = create_spec("Pi 4 Case", ...,
    engine="build123d",  # or "cadquery", "openscad"
)
```

Tracks which engine generated the geometry. The validator uses this to choose the right import path.

**5. Printability threshold: WARN band for wall thickness**

Round 4 Frodo review noted 1.2mm microSD dividers at exactly the threshold. The current `check_printability.py` already has a 70% WARN band, but the spec should let users set an explicit warn threshold:

```python
spec = create_spec("SD tray", ...,
    min_wall_mm=1.2,
    warn_wall_mm=1.5,  # WARN if wall < 1.5mm, FAIL if < 1.2mm
)
```

---

## 7. Cross-Section Renderer

### Port, don't rewrite

The cross-section renderer (`render_cross_sections.py`) is engine-agnostic. It:

1. Loads STEP via CadQuery → tessellates to trimesh
2. Slices with `mesh.section()` (trimesh, not OCC)
3. Rasterizes polygons with PIL
4. Annotates with matplotlib

Steps 2-4 don't touch the modeling engine at all. Step 1 needs a minor change: try build123d import first, fall back to CadQuery:

```python
def _load_mesh(step_path):
    try:
        from build123d import import_step
        shape = import_step(step_path)
        # tessellate via OCC (same path as before, just different import)
        ...
    except ImportError:
        import cadquery as cq
        shape = cq.importers.importStep(step_path)
        ...
```

The rest of the renderer — slicing, dimensioning, scale bars, visual theme — ports unchanged.

### Enhancement: automatic feature-driven cuts

Currently the renderer reads the spec for smart cut locations but falls back to 4 evenly-spaced sections. The novel skill should make feature-driven cuts the default:

For every feature in the spec with a `position` or `probe_z`, generate a cut at that location. For `"pattern"` features, cut through the first element and the last element. This ensures every declared feature gets at least one cross-section verification.

Minimum sections per checkpoint: 3 (unchanged). But with full spec capture, a typical Phase 2 part with 5 features should generate 5+ feature-specific sections plus 3 general sections = 8 total. This matches the Round 5 pattern (8 sections at Phase 2) that Frodo approved.

---

## 8. Checkpoint Workflow & Gate Enforcement

### The problem with text-based gates

The current SKILL.md uses bold text and blockquotes to enforce gates:

> **GATE: Do not proceed to the next phase until the user explicitly approves.**

This works when Claude reads SKILL.md carefully. It fails when:
- Context is getting full and Claude skims instructions
- The agent is in a "flow state" and skips the pause
- Multiple agents are coordinating and one assumes the other handled the gate

Round 1 and Round 3 both had gate violations. Rounds 4-6 held, but that's agent behavior, not enforcement.

### Programmatic gate enforcement: `gate_enforcer.py`

The gate enforcer is a state machine persisted to disk alongside the spec:

```python
from gate_enforcer import GateEnforcer

gate = GateEnforcer("pi_case")
gate.begin_phase("phase_1")           # creates .gate.json
# ... build geometry, run validators ...
gate.record_validation("validate_geometry", passed=True)
gate.record_validation("check_printability", passed=True)
gate.record_validation("validate_manifold", passed=True)
gate.record_cross_sections(["section_1.png", "section_2.png", "section_3.png"])

# This BLOCKS until called — Claude must explicitly invoke it
gate.request_approval("phase_1")      # prints: "GATE: Phase 1 complete. Show
                                      # preview + cross-sections to user and
                                      # wait for explicit approval."

# After user approves:
gate.approve("phase_1", approved_by="user")
gate.begin_phase("phase_2")           # only succeeds if phase_1 is approved
```

**State file: `.gate.json`**

```json
{
  "part_name": "pi_case",
  "phases": {
    "phase_1": {
      "status": "approved",
      "validations": {
        "validate_geometry": {"passed": true, "timestamp": "..."},
        "check_printability": {"passed": true, "timestamp": "..."},
        "validate_manifold": {"passed": true, "timestamp": "..."}
      },
      "cross_sections": ["section_1.png", "section_2.png", "section_3.png"],
      "approved_by": "user",
      "approved_at": "..."
    },
    "phase_2": {
      "status": "in_progress",
      "validations": {}
    }
  }
}
```

**Enforcement rules:**

1. `begin_phase(N)` raises if phase N-1 is not `"approved"`.
2. `request_approval(N)` raises if any required validation has `passed=False`.
3. `request_approval(N)` raises if `cross_sections` has fewer than 3 entries.
4. `approve(N)` can only be called after `request_approval(N)`.

The gate enforcer doesn't prevent Claude from writing code — it prevents Claude from exporting and moving on without completing the validation + approval cycle.

**Sub-phase gates:**

For complex parts with sub-phases (section 6):

```python
gate.begin_phase("phase_2a")
# ... build large cutouts ...
gate.request_approval("phase_2a")
gate.approve("phase_2a", approved_by="user")
gate.begin_phase("phase_2b")          # requires 2a approved
```

### SKILL.md gate language (still needed)

The programmatic enforcer is the backstop. SKILL.md still needs gate language because Claude reads SKILL.md before writing any code. The language should be more directive:

```markdown
### GATE PROTOCOL

After completing each phase:
1. Run `gate.record_validation()` for all three validators
2. Run `gate.record_cross_sections()` with all section PNGs
3. Call `gate.request_approval()` — this prints the gate message
4. STOP. Show the preview, cross-sections, and validator results to the user.
5. Wait for the user to say "approved" or give corrections.
6. Call `gate.approve()` only after explicit user approval.
7. Only then call `gate.begin_phase()` for the next phase.

Skipping any step raises a RuntimeError. The gate enforcer is not optional.
```

---

## 9. Context Management

### The problem

Round 6 (Pi case) exhausted context at Phase 2 → Phase 3. The script was 12.8KB of CadQuery with 7+ port cutouts. Each phase carries forward the full script from the previous phase, plus validator output, plus cross-section descriptions, plus the conversation history.

Context exhaustion is the ceiling on part complexity. The current skill has no strategy for it.

### Strategy 1: Sub-phase decomposition (spec-driven)

Complex parts split Phase 2 into sub-phases (section 6). Each sub-phase:
- Starts from the previous sub-phase's STEP export (not from the script text)
- Writes a new, shorter script that imports the STEP and adds features
- Gets its own validation cycle and gate

```python
from build123d import *

# Phase 2b: small port cutouts
# Imports the STEP from Phase 2a (large cutouts already applied)
base = import_step("phase2a_features.step")

with BuildPart() as part:
    Add(base)
    # ... add only phase 2b features ...
```

This bounds each script to ~3-5 features regardless of total part complexity.

### Strategy 2: Complexity estimator (`context_budget.py`)

Before starting a part, estimate context cost:

```python
from context_budget import estimate_complexity

estimate = estimate_complexity(spec)
# Returns:
# {
#   "feature_count": 12,
#   "estimated_script_tokens": 4200,
#   "estimated_phases": 5,        # including sub-phases
#   "sub_phase_split": {
#     "2a": ["usb_c", "hdmi_1", "hdmi_2"],
#     "2b": ["usb_a", "ethernet", "audio"],
#     "2c": ["standoff_1", "standoff_2", "standoff_3", "standoff_4"],
#   },
#   "risk": "high",               # "low" (<6 features), "medium" (6-10), "high" (>10)
#   "recommendation": "Split Phase 2 into 3 sub-phases. Import STEP between sub-phases."
# }
```

**Heuristics:**

| Feature count | Risk | Action |
|---|---|---|
| 1-5 | Low | Standard 3-phase workflow |
| 6-10 | Medium | Split Phase 2 into 2 sub-phases |
| 11+ | High | Split Phase 2 into ceil(N/4) sub-phases |
| Port cutouts | +2 each | Port cutouts are verbose (position, rotation, dimensions) |
| Pattern features | +1 total | Patterns are compact (one element + array params) |

**SKILL.md guidance:**

```markdown
### Context Management

Before Phase 1, run `estimate_complexity(spec)`. If risk is "medium" or "high":
1. Present the sub-phase split to the user for approval.
2. Each sub-phase imports the previous sub-phase's STEP — do NOT carry forward script text.
3. Each sub-phase gets its own gate approval.

For ALL parts, regardless of complexity:
- Import STEP at the start of each phase (not the script text from the prior phase).
- Keep scripts under 200 lines. If a script exceeds 200 lines, split it.
- Delete intermediate STEP files after the final export (keep only final + per-phase exports).
```

### Strategy 3: STEP-as-checkpoint (always)

Even for simple parts, each phase should start by importing the previous phase's STEP rather than carrying forward the Python script:

```python
# Phase 2 — starts from Phase 1's exported STEP
from build123d import *

base = import_step("phase1_base.step")

with BuildPart() as part:
    Add(base)
    # Phase 2 features only
    ...
```

This has two benefits:
1. The Phase 1 script text is not in context during Phase 2.
2. If Phase 1 was generated by a different agent (or a previous conversation), Phase 2 still works.

The downside: importing STEP loses parametric history. The parameters from Phase 1 must be re-declared (or read from the spec) in Phase 2. This is acceptable because the spec is the source of truth for dimensions, not the script.

---

## 10. 3MF Export

### Why 3MF over STL

STL is a bag of triangles with no metadata. 3MF carries:
- **Units** (mm, inches) — no more "is this in mm or inches?" at the slicer
- **Color** — per-object color for multi-material prints
- **Metadata** — part name, material, author, print settings
- **Multiple objects** — plate packing in a single file
- **Guaranteed manifold** — the 3MF spec requires manifold meshes

### Implementation: `export_3mf.py`

```
export_3mf.py <input.step> <output.3mf> [--spec part.spec.json] [--color R G B A]
```

**Pipeline:**

1. Load STEP via OCC tessellation (same as render_preview.py).
2. Run Manifold validation (import from `validate_manifold.py`).
3. Build 3MF XML structure with metadata from spec:
   - Part name from `spec.part_name`
   - Material from `spec.material`
   - Color from `spec.color` or default PLA grey
   - Units: always millimeters
4. Write 3MF (ZIP archive with XML + mesh data).

**Library:** `lib3mf` (official 3MF Consortium library, pip installable) or `trimesh.exchange.threedmf` (simpler, fewer features). Start with trimesh; switch to lib3mf if we need multi-material or build plate metadata.

**Fallback:** If 3MF export fails (library issues, complex geometry), fall back to STEP + STL dual export with a WARN. Never block delivery on 3MF failure.

### Default export format

The novel skill defaults to 3MF for final delivery (Phase 3). Intermediate phases still export STEP (lossless B-rep for re-import). The export chain:

```
Phase 1: STEP only (for Phase 2 import)
Phase 2: STEP only (for Phase 3 import)
Phase 3: STEP + 3MF (STEP for archival, 3MF for printing)
         + STL if user requests or 3MF fails
```

### Multi-object plates

For plate packing (Phase 4), 3MF's multi-object support replaces the compound STEP/STL approach:

```python
# Each part becomes a 3MF object with its own transform
for item in plate:
    add_object(archive, item.mesh, transform=item.placement, name=item.name)
```

One 3MF file per plate, all objects correctly positioned. The slicer imports it as a pre-arranged plate.

---

## 11. Validator Pipeline (Adapted)

### Full pipeline order

```
1. gate.begin_phase(N)
2. Claude writes build123d script
3. Script runs, exports STEP
4. validate_geometry.py part.step          — spec vs. reality
5. check_printability.py part.step         — FDM checks (mesh-based)
6. validate_manifold.py part.step          — mesh topology
7. render_cross_sections.py part.step      — visual verification
8. render_preview.py part.step preview.png — 3D preview
9. gate.record_validation(...)             — all three validators
10. gate.record_cross_sections(...)        — all section PNGs
11. gate.request_approval(N)               — STOP and wait
12. [user reviews and approves]
13. gate.approve(N)
14. [Phase 3 only] export_3mf.py part.step final.3mf
```

### validate_geometry.py changes

**Import path:** Try build123d first, fall back to CadQuery:

```python
def _load_step(step_path):
    try:
        from build123d import import_step
        return import_step(step_path)
    except ImportError:
        import cadquery as cq
        return cq.importers.importStep(step_path)
```

**Bounding box:** build123d's `BoundBox` has the same `xmin/xmax/xlen` interface. Adapter may be needed if attribute names differ.

**Cross-section measurement:** The current `_cross_section_at_z()` uses CadQuery's `.intersect()` with a thin slab. build123d equivalent:

```python
from build123d import *

def _cross_section_at_z(shape, z, slab_thickness=0.2):
    slab = Pos(0, 0, z) * Box(1e6, 1e6, slab_thickness)
    section = shape & slab  # algebra mode intersection
    bb = section.bounding_box()
    if bb.size.X < 0.001 and bb.size.Y < 0.001:
        return None
    return section
```

**Hole detection:** Same OCC `TopExp_Explorer` path — engine-agnostic.

### check_printability.py changes

Minimal. The entire script works on trimesh meshes loaded from STEP/STL. The STEP → trimesh tessellation path is shared with the renderer. Only the STEP loading function needs the build123d/CadQuery import fallback.

### bd_debug_helpers.py

Replaces `cq_debug_helpers.py`. build123d has better built-in error handling (exceptions on degenerate booleans), so the helpers are lighter:

```python
def verify_boolean(before, after, operation="cut", label=""):
    """Check that a boolean operation changed the geometry."""
    vol_before = before.volume
    vol_after = after.volume
    if abs(vol_after - vol_before) < 0.001:
        raise RuntimeError(
            f"[Boolean {label}] {operation} produced NO change! "
            f"Volume: {vol_before:.2f} -> {vol_after:.2f}"
        )
    return after

def verify_bounds(body, feature, label="", tolerance=0.1):
    """Check that a feature stays within the body's bounding box."""
    bb_body = body.bounding_box()
    bb_feat = feature.bounding_box()
    # ... same overflow logic as cq_debug_helpers ...
```

Note: build123d's algebra mode (`part - cut`) already raises on non-intersecting booleans in many cases. `verify_boolean` is the safety net for cases where it doesn't.

---

## 12. Script Template

```python
from build123d import *
import sys
from pathlib import Path

# Skill library imports
sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/scripts"))
sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/lib"))
from bd_debug_helpers import verify_boolean, verify_bounds
from spec_format import create_spec, write_spec
from gate_enforcer import GateEnforcer

# ============================================================
# PARAMETERS
# ============================================================
width = 60.0        # mm
depth = 40.0        # mm
height = 25.0       # mm
wall = 2.0          # mm
r_ext = 3.0         # mm — exterior corner fillet
clearance = 0.3     # mm — FDM clearance

# ============================================================
# SPEC — declare design intent before building geometry
# ============================================================
spec = create_spec(
    "Example box",
    width=width, depth=depth, height=height,
    material="PLA", min_wall_mm=wall,
    engine="build123d",
    features=[
        {"type": "pocket", "name": "main cavity",
         "width": width - 2*wall, "depth": depth - 2*wall},
    ],
)
write_spec(spec, "phase1_base.step")

# ============================================================
# GATE
# ============================================================
gate = GateEnforcer("example_box")
gate.begin_phase("phase_1")

# ============================================================
# MODEL
# ============================================================
with BuildPart() as part:
    Box(width, depth, height)
    Fillet(*part.edges().filter_by(Axis.Z), radius=r_ext)
    Shell(*part.faces().sort_by(Axis.Z).last, thickness=-wall)

result = part.part

# ============================================================
# EXPORT
# ============================================================
export_step(result, "phase1_base.step")
print(f"Exported: {width}x{depth}x{height}mm")
```

---

## 13. Migration Path

The novel skill doesn't replace the current cad-skill overnight. Migration plan:

1. **Phase A: Install and verify** — `setup_env.sh` installs build123d alongside CadQuery. Verify both import. Run existing test fixtures through both engines.

2. **Phase B: Dual-engine testing** — Pick 2-3 parts from the Round 1-6 test suite. Rebuild them with build123d. Compare validator results. Identify build123d-specific gotchas for BUILD123D_REFERENCE.md.

3. **Phase C: Novel skill standalone** — Deploy the novel skill directory. Keep cad-skill as-is (no breaking changes). CLAUDE.md triggers route new CAD requests to novel-cad-skill.

4. **Phase D: Deprecate cad-skill** — After 3+ successful builds with the novel skill, remove cad-skill from CLAUDE.md triggers. Keep the directory for reference.

---

## 14. Open Questions

1. **manifold3d Windows wheels** — Does `pip install manifold3d` work on Windows with Python 3.13? Needs verification during setup_env.sh. Fallback to trimesh-only validation if not.

2. **3MF library choice** — `lib3mf` vs `trimesh.exchange.threedmf`. lib3mf is more capable but heavier. trimesh is already a dependency. Start with trimesh, upgrade if needed.

3. **build123d version pinning** — build123d is actively developed. Pin to a known-good version in requirements.txt. Test before upgrading.

4. **OpenSCAD path on Windows** — The fallback chain needs OpenSCAD on PATH. Document installation in setup_env.sh. Don't make it a hard dependency — most parts won't need it.

5. **Plate packing rewrite** — The bitmap nesting algorithm in the current skill uses CadQuery-specific APIs for compound assembly. Needs porting to build123d or to a pure OCC path. Low priority — plate packing is Phase 4, used rarely.
