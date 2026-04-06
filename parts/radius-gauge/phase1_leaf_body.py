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
        "jaw_angle": 110,
        "hole_dia": 5.0,
        "corner_r": 2.0,
        "tip_r": 0.4,
        "back_bulge": 0.5,         # fraction of r for back curve outward bulge
        "min_back_padding": 12.0,  # min padding beyond arc endpoints for hole/text
    },
    "large": {
        "architecture": "talon",
        "thickness": 2.5,
        "convex_sweep": 60,
        "concave_corner_sweep": 80,
        "concave_edge_sweep": 40,
        "jaw_angle": 90,
        "hole_dia": 6.0,
        "corner_r": 3.0,
        "tip_r": 0.6,
        "back_bulge": 0.30,
        "min_back_padding": 10.0,
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
    # Offset toward concave-corner end: 35% from concave end toward convex end.
    # This lets leaves hang with convex end up on the ring string.
    hole_x = body_left_x + 0.35 * (cvx_top[0] - body_left_x)
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
    """Build a talon-shaped leaf — tight hook like a raptor's claw.

    The tip is at the origin with the jaw opening rightward (+X).
    Convex arc sweeps upward from the tip, concave arc sweeps downward.
    Tangent lines depart from arc endpoints for G1 continuity, then a
    smooth back arc connects them to form a teardrop/talon silhouette.
    The 40-deg concave edge notch sits on the concave-side tangent line
    (non-gauging surface). String hole is in the widest part of the body.
    """
    cvx_sweep = f["convex_sweep"]
    ccv_sweep = f["concave_corner_sweep"]
    half_edge = f["concave_edge_sweep"] / 2.0
    jaw_angle = f["jaw_angle"]
    thickness = f["thickness"]
    hole_dia = f["hole_dia"]
    corner_r = f["corner_r"]
    tip_r = f["tip_r"]
    back_bulge = f["back_bulge"]
    min_back_pad = f["min_back_padding"]
    half_jaw = jaw_angle / 2.0

    # --- Arc centers ---
    # Tip at origin. The jaw bisector is along +X.
    # Convex center below the jaw bisector, concave center above.
    cvx_cx = -r * math.cos(math.radians(90 - half_jaw))
    cvx_cy = -r * math.sin(math.radians(90 - half_jaw))
    ccv_cx = cvx_cx
    ccv_cy = -cvx_cy

    # --- Convex arc: tip -> cvx_end (CCW, sweeps upward then back) ---
    tip_angle_cvx = math.degrees(math.atan2(0 - cvx_cy, 0 - cvx_cx))
    cvx_end_angle = tip_angle_cvx + cvx_sweep
    cvx_end = _pt(cvx_cx, cvx_cy, r, cvx_end_angle)
    cvx_tan_angle = cvx_end_angle + 90

    # --- Concave arc: tip -> ccv_end (CW, sweeps downward then back) ---
    tip_angle_ccv = math.degrees(math.atan2(0 - ccv_cy, 0 - ccv_cx))
    ccv_end_angle = tip_angle_ccv - ccv_sweep
    ccv_end = _pt(ccv_cx, ccv_cy, r, ccv_end_angle)
    ccv_tan_angle = ccv_end_angle - 90

    # --- Tangent departures for G1 continuity ---
    # Tangent length scales with radius but must be long enough to
    # create a body region that fits the string hole with wall margin.
    min_tang_for_hole = hole_dia + 6.0  # hole diameter + wall on each side
    tang_len = max(min_tang_for_hole, 0.3 * r)
    cvx_depart = (cvx_end[0] + tang_len * math.cos(math.radians(cvx_tan_angle)),
                  cvx_end[1] + tang_len * math.sin(math.radians(cvx_tan_angle)))
    ccv_depart = (ccv_end[0] + tang_len * math.cos(math.radians(ccv_tan_angle)),
                  ccv_end[1] + tang_len * math.sin(math.radians(ccv_tan_angle)))

    # --- Back connecting arc ---
    back_dx = ccv_depart[0] - cvx_depart[0]
    back_dy = ccv_depart[1] - cvx_depart[1]
    back_chord = math.hypot(back_dx, back_dy)
    back_mid = ((cvx_depart[0] + ccv_depart[0]) / 2.0,
                (cvx_depart[1] + ccv_depart[1]) / 2.0)

    # Bulge direction: perpendicular to chord, pointing away from tip.
    chord_angle = math.atan2(back_dy, back_dx)
    perp_angle = chord_angle - math.pi / 2.0
    bulge_dist = max(back_bulge * r, min_back_pad)
    if math.cos(perp_angle) > 0:
        perp_angle += math.pi

    half_chord = back_chord / 2.0
    sagitta = max(bulge_dist, 0.1)
    back_r = (sagitta * sagitta + half_chord * half_chord) / (2.0 * sagitta)

    # --- Edge notch on the concave-side tangent line ---
    # The notch is a concave scallop (40-deg arc) cut into the tangent
    # line between ccv_end and ccv_depart. Place it at the midpoint.
    ccv_tang_dx = math.cos(math.radians(ccv_tan_angle))
    ccv_tang_dy = math.sin(math.radians(ccv_tan_angle))
    notch_half_len = r * math.sin(math.radians(half_edge))
    # Clamp notch size to fit on the tangent line
    if notch_half_len * 2 > tang_len * 0.6:
        notch_half_len = tang_len * 0.3
    notch_center_t = tang_len * 0.5  # midpoint of tangent line
    notch_t1 = notch_center_t - notch_half_len
    notch_t2 = notch_center_t + notch_half_len
    notch_p1 = (ccv_end[0] + notch_t1 * ccv_tang_dx,
                ccv_end[1] + notch_t1 * ccv_tang_dy)
    notch_p2 = (ccv_end[0] + notch_t2 * ccv_tang_dx,
                ccv_end[1] + notch_t2 * ccv_tang_dy)

    # --- String hole ---
    # Back arc center for computing the apex (thickest point).
    back_center = (back_mid[0] + (back_r - sagitta) * math.cos(perp_angle + math.pi),
                   back_mid[1] + (back_r - sagitta) * math.sin(perp_angle + math.pi))
    back_a_mid_angle = math.atan2(
        back_mid[1] + sagitta * math.sin(perp_angle) - back_center[1],
        back_mid[0] + sagitta * math.cos(perp_angle) - back_center[0])
    back_apex = (back_center[0] + back_r * math.cos(back_a_mid_angle),
                 back_center[1] + back_r * math.sin(back_a_mid_angle))

    # Place hole between cvx_depart and back apex.
    hole_center = (0.55 * cvx_depart[0] + 0.45 * back_apex[0],
                   0.55 * cvx_depart[1] + 0.45 * back_apex[1])
    hole_r = hole_dia / 2.0

    # --- Build profile ---
    with BuildPart() as part:
        with BuildSketch() as sk:
            with BuildLine() as ln:
                # 1. Convex arc: tip -> cvx_end (unbroken gauging surface)
                RadiusArc((0, 0), cvx_end, r)

                # 2. G1 tangent departure from convex end
                Line(cvx_end, cvx_depart)

                # 3. Back arc: smooth curve connecting the two tangent
                #    departure points, bulging away from the tip.
                RadiusArc(cvx_depart, ccv_depart, -back_r)

                # 4. Concave-side tangent: ccv_depart -> notch -> ccv_end
                #    Split into three parts with a concave scallop notch.
                Line(ccv_depart, notch_p2)

                # 5. Edge notch: 40-deg concave arc on the tangent line.
                #    Positive r = the arc curves inward (toward the body).
                RadiusArc(notch_p2, notch_p1, r)

                # 6. Rest of tangent line to concave arc endpoint
                Line(notch_p1, ccv_end)

                # 7. Concave arc: ccv_end -> tip (unbroken gauging surface)
                RadiusArc(ccv_end, (0, 0), -r)

            make_face()
        extrude(amount=thickness)

        # String hole
        with Locations([(hole_center[0], hole_center[1])]):
            Hole(radius=hole_r, depth=thickness)

        # Fillet tip
        z_edges = part.part.edges().filter_by(Axis.Z)
        tip_edges = []
        for e in z_edges:
            c = e.center()
            if math.hypot(c.X, c.Y) < 2.0:
                tip_edges.append(e)

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
