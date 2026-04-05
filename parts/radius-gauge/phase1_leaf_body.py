"""Phase 1: Parametric radius gauge leaf body generator.

Two leaf architectures:
  - SMALL (dual-ended): Convex on one end, concave on the other, side notch
  - MEDIUM/LARGE (talon): Convex and concave arcs share a tip, meet at a point.
    40-deg edge notch on the spine. String hole in body meat.

No text/labeling — that's Phase 2.

Usage:
    python phase1_leaf_body.py                  # builds 3 representative leaves
    python phase1_leaf_body.py --radius 6.35    # single leaf at 1/4" (6.35mm)
"""

import math
import sys
from pathlib import Path

from build123d import (
    Axis,
    BuildLine,
    BuildPart,
    BuildSketch,
    Hole,
    Line,
    Locations,
    Mode,
    RadiusArc,
    extrude,
    export_step,
    fillet,
    make_face,
)

# ---------------------------------------------------------------------------
# Form factor parameters by ring size
# ---------------------------------------------------------------------------

FORM_FACTORS = {
    "small": {
        "architecture": "dual_ended",
        "thickness": 2.0,
        "convex_sweep": 120,
        "hole_dia": 4.0,
        "relief_r": 0.8,
        "corner_r": 1.5,
        "body_width": 12.0,
        "min_handle": 30.0,
    },
    "medium": {
        "architecture": "talon",
        "thickness": 2.2,
        "convex_sweep": 90,
        "jaw_angle": 160,  # degrees between convex/concave at tip
        "hole_dia": 5.0,
        "relief_r": 1.0,
        "corner_r": 2.0,
        "body_extension_factor": 0.5,
        "min_body_extension": 20.0,
    },
    "large": {
        "architecture": "talon",
        "thickness": 2.5,
        "convex_sweep": 60,
        "jaw_angle": 140,  # tighter jaw = more material efficient at large radii
        "hole_dia": 6.0,
        "relief_r": 1.2,
        "corner_r": 3.0,
        "body_extension_factor": 0.4,
        "min_body_extension": 25.0,
    },
}

CONCAVE_CORNER_SWEEP = 80  # degrees
CONCAVE_EDGE_SWEEP = 40    # degrees


def classify_ring(radius_mm: float) -> str:
    """Classify a radius into small/medium/large ring."""
    if radius_mm <= 12.7:   # up to 1/2"
        return "small"
    elif radius_mm <= 50.8:  # up to 2"
        return "medium"
    return "large"


# ---------------------------------------------------------------------------
# SMALL: Dual-ended architecture
# ---------------------------------------------------------------------------

def _build_dual_ended(r: float, f: dict):
    """Build a small dual-ended leaf: convex top, concave bottom, side notch."""
    hw = f["body_width"] / 2.0
    cvx_half = f["convex_sweep"] / 2.0
    ccv_half = CONCAVE_CORNER_SWEEP / 2.0
    edge_half = CONCAVE_EDGE_SWEEP / 2.0

    # Convex tangent spread
    cvx_tangent_x = r * math.sin(math.radians(cvx_half))
    main_hw = max(hw, cvx_tangent_x)

    # Handle length
    handle_len = max(f["min_handle"], 2.0 * r + 15.0)
    body_top = handle_len / 2.0
    body_bot = -handle_len / 2.0

    # Convex tangent points
    cvx_r_x = r * math.sin(math.radians(cvx_half))
    cvx_r_y = body_top + r * math.cos(math.radians(cvx_half))
    cvx_l_x = -cvx_r_x
    cvx_l_y = cvx_r_y

    # Concave notch geometry
    ccv_notch_hw = r * math.sin(math.radians(ccv_half))
    if ccv_notch_hw > hw:
        effective_ccv_half = math.degrees(math.asin(hw / r))
        ccv_notch_hw = hw
    else:
        effective_ccv_half = ccv_half

    # Side notch geometry
    edge_notch_hw = r * math.sin(math.radians(edge_half))
    available_side = handle_len * 0.4
    if 2 * edge_notch_hw > available_side:
        edge_notch_hw = available_side / 2.0

    notch_top = edge_notch_hw
    notch_bot = -edge_notch_hw

    with BuildPart() as part:
        with BuildSketch() as sk:
            with BuildLine() as ln:
                # Convex arc: right tangent -> left tangent
                RadiusArc((cvx_r_x, cvx_r_y), (cvx_l_x, cvx_l_y), r)

                # Left side down
                if cvx_tangent_x < main_hw:
                    Line((cvx_l_x, cvx_l_y), (-main_hw, cvx_l_y))
                    Line((-main_hw, cvx_l_y), (-main_hw, body_bot))
                else:
                    Line((cvx_l_x, cvx_l_y), (-main_hw, body_bot))

                # Concave corner arc at bottom
                if ccv_notch_hw < main_hw:
                    Line((-main_hw, body_bot), (-ccv_notch_hw, body_bot))
                RadiusArc((-ccv_notch_hw, body_bot), (ccv_notch_hw, body_bot), -r)
                if ccv_notch_hw < main_hw:
                    Line((ccv_notch_hw, body_bot), (main_hw, body_bot))

                # Right side up with edge notch (concave into body)
                Line((main_hw, body_bot), (main_hw, notch_bot))
                RadiusArc((main_hw, notch_bot), (main_hw, notch_top), r)

                # Right side to convex tangent
                if cvx_tangent_x < main_hw:
                    Line((main_hw, notch_top), (main_hw, cvx_r_y))
                    Line((main_hw, cvx_r_y), (cvx_r_x, cvx_r_y))
                else:
                    Line((main_hw, notch_top), (cvx_r_x, cvx_r_y))

            make_face()
        extrude(amount=f["thickness"])

        # String hole — offset toward concave end
        hole_y = body_bot + abs(body_bot) * 0.35
        with Locations([(0, hole_y)]):
            Hole(radius=f["hole_dia"] / 2.0, depth=f["thickness"])

        # Fillet all Z-parallel corners for comfort.
        # Skip the string hole edges (small radius, near hole center).
        z_edges = part.part.edges().filter_by(Axis.Z)
        hole_y = body_bot + abs(body_bot) * 0.35
        corner_r = f["corner_r"]
        body_corners = [e for e in z_edges
                        if not (abs(e.center().Y - hole_y) < f["hole_dia"]
                                and abs(e.center().X) < f["hole_dia"])]
        if body_corners:
            try:
                fillet(body_corners, radius=corner_r)
            except Exception:
                try:
                    fillet(body_corners, radius=corner_r * 0.5)
                except Exception:
                    pass

    return part.part


# ---------------------------------------------------------------------------
# MEDIUM/LARGE: Talon architecture
# ---------------------------------------------------------------------------

def _build_talon(r: float, f: dict):
    """Build a talon leaf: convex and concave arcs share a tip.

    The jaw_angle controls how open the talon is at the tip:
      - 180 = jaws straight across (widest body)
      - 140 = tighter pinch (more material efficient for large radii)

    Layout (tip pointing right, +X):
      - Tip at origin (0, 0)
      - Convex arc center above-left of tip, at distance r
      - Concave arc center below-left of tip, at distance r
      - Body extends left from arc endpoints
      - 40-deg edge notch on the back (left) spine
      - String hole in body meat
    """
    cvx_sweep = f["convex_sweep"]
    ccv_sweep = CONCAVE_CORNER_SWEEP
    edge_sweep = CONCAVE_EDGE_SWEEP
    jaw_angle = f["jaw_angle"]
    thickness = f["thickness"]
    hole_dia = f["hole_dia"]
    half_jaw = jaw_angle / 2.0

    # --- Arc centers ---
    # The convex arc center is above the tip, rotated so the jaw opening
    # has the specified angle. At jaw_angle=180, centers are at (0, +-r).
    # As jaw_angle decreases, centers rotate toward -X (behind the tip).
    cvx_cx = -r * math.cos(math.radians(half_jaw))
    cvx_cy = r * math.sin(math.radians(half_jaw))

    ccv_cx = cvx_cx
    ccv_cy = -cvx_cy

    # --- Convex arc endpoints ---
    # Tip is at angle (360 - half_jaw) from convex center (pointing toward tip).
    # Sweep CCW by cvx_sweep degrees.
    tip_angle_cvx = 360 - half_jaw
    cvx_end_angle = tip_angle_cvx - cvx_sweep
    cvx_end_x = cvx_cx + r * math.cos(math.radians(cvx_end_angle))
    cvx_end_y = cvx_cy + r * math.sin(math.radians(cvx_end_angle))

    # --- Concave arc endpoints ---
    # Tip is at angle half_jaw from concave center.
    # Sweep CW by ccv_sweep degrees.
    tip_angle_ccv = half_jaw
    ccv_end_angle = tip_angle_ccv + ccv_sweep
    ccv_end_x = ccv_cx + r * math.cos(math.radians(ccv_end_angle))
    ccv_end_y = ccv_cy + r * math.sin(math.radians(ccv_end_angle))

    # --- Body extension ---
    body_ext = max(f["min_body_extension"], r * f["body_extension_factor"])
    body_left = min(cvx_end_x, ccv_end_x) - body_ext

    # --- 40-deg edge notch on the back spine (left side) ---
    edge_half = edge_sweep / 2.0
    edge_notch_hw = r * math.sin(math.radians(edge_half))
    spine_length = cvx_end_y - ccv_end_y
    if spine_length < 4 * edge_notch_hw:
        # Spine too short for notch — scale down
        edge_notch_hw = spine_length * 0.2

    spine_mid_y = (cvx_end_y + ccv_end_y) / 2.0
    edge_notch_top = spine_mid_y + edge_notch_hw
    edge_notch_bot = spine_mid_y - edge_notch_hw

    # --- String hole ---
    hole_x = body_left + body_ext * 0.45
    hole_y = spine_mid_y

    with BuildPart() as part:
        with BuildSketch() as sk:
            with BuildLine() as ln:
                # CONVEX ARC: tip -> cvx_end
                RadiusArc((0, 0), (cvx_end_x, cvx_end_y), r)

                # Top of body
                Line((cvx_end_x, cvx_end_y), (body_left, cvx_end_y))

                # Left spine with edge notch (concave into body)
                Line((body_left, cvx_end_y), (body_left, edge_notch_top))
                RadiusArc(
                    (body_left, edge_notch_top),
                    (body_left, edge_notch_bot),
                    r,
                )
                Line((body_left, edge_notch_bot), (body_left, ccv_end_y))

                # Bottom of body
                Line((body_left, ccv_end_y), (ccv_end_x, ccv_end_y))

                # CONCAVE ARC: ccv_end -> tip
                RadiusArc((ccv_end_x, ccv_end_y), (0, 0), -r)

            make_face()
        extrude(amount=thickness)

        # String hole
        with Locations([(hole_x, hole_y)]):
            Hole(radius=hole_dia / 2.0, depth=thickness)

        # Fillet all Z-parallel edges (corner pillars through thickness)
        # Body corners get full corner_r, tip gets a smaller comfort fillet
        corner_r = f["corner_r"]
        tip_r = min(corner_r * 0.5, r * 0.03)  # small relative to gauge radius
        z_edges = part.part.edges().filter_by(Axis.Z)

        # Separate tip from body corners
        tip_edges = []
        body_corners = []
        for e in z_edges:
            c = e.center()
            if abs(c.X) < 1.0 and abs(c.Y) < 1.0:
                tip_edges.append(e)
            else:
                body_corners.append(e)

        if body_corners:
            try:
                fillet(body_corners, radius=corner_r)
            except Exception:
                try:
                    fillet(body_corners, radius=corner_r * 0.5)
                except Exception:
                    pass

        if tip_edges:
            try:
                fillet(tip_edges, radius=tip_r)
            except Exception:
                pass

    return part.part


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_leaf(radius_mm: float, form_key: str = None):
    """Build a single leaf body."""
    if form_key is None:
        form_key = classify_ring(radius_mm)
    f = FORM_FACTORS[form_key]

    if f["architecture"] == "dual_ended":
        return _build_dual_ended(radius_mm, f)
    else:
        return _build_talon(radius_mm, f)


def build_representative_leaves():
    """Build one leaf per form factor for Phase 1 validation."""
    reps = {
        "small": 6.35,    # 1/4"
        "medium": 25.4,   # 1"
        "large": 76.2,    # 3"
    }

    out = Path(__file__).parent / "phase1_output"
    out.mkdir(exist_ok=True)

    for key, radius in reps.items():
        print(f"Building {key} leaf (R={radius}mm / {radius/25.4:.3f}\")...")
        leaf = build_leaf(radius, key)

        path = out / f"leaf_{key}_R{radius:.1f}mm.step"
        export_step(leaf, str(path))

        bb = leaf.bounding_box()
        print(f"  Architecture: {FORM_FACTORS[key]['architecture']}")
        print(f"  Volume:  {leaf.volume:.2f} mm^3")
        print(f"  BBox:    {bb.size.X:.2f} x {bb.size.Y:.2f} x {bb.size.Z:.2f} mm")
        print(f"  Exported: {path}")
        print()

    print(f"Output: {out}")


def build_single_leaf(radius_mm: float):
    """Build a single leaf, auto-classifying ring size."""
    key = classify_ring(radius_mm)
    print(f"Building leaf R={radius_mm}mm (ring: {key})...")
    leaf = build_leaf(radius_mm, key)

    out = Path(__file__).parent / "phase1_output"
    out.mkdir(exist_ok=True)

    path = out / f"leaf_R{radius_mm:.2f}mm.step"
    export_step(leaf, str(path))

    bb = leaf.bounding_box()
    print(f"  Architecture: {FORM_FACTORS[key]['architecture']}")
    print(f"  Volume:  {leaf.volume:.2f} mm^3")
    print(f"  BBox:    {bb.size.X:.2f} x {bb.size.Y:.2f} x {bb.size.Z:.2f} mm")
    print(f"  Exported: {path}")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--radius":
        build_single_leaf(float(sys.argv[2]))
    else:
        build_representative_leaves()
