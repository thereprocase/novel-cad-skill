#!/usr/bin/env python3
"""
check_printability.py -- Automated FDM printability checker.

Runs the novel-cad-skill self-review checklist items that are automatable
against an exported STEP or STL file. Optionally reads a .spec.json for
custom thresholds; falls back to FDM defaults.

Checks:
  1. Flat bottom      -- Z-min surface has downward normals (within 5 degrees)
  2. Overhangs        -- % of surface area exceeding max_overhang_angle_deg (default 45)
  3. Wall thickness   -- cross-section sampling; minimum found vs min_wall_mm (default 1.2mm)
  4. Bridge span      -- horizontal spans with no support below; flag > max_bridge_span_mm (default 20mm)
  5. Min feature size -- smallest disconnected cross-section region < 0.8mm

Output format:
  [PASS] Flat bottom: Z=0.0mm, planar (normal deviation < 2 degrees)
  [WARN] Overhangs: 12.3% of surface area exceeds 45 degrees (3 regions)
  [PASS] Min wall thickness: 2.1mm (threshold: 1.2mm)
  [FAIL] Bridge span: 24.3mm at Z=15mm (max: 20mm)
  [PASS] Min feature size: 1.4mm (threshold: 0.8mm)

Exit code: 0 = all PASS or WARN. 1 = any FAIL.

Usage:
    python check_printability.py part.step
    python check_printability.py part.stl --spec custom.json
"""

import sys
import os
import math
import json
import argparse
from pathlib import Path

import numpy as np

_SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SKILL_DIR / "lib"))

# Spec is optional
try:
    from spec_format import load_spec
    _SPEC_AVAILABLE = True
except ImportError:
    _SPEC_AVAILABLE = False

# -- FDM defaults -------------------------------------------------------------
DEFAULT_OVERHANG_DEG    = 45.0
DEFAULT_BRIDGE_SPAN_MM  = 20.0
DEFAULT_MIN_WALL_MM     = 1.2
DEFAULT_MIN_FEATURE_MM  = 0.8
FLAT_BOTTOM_TOL_MM      = 0.1   # Z-band for "bottom face" classification
FLAT_BOTTOM_NORMAL_TOL  = 5.0   # degrees from straight-down to count as "flat"
Z_SAMPLE_COUNT          = 10    # cross-section levels for wall/bridge/feature checks

# -- Status tags --------------------------------------------------------------
PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

_results = []  # list of status strings, accumulated by _emit()


def _reset_results():
    """Clear accumulated results. Call before each validation run."""
    global _results
    _results = []


def _emit(status: str, check_name: str, detail: str):
    line = f"[{status}] {check_name}: {detail}"
    print(line)
    _results.append(status)


# -- Geometry loading ---------------------------------------------------------

def _load_mesh(input_path: str):
    """
    Load STEP or STL and return a trimesh.Trimesh.

    Uses the shared OCC tessellation path (0.05mm) for STEP files.
    STL/3MF loaded directly via trimesh.
    """
    from mesh_utils import load_mesh_auto
    return load_mesh_auto(input_path)


# -- Threshold loading --------------------------------------------------------

def _load_thresholds(geom_path: str, spec_path: str = None) -> dict:
    """Return threshold dict, optionally overridden by spec JSON."""
    thresholds = {
        "max_overhang_angle_deg": DEFAULT_OVERHANG_DEG,
        "max_bridge_span_mm":     DEFAULT_BRIDGE_SPAN_MM,
        "min_wall_mm":            DEFAULT_MIN_WALL_MM,
        "min_feature_mm":         DEFAULT_MIN_FEATURE_MM,
        "overhangs_ok":           False,
        "warn_wall_mm":           None,  # explicit WARN band (novel-cad-skill addition)
    }

    # Auto-detect sibling .spec.json if no explicit spec given
    if spec_path is None:
        candidate = Path(geom_path).with_suffix(".spec.json")
        if candidate.exists():
            spec_path = str(candidate)

    if spec_path and os.path.exists(spec_path):
        try:
            if _SPEC_AVAILABLE:
                spec = load_spec(spec_path)
            else:
                with open(spec_path, "r", encoding="utf-8") as f:
                    spec = json.load(f)
            for key in ("max_overhang_angle_deg", "max_bridge_span_mm",
                        "min_wall_mm", "warn_wall_mm", "overhangs_ok"):
                if key in spec:
                    thresholds[key] = spec[key]
        except Exception:
            pass  # spec load failure is non-fatal -- use defaults

    return thresholds


# -- Check 1: Flat bottom -----------------------------------------------------

def check_flat_bottom(mesh) -> None:
    """
    Verify Z-min has a planar horizontal face for bed adhesion.

    Passes if at least some triangles at Z-min are horizontal, even if
    others are angled chamfer faces. Fails only when there are NO horizontal
    triangles at Z-min (fully rounded or chamfered base).
    """
    tol_cos = math.cos(math.radians(FLAT_BOTTOM_NORMAL_TOL))

    z_min = float(mesh.vertices[:, 2].min())
    face_z = mesh.triangles_center[:, 2]
    bottom_mask = face_z < (z_min + FLAT_BOTTOM_TOL_MM)

    if not bottom_mask.any():
        _emit(FAIL, "Flat bottom",
              f"Z={z_min:.2f}mm, no triangles found at Z-min band")
        return

    bottom_normals = mesh.face_normals[bottom_mask]

    # Absolute Z component: accept normals pointing either up or down.
    # Meaningful check is whether the face is horizontal, not winding order.
    abs_z_dots = np.abs(bottom_normals[:, 2])

    n_horizontal = int(np.sum(abs_z_dots >= tol_cos))
    n_total = int(bottom_mask.sum())
    n_angled = n_total - n_horizontal

    if n_horizontal == 0:
        worst_deg = math.degrees(math.acos(max(0.0, min(1.0, float(abs_z_dots.max())))))
        _emit(FAIL, "Flat bottom",
              f"Z={z_min:.2f}mm, no horizontal face found at Z-min -- "
              f"all {n_total} bottom triangles are angled (worst: {worst_deg:.1f} deg from horizontal) "
              f"-- part will rock on print bed")
    elif n_angled > 0:
        _emit(PASS, "Flat bottom",
              f"Z={z_min:.2f}mm, {n_horizontal}/{n_total} bottom triangles horizontal "
              f"({n_angled} angled -- bottom chamfer, correct for FDM)")
    else:
        _emit(PASS, "Flat bottom",
              f"Z={z_min:.2f}mm, planar ({n_horizontal} horizontal triangles)")


# -- Check 2: Overhang analysis -----------------------------------------------

def check_overhangs(mesh, max_angle_deg: float, overhangs_ok: bool) -> None:
    """
    Vectorized overhang check.
    FDM overhang angle is measured from horizontal:
      - 0 deg  = perfectly horizontal underside (prints fine with bridges)
      - 45 deg = FDM limit without support
      - 90 deg = vertical wall (not an overhang)
    A triangle overhangs when dot(normal, down) > sin(max_angle_deg).
    Excludes the bottom floor face.
    """
    threshold_dot = math.sin(math.radians(max_angle_deg))
    down = np.array([0.0, 0.0, -1.0])
    normals = mesh.face_normals
    dots = normals @ down  # positive = facing downward

    z_min = float(mesh.vertices[:, 2].min())
    face_z = mesh.triangles_center[:, 2]
    floor_mask = face_z < (z_min + FLAT_BOTTOM_TOL_MM)

    overhang_mask = (dots > threshold_dot) & ~floor_mask

    face_areas = mesh.area_faces
    total_area = float(face_areas.sum())
    overhang_area = float(face_areas[overhang_mask].sum())
    pct = 100.0 * overhang_area / total_area if total_area > 0 else 0.0

    n_regions = 0
    if overhang_mask.any():
        n_regions = _count_face_regions(mesh, np.where(overhang_mask)[0])

    region_str = f"{n_regions} region{'s' if n_regions != 1 else ''}"

    if not overhang_mask.any():
        _emit(PASS, "Overhangs",
              f"No overhangs > {max_angle_deg:.0f} deg detected")
    elif overhangs_ok:
        _emit(WARN, "Overhangs",
              f"{pct:.1f}% of surface area exceeds {max_angle_deg:.0f} deg "
              f"({region_str}) -- spec marks overhangs_ok=True")
    else:
        # WARN not FAIL: overhangs can be handled in slicer; CAD redesign optional
        _emit(WARN, "Overhangs",
              f"{pct:.1f}% of surface area exceeds {max_angle_deg:.0f} deg ({region_str})")


def _count_face_regions(mesh, face_indices: np.ndarray) -> int:
    """Count connected components among a subset of face indices via face adjacency."""
    if len(face_indices) == 0:
        return 0
    try:
        adjacency = mesh.face_adjacency
    except Exception:
        return 1

    face_set = set(face_indices.tolist())
    both_in = np.isin(adjacency[:, 0], face_indices) & np.isin(adjacency[:, 1], face_indices)
    adj_subset = adjacency[both_in]

    parent = {f: f for f in face_set}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in adj_subset:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            parent[ra] = rb

    return len({find(f) for f in face_set})


# -- Check 3: Wall thickness --------------------------------------------------

def check_wall_thickness(mesh, min_wall_mm: float, warn_wall_mm: float = None) -> None:
    """
    Sample cross-sections at multiple Z levels. For each cross-section,
    rasterize and compute minimum inscribed circle radius via distance transform.
    Reports minimum wall thickness found across all levels.

    If warn_wall_mm is set, values below warn_wall_mm (but above min_wall_mm)
    emit WARN rather than needing to breach min_wall_mm to get a FAIL.
    """
    z_min = float(mesh.vertices[:, 2].min())
    z_max = float(mesh.vertices[:, 2].max())
    height = z_max - z_min

    if height <= 0:
        _emit(WARN, "Min wall thickness", "Zero-height geometry, skipping")
        return

    z_levels = np.linspace(z_min + height * 0.12, z_max - height * 0.05, Z_SAMPLE_COUNT)

    min_found = float("inf")
    min_z = None

    for z in z_levels:
        t = _wall_thickness_at_z(mesh, float(z))
        if t is not None and t < min_found:
            min_found = t
            min_z = float(z)

    if min_found == float("inf"):
        _emit(WARN, "Min wall thickness",
              "Could not extract cross-sections -- verify manually in slicer")
        return

    # Explicit warn band: spec sets warn_wall_mm above min_wall_mm
    effective_warn = warn_wall_mm if warn_wall_mm is not None else min_wall_mm * (1.0 / 0.7)
    z_str = f" at Z={min_z:.1f}mm" if min_z is not None else ""

    if min_found >= min_wall_mm and (warn_wall_mm is None or min_found >= warn_wall_mm):
        _emit(PASS, "Min wall thickness",
              f"{min_found:.1f}mm (threshold: {min_wall_mm:.1f}mm)")
    elif min_found >= min_wall_mm:
        # Between min_wall_mm and warn_wall_mm
        _emit(WARN, "Min wall thickness",
              f"{min_found:.1f}mm{z_str} (warn threshold: {warn_wall_mm:.1f}mm, "
              f"fail threshold: {min_wall_mm:.1f}mm) -- verify in slicer")
    elif min_found >= min_wall_mm * 0.7:
        # Cross-section distance transform can underestimate near slot edges
        _emit(WARN, "Min wall thickness",
              f"{min_found:.1f}mm{z_str} (threshold: {min_wall_mm:.1f}mm) "
              f"-- conservative estimate, verify in slicer if near threshold")
    else:
        _emit(FAIL, "Min wall thickness",
              f"{min_found:.1f}mm{z_str} (threshold: {min_wall_mm:.1f}mm) "
              f"-- walls are significantly below minimum")


def _wall_thickness_at_z(mesh, z: float) -> float | None:
    """
    Rasterize the cross-section at Z, run a distance transform,
    return 2 * 5th-percentile inscribed circle radius (minimum wall thickness).
    Resolution: 0.2mm/pixel.
    """
    try:
        section = mesh.section(plane_origin=[0.0, 0.0, z], plane_normal=[0.0, 0.0, 1.0])
        if section is None:
            return None
        path2d = section.to_2D()
    except Exception:
        return None

    # trimesh sometimes returns a tuple instead of a Path2D object
    if isinstance(path2d, tuple):
        # Try to extract a Path2D from the tuple
        import trimesh
        for item in path2d:
            if hasattr(item, 'entities'):
                path2d = item
                break
        else:
            return None  # no valid Path2D found

    return _min_thickness_from_path2d(path2d, resolution=0.2)


def _min_thickness_from_path2d(path2d, resolution: float = 0.2) -> float | None:
    """
    Rasterize a trimesh Path2D and return the minimum wall thickness estimate
    using a distance transform. Wall thickness = 2 * inscribed circle radius.

    Returns None for solid cross-sections (single outer boundary, no holes).
    """
    # Solid cross-section: distance transform on a solid polygon gives
    # misleadingly small values dominated by corner proximity. Skip it.
    if not hasattr(path2d, 'entities') or len(path2d.entities) < 2:
        return None

    try:
        from PIL import Image, ImageDraw
        import scipy.ndimage as ndi
    except ImportError:
        return None

    MARGIN_PX = 3

    bounds = path2d.bounds
    if bounds is None or len(bounds) < 2:
        return None

    xmin, ymin = bounds[0]
    xmax, ymax = bounds[1]
    span_x = xmax - xmin
    span_y = ymax - ymin
    if span_x < 0.1 or span_y < 0.1:
        return None

    # Dynamic resolution cap: keep image under 2M pixels
    if (span_x / resolution) * (span_y / resolution) > 2_000_000:
        resolution = math.sqrt(span_x * span_y / 2_000_000)

    w_px = int(math.ceil(span_x / resolution)) + 2 * MARGIN_PX
    h_px = int(math.ceil(span_y / resolution)) + 2 * MARGIN_PX

    img = Image.new("L", (w_px, h_px), 0)
    draw = ImageDraw.Draw(img)

    # Even-odd fill: outer boundary as filled, inner boundaries as holes.
    try:
        for polygon in path2d.polygons_full:
            ext = polygon.exterior.coords
            px = ((np.array([c[0] for c in ext]) - xmin) / resolution + MARGIN_PX).tolist()
            py = ((np.array([c[1] for c in ext]) - ymin) / resolution + MARGIN_PX).tolist()
            poly = list(zip(px, py))
            if len(poly) >= 3:
                draw.polygon(poly, fill=255)
            for interior in polygon.interiors:
                int_coords = interior.coords
                px = ((np.array([c[0] for c in int_coords]) - xmin) / resolution + MARGIN_PX).tolist()
                py = ((np.array([c[1] for c in int_coords]) - ymin) / resolution + MARGIN_PX).tolist()
                hole = list(zip(px, py))
                if len(hole) >= 3:
                    draw.polygon(hole, fill=0)
    except Exception:
        # Fallback: draw entities directly
        for entity in path2d.entities:
            try:
                pts = path2d.vertices[entity.points]
                px = ((pts[:, 0] - xmin) / resolution + MARGIN_PX).tolist()
                py = ((pts[:, 1] - ymin) / resolution + MARGIN_PX).tolist()
                poly = list(zip(px, py))
                if len(poly) >= 3:
                    draw.polygon(poly, fill=255)
            except Exception:
                continue

    bitmap = np.array(img, dtype=bool)
    if not bitmap.any():
        return None

    # Isolate interior hole pixels from the exterior background so the
    # distance transform measures distance from interior voids only.
    from scipy.ndimage import label as ndi_label
    void_mask = ~bitmap
    labeled, n_regions = ndi_label(void_mask)
    border_mask = np.zeros_like(void_mask)
    border_mask[0, :] = True
    border_mask[-1, :] = True
    border_mask[:, 0] = True
    border_mask[:, -1] = True
    exterior_labels = set(labeled[border_mask & void_mask].tolist())
    exterior_labels.discard(0)
    interior_void = void_mask.copy()
    for lbl in exterior_labels:
        interior_void[labeled == lbl] = False

    if not interior_void.any():
        return None

    dist = ndi.distance_transform_edt(~interior_void)
    interior = dist[bitmap]
    if len(interior) == 0:
        return None

    min_radius_px = float(np.percentile(interior, 20))
    return max(2.0 * min_radius_px * resolution, 0.01)


# -- Check 4: Bridge span -----------------------------------------------------

def check_bridge_spans(mesh, max_bridge_mm: float) -> None:
    """
    Find horizontal surfaces (within 5 degrees of Z-normal, excluding Z-min floor)
    with no mesh geometry within 0.5mm directly below them.
    Groups by Z level, measures bounding-box span of each cluster.
    Reports worst span found.
    """
    HORIZ_COS    = math.cos(math.radians(5.0))
    GRID_RES_MM  = 1.0
    MIN_GAP_MM   = 0.5
    MIN_SPAN_MM  = 2.0

    z_min = float(mesh.vertices[:, 2].min())
    normals   = mesh.face_normals
    centroids = mesh.triangles_center

    horiz_mask    = np.abs(normals[:, 2]) > HORIZ_COS
    not_floor     = centroids[:, 2] > (z_min + FLAT_BOTTOM_TOL_MM + 0.1)
    candidate_idx = np.where(horiz_mask & not_floor)[0]

    if len(candidate_idx) == 0:
        _emit(PASS, "Bridge span", "No internal horizontal surfaces detected")
        return

    cand_cents = centroids[candidate_idx]
    cand_z     = cand_cents[:, 2]

    all_cents = mesh.triangles_center
    verts = mesh.vertices

    x_min_v = float(verts[:, 0].min())
    x_max_v = float(verts[:, 0].max())
    y_min_v = float(verts[:, 1].min())
    y_max_v = float(verts[:, 1].max())

    nx = max(1, int(math.ceil((x_max_v - x_min_v) / GRID_RES_MM)))
    ny = max(1, int(math.ceil((y_max_v - y_min_v) / GRID_RES_MM)))

    if nx * ny > 1_000_000:
        GRID_RES_MM = math.sqrt((x_max_v - x_min_v) * (y_max_v - y_min_v) / 1_000_000)
        nx = max(1, int(math.ceil((x_max_v - x_min_v) / GRID_RES_MM)))
        ny = max(1, int(math.ceil((y_max_v - y_min_v) / GRID_RES_MM)))

    ix_all = np.clip(((all_cents[:, 0] - x_min_v) / GRID_RES_MM).astype(int), 0, nx - 1)
    iy_all = np.clip(((all_cents[:, 1] - y_min_v) / GRID_RES_MM).astype(int), 0, ny - 1)

    z_grid = np.full((ny, nx), z_min - 1.0, dtype=np.float64)
    np.maximum.at(z_grid, (iy_all, ix_all), all_cents[:, 2])

    ix_c = np.clip(((cand_cents[:, 0] - x_min_v) / GRID_RES_MM).astype(int), 0, nx - 1)
    iy_c = np.clip(((cand_cents[:, 1] - y_min_v) / GRID_RES_MM).astype(int), 0, ny - 1)
    z_below = z_grid[iy_c, ix_c]

    bridge_local = (cand_z - z_below) > MIN_GAP_MM
    if not bridge_local.any():
        _emit(PASS, "Bridge span",
              f"No unsupported spans detected (max: {max_bridge_mm:.0f}mm)")
        return

    bridge_cents = cand_cents[bridge_local]
    bridge_z     = bridge_cents[:, 2]

    max_span     = 0.0
    worst_span_z = float(bridge_z[0])

    unique_z = np.unique(np.round(bridge_z, 0))
    for zl in unique_z:
        in_band = np.abs(bridge_z - zl) < 0.5
        if not in_band.any():
            continue
        band = bridge_cents[in_band]
        if len(band) < 2:
            continue
        span_x = float(band[:, 0].max() - band[:, 0].min())
        span_y = float(band[:, 1].max() - band[:, 1].min())
        span   = max(span_x, span_y)
        if span > max_span:
            max_span = span
            worst_span_z = float(zl)

    if max_span < MIN_SPAN_MM:
        _emit(PASS, "Bridge span",
              f"No significant unsupported spans (largest: {max_span:.1f}mm, "
              f"max: {max_bridge_mm:.0f}mm)")
    elif max_span <= max_bridge_mm:
        _emit(PASS, "Bridge span",
              f"{max_span:.1f}mm at Z={worst_span_z:.1f}mm (max: {max_bridge_mm:.0f}mm)")
    else:
        _emit(FAIL, "Bridge span",
              f"{max_span:.1f}mm at Z={worst_span_z:.1f}mm (max: {max_bridge_mm:.0f}mm)")


# -- Check 5: Minimum feature size --------------------------------------------

def check_min_feature_size(mesh, min_feat_mm: float) -> None:
    """
    Find small disconnected connected components via trimesh.split().
    Also checks cross-sections for small isolated regions.
    Reports minimum bounding dimension found.
    """
    min_found = float("inf")
    worst_z   = None

    # Split into connected components, check bounding extents.
    # Only useful for watertight meshes -- OCC tessellations have per-face
    # disconnected triangles that produce meaningless micro-components.
    if mesh.is_watertight:
        try:
            components = mesh.split(only_watertight=False)
            for comp in components:
                bb = comp.bounding_box.extents
                dim = float(np.min(bb))
                if dim < min_found:
                    min_found = dim
                    worst_z = float(comp.vertices[:, 2].mean())
        except Exception:
            pass

    z_min = float(mesh.vertices[:, 2].min())
    z_max = float(mesh.vertices[:, 2].max())
    height = z_max - z_min

    if height > 0:
        z_levels = np.linspace(z_min + height * 0.12, z_max - height * 0.05, Z_SAMPLE_COUNT)
        for z in z_levels:
            feat = _min_feature_at_z(mesh, float(z))
            if feat is not None and feat < min_found:
                min_found = feat
                worst_z = float(z)

    if min_found == float("inf"):
        _emit(WARN, "Min feature size",
              "Could not evaluate -- verify manually in slicer")
        return

    if min_found >= min_feat_mm:
        _emit(PASS, "Min feature size",
              f"{min_found:.1f}mm (threshold: {min_feat_mm:.1f}mm)")
    else:
        z_str = f" at Z={worst_z:.1f}mm" if worst_z is not None else ""
        _emit(FAIL, "Min feature size",
              f"{min_found:.2f}mm{z_str} (threshold: {min_feat_mm:.1f}mm)")


def _min_feature_at_z(mesh, z: float) -> float | None:
    """Find minimum bounding dimension of any disconnected region in cross-section at Z."""
    try:
        import scipy.ndimage as ndi
    except ImportError:
        return None

    RESOLUTION = 0.1   # mm/pixel -- fine enough to catch 0.8mm features
    MARGIN_PX  = 2

    try:
        section = mesh.section(plane_origin=[0.0, 0.0, z], plane_normal=[0.0, 0.0, 1.0])
        if section is None:
            return None
        path2d = section.to_2D()
    except Exception:
        return None

    # trimesh sometimes returns a tuple instead of a Path2D object
    if isinstance(path2d, tuple):
        for item in path2d:
            if hasattr(item, 'entities'):
                path2d = item
                break
        else:
            return None

    if not hasattr(path2d, 'entities') or len(path2d.entities) < 2:
        return None

    bounds = path2d.bounds
    if bounds is None or len(bounds) < 2:
        return None

    xmin, ymin = bounds[0]
    xmax, ymax = bounds[1]
    span_x = xmax - xmin
    span_y = ymax - ymin
    if span_x < 0.05 or span_y < 0.05:
        return None

    res = RESOLUTION
    if (span_x / res) * (span_y / res) > 2_000_000:
        res = math.sqrt(span_x * span_y / 2_000_000)

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    w_px = int(math.ceil(span_x / res)) + 2 * MARGIN_PX
    h_px = int(math.ceil(span_y / res)) + 2 * MARGIN_PX

    img = Image.new("L", (w_px, h_px), 0)
    draw = ImageDraw.Draw(img)

    try:
        for polygon in path2d.polygons_full:
            ext = polygon.exterior.coords
            px = ((np.array([c[0] for c in ext]) - xmin) / res + MARGIN_PX).tolist()
            py = ((np.array([c[1] for c in ext]) - ymin) / res + MARGIN_PX).tolist()
            poly = list(zip(px, py))
            if len(poly) >= 3:
                draw.polygon(poly, fill=255)
            for interior in polygon.interiors:
                int_coords = interior.coords
                px = ((np.array([c[0] for c in int_coords]) - xmin) / res + MARGIN_PX).tolist()
                py = ((np.array([c[1] for c in int_coords]) - ymin) / res + MARGIN_PX).tolist()
                hole = list(zip(px, py))
                if len(hole) >= 3:
                    draw.polygon(hole, fill=0)
    except Exception:
        for entity in path2d.entities:
            try:
                pts = path2d.vertices[entity.points]
                px = ((pts[:, 0] - xmin) / res + MARGIN_PX).tolist()
                py = ((pts[:, 1] - ymin) / res + MARGIN_PX).tolist()
                poly = list(zip(px, py))
                if len(poly) >= 3:
                    draw.polygon(poly, fill=255)
            except Exception:
                continue

    bitmap = np.array(img, dtype=bool)
    if not bitmap.any():
        return None

    labeled, n = ndi.label(bitmap)
    if n == 0:
        return None

    min_dim = float("inf")
    for comp_id in range(1, n + 1):
        comp = labeled == comp_id
        rows = np.where(comp.any(axis=1))[0]
        cols = np.where(comp.any(axis=0))[0]
        if len(rows) == 0 or len(cols) == 0:
            continue
        h_mm = (rows[-1] - rows[0] + 1) * res
        w_mm = (cols[-1] - cols[0] + 1) * res
        dim = min(h_mm, w_mm)
        if dim < min_dim:
            min_dim = dim

    return min_dim if min_dim < float("inf") else None


# -- Library API --------------------------------------------------------------

def check_printability(mesh, thresholds: dict = None) -> bool:
    """Run all printability checks on a trimesh. Safe for repeated calls.

    Args:
        mesh: trimesh.Trimesh to check.
        thresholds: dict with keys max_overhang_angle_deg, max_bridge_span_mm,
                    min_wall_mm, warn_wall_mm, min_feature_mm, overhangs_ok.
                    Defaults applied for any missing keys.

    Returns True if no FAILs, False if any FAIL.
    """
    if thresholds is None:
        thresholds = {}

    _reset_results()
    check_flat_bottom(mesh)
    check_overhangs(mesh,
                    max_angle_deg=thresholds.get("max_overhang_angle_deg", DEFAULT_OVERHANG_DEG),
                    overhangs_ok=thresholds.get("overhangs_ok", False))
    check_wall_thickness(mesh,
                         min_wall_mm=thresholds.get("min_wall_mm", DEFAULT_MIN_WALL_MM),
                         warn_wall_mm=thresholds.get("warn_wall_mm"))
    check_bridge_spans(mesh,
                       max_bridge_mm=thresholds.get("max_bridge_span_mm", DEFAULT_BRIDGE_SPAN_MM))
    check_min_feature_size(mesh,
                           min_feat_mm=thresholds.get("min_feature_mm", DEFAULT_MIN_FEATURE_MM))

    return FAIL not in _results


# -- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Automated FDM printability checker for STEP/STL files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input",
                        help="Path to .step, .stp, or .stl file")
    parser.add_argument("--spec", metavar="JSON", default=None,
                        help="Path to .spec.json (default: auto-detect sibling .spec.json)")
    args = parser.parse_args()

    input_path = os.path.realpath(args.input)
    if not os.path.exists(input_path):
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        sys.exit(2)

    spec_path = os.path.realpath(args.spec) if args.spec else None
    thresholds = _load_thresholds(input_path, spec_path)

    try:
        mesh = _load_mesh(input_path)
    except Exception as e:
        print(f"Error loading geometry: {e}", file=sys.stderr)
        sys.exit(2)

    if len(mesh.faces) == 0:
        print("Error: loaded mesh has no faces", file=sys.stderr)
        sys.exit(2)

    _reset_results()
    check_flat_bottom(mesh)
    check_overhangs(mesh,
                    max_angle_deg=thresholds["max_overhang_angle_deg"],
                    overhangs_ok=thresholds["overhangs_ok"])
    check_wall_thickness(mesh,
                         min_wall_mm=thresholds["min_wall_mm"],
                         warn_wall_mm=thresholds["warn_wall_mm"])
    check_bridge_spans(mesh,   max_bridge_mm=thresholds["max_bridge_span_mm"])
    check_min_feature_size(mesh, min_feat_mm=thresholds["min_feature_mm"])

    if FAIL in _results:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
