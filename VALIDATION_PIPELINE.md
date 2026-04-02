# Validation Pipeline 2.0 — build123d CAD Skill

Design document for the measurement and validation pipeline of the novel build123d-based CAD skill. This pipeline replaces the CadQuery-era validators with build123d-native equivalents, adds a manifold validation layer, and incorporates lessons from 6 rounds of testing.

---

## Architecture Overview

The pipeline has three layers, executed in order:

```
Layer 1: Construction-Time Checks (inline in build scripts)
   verify_boolean(), verify_feature_bounds(), debug_context()

Layer 2: Manifold Validation (post-construction, pre-export)
   manifold3d mesh check, repair attempt, abort on failure

Layer 3: Post-Export Validation (after 3MF/STEP export)
   validate_geometry.py    — spec vs. reality dimensional checks
   check_printability.py   — FDM-specific structural analysis
   render_cross_sections.py — annotated raster cross-section images
```

Each layer catches a different class of failure. Layer 1 catches programming errors in the build script (silent booleans, workplane drift). Layer 2 catches topological defects (non-manifold edges, self-intersections) that would produce unprintable meshes. Layer 3 catches dimensional drift, printability violations, and provides visual evidence for human review.

---

## 1. Construction-Time Checks for build123d

### The Problem

CadQuery uses a fluent `Workplane` API where booleans are chained methods (`.cut()`, `.union()`). The existing `verify_boolean()` compares before/after `Workplane` objects by volume, face count, and centroid shift.

build123d uses a context manager pattern:

```python
with BuildPart() as part:
    Box(100, 80, 50)
    with Locations((20, 0, 0)):
        Hole(5)
```

There is no explicit before/after — operations mutate the builder's internal state within the context. The `part.part` (or `part.solid`) property gives the current solid at any point.

### Adaptation: `verify_boolean_b3d()`

```python
def verify_boolean_b3d(builder, operation_label: str, snapshot_before=None):
    """Verify that the most recent operation changed the builder's solid.

    Usage:
        with BuildPart() as part:
            Box(100, 80, 50)
            snap = snapshot(part)       # capture state before cut
            Hole(5)
            verify_boolean_b3d(part, "ventilation hole", snap)
    """
```

**Strategy:** Snapshot the builder state (volume, face count, bounding box centroid) *before* the operation. After the operation, compare. Same detection logic as the CadQuery version — volume unchanged + faces unchanged + centroid unchanged = silent failure.

**`snapshot()` helper:**

```python
def snapshot(builder) -> dict:
    """Capture builder state for later comparison."""
    solid = builder.part
    return {
        'volume': solid.volume,
        'face_count': len(solid.faces()),
        'bbox': solid.bounding_box(),
    }
```

**Key difference from CadQuery:** In CadQuery, `.cut()` returns a new object, so comparing `before` and `after` is natural. In build123d, the builder mutates in place. The snapshot must be taken explicitly before the operation. This is slightly more ceremony, but the error message is the same: `RuntimeError` with volume/face deltas.

### `verify_feature_bounds_b3d()`

Same logic as CadQuery version. Compare bounding box of `builder.part` before and after an additive operation. Flag X/Y/Z overflow beyond tolerance.

```python
def verify_feature_bounds_b3d(builder, snapshot_before: dict, label: str, tolerance: float = 0.1):
    bb_after = builder.part.bounding_box()
    bb_before = snapshot_before['bbox']
    # Check each axis for overflow
    ...
```

### `debug_context()`

Replaces `debug_workplane()`. build123d doesn't have explicit workplanes in the same sense — it uses `Plane` objects and location contexts. The debug helper prints the current builder's active plane origin and normal, and optionally asserts expected values.

```python
def debug_context(builder, label: str = "", expected_origin=None, tolerance=0.1):
    """Print the current builder context plane. Raise on drift."""
    plane = builder.exit_workplanes[-1] if builder.exit_workplanes else Plane.XY
    origin = plane.origin.to_tuple()
    normal = plane.z_dir.to_tuple()
    print(f"[CTX {label}] origin=({origin[0]:.2f}, {origin[1]:.2f}, {origin[2]:.2f}) "
          f"normal=({normal[0]:.2f}, {normal[1]:.2f}, {normal[2]:.2f})")
    if expected_origin is not None:
        dist = sum((a - b) ** 2 for a, b in zip(origin, expected_origin)) ** 0.5
        if dist > tolerance:
            raise ValueError(f"[CTX {label}] Origin drift: expected {expected_origin}, got {origin}")
```

### `StepExporter` (debug mode)

Unchanged in concept. Exports intermediate `.stl` snapshots of `builder.part` at each construction step. In build123d:

```python
class StepExporter:
    def export(self, builder, label=""):
        if not self.enabled:
            return
        self.step_num += 1
        solid = builder.part
        solid.export_stl(f"{self.prefix}_{self.step_num:02d}_{label}.stl")
```

---

## 2. Manifold Validation Layer

### Where It Sits

Between construction and export. After `BuildPart()` completes and before `export_3mf()` or `export_step()`. This is the "last chance" to catch topological defects that would produce unprintable geometry.

```
BuildPart() context exits
    |
    v
manifold_check(solid) ── PASS ──> export_3mf() / export_step()
    |
    FAIL
    |
    v
manifold_repair(solid) ── PASS ──> export with warning
    |
    FAIL
    |
    v
ABORT: "Non-manifold geometry cannot be repaired. See diagnostic output."
```

### API

```python
import manifold3d
from build123d import Part

def manifold_check(solid) -> tuple[bool, str]:
    """Check if a solid is manifold using manifold3d.

    Returns (is_manifold, detail_string).
    """
    # Tessellate the build123d solid to vertices + faces
    mesh = solid.tessellate(tolerance=0.01)
    verts = [(v.X, v.Y, v.Z) for v in mesh[0]]
    faces = mesh[1]

    try:
        m = manifold3d.Manifold(
            mesh=manifold3d.Mesh(
                vert_properties=np.array(verts, dtype=np.float32),
                tri_verts=np.array(faces, dtype=np.uint32)
            )
        )
        status = m.status()
        if status == manifold3d.Manifold.Error.NoError:
            return True, f"Manifold OK: {len(verts)} vertices, {len(faces)} triangles"
        else:
            return False, f"Manifold error: {status.name}"
    except Exception as e:
        return False, f"Manifold check failed: {e}"
```

### Error Recovery

```python
def manifold_repair(solid) -> tuple[bool, object, str]:
    """Attempt to repair non-manifold geometry.

    Strategy:
    1. Re-tessellate at finer tolerance (0.001mm)
    2. Run trimesh repair (fill_holes, fix_normals, fix_winding)
    3. Re-check with manifold3d

    Returns (success, repaired_mesh_or_None, detail).
    """
    import trimesh

    mesh = solid.tessellate(tolerance=0.001)
    verts = np.array([(v.X, v.Y, v.Z) for v in mesh[0]])
    faces = np.array(mesh[1])

    tm = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    trimesh.repair.fill_holes(tm)
    trimesh.repair.fix_normals(tm)
    trimesh.repair.fix_winding(tm)

    # Re-check
    try:
        m = manifold3d.Manifold(
            mesh=manifold3d.Mesh(
                vert_properties=tm.vertices.astype(np.float32),
                tri_verts=tm.faces.astype(np.uint32)
            )
        )
        if m.status() == manifold3d.Manifold.Error.NoError:
            return True, tm, "Repaired via trimesh fill_holes + fix_normals"
        else:
            return False, None, f"Repair failed: {m.status().name}"
    except Exception as e:
        return False, None, f"Repair attempt raised: {e}"
```

### Integration Point

The manifold check wraps the export call:

```python
def safe_export(solid, path: str, format="3mf"):
    """Export with mandatory manifold validation."""
    ok, detail = manifold_check(solid)
    print(f"[manifold] {detail}")

    if not ok:
        print("[manifold] Attempting repair...")
        repaired, mesh, repair_detail = manifold_repair(solid)
        print(f"[manifold] {repair_detail}")
        if not repaired:
            raise RuntimeError(
                f"Non-manifold geometry cannot be exported. "
                f"Fix the build script before proceeding.\n{detail}"
            )
        # Export repaired mesh directly
        if format == "3mf":
            mesh.export(path)
        else:
            mesh.export(path)
        print(f"[manifold] WARNING: Exported repaired mesh — original solid had defects")
        return

    # Clean path: solid is manifold, export normally
    if format == "3mf":
        solid.export_3mf(path)
    else:
        solid.export_step(path)
```

### Why manifold3d, not just trimesh.is_watertight

`trimesh.is_watertight` checks edge pairing (every edge shared by exactly 2 faces) but misses self-intersections and degenerate triangles. manifold3d performs a full constructive-solid-geometry-compatible manifold check that catches:
- Self-intersecting faces
- Zero-area triangles
- Non-orientable surfaces
- T-junctions (edges shared by 3+ faces)

These are precisely the defects that cause slicer failures on otherwise "watertight" meshes.

---

## 3. Cross-Section Renderer 2.0

### What to Port

The existing renderer's core pipeline is solid and battle-tested:

1. **Mesh-based slicing** (trimesh `mesh.section()`) — NOT OCC boolean sections. This was a hard-won lesson: OCC `BRepAlgoAPI_Section` produces degenerate edges on near-planar faces. The trimesh approach is reliable.

2. **Rasterization via PIL** — `_rasterize_polygons()` converts shapely polygons to a bitmap at 0.05mm/pixel resolution. This is the measurement substrate.

3. **Even-odd fill rule** — `polygons_full` from shapely gives proper exterior/interior topology. This fixed the false-positive wall thickness readings on open-slot geometry.

4. **Gap measurement via scanline** — `_measure_gaps()` finds interior voids by scanning the bitmap at mid-row/mid-col. Simple, robust, no OCC dependency.

5. **Smart cut plane selection from spec** — `_compute_cut_planes()` reads the spec and places cuts perpendicular to features at 40-60% along their length. Feature-driven cuts are more informative than arbitrary centroid slices.

6. **Minimum 4 sections always** — XY lower, XY upper, XZ side, YZ front. Regardless of spec contents. This was a Round 3 lesson (zero cross-sections = missed bugs).

**Port these unchanged.** The mesh-based pipeline has no CadQuery dependency — it operates on trimesh meshes loaded from exported files.

### What to Rewrite

1. **Mesh loading.** The current `_load_mesh()` roundtrips through CadQuery (`cq.importers.importStep` -> temp STL -> trimesh). For build123d, the loader should:
   - Accept `.3mf` as primary format (not just STEP/STL)
   - Load 3MF directly via trimesh (which supports 3MF natively)
   - Fall back to STEP via build123d import if needed

```python
def _load_mesh(input_path: str):
    """Load 3MF, STEP, or STL and return a trimesh.Trimesh."""
    import trimesh
    ext = Path(input_path).suffix.lower()

    if ext == ".3mf":
        scene = trimesh.load(input_path)
        if isinstance(scene, trimesh.Scene):
            return trimesh.util.concatenate(list(scene.geometry.values()))
        return scene

    elif ext in (".step", ".stp"):
        # Use build123d's STEP import, tessellate, load as trimesh
        from build123d import import_step
        solid = import_step(input_path)
        verts_faces = solid.tessellate(tolerance=0.01)
        verts = np.array([(v.X, v.Y, v.Z) for v in verts_faces[0]])
        faces = np.array(verts_faces[1])
        return trimesh.Trimesh(vertices=verts, faces=faces, process=False)

    else:
        return trimesh.load(input_path, force="mesh")
```

2. **Dimension line rendering.** The current renderer draws basic dimension lines with matplotlib annotations. Version 2.0 adds:
   - Alternating-block scale bars (see Section 6)
   - Proper mechanical drawing dimension lines with extension lines, arrows, and centered text
   - Spec-vs-measured annotations: `"5.02mm (spec: 5.00 +/- 0.30)"` in green for PASS, red for FAIL
   - Wall thickness callouts on thin sections

3. **Cut plane selection 2.0.** Add support for:
   - **Pattern features** — ventilation grids, bolt arrays. Cut at the first instance AND between two instances to show pitch.
   - **Two-part assemblies** — when the spec declares `assembly_parts`, render each part's sections independently plus a combined view at the mating surface.
   - **Feature-axis-aware cuts** — the current code assumes slots run along Y. Version 2.0 reads a `feature_axis` field from the spec to orient the cut perpendicular to the feature's actual long axis.

### Smart Cut Plane Selection Algorithm

```python
def _compute_cut_planes_v2(spec, mesh):
    cuts = []
    bb = mesh.bounds
    # ... bounding box setup ...

    for feat in spec.get("features", []):
        feat_type = feat["type"]
        axis = feat.get("feature_axis", "y")  # default: feature runs along Y

        if feat_type == "slot":
            # Cut perpendicular to feature axis at 45% along its length
            frac = 0.45
            _add_perpendicular_cut(cuts, feat, axis, frac, bb)

        elif feat_type == "hole":
            # Cut XY at 45% of hole depth
            _add_hole_cut(cuts, feat, bb)

        elif feat_type == "pattern":
            # NEW: cut at first instance and between instances
            instances = feat.get("instances", [])
            pitch = feat.get("pitch", 0)
            if instances:
                _add_perpendicular_cut(cuts, feat, axis, 0.0, bb,
                                       offset=instances[0])
            if len(instances) >= 2 and pitch > 0:
                mid = (instances[0] + instances[1]) / 2
                _add_perpendicular_cut(cuts, feat, axis, 0.0, bb,
                                       offset=mid)

        elif feat_type == "mating_surface":
            # NEW: cut at the mating plane for two-part assemblies
            _add_mating_cut(cuts, feat, bb)

    # ALWAYS add the 4 mandatory general sections
    _add_general_sections(cuts, spec, bb)

    return _deduplicate_cuts(cuts)
```

### Cut Deduplication

When multiple features request cuts at similar positions (within 2mm), merge them into a single cut with combined `expected` annotations. This prevents redundant renders without losing measurement coverage.

```python
def _deduplicate_cuts(cuts, threshold_mm=2.0):
    """Merge cuts whose origins are within threshold_mm of each other."""
    merged = []
    for cut in cuts:
        origin = np.array(cut['origin'])
        normal = np.array(cut['normal'])
        found = False
        for existing in merged:
            if (np.allclose(normal, existing['normal'], atol=0.01) and
                np.linalg.norm(origin - np.array(existing['origin'])) < threshold_mm):
                existing['expected'].extend(cut['expected'])
                existing['label'] += f" + {cut['label'].split('—')[-1].strip()}"
                found = True
                break
        if not found:
            merged.append(cut)
    return merged
```

---

## 4. Geometry Validator 2.0

### What Changes

The geometry validator loads STEP files via CadQuery and uses OCC topology access (`TopExp_Explorer`, `BRepAdaptor_Curve`) for hole detection. build123d wraps the same OCCT kernel but with different Python bindings.

**Key adaptation: topology access patterns.**

CadQuery:
```python
shape = cq.importers.importStep(path)
solid = shape.val().wrapped        # OCP.TopoDS.TopoDS_Solid
bb = shape.val().BoundingBox()     # CQ BoundingBox
volume = shape.val().Volume()
faces = shape.val().Faces()
```

build123d:
```python
from build123d import import_step
solid = import_step(path)
bb = solid.bounding_box()          # build123d BoundingBox
volume = solid.volume
faces = solid.faces()              # returns list of Face objects
```

The BoundingBox API differs:

| Property | CadQuery | build123d |
|----------|----------|-----------|
| X extent | `bb.xlen` | `bb.size.X` |
| Y extent | `bb.ylen` | `bb.size.Y` |
| Z extent | `bb.zlen` | `bb.size.Z` |
| X min | `bb.xmin` | `bb.min.X` |
| X max | `bb.xmax` | `bb.max.X` |

### `_find_nearest_hole()` Adaptation

The current implementation uses raw OCC `TopExp_Explorer` to iterate edges and `BRepAdaptor_Curve` to detect circles. build123d provides a higher-level API:

```python
def _find_nearest_hole_b3d(solid, expected_diameter, position=None):
    """Find circular edges in a build123d solid."""
    from build123d import Edge
    import math

    candidates = []
    for edge in solid.edges():
        if edge.geom_type() == "CIRCLE":
            radius = edge.radius
            diameter = radius * 2.0
            center = edge.center()
            pos = (center.X, center.Y, center.Z)
            candidates.append((diameter, pos))

    # Same sorting/matching logic as CadQuery version
    ...
```

This is cleaner — no raw OCC imports needed. build123d's `Edge.geom_type()` and `Edge.radius` encapsulate the `BRepAdaptor_Curve` calls.

### Cross-Section Measurement

The current `_cross_section_at_z()` uses a CadQuery thin-slab intersection to avoid OCC section bugs. For the geometry validator (not the renderer), build123d offers `Part.section()`:

```python
def _cross_section_at_z_b3d(solid, z: float):
    """Cross-section using build123d's section method."""
    from build123d import Plane, Vector
    plane = Plane(origin=Vector(0, 0, z), z_dir=Vector(0, 0, 1))
    try:
        section = solid.section(plane)
        if section is None or len(section.edges()) == 0:
            return None
        return section
    except Exception:
        return None
```

**Important caveat:** build123d's `section()` still calls OCC under the hood. If it produces degenerate edges (the same OCC bug the CadQuery pipeline worked around), fall back to the thin-slab approach using build123d's boolean intersection:

```python
def _cross_section_at_z_slab(solid, z: float, thickness=0.2):
    """Thin-slab fallback for cross-section measurement."""
    from build123d import Box, Pos
    slab = Pos(0, 0, z) * Box(1e6, 1e6, thickness)
    try:
        section = solid & slab  # build123d intersection operator
        bb = section.bounding_box()
        if bb.size.X < 0.001 and bb.size.Y < 0.001:
            return None
        return section
    except Exception:
        return None
```

### What Stays the Same

- `CheckResult` class (PASS/WARN/FAIL with detail strings)
- `check_overall_dimensions()` logic (compare BB to spec, report delta)
- `check_features()` structure (iterate spec features, probe geometry)
- `check_components()` fit-checking logic
- `check_minimum_wall()` cross-section sampling at 5 Z heights
- `_measure_slot_gap_at_z()` occupancy-probe approach (but using build123d booleans instead of CadQuery)
- WARN threshold for wall thickness within 0.3mm of minimum

---

## 5. Printability Checker 2.0

### What Changes

The printability checker operates entirely on trimesh meshes — it has no direct CadQuery/build123d dependency except for STEP loading. The only change is the mesh loading path.

**Current:** STEP -> CadQuery tessellation -> OCC face/triangle extraction -> trimesh  
**New:** 3MF -> trimesh (native) OR STEP -> build123d tessellation -> trimesh

```python
def _load_mesh_v2(input_path: str):
    """Load 3MF, STEP, or STL to trimesh."""
    import trimesh
    ext = Path(input_path).suffix.lower()

    if ext == ".3mf":
        mesh = trimesh.load(input_path)
        if isinstance(mesh, trimesh.Scene):
            parts = [g for g in mesh.geometry.values()
                     if isinstance(g, trimesh.Trimesh)]
            if not parts:
                raise ValueError(f"No mesh geometry in {input_path}")
            mesh = trimesh.util.concatenate(parts)
        return mesh

    elif ext in (".step", ".stp"):
        from build123d import import_step
        solid = import_step(input_path)
        tess = solid.tessellate(tolerance=0.05)
        verts = np.array([(v.X, v.Y, v.Z) for v in tess[0]], dtype=np.float64)
        faces = np.array(tess[1], dtype=np.int32)
        return trimesh.Trimesh(vertices=verts, faces=faces, process=False)

    else:
        mesh = trimesh.load(input_path, force="mesh")
        if isinstance(mesh, trimesh.Scene):
            parts = [g for g in mesh.geometry.values()
                     if isinstance(g, trimesh.Trimesh)]
            mesh = trimesh.util.concatenate(parts)
        return mesh
```

### What Stays the Same

All five checks are mesh-based and kernel-agnostic:

1. **Flat bottom** (`check_flat_bottom`) — triangle normal analysis at Z-min. Unchanged.
2. **Overhangs** (`check_overhangs`) — vectorized dot product against down vector. Unchanged.
3. **Wall thickness** (`check_wall_thickness`) — raster cross-section + distance transform. Unchanged. The even-odd fill via `polygons_full` and interior-void isolation are critical — do not regress these.
4. **Bridge span** (`check_bridge_spans`) — XY grid support check. Unchanged.
5. **Min feature size** (`check_min_feature_size`) — connected component analysis in cross-sections. Unchanged.

### New: 3MF Unit Validation

3MF files carry explicit unit metadata. Add a pre-flight check:

```python
def check_3mf_units(path: str) -> CheckResult:
    """Verify 3MF file uses millimeters."""
    import zipfile
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(path) as z:
        with z.open("3D/3dmodel.model") as f:
            tree = ET.parse(f)
    root = tree.getroot()
    ns = root.tag.split('}')[0] + '}' if '}' in root.tag else ''
    unit = root.attrib.get('unit', 'millimeter')

    if unit == 'millimeter':
        return _pass("3MF units", "millimeter (correct)")
    else:
        return _fail("3MF units",
                     f"'{unit}' — expected 'millimeter'. "
                     f"Part will be the wrong size in the slicer.")
```

---

## 6. Dimension Line Rendering

### Alternating-Block Scale Bar

The current renderer uses matplotlib's `AnchoredSizeBar`. Version 2.0 replaces this with a mechanical-drawing-style alternating-block scale bar that communicates scale at a glance:

```
 |█████|     |█████|     |█████|
 0    10    20    30    40    50 mm
```

**Implementation:**

```python
def _draw_scale_bar(ax, x_start, y_pos, total_mm, mm_per_pixel, n_blocks=5):
    """Draw an alternating black/white scale bar with mm labels."""
    block_mm = total_mm / n_blocks
    block_px = block_mm / mm_per_pixel

    for i in range(n_blocks):
        color = 'white' if i % 2 == 0 else '#666666'
        x = x_start + i * block_px
        rect = patches.Rectangle((x, y_pos), block_px, 8,
                                  facecolor=color, edgecolor='white',
                                  linewidth=0.5)
        ax.add_patch(rect)

    # Tick labels at block boundaries
    for i in range(n_blocks + 1):
        x = x_start + i * block_px
        label_mm = i * block_mm
        ax.text(x, y_pos - 3, f"{label_mm:.0f}",
                ha='center', va='top', color='white', fontsize=6)

    # Unit label
    ax.text(x_start + total_mm / mm_per_pixel / 2, y_pos - 12, "mm",
            ha='center', va='top', color='#AAAAAA', fontsize=7)
```

### Mechanical Drawing Dimension Lines

Proper ISO 129-style dimension lines with extension lines and arrowheads:

```python
def _draw_dimension(ax, p1, p2, label, offset_px=30, color='white',
                    spec_value=None, tolerance=None):
    """Draw a dimension line between two points with extension lines.

    p1, p2: (x, y) in pixel coordinates
    label: measurement text (e.g., "42.50mm")
    spec_value: if provided, annotate with spec comparison
    tolerance: +/- tolerance for PASS/FAIL coloring
    """
    # Extension lines: short perpendicular lines at p1 and p2
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = (dx**2 + dy**2) ** 0.5
    if length < 1:
        return

    # Normal direction for offset
    nx, ny = -dy / length, dx / length

    # Extension line endpoints
    e1_start = (p1[0] + nx * 5, p1[1] + ny * 5)
    e1_end = (p1[0] + nx * (offset_px + 5), p1[1] + ny * (offset_px + 5))
    e2_start = (p2[0] + nx * 5, p2[1] + ny * 5)
    e2_end = (p2[0] + nx * (offset_px + 5), p2[1] + ny * (offset_px + 5))

    # Draw extension lines
    ax.plot([e1_start[0], e1_end[0]], [e1_start[1], e1_end[1]],
            color=color, linewidth=0.5, alpha=0.7)
    ax.plot([e2_start[0], e2_end[0]], [e2_start[1], e2_end[1]],
            color=color, linewidth=0.5, alpha=0.7)

    # Dimension line with arrows
    dim_y = p1[1] + ny * offset_px
    dim_x1 = p1[0] + nx * offset_px
    dim_x2 = p2[0] + nx * offset_px
    ax.annotate('', xy=(dim_x2, p2[1] + ny * offset_px),
                xytext=(dim_x1, dim_y),
                arrowprops=dict(arrowstyle='<->', color=color, lw=0.8))

    # Label at midpoint
    mid_x = (dim_x1 + dim_x2) / 2
    mid_y = (dim_y + p2[1] + ny * offset_px) / 2

    # Color by spec comparison
    text_color = color
    if spec_value is not None and tolerance is not None:
        measured = float(label.replace('mm', ''))
        delta = abs(measured - spec_value)
        if delta <= tolerance:
            text_color = '#44CC44'  # green = PASS
            label += f"\n(spec: {spec_value:.2f} +/-{tolerance:.2f})"
        else:
            text_color = '#FF4444'  # red = FAIL
            label += f"\n(spec: {spec_value:.2f} +/-{tolerance:.2f} FAIL)"

    ax.text(mid_x, mid_y + ny * 3, label,
            ha='center', va='center', color=text_color, fontsize=6,
            bbox=dict(boxstyle='round,pad=0.2', facecolor='#2B2B2B',
                      edgecolor='none', alpha=0.8))
```

### Automatic Dimension Placement

For each cross-section, the renderer automatically places dimension lines for:

1. **Overall extents** — width and height of the cross-section bounding box
2. **Gap widths** — each interior void detected by scanline measurement
3. **Wall thicknesses** — material runs adjacent to gaps
4. **Spec-annotated features** — dimensions from the `expected` list in the cut definition, with PASS/FAIL coloring

Dimension lines are placed on alternating sides (left/right, top/bottom) to avoid overlap. The offset increases for each successive dimension on the same side.

---

## 7. Spec Format 2.0

### Current Spec Fields (unchanged)

```json
{
    "part_name": "string",
    "overall_dimensions": {
        "width": 0.0, "depth": 0.0, "height": 0.0,
        "tolerance": 0.3
    },
    "material": "PLA",
    "min_wall_mm": 1.2,
    "components": [...],
    "features": [...],
    "overhangs_ok": false,
    "max_overhang_angle_deg": 45.0,
    "max_bridge_span_mm": 20.0
}
```

### New Feature Type: `"pattern"`

For ventilation grids, bolt arrays, and other repeated features:

```json
{
    "type": "pattern",
    "name": "ventilation grid",
    "element_type": "slot",
    "element_width": 2.0,
    "element_length": 15.0,
    "count": 20,
    "pitch": 3.0,
    "pattern_axis": "x",
    "feature_axis": "y",
    "region": {
        "center": [50.0, 40.0, 25.0],
        "span": [60.0, 0.0, 15.0]
    },
    "tolerance": 0.3
}
```

**Validation:** The validator checks:
- Total pattern extent: `(count - 1) * pitch + element_width` fits within `region.span`
- Element width at a sampled instance (cross-section probe)
- Pitch uniformity between adjacent instances (sample 3 pairs)

**Cross-section renderer:** Cuts at the first element AND between elements 1-2 to show pitch.

### New Feature Type: `"mating_surface"`

For two-part assemblies (base + lid, body + cap):

```json
{
    "type": "mating_surface",
    "name": "lid mating edge",
    "plane_z": 25.0,
    "mating_clearance_mm": 0.3,
    "interlock_type": "snap_fit",
    "partner_part": "lid.3mf"
}
```

**Validation:**
- Cross-section at `plane_z` shows the mating profile
- If `partner_part` is specified and exists, load both parts and verify clearance at the mating plane
- Snap-fit geometry: measure undercut depth and deflection angle

### New Top-Level Field: `"assembly_parts"`

```json
{
    "assembly_parts": [
        {"name": "base", "file": "base.3mf", "role": "primary"},
        {"name": "lid", "file": "lid.3mf", "role": "secondary"}
    ]
}
```

When present, the cross-section renderer produces:
1. Individual sections for each part
2. Combined sections showing both parts at the mating interface
3. Clearance measurements between parts

### New Feature Field: `"feature_axis"`

Added to all feature types. Tells the cross-section renderer which direction the feature runs, so it can cut perpendicular:

```json
{
    "type": "slot",
    "name": "DIMM slot",
    "width": 5.0,
    "feature_axis": "y",
    "tolerance": 0.3
}
```

Valid values: `"x"`, `"y"`, `"z"`. Default: `"y"` (backward compatible with existing behavior).

### Export Format Field

```json
{
    "export_format": "3mf",
    "export_metadata": {
        "author": "cad-skill",
        "description": "Gridfinity SSD+DIMM bin",
        "print_material": "PLA",
        "print_nozzle_mm": 0.4,
        "print_layer_mm": 0.2
    }
}
```

The `export_format` field defaults to `"3mf"`. When set to `"step"`, the pipeline skips 3MF-specific checks (unit validation) and uses STEP export. The `export_metadata` fields are written into the 3MF file's metadata section — they show up in slicer part info and help identify parts months later.

---

## Migration Path

### Phase 1: Drop-in Compatibility

The post-export validators (Layer 3) work on mesh files, not build scripts. They can be ported first with only the mesh-loading functions changed. The rest of the pipeline operates on trimesh meshes and numpy arrays — kernel-agnostic.

**Files to modify:** `_load_mesh()` in all three scripts.  
**Files unchanged:** Every check function, every measurement function, every rendering function.

### Phase 2: Construction-Time Checks

Port `cq_debug_helpers.py` to `b3d_debug_helpers.py`. The snapshot-based approach is new but the detection logic (volume/face/centroid comparison) is identical.

### Phase 3: Manifold Layer

New code. Requires `manifold3d` as a dependency. No CadQuery equivalent exists — this is a net-new capability.

### Phase 4: Spec Format Extensions

Add new feature types (`pattern`, `mating_surface`) and fields (`feature_axis`, `assembly_parts`, `export_format`). All new fields are optional with backward-compatible defaults — existing specs continue to work.

### Phase 5: Cross-Section Renderer Enhancements

Dimension line rendering, alternating-block scale bars, spec-vs-measured annotations. These are additive — the existing renderer output is a subset of the new output.

---

## Dependency Matrix

| Component | trimesh | numpy | PIL | scipy | matplotlib | manifold3d | build123d | cadquery |
|-----------|---------|-------|-----|-------|------------|------------|-----------|---------|
| Layer 1 (construction checks) | | | | | | | **required** | |
| Layer 2 (manifold validation) | required | required | | | | **required** | required | |
| validate_geometry.py | | required | | | | | required | |
| check_printability.py | required | required | required | required | | | optional* | |
| render_cross_sections.py | required | required | required | | required | | optional* | |

*STEP loading only. 3MF loading uses trimesh directly.

---

## Test Strategy

### Unit Tests for Each Check

Each check function gets a synthetic test mesh:

- **`test_verify_boolean_b3d`** — Build a box, take snapshot, add a hole, verify detection. Build a box, take snapshot, do nothing, verify RuntimeError.
- **`test_manifold_check`** — Create a known-good mesh (cube), verify PASS. Create a self-intersecting mesh (bowtie), verify FAIL.
- **`test_wall_thickness_open_slot`** — The open-slot false-positive regression test. Create a U-channel cross-section, verify wall thickness measurement uses even-odd fill and doesn't report the open side as a thin wall.
- **`test_pattern_feature_validation`** — Create a plate with 5 identical slots at regular pitch, verify element width and pitch uniformity checks.

### Integration Test

End-to-end: build123d script -> manifold check -> 3MF export -> validate_geometry -> check_printability -> render_cross_sections. The gridfinity SSD+DIMM bin serves as the integration test case — it exercises slots, pockets, wall thickness, and cross-section rendering.

### Regression Tests from Round History

| Round | Bug | Regression Test |
|-------|-----|-----------------|
| R1 | Missing cross-sections | Assert >= 4 section PNGs produced per run |
| R2 | Empty spec features array | Assert spec validation rejects empty features on non-trivial geometry |
| R5 | Silent chamfer boolean | `test_verify_boolean` with a no-op cut raises RuntimeError |
| R5 | `to_planar()` deprecation | No `to_planar` calls anywhere in codebase |
| R6 | No pattern feature type | `test_pattern_feature_validation` exists |
| R6 | No two-part assembly support | `test_mating_surface_validation` exists |
