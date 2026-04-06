"""Phase 1: Parametric radius gauge leaf body generator.

Two leaf architectures:
  - SMALL (dual-ended dogbone, R <= 12.7mm):
    Convex arc on one end, 80-deg concave corner on the other,
    40-deg concave edge notch on the side. Body sides follow arc
    tangent at each end for G1-continuous transitions.

  - MEDIUM/LARGE (talon, R > 12.7mm):
    Convex and concave arcs share a tip. Body lines depart from
    arc endpoints along tangent direction, then connect to spine.
    40-deg edge notch on the back spine. String hole in body.

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
    RadiusArc,
    extrude,
    export_step,
    fillet,
    make_face,
)

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

FORM_FACTORS = {
    "small": {
        "architecture": "dual_ended",
        "thickness": 2.0,
        "convex_sweep": 120,
        "concave_corner_sweep": 80,
        "concave_edge_sweep": 40,
        "hole_dia": 4.0,
        "corner_r": 1.0,
        "flare_length": 3.0,       # tangent flare from convex arc (short)
        "handle_length": 12.0,     # straight handle section
        "min_total_length": 25.0,  # minimum tip-to-tip
    },
    "medium": {
        "architecture": "talon",
        "thickness": 2.2,
        "convex_sweep": 90,
        "concave_corner_sweep": 80,
        "concave_edge_sweep": 40,
        "jaw_angle": 160,
        "hole_dia": 5.0,
        "corner_r": 2.0,
        "tip_r": 0.4,
        "body_extension_factor": 0.5,
        "min_body_extension": 20.0,
    },
    "large": {
        "architecture": "talon",
        "thickness": 2.5,
        "convex_sweep": 60,
        "concave_corner_sweep": 80,
        "concave_edge_sweep": 40,
        "jaw_angle": 140,
        "hole_dia": 6.0,
        "corner_r": 3.0,
        "tip_r": 0.6,
        "body_extension_factor": 0.4,
        "min_body_extension": 25.0,
    },
}


def classify_ring(radius_mm: float) -> str:
    if radius_mm <= 12.7:
        return "small"
    elif radius_mm <= 50.8:
        return "medium"
    return "large"


def _pt(cx, cy, r, angle_deg):
    """Point on circle at angle (degrees) from center."""
    a = math.radians(angle_deg)
    return (cx + r * math.cos(a), cy + r * math.sin(a))


# ---------------------------------------------------------------------------
# Dual-ended dogbone (small rings)
# ---------------------------------------------------------------------------

def _build_dual_ended(r: float, f: dict):
    """Build a dual-ended leaf: convex arc on one end, concave scoop on other.

    Coordinate system:
      - Convex arc centered at origin, tip at (+r, 0)
      - Body extends in -X direction
      - Concave scoop bites into the left end of the body

    The concave scoop endpoints sit on the body's left edge.
    The arc curves rightward (+X) into the body like a bite.
    """
    half_cvx = f["convex_sweep"] / 2.0
    half_ccv = f["concave_corner_sweep"] / 2.0
    half_edge = f["concave_edge_sweep"] / 2.0
    thickness = f["thickness"]
    hole_dia = f["hole_dia"]
    corner_r = f["corner_r"]

    # --- Convex arc (centered at origin) ---
    cvx_top = _pt(0, 0, r, half_cvx)
    cvx_bot = _pt(0, 0, r, -half_cvx)

    # Body half-width = Y of convex arc endpoints
    hw = cvx_top[1]

    # --- Concave arc positioning ---
    # Arc endpoints sit on the body's left edge at y = ±ccv_hw.
    # The arc center is placed so the scoop curves rightward into the body.
    total_len = max(f["min_total_length"], 3.0 * r + 10.0)
    body_left_x = -(total_len - r)

    # Half-width of the concave scoop on the left edge
    ccv_hw = r * math.sin(math.radians(half_ccv))

    # Arc endpoints on the body's left edge
    ccv_top = (body_left_x, ccv_hw)
    ccv_bot = (body_left_x, -ccv_hw)

    # --- Edge notch on top edge (40-deg concave) ---
    handle_start_x = cvx_top[0]
    handle_end_x = body_left_x
    handle_mid_x = (handle_start_x + handle_end_x) / 2.0
    notch_dx = r * math.sin(math.radians(half_edge))

    notch_cx = handle_mid_x
    margin = 2.0
    if notch_cx - notch_dx < handle_end_x + margin:
        notch_cx = handle_end_x + margin + notch_dx
    if notch_cx + notch_dx > handle_start_x - margin:
        notch_cx = handle_start_x - margin - notch_dx

    notch_right = (notch_cx + notch_dx, hw)
    notch_left = (notch_cx - notch_dx, hw)

    # --- String hole ---
    hole_x = handle_mid_x
    hole_y = 0.0

    # --- Build CCW profile ---
    with BuildPart() as part:
        with BuildSketch() as sk:
            with BuildLine() as ln:
                # 1. Convex arc: bot -> top, bulging right (+X).
                RadiusArc(cvx_bot, cvx_top, -r)

                # 2. Top edge with notch
                Line(cvx_top, notch_right)
                RadiusArc(notch_right, notch_left, r)

                # 3. Top side to concave scoop top
                if abs(ccv_hw - hw) > 0.1:
                    # Body is wider than concave arc: run to body corner,
                    # then drop to scoop endpoint
                    Line(notch_left, (body_left_x, hw))
                    Line((body_left_x, hw), ccv_top)
                else:
                    Line(notch_left, ccv_top)

                # 4. Concave scoop arc: top -> bot (scooping rightward into body).
                #    Positive r = minor arc = curves toward +X (into body).
                RadiusArc(ccv_top, ccv_bot, r)

                # 5. Bottom side back to convex
                if abs(ccv_hw - hw) > 0.1:
                    Line(ccv_bot, (body_left_x, -hw))
                    Line((body_left_x, -hw), cvx_bot)
                else:
                    Line(ccv_bot, cvx_bot)

            make_face()
        extrude(amount=thickness)

        # String hole
        with Locations([(hole_x, hole_y)]):
            Hole(radius=hole_dia / 2.0, depth=thickness)

        # Fillet cosmetic body corners only (not gauging surfaces)
        _fillet_body_corners(part, corner_r, gauging_x_min=body_left_x,
                            gauging_x_max=cvx_top[0])

    return part.part


# ---------------------------------------------------------------------------
# Talon architecture (medium/large)
# ---------------------------------------------------------------------------

def _build_talon(r: float, f: dict):
    """Build a talon leaf with G1-continuous transitions.

    Horizontal orientation: tip at right (+X), body extends left (-X).
    Convex arc sweeps upward from tip, concave arc sweeps downward.
    Tangent lines depart arc endpoints for G1 continuity, then
    vertical segments connect to the back spine.
    """
    cvx_sweep = f["convex_sweep"]
    ccv_sweep = f["concave_corner_sweep"]
    half_edge = f["concave_edge_sweep"] / 2.0
    jaw_angle = f["jaw_angle"]
    thickness = f["thickness"]
    hole_dia = f["hole_dia"]
    corner_r = f["corner_r"]
    tip_r = f["tip_r"]
    half_jaw = jaw_angle / 2.0

    # --- Arc centers ---
    # Tip at origin, jaw opens rightward (+X). The bisector of the jaw
    # angle lies along +X. Convex center is left-and-slightly-below,
    # concave center is left-and-slightly-above (mirror about X axis).
    # The angle (90 - half_jaw) measures the tilt of the radius from
    # the -X axis toward the tip.
    cvx_cx = -r * math.cos(math.radians(90 - half_jaw))
    cvx_cy = -r * math.sin(math.radians(90 - half_jaw))
    ccv_cx = cvx_cx
    ccv_cy = -cvx_cy

    # --- Convex arc: tip to cvx_end (CCW, sweeps upward then left) ---
    tip_angle_cvx = math.degrees(math.atan2(0 - cvx_cy, 0 - cvx_cx))
    cvx_end_angle = tip_angle_cvx + cvx_sweep
    cvx_end = _pt(cvx_cx, cvx_cy, r, cvx_end_angle)
    # CCW tangent at cvx_end: +90 from radius direction
    cvx_tan = (math.cos(math.radians(cvx_end_angle + 90)),
               math.sin(math.radians(cvx_end_angle + 90)))

    # --- Concave arc: tip to ccv_end (CW, sweeps downward then left) ---
    tip_angle_ccv = math.degrees(math.atan2(0 - ccv_cy, 0 - ccv_cx))
    ccv_end_angle = tip_angle_ccv - ccv_sweep
    ccv_end = _pt(ccv_cx, ccv_cy, r, ccv_end_angle)
    # CW tangent at ccv_end: -90 from radius direction
    ccv_tan = (math.cos(math.radians(ccv_end_angle - 90)),
               math.sin(math.radians(ccv_end_angle - 90)))

    # --- Body layout ---
    # Short tangent departure for G1 continuity, then vertical to spine Y,
    # then horizontal spine connecting top and bottom.
    body_ext = max(f["min_body_extension"], r * f["body_extension_factor"])
    tang_len = min(5.0, 0.2 * r)

    # Extend tangent from convex end
    top_tang_end = (cvx_end[0] + tang_len * cvx_tan[0],
                    cvx_end[1] + tang_len * cvx_tan[1])

    # Extend tangent from concave end
    bot_tang_end = (ccv_end[0] + tang_len * ccv_tan[0],
                    ccv_end[1] + tang_len * ccv_tan[1])

    # Spine Y: vertical back edge, left of everything.
    # Place it body_ext past the leftmost tangent endpoint.
    spine_x = min(top_tang_end[0], bot_tang_end[0]) - body_ext
    spine_x = min(spine_x, -body_ext * 0.3)

    # Vertical segments from tangent endpoints down/up to spine
    top_spine = (spine_x, top_tang_end[1])
    bot_spine = (spine_x, bot_tang_end[1])

    # --- Edge notch on the back spine (vertical left edge) ---
    spine_mid_y = (top_spine[1] + bot_spine[1]) / 2.0
    spine_len = abs(top_spine[1] - bot_spine[1])
    notch_hh = r * math.sin(math.radians(half_edge))
    if spine_len < 4 * notch_hh:
        notch_hh = spine_len * 0.2

    notch_top = (spine_x, spine_mid_y + notch_hh)
    notch_bot = (spine_x, spine_mid_y - notch_hh)

    # --- String hole ---
    hole_x = (spine_x + min(cvx_end[0], ccv_end[0])) / 2.0
    hole_y = spine_mid_y

    # --- Build CCW profile ---
    with BuildPart() as part:
        with BuildSketch() as sk:
            with BuildLine() as ln:
                # Convex arc: tip -> cvx_end (CCW, positive r)
                RadiusArc((0, 0), cvx_end, r)

                # Top tangent departure (G1)
                Line(cvx_end, top_tang_end)

                # Vertical to spine (top)
                if abs(top_tang_end[0] - spine_x) > 0.01:
                    Line(top_tang_end, top_spine)

                # Spine top -> notch top
                Line(top_spine, notch_top)

                # Edge notch: vertical, curving into body (+X direction)
                RadiusArc(notch_top, notch_bot, r)

                # Notch bot -> spine bot
                Line(notch_bot, bot_spine)

                # Vertical from spine to bottom tangent start
                if abs(bot_tang_end[0] - spine_x) > 0.01:
                    Line(bot_spine, bot_tang_end)

                # Bottom tangent line to ccv_end (G1)
                Line(bot_tang_end, ccv_end)

                # Concave arc: ccv_end -> tip
                RadiusArc(ccv_end, (0, 0), -r)

            make_face()
        extrude(amount=thickness)

        with Locations([(hole_x, hole_y)]):
            Hole(radius=hole_dia / 2.0, depth=thickness)

        # Fillet body corners and tip
        z_edges = part.part.edges().filter_by(Axis.Z)
        tip_edges = []
        body_corners = []
        for e in z_edges:
            c = e.center()
            if math.hypot(c.X, c.Y) < 2.0:
                tip_edges.append(e)
            elif c.X < min(cvx_end[0], ccv_end[0]) - 1.0:
                body_corners.append(e)

        if body_corners:
            try:
                fillet(body_corners, radius=corner_r)
            except Exception:
                try:
                    fillet(body_corners, radius=corner_r * 0.5)
                except Exception:
                    pass

        if tip_edges and tip_r > 0:
            try:
                fillet(tip_edges, radius=tip_r)
            except Exception:
                pass

    return part.part


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fillet_body_corners(part, corner_r, gauging_x_min, gauging_x_max):
    """Fillet Z-parallel edges that are not on gauging surfaces."""
    z_edges = part.part.edges().filter_by(Axis.Z)
    body_corners = []
    for e in z_edges:
        c = e.center()
        if gauging_x_min + 1.0 < c.X < gauging_x_max - 1.0:
            body_corners.append(e)

    if body_corners:
        try:
            fillet(body_corners, radius=corner_r)
        except Exception:
            try:
                fillet(body_corners, radius=corner_r * 0.5)
            except Exception:
                pass


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
    return _build_talon(radius_mm, f)


def build_representative_leaves():
    """Build one leaf per form factor for Phase 1 validation."""
    reps = {
        "small": 6.35,
        "medium": 25.4,
        "large": 76.2,
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
