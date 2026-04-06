"""V2 Small leaf body generator — dual-ended dogbone.

Convex arc on one end, 80-deg concave scoop on the other,
40-deg concave edge notch on the top edge.

V1 lessons:
  - Don't use G1 tangent flare — creates cat ear artifacts
  - Body width = convex arc endpoint spread (no shelf, no flare)
  - Concave scoop is a clean bite, no prongs
  - Edge notch must be concave INTO body (positive RadiusArc)

Coordinate system:
  - Convex arc centered at origin, tip at (+r, 0)
  - Body extends in -X direction
  - Concave scoop bites into the left end
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


DOGBONE_PARAMS = {
    "thickness": 2.0,
    "convex_sweep": 120,
    "concave_corner_sweep": 80,
    "concave_edge_sweep": 40,
    "hole_dia": 4.0,
    "corner_r": 1.0,
    "tip_r": 0.3,
}


def build_dogbone(r: float, params: dict = None):
    """Build a small dual-ended dogbone leaf.

    Returns the Part object.
    """
    if params is None:
        params = DOGBONE_PARAMS
    half_cvx = params["convex_sweep"] / 2.0
    half_ccv = params["concave_corner_sweep"] / 2.0
    half_edge = params["concave_edge_sweep"] / 2.0
    thickness = params["thickness"]
    hole_dia = params["hole_dia"]
    corner_r = params["corner_r"]

    # --- Convex arc (centered at origin) ---
    cvx_top = _pt(0, 0, r, half_cvx)
    cvx_bot = _pt(0, 0, r, -half_cvx)
    hw = cvx_top[1]  # body half-width = Y of convex endpoints

    # --- Total length ---
    total_len = max(25.0, 3.0 * r + 10.0)
    body_left_x = -(total_len - r)

    # --- Concave scoop: endpoints on body left edge ---
    ccv_hw = r * math.sin(math.radians(half_ccv))
    ccv_top = (body_left_x, ccv_hw)
    ccv_bot = (body_left_x, -ccv_hw)

    # --- Edge notch on top edge ---
    handle_start_x = cvx_top[0]
    handle_end_x = body_left_x
    handle_mid_x = (handle_start_x + handle_end_x) / 2.0
    notch_dx = r * math.sin(math.radians(half_edge))

    notch_cx = handle_mid_x
    margin = 2.0
    notch_cx = max(notch_cx, handle_end_x + margin + notch_dx)
    notch_cx = min(notch_cx, handle_start_x - margin - notch_dx)

    notch_right = (notch_cx + notch_dx, hw)
    notch_left = (notch_cx - notch_dx, hw)

    # --- String hole: offset toward concave end (35% from left) ---
    hole_x = body_left_x + 0.35 * (cvx_top[0] - body_left_x)

    # --- Build profile ---
    with BuildPart() as part:
        with BuildSketch() as sk:
            with BuildLine() as ln:
                # Convex arc: bot -> top, bulging right
                RadiusArc(cvx_bot, cvx_top, -r)

                # Top edge with notch
                Line(cvx_top, notch_right)
                RadiusArc(notch_right, notch_left, r)  # concave into body

                # Top side to concave region
                if abs(ccv_hw - hw) > 0.1:
                    Line(notch_left, (body_left_x, hw))
                    Line((body_left_x, hw), ccv_top)
                else:
                    Line(notch_left, ccv_top)

                # Concave scoop: positive r = minor arc scooping into body
                RadiusArc(ccv_top, ccv_bot, r)

                # Bottom side back to convex
                if abs(ccv_hw - hw) > 0.1:
                    Line(ccv_bot, (body_left_x, -hw))
                    Line((body_left_x, -hw), cvx_bot)
                else:
                    Line(ccv_bot, cvx_bot)

            make_face()
        extrude(amount=thickness)

        # String hole
        with Locations([(hole_x, 0.0)]):
            Hole(radius=hole_dia / 2.0, depth=thickness)

        # Hole chamfer
        hole_edges = [e for e in part.part.edges().filter_by(GeomType.CIRCLE)
                      if abs(e.radius - hole_dia / 2.0) < 0.1]
        if hole_edges:
            try:
                chamfer(hole_edges, length=0.2)
            except Exception:
                pass

        # Fillet cosmetic corners (not gauging surfaces)
        z_edges = part.part.edges().filter_by(Axis.Z)
        body_corners = [e for e in z_edges
                        if body_left_x + 1.0 < e.center().X < cvx_top[0] - 1.0]
        if body_corners:
            try:
                fillet(body_corners, radius=corner_r)
            except Exception:
                try:
                    fillet(body_corners, radius=corner_r * 0.5)
                except Exception:
                    print(f"  WARNING: Body corner fillet failed")

    return part.part


if __name__ == "__main__":
    out = Path(__file__).parent / "output"
    out.mkdir(exist_ok=True)

    r = 6.35  # 1/4"
    print(f"Building small dogbone (R={r}mm / {r/25.4:.3f}\")...")
    leaf = build_dogbone(r)
    bb = leaf.bounding_box()
    print(f"  BBox: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f}mm")
    print(f"  Volume: {leaf.volume:.0f}mm³")

    step_path = out / f"dogbone_small_R{r:.1f}mm.step"
    export_step(leaf, str(step_path))
    print(f"  Exported: {step_path}")
