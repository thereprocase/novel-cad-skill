"""Phase 1: Parametric radius gauge leaf body generator.

Generates leaf bodies with 3 gauging profiles:
  - End A (+Y): Convex arc (measures concave/inside features)
  - End B (-Y): 80-deg concave corner arc (measures fillets in 90-deg corners)
  - Side (+X): 40-deg concave edge notch (measures radii along an edge)

No text/labeling — that's Phase 2.

Usage:
    python phase1_leaf_body.py                  # builds 3 representative leaves
    python phase1_leaf_body.py --radius 6.35    # single leaf at 1/4" (6.35mm)
"""

import math
import sys
from pathlib import Path

from build123d import (
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
    make_face,
)

# ---------------------------------------------------------------------------
# Form factor parameters by ring size
# ---------------------------------------------------------------------------

FORM_FACTORS = {
    "small": {
        "thickness": 2.0,
        "convex_sweep": 120,
        "hole_dia": 4.0,
        "relief_r": 0.8,
        "body_width": 12.0,
        "min_handle": 30.0,
    },
    "medium": {
        "thickness": 2.2,
        "convex_sweep": 90,
        "hole_dia": 5.0,
        "relief_r": 1.0,
        "body_width": 16.0,
        "min_handle": 40.0,
    },
    "large": {
        "thickness": 2.5,
        "convex_sweep": 60,
        "hole_dia": 6.0,
        "relief_r": 1.2,
        "body_width": 22.0,
        "min_handle": 55.0,
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


def build_leaf(radius_mm: float, form_key: str = None):
    """Build a single leaf body as a build123d Part.

    Profile traced clockwise from convex-right tangent point:
      1. Convex arc across the top (left to right from viewer, but we trace R->L)
      2. Left side down
      3. Concave corner arc across the bottom
      4. Right side up, with concave edge notch at midpoint
      5. Close back to start
    """
    if form_key is None:
        form_key = classify_ring(radius_mm)
    f = FORM_FACTORS[form_key]

    r = radius_mm
    hw = f["body_width"] / 2.0
    cvx_half = f["convex_sweep"] / 2.0
    ccv_half = CONCAVE_CORNER_SWEEP / 2.0
    edge_half = CONCAVE_EDGE_SWEEP / 2.0

    # --- Convex end geometry (top, +Y) ---
    # Arc center at (0, body_top). Tangent points where arc meets body sides.
    # For the convex arc: the tangent point x = r*sin(half_angle)
    cvx_tangent_x = r * math.sin(math.radians(cvx_half))

    # If the convex tangent spread is wider than body, body widens there.
    # If narrower, we add horizontal transitions.
    cvx_body_hw = max(hw, cvx_tangent_x)

    # Body length: enough for handle between features
    handle_len = max(f["min_handle"], 2.5 * r + 15.0)
    body_top = handle_len / 2.0
    body_bot = -handle_len / 2.0

    # Convex tangent points (relative to arc center at y=body_top)
    cvx_r = (cvx_tangent_x, body_top + r * math.cos(math.radians(cvx_half)))
    cvx_l = (-cvx_tangent_x, cvx_r[1])

    # --- Concave corner geometry (bottom, -Y) ---
    # Notch opening half-width
    ccv_notch_hw = r * math.sin(math.radians(ccv_half))

    # If notch wider than body, clamp sweep to fit body width
    if ccv_notch_hw > hw:
        effective_ccv_half = math.degrees(math.asin(hw / r))
        ccv_notch_hw = hw
    else:
        effective_ccv_half = ccv_half

    ccv_depth = r * (1.0 - math.cos(math.radians(effective_ccv_half)))

    # Concave arc endpoints: notch opens downward from body_bot
    ccv_l = (-ccv_notch_hw, body_bot)
    ccv_r = (ccv_notch_hw, body_bot)
    # Arc bottom point at (0, body_bot - ccv_depth)

    # --- Side notch geometry (right side, +X) ---
    edge_notch_hw = r * math.sin(math.radians(edge_half))

    # If notch chord exceeds available side length, scale down
    available_side = handle_len * 0.4  # use 40% of handle for notch
    if 2 * edge_notch_hw > available_side:
        edge_notch_hw = available_side / 2.0
        edge_half = math.degrees(math.asin(edge_notch_hw / r))

    edge_notch_depth = r * (1.0 - math.cos(math.radians(edge_half)))
    notch_center_y = 0.0  # mid-body
    notch_top = notch_center_y + edge_notch_hw
    notch_bot = notch_center_y - edge_notch_hw

    # Use the wider of convex spread or body width for the main body
    main_hw = cvx_body_hw

    # --- Build the closed profile ---
    with BuildPart() as part:
        with BuildSketch() as sk:
            with BuildLine() as ln:
                # 1. CONVEX ARC: right tangent -> left tangent (counterclockwise)
                RadiusArc(cvx_r, cvx_l, r)

                # 2. LEFT SIDE: transition from convex tangent down to body_bot
                if cvx_tangent_x < main_hw:
                    # Horizontal transition from convex tangent to body edge
                    Line(cvx_l, (-main_hw, cvx_l[1]))
                    Line((-main_hw, cvx_l[1]), (-main_hw, body_bot))
                else:
                    Line(cvx_l, (-main_hw, body_bot))

                # 3. CONCAVE CORNER ARC at bottom
                if ccv_notch_hw < main_hw:
                    # Shelf from body edge to notch edge
                    Line((-main_hw, body_bot), ccv_l)

                # Concave arc: left to right, curving downward (negative radius)
                RadiusArc(ccv_l, ccv_r, -r)

                if ccv_notch_hw < main_hw:
                    # Shelf from notch edge back to body edge
                    Line(ccv_r, (main_hw, body_bot))

                # 4. RIGHT SIDE with edge notch
                # Bottom of right side up to notch
                Line((main_hw, body_bot), (main_hw, notch_bot))

                # Edge notch: concave arc curving inward (negative radius)
                RadiusArc(
                    (main_hw, notch_bot),
                    (main_hw, notch_top),
                    -r,
                )

                # Top of right side up to convex tangent
                if cvx_tangent_x < main_hw:
                    Line((main_hw, notch_top), (main_hw, cvx_r[1]))
                    Line((main_hw, cvx_r[1]), cvx_r)
                else:
                    Line((main_hw, notch_top), cvx_r)

            make_face()

        # Extrude to leaf thickness
        extrude(amount=f["thickness"])

        # --- STRING HOLE ---
        # Offset toward concave end, 35% up from bottom
        hole_y = body_bot + abs(body_bot) * 0.35
        hole_r = f["hole_dia"] / 2.0

        with Locations([(0, hole_y)]):
            Hole(radius=hole_r, depth=f["thickness"])

    return part.part


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
    print(f"  Volume:  {leaf.volume:.2f} mm^3")
    print(f"  BBox:    {bb.size.X:.2f} x {bb.size.Y:.2f} x {bb.size.Z:.2f} mm")
    print(f"  Exported: {path}")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--radius":
        build_single_leaf(float(sys.argv[2]))
    else:
        build_representative_leaves()
