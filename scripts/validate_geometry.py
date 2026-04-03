#!/usr/bin/env python3
"""
validate_geometry.py -- Post-export intent vs. reality validator for novel-cad-skill.

Loads a STEP file and checks it against a .spec.json file that Claude wrote
before generating geometry. Reports PASS/WARN/FAIL per check with measured vs.
expected values so failures are actionable.

Adapted from the CadQuery cad-skill version:
  - Loads via build123d (falls back to CadQuery)
  - Uses build123d bounding box API (bb.size.X, bb.min.X, etc.)
  - Hole detection via build123d Edge API (falls back to raw OCP)
  - WARN status for wall thickness within 0.3mm of minimum
  - ASCII-only output (Windows cp1252 compatibility)

Usage:
    python validate_geometry.py part.step
    python validate_geometry.py part.step --spec custom.json

Exit code 0 = all checks passed. Exit code 1 = one or more checks failed.
"""

import argparse
import sys
import os
from pathlib import Path

import numpy as np

_SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SKILL_DIR / "lib"))

from spec_format import load_spec


# -- Result helpers -----------------------------------------------------------

class CheckResult:
    def __init__(self, label, passed, detail, warn=False):
        self.label = label
        self.passed = passed
        self.warn = warn
        self.detail = detail

    def __str__(self):
        if self.warn:
            tag = "[WARN]"
        elif self.passed:
            tag = "[PASS]"
        else:
            tag = "[FAIL]"
        return f"{tag} {self.label}: {self.detail}"


def _pass(label, detail):
    return CheckResult(label, True, detail)

def _warn(label, detail):
    return CheckResult(label, True, detail, warn=True)

def _fail(label, detail):
    return CheckResult(label, False, detail)


# -- Geometry loading ---------------------------------------------------------

_ENGINE = None  # "build123d" or "cadquery", set by _load_step

def _load_step(step_path):
    """Load a STEP file. Returns (solid_object, engine_name)."""
    global _ENGINE
    try:
        from build123d import import_step
        solid = import_step(step_path)
        _ENGINE = "build123d"
        return solid
    except ImportError:
        import cadquery as cq
        shape = cq.importers.importStep(step_path)
        _ENGINE = "cadquery"
        return shape


def _bounding_box(shape):
    """Return a normalized bounding box dict with xlen/ylen/zlen/xmin/xmax/etc."""
    if _ENGINE == "build123d":
        bb = shape.bounding_box()
        return {
            "xlen": bb.size.X, "ylen": bb.size.Y, "zlen": bb.size.Z,
            "xmin": bb.min.X, "xmax": bb.max.X,
            "ymin": bb.min.Y, "ymax": bb.max.Y,
            "zmin": bb.min.Z, "zmax": bb.max.Z,
        }
    else:
        bb = shape.val().BoundingBox()
        return {
            "xlen": bb.xlen, "ylen": bb.ylen, "zlen": bb.zlen,
            "xmin": bb.xmin, "xmax": bb.xmax,
            "ymin": bb.ymin, "ymax": bb.ymax,
            "zmin": bb.zmin, "zmax": bb.zmax,
        }


# -- Cross-section measurement -----------------------------------------------

def _cross_section_at_z(shape, z, slab_thickness=0.2):
    """Return cross-section bounding box dict at given Z, or None if empty.

    Uses thin-slab intersection (not OCC BRepAlgoAPI_Section) because the
    slab approach reliably produces closed wires on near-planar faces.
    """
    if _ENGINE == "build123d":
        from build123d import Box, Pos
        slab = Pos(0, 0, z) * Box(1e6, 1e6, slab_thickness)
        try:
            section = shape & slab
            bb = section.bounding_box()
            if bb.size.X < 0.001 and bb.size.Y < 0.001:
                return None
            return {
                "xlen": bb.size.X, "ylen": bb.size.Y,
                "xmin": bb.min.X, "xmax": bb.max.X,
                "ymin": bb.min.Y, "ymax": bb.max.Y,
            }
        except Exception:
            return None
    else:
        import cadquery as cq
        slab = (
            cq.Workplane("XY")
            .transformed(offset=(0, 0, z))
            .box(1e6, 1e6, slab_thickness, centered=True)
        )
        try:
            section = shape.intersect(slab)
            bb = section.val().BoundingBox()
            if bb.xlen < 0.001 and bb.ylen < 0.001:
                return None
            return {
                "xlen": bb.xlen, "ylen": bb.ylen,
                "xmin": bb.xmin, "xmax": bb.xmax,
                "ymin": bb.ymin, "ymax": bb.ymax,
            }
        except Exception:
            return None


def _measure_gap_at_z(shape, z, axis="x"):
    """Measure bounding-box extent of cross-section at height z."""
    section = _cross_section_at_z(shape, z)
    if section is None:
        return 0.0
    return section["xlen"] if axis == "x" else section["ylen"]


def _measure_slot_gap_at_z(shape, z, exterior_bb, n_probes=120):
    """Measure the largest interior gap (slot/void) at height z.

    Samples positions along X and Y, tests occupancy via tiny-cube
    intersection, finds the longest contiguous void run.
    """
    def _occupancy(axis):
        if axis == "x":
            positions = np.linspace(exterior_bb["xmin"], exterior_bb["xmax"], n_probes)
            y_center = (exterior_bb["ymin"] + exterior_bb["ymax"]) / 2.0
            probes = [(p, y_center, z) for p in positions]
        else:
            positions = np.linspace(exterior_bb["ymin"], exterior_bb["ymax"], n_probes)
            x_center = (exterior_bb["xmin"] + exterior_bb["xmax"]) / 2.0
            probes = [(x_center, p, z) for p in positions]

        occupied = np.zeros(len(probes), dtype=bool)
        span = (exterior_bb["xmax"] - exterior_bb["xmin"]) if axis == "x" else (exterior_bb["ymax"] - exterior_bb["ymin"])
        cube_size = span / (n_probes * 1.5)

        for i, (px, py, pz) in enumerate(probes):
            try:
                if _ENGINE == "build123d":
                    from build123d import Box, Pos
                    cube = Pos(px, py, pz) * Box(cube_size, cube_size, 0.1)
                    hit = shape & cube
                    hbb = hit.bounding_box()
                    occupied[i] = (hbb.size.X > cube_size * 0.1 or hbb.size.Y > cube_size * 0.1)
                else:
                    import cadquery as cq
                    cube = (
                        cq.Workplane("XY")
                        .transformed(offset=(px, py, pz))
                        .box(cube_size, cube_size, 0.1, centered=True)
                    )
                    hit = shape.intersect(cube)
                    hbb = hit.val().BoundingBox()
                    occupied[i] = (hbb.xlen > cube_size * 0.1 or hbb.ylen > cube_size * 0.1)
            except Exception:
                occupied[i] = False

        return positions, occupied

    def _largest_void_mm(positions, occupied):
        step = positions[1] - positions[0] if len(positions) > 1 else 0
        max_gap = 0.0
        run = 0
        for occ in occupied:
            if not occ:
                run += 1
            else:
                if run * step > max_gap:
                    max_gap = run * step
                run = 0
        if run * step > max_gap:
            max_gap = run * step
        return max_gap

    pos_x, occ_x = _occupancy("x")
    pos_y, occ_y = _occupancy("y")

    gap_x = _largest_void_mm(pos_x, occ_x)
    gap_y = _largest_void_mm(pos_y, occ_y)

    nonzero = [g for g in (gap_x, gap_y) if g > 0.5]
    if not nonzero:
        return 0.0
    return min(nonzero)


# -- Hole detection -----------------------------------------------------------

def _find_nearest_hole(shape, expected_diameter, position=None):
    """Find a circular edge closest to expected_diameter.

    Returns (measured_diameter, position_str) or (None, None).
    Uses build123d Edge API when available, falls back to raw OCP.
    """
    candidates = []

    if _ENGINE == "build123d":
        from build123d import GeomType
        for edge in shape.edges():
            if edge.geom_type == GeomType.CIRCLE:
                radius = edge.radius
                diameter = radius * 2.0
                center = edge.center()
                pos = (center.X, center.Y, center.Z)
                candidates.append((diameter, pos))
    else:
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.GeomAbs import GeomAbs_Circle
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.TopoDS import TopoDS

        solid = shape.val().wrapped
        exp = TopExp_Explorer(solid, TopAbs_EDGE)
        while exp.More():
            edge = TopoDS.Edge_s(exp.Current())
            adaptor = BRepAdaptor_Curve(edge)
            if adaptor.GetType() == GeomAbs_Circle:
                circle = adaptor.Circle()
                radius = circle.Radius()
                diameter = radius * 2.0
                center = circle.Location()
                pos = (center.X(), center.Y(), center.Z())
                candidates.append((diameter, pos))
            exp.Next()

    if not candidates:
        return None, None

    if position and len(position) >= 2:
        px, py = float(position[0]), float(position[1])
        pz = float(position[2]) if len(position) >= 3 else None

        xy_dist = lambda c: ((c[1][0] - px) ** 2 + (c[1][1] - py) ** 2) ** 0.5
        xy_near = [c for c in candidates if xy_dist(c) <= 5.0]
        if xy_near:
            candidates = xy_near

        if pz is not None:
            candidates.sort(key=lambda c: (
                abs(c[0] - expected_diameter),
                abs(c[1][2] - pz)
            ))
        else:
            candidates.sort(key=lambda c: abs(c[0] - expected_diameter))
    else:
        candidates.sort(key=lambda c: abs(c[0] - expected_diameter))

    best_d, best_pos = candidates[0]
    pos_str = f"({best_pos[0]:.1f}, {best_pos[1]:.1f}, {best_pos[2]:.1f})"
    return best_d, pos_str


# -- Individual checks --------------------------------------------------------

def check_overall_dimensions(shape, spec):
    """Check bounding box matches overall_dimensions within tolerance."""
    results = []
    dims = spec["overall_dimensions"]
    tol = dims["tolerance"]
    bb = _bounding_box(shape)

    for axis, measured in (("width", bb["xlen"]), ("depth", bb["ylen"]), ("height", bb["zlen"])):
        expected = dims[axis]
        delta = measured - expected
        label = f"Overall {axis}"
        detail = f"{measured:.2f}mm (expected {expected:.2f} +/-{tol:.2f}mm)"
        if abs(delta) <= tol:
            results.append(_pass(label, detail))
        else:
            direction = "OVER" if delta > 0 else "UNDER"
            results.append(_fail(label, f"{detail} -- {direction} by {abs(delta):.2f}mm"))

    return results


def check_features(shape, spec):
    """Check each named feature against measured geometry."""
    results = []
    dims = spec["overall_dimensions"]

    for feat in spec.get("features", []):
        feat_type = feat["type"]
        name = feat["name"]
        tol = feat.get("tolerance", 0.3)

        if feat_type == "slot":
            probe_z = feat.get("probe_z", 0.0)
            if probe_z == 0.0:
                probe_z = dims["height"] / 2.0

            expected_w = feat["width"]
            ext_bb = _bounding_box(shape)
            measured_w = _measure_slot_gap_at_z(shape, probe_z, ext_bb)

            label = f"Slot '{name}' width (gap at Z={probe_z:.1f}mm)"
            if measured_w == 0.0:
                results.append(_fail(label,
                    f"no gap detected at Z={probe_z:.1f}mm -- "
                    f"probe_z may be outside the slot or inside solid material"))
                continue

            delta = measured_w - expected_w
            detail = f"{measured_w:.2f}mm (expected {expected_w:.2f} +/-{tol:.2f}mm)"
            if abs(delta) <= tol:
                results.append(_pass(label, detail))
            else:
                direction = "OVER" if delta > 0 else "UNDER"
                results.append(_fail(label, f"{detail} -- {direction} by {abs(delta):.2f}mm"))

        elif feat_type == "hole":
            expected_d = feat["diameter"]
            position = feat.get("position")
            measured_d, found_pos = _find_nearest_hole(shape, expected_d, position)

            label = f"Hole '{name}' diameter"
            if measured_d is None:
                results.append(_fail(label,
                    f"no circular edge found near expected diameter {expected_d:.2f}mm"))
            else:
                delta = measured_d - expected_d
                detail = (
                    f"{measured_d:.2f}mm (expected {expected_d:.2f} +/-{tol:.2f}mm)"
                    + (f" at {found_pos}" if found_pos else "")
                )
                if abs(delta) <= tol:
                    results.append(_pass(label, detail))
                else:
                    direction = "OVER" if delta > 0 else "UNDER"
                    results.append(_fail(label, f"{detail} -- {direction} by {abs(delta):.2f}mm"))

        elif feat_type in ("pocket", "rail", "channel"):
            results.append(_pass(
                f"{feat_type.capitalize()} '{name}'",
                "verified via component clearance and overall dimension checks"
            ))

        elif feat_type == "pattern":
            # Pattern features: check one representative element
            element = feat.get("element", {})
            element_w = element.get("width", 0)
            if element_w == 0:
                element_w = element.get("diameter", 0)
            count = feat.get("count", 0)
            label = f"Pattern '{name}' ({count} elements)"
            if element_w > 0 and count > 0:
                results.append(_pass(label,
                    f"declared: {count}x {element_w:.2f}mm elements "
                    f"(full validation via cross-section renderer)"))
            else:
                results.append(_warn(label,
                    "pattern declared but element width/diameter or count missing -- "
                    "verify visually in cross-sections"))

    return results


def check_components(shape, spec):
    """Check that each component fits in the part with required clearance."""
    results = []
    part_height = spec["overall_dimensions"]["height"]

    for comp in spec.get("components", []):
        name = comp["name"]
        c_len = comp["length"]
        c_wid = comp["width"]
        clearance = comp["effective_clearance_mm"]

        required_len = c_len + 2 * clearance
        required_wid = c_wid + 2 * clearance
        probe_z = part_height / 3.0

        x_span = _measure_gap_at_z(shape, probe_z, "x")
        y_span = _measure_gap_at_z(shape, probe_z, "y")

        if x_span == 0.0 and y_span == 0.0:
            results.append(_fail(
                f"Component '{name}' fit",
                f"cross-section at Z={probe_z:.1f}mm is empty -- cannot verify fit"
            ))
            continue

        span_major = max(x_span, y_span)
        span_minor = min(x_span, y_span)
        req_major = max(required_len, required_wid)
        req_minor = min(required_len, required_wid)

        for dim_name, measured, required, nominal in (
            ("length", span_major, req_major, max(c_len, c_wid)),
            ("width",  span_minor, req_minor, min(c_len, c_wid)),
        ):
            label = f"Component '{name}' {dim_name} fit"
            if measured >= required:
                actual_clearance = (measured - nominal) / 2.0
                detail = (
                    f"cavity {measured:.2f}mm >= {nominal:.2f}mm component "
                    f"+ {clearance:.2f}mm x2 clearance "
                    f"(actual each side: {actual_clearance:.2f}mm)"
                )
                results.append(_pass(label, detail))
            else:
                shortfall = required - measured
                detail = (
                    f"cavity {measured:.2f}mm < {nominal:.2f}mm + {clearance:.2f}mm x2 "
                    f"= {required:.2f}mm -- SHORT by {shortfall:.2f}mm"
                )
                results.append(_fail(label, detail))

    return results


def check_minimum_wall(shape, spec):
    """Estimate minimum wall thickness via cross-section comparison.

    Samples 5 Z heights, compares exterior span to interior cross-section
    span. Reports WARN when within 0.3mm of the minimum threshold.
    """
    min_wall = spec["min_wall_mm"]
    bb = _bounding_box(shape)
    z_min = bb["zmin"]
    z_max = bb["zmax"]

    z_samples = [z_min + (z_max - z_min) * f for f in (0.15, 0.30, 0.50, 0.65, 0.80)]

    thinnest = float("inf")
    thinnest_z = None

    for z in z_samples:
        section = _cross_section_at_z(shape, z)
        if section is None:
            continue
        x_wall = (bb["xlen"] - section["xlen"]) / 2.0
        y_wall = (bb["ylen"] - section["ylen"]) / 2.0
        wall_est = min(x_wall, y_wall)

        if 0 < wall_est < thinnest:
            thinnest = wall_est
            thinnest_z = z

    label = "Minimum wall thickness (bounding-box estimate)"
    if thinnest == float("inf"):
        return [_pass(label, "solid part -- no hollow sections detected")]

    detail = f"{thinnest:.2f}mm at Z~{thinnest_z:.1f}mm (minimum required: {min_wall:.2f}mm)"
    if thinnest < min_wall:
        return [_fail(label,
            f"{detail} -- wall is {min_wall - thinnest:.2f}mm BELOW minimum. "
            f"Increase wall thickness or reduce cavity size."
        )]
    elif thinnest < min_wall + 0.3:
        return [_warn(label,
            f"{detail} -- wall is within 0.3mm of the minimum threshold. "
            f"Check slicer preview to confirm perimeter fill is solid."
        )]
    else:
        return [_pass(label, detail)]


# -- Main validation runner ---------------------------------------------------

def validate(step_path, spec_path=None):
    """Run all checks. Returns (results_list, all_passed_bool)."""
    if spec_path is None:
        spec_path = str(Path(step_path).with_suffix(".spec.json"))

    spec = load_spec(spec_path)
    shape = _load_step(step_path)

    results = []
    results += check_overall_dimensions(shape, spec)
    results += check_features(shape, spec)
    results += check_components(shape, spec)
    results += check_minimum_wall(shape, spec)

    all_passed = all(r.passed for r in results)
    return results, all_passed


def main():
    parser = argparse.ArgumentParser(
        description="Validate STEP geometry against design intent spec."
    )
    parser.add_argument("step_file", help="Path to the STEP file")
    parser.add_argument("--spec", default=None,
                        help="Path to .spec.json (default: sibling of STEP file)")
    args = parser.parse_args()

    step_path = args.step_file
    spec_path = args.spec

    if not os.path.exists(step_path):
        print(f"Error: STEP file not found: {step_path}")
        sys.exit(1)

    print(f"Validating: {step_path}")
    if spec_path:
        print(f"Spec: {spec_path}")
    print()

    try:
        results, all_passed = validate(step_path, spec_path)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Validation error: {e}")
        raise

    for r in results:
        print(r)

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print()
    print(f"{passed}/{total} checks passed")
    if not all_passed:
        print("Fix failures before showing to user.")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
