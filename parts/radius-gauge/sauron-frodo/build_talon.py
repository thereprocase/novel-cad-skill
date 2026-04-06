"""V2 Talon leaf body generator — medium and large rings.

Design rules:
  - Only three surfaces need precision curves: convex arc, concave arc, edge notch
  - Everything else is straight lines — no bulge, no excess material
  - Never project body material into the workpiece mating zone
  - Hole boss: local widening only if needed for string hole wall thickness

Profile:
  tip → convex arc → tangent departure → straight line → (hole boss) →
  straight line → tangent departure → edge notch → concave arc → tip
"""

import math
import sys
from pathlib import Path

from build123d import (
    Axis,
    BuildLine,
    BuildPart,
    BuildSketch,
    GeomType,
    Hole,
    Line,
    Locations,
    RadiusArc,
    chamfer,
    extrude,
    export_step,
    fillet,
    make_face,
)

SKILL_DIR = Path.home() / ".claude/skills/novel-cad-skill"
sys.path.insert(0, str(SKILL_DIR / "lib"))
sys.path.insert(0, str(SKILL_DIR / "scripts"))


def _pt(cx, cy, r, angle_deg):
    a = math.radians(angle_deg)
    return (cx + r * math.cos(a), cy + r * math.sin(a))


TALON_PARAMS = {
    "medium": {
        "thickness": 2.2,
        "convex_sweep": 90,
        "concave_corner_sweep": 80,
        "concave_edge_sweep": 40,
        "jaw_angle": 110,
        "hole_dia": 5.0,
        "tip_r": 0.4,
        "min_wall_around_hole": 2.5,
    },
    "large": {
        "thickness": 2.5,
        "convex_sweep": 60,
        "concave_corner_sweep": 80,
        "concave_edge_sweep": 40,
        "jaw_angle": 90,
        "hole_dia": 6.0,
        "tip_r": 0.6,
        "min_wall_around_hole": 3.0,
    },
}


def build_talon(r: float, params: dict):
    """Build a talon leaf — straight-line back, no bulge."""
    cvx_sweep = params["convex_sweep"]
    ccv_sweep = params["concave_corner_sweep"]
    half_edge = params["concave_edge_sweep"] / 2.0
    jaw_angle = params["jaw_angle"]
    thickness = params["thickness"]
    hole_dia = params["hole_dia"]
    tip_r = params["tip_r"]
    half_jaw = jaw_angle / 2.0

    # --- Arc centers (tip at origin, jaw bisector along +X) ---
    cvx_cx = -r * math.cos(math.radians(90 - half_jaw))
    cvx_cy = -r * math.sin(math.radians(90 - half_jaw))
    ccv_cx = cvx_cx
    ccv_cy = -cvx_cy

    # --- Convex arc: tip → cvx_end ---
    tip_angle_cvx = math.degrees(math.atan2(-cvx_cy, -cvx_cx))
    cvx_end_angle = tip_angle_cvx + cvx_sweep
    cvx_end = _pt(cvx_cx, cvx_cy, r, cvx_end_angle)
    cvx_tan_angle = cvx_end_angle + 90

    # --- Concave arc: tip → ccv_end ---
    tip_angle_ccv = math.degrees(math.atan2(-ccv_cy, -ccv_cx))
    ccv_end_angle = tip_angle_ccv - ccv_sweep
    ccv_end = _pt(ccv_cx, ccv_cy, r, ccv_end_angle)
    ccv_tan_angle = ccv_end_angle - 90

    # --- Tangent departures: long enough to contain the string hole ---
    min_wall = params["min_wall_around_hole"]
    tang_len = max(hole_dia / 2.0 + min_wall, 0.06 * r)
    cvx_depart = (cvx_end[0] + tang_len * math.cos(math.radians(cvx_tan_angle)),
                  cvx_end[1] + tang_len * math.sin(math.radians(cvx_tan_angle)))
    ccv_depart = (ccv_end[0] + tang_len * math.cos(math.radians(ccv_tan_angle)),
                  ccv_end[1] + tang_len * math.sin(math.radians(ccv_tan_angle)))

    # --- Edge notch on concave tangent line ---
    # Only add notch if the tangent line is long enough to hold it
    # without creating thin fin artifacts. Need at least 2x the notch
    # chord length to leave structural material on both sides.
    ccv_tang_dx = math.cos(math.radians(ccv_tan_angle))
    ccv_tang_dy = math.sin(math.radians(ccv_tan_angle))
    notch_half_len = r * math.sin(math.radians(half_edge))
    min_tang_for_notch = notch_half_len * 2 + 4.0  # notch chord + 2mm margin each side
    has_notch = tang_len >= min_tang_for_notch

    if has_notch:
        notch_t1 = tang_len * 0.5 - notch_half_len
        notch_t2 = tang_len * 0.5 + notch_half_len
        notch_p1 = (ccv_end[0] + notch_t1 * ccv_tang_dx,
                    ccv_end[1] + notch_t1 * ccv_tang_dy)
        notch_p2 = (ccv_end[0] + notch_t2 * ccv_tang_dx,
                    ccv_end[1] + notch_t2 * ccv_tang_dy)

    # --- Back profile with optional hole boss ---
    back_dx = ccv_depart[0] - cvx_depart[0]
    back_dy = ccv_depart[1] - cvx_depart[1]
    back_len = math.hypot(back_dx, back_dy)
    back_unit = (back_dx / back_len, back_dy / back_len)

    # Perpendicular direction (outward, away from tip at origin)
    perp = (-back_unit[1], back_unit[0])
    back_mid = ((cvx_depart[0] + ccv_depart[0]) / 2.0,
                (cvx_depart[1] + ccv_depart[1]) / 2.0)
    if back_mid[0] * perp[0] + back_mid[1] * perp[1] < 0:
        perp = (back_unit[1], -back_unit[0])

    min_wall = params["min_wall_around_hole"]
    hole_r = hole_dia / 2.0
    boss_depth = hole_r + min_wall  # perpendicular outward from back line
    needs_boss = tang_len < boss_depth

    # Hole on the convex tangent line midpoint — widest part of the body,
    # far from the concave tangent junction where thin fins form.
    hole_center = ((cvx_end[0] + cvx_depart[0]) / 2.0,
                   (cvx_end[1] + cvx_depart[1]) / 2.0)

    # Boss geometry: rectangular bump along back line, centered at back midpoint
    boss_half_w = (hole_dia + 2 * min_wall) / 2.0  # half-width along back line
    boss_start_t = 0.5 - boss_half_w / back_len  # parametric position on back line
    boss_end_t = 0.5 + boss_half_w / back_len
    boss_start_t = max(0.05, boss_start_t)
    boss_end_t = min(0.95, boss_end_t)

    boss_p1 = (cvx_depart[0] + boss_start_t * back_dx,
               cvx_depart[1] + boss_start_t * back_dy)
    boss_p2 = (cvx_depart[0] + boss_end_t * back_dx,
               cvx_depart[1] + boss_end_t * back_dy)
    boss_p1_out = (boss_p1[0] + boss_depth * perp[0],
                   boss_p1[1] + boss_depth * perp[1])
    boss_p2_out = (boss_p2[0] + boss_depth * perp[0],
                   boss_p2[1] + boss_depth * perp[1])

    # --- Build profile ---
    with BuildPart() as part:
        with BuildSketch() as sk:
            with BuildLine() as ln:
                # Convex gauging arc
                RadiusArc((0, 0), cvx_end, r)
                # G1 tangent departure
                Line(cvx_end, cvx_depart)
                # Straight back — no boss, tangent lines are long enough for hole
                Line(cvx_depart, ccv_depart)
                # Concave tangent (with edge notch if tangent is long enough)
                if has_notch:
                    Line(ccv_depart, notch_p2)
                    RadiusArc(notch_p2, notch_p1, r)
                    Line(notch_p1, ccv_end)
                else:
                    Line(ccv_depart, ccv_end)
                # Concave gauging arc
                RadiusArc(ccv_end, (0, 0), -r)
            make_face()
        extrude(amount=thickness)

        # String hole
        with Locations([(hole_center[0], hole_center[1])]):
            Hole(radius=hole_r, depth=thickness)

        # Hole chamfer
        hole_edges = [e for e in part.part.edges().filter_by(GeomType.CIRCLE)
                      if abs(e.radius - hole_r) < 0.2]
        if hole_edges:
            try:
                chamfer(hole_edges, length=0.3)
            except Exception:
                pass

        # Fillet ALL Z-parallel edges (body corners + tip + junctions)
        # This rounds the sharp junction corners that create fin artifacts
        z_edges = part.part.edges().filter_by(Axis.Z)
        if z_edges:
            try:
                fillet(z_edges, radius=tip_r)
            except Exception:
                # Try individually — some edges may be too short
                for e in z_edges:
                    try:
                        fillet([e], radius=tip_r)
                    except Exception:
                        pass

    return part.part


if __name__ == "__main__":
    out = Path(__file__).parent / "output"
    out.mkdir(exist_ok=True)

    for name, params in TALON_PARAMS.items():
        r = 25.4 if name == "medium" else 76.2
        print(f"Building {name} talon (R={r}mm)...")
        leaf = build_talon(r, params)
        bb = leaf.bounding_box()
        print(f"  BBox: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f}mm")
        print(f"  Volume: {leaf.volume:.0f}mm³")

        step_path = out / f"talon_{name}_R{r:.1f}mm.step"
        export_step(leaf, str(step_path))
        print(f"  Exported: {step_path}")
        print()
