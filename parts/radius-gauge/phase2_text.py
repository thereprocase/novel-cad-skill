"""Phase 2: Multi-body text labels for radius gauge leaves.

Adds debossed text inlays for multi-color 3D printing (MMU).
Each leaf produces 3 bodies:
  - leaf: main body with debossed pockets (blue SAE / red metric)
  - text_top: text inlay filling top-face pockets (white)
  - text_bottom: text inlay filling bottom-face pockets (white)

Usage:
    python phase2_text.py                # builds R=6.35mm test leaf with text
    python phase2_text.py --radius 6.35  # same, explicit
"""

import math
import sys
from pathlib import Path

from build123d import (
    BuildPart,
    BuildSketch,
    Compound,
    FontStyle,
    Hole,
    Locations,
    Mode,
    Plane,
    Text,
    add,
    extrude,
    export_step,
)

# ---------------------------------------------------------------------------
# Import phase 1 leaf builder
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
from phase1_leaf_body import (
    FORM_FACTORS,
    build_leaf,
    classify_ring,
    _pt,
)

# ---------------------------------------------------------------------------
# Text layout parameters
# ---------------------------------------------------------------------------

DEBOSS_DEPTH = 0.5  # mm — depth of text pocket
MIN_TEXT_HEIGHT = 4.0  # mm
PREFERRED_TEXT_HEIGHT = 6.0  # mm
TEXT_FONT = "Arial"


def _fraction_label(radius_mm: float) -> str:
    """Convert radius in mm to SAE fraction string.

    Returns the simplest fraction representation. For sizes >= 1",
    uses mixed number format: "1", "1-1/8", "2-1/4", etc.
    """
    from fractions import Fraction

    inches = radius_mm / 25.4

    # Snap to nearest 1/32 (finest resolution in the gauge set)
    thirty_seconds = round(inches * 32)
    frac = Fraction(thirty_seconds, 32)

    whole = int(frac)
    remainder = frac - whole

    if remainder == 0:
        return str(whole) if whole > 0 else "0"
    elif whole == 0:
        return f"{remainder.numerator}/{remainder.denominator}"
    else:
        return f"{whole}-{remainder.numerator}/{remainder.denominator}"


def _decimal_label(radius_mm: float) -> str:
    """Convert radius to decimal inches string."""
    inches = radius_mm / 25.4
    return f"{inches:.3f}"


def _metric_label(radius_mm: float) -> str:
    """Format metric radius label."""
    if radius_mm == int(radius_mm):
        return f"{int(radius_mm)}mm"
    return f"{radius_mm:.1f}mm"


def _compute_text_area_small(radius_mm: float, form: dict):
    """Compute available text area on a small dual-ended leaf.

    Returns (center_x, center_y, available_width, available_height,
             hole_x, hole_y, hole_r).
    The text area is the clear rectangle between the string hole
    and the convex arc end. This avoids text/hole overlap.
    """
    r = radius_mm
    half_cvx = form["convex_sweep"] / 2.0
    total_len = max(form["min_total_length"], 3.0 * r + 10.0)
    body_left_x = -(total_len - r)

    # Convex arc top point
    cvx_top = _pt(0, 0, r, half_cvx)

    # Half-width of body
    hw = cvx_top[1]

    # String hole position (matches phase1_leaf_body.py)
    hole_x = (cvx_top[0] + body_left_x) / 2.0
    hole_y = 0.0
    hole_r = form["hole_dia"] / 2.0

    # Text area: between the hole's right edge and the convex arc.
    # 1.5mm margin from hole edge, 3mm margin from convex arc.
    text_left = hole_x + hole_r + 1.5
    text_right = cvx_top[0] - 3.0
    text_width = text_right - text_left
    text_height = 2.0 * hw - 2.0  # 1mm margin each side

    # If text area between hole and convex end is too narrow,
    # try the other side (between hole and concave end).
    if text_width < 6.0:
        alt_left = body_left_x + 3.0
        alt_right = hole_x - hole_r - 1.5
        alt_width = alt_right - alt_left
        if alt_width > text_width:
            text_left = alt_left
            text_right = alt_right
            text_width = alt_width

    center_x = (text_left + text_right) / 2.0
    center_y = 0.0

    return center_x, center_y, text_width, text_height, hole_x, hole_y, hole_r


def _compute_text_area_talon(radius_mm: float, form: dict):
    """Compute available text area on a talon (medium/large) leaf.

    The talon has tip at origin, body extending left (-X).
    Text area is the rectangle between the arc endpoints and the spine,
    avoiding the string hole.

    Returns (center_x, center_y, available_width, available_height,
             hole_x, hole_y, hole_r).
    """
    r = radius_mm
    cvx_sweep = form["convex_sweep"]
    ccv_sweep = form["concave_corner_sweep"]
    jaw_angle = form["jaw_angle"]
    hole_dia = form["hole_dia"]
    half_jaw = jaw_angle / 2.0

    # Replicate arc center / endpoint math from _build_talon
    cvx_cx = -r * math.cos(math.radians(90 - half_jaw))
    cvx_cy = -r * math.sin(math.radians(90 - half_jaw))
    ccv_cx = cvx_cx
    ccv_cy = -cvx_cy

    tip_angle_cvx = math.degrees(math.atan2(0 - cvx_cy, 0 - cvx_cx))
    cvx_end_angle = tip_angle_cvx + cvx_sweep
    cvx_end = _pt(cvx_cx, cvx_cy, r, cvx_end_angle)

    tip_angle_ccv = math.degrees(math.atan2(0 - ccv_cy, 0 - ccv_cx))
    ccv_end_angle = tip_angle_ccv - ccv_sweep
    ccv_end = _pt(ccv_cx, ccv_cy, r, ccv_end_angle)

    # Tangent extensions
    cvx_tan_dir = (math.cos(math.radians(cvx_end_angle + 90)),
                   math.sin(math.radians(cvx_end_angle + 90)))
    ccv_tan_dir = (math.cos(math.radians(ccv_end_angle - 90)),
                   math.sin(math.radians(ccv_end_angle - 90)))

    tang_len = min(5.0, 0.2 * r)
    top_tang_end = (cvx_end[0] + tang_len * cvx_tan_dir[0],
                    cvx_end[1] + tang_len * cvx_tan_dir[1])
    bot_tang_end = (ccv_end[0] + tang_len * ccv_tan_dir[0],
                    ccv_end[1] + tang_len * ccv_tan_dir[1])

    body_ext = max(form["min_body_extension"], r * form["body_extension_factor"])
    spine_x = min(top_tang_end[0], bot_tang_end[0]) - body_ext
    spine_x = min(spine_x, -body_ext * 0.3)

    # String hole (same as _build_talon)
    spine_mid_y = (top_tang_end[1] + bot_tang_end[1]) / 2.0
    hole_x = (spine_x + min(cvx_end[0], ccv_end[0])) / 2.0
    hole_y = spine_mid_y
    hole_r = hole_dia / 2.0

    # Text area: right boundary is arc endpoints, left boundary is spine.
    # Use the leftmost arc endpoint X as the right boundary (with margin).
    arc_left_x = min(cvx_end[0], ccv_end[0])
    text_right = arc_left_x - 3.0   # 3mm margin from arcs
    text_left = spine_x + 3.0       # 3mm margin from spine

    # Vertical bounds: between top and bottom tangent endpoints
    text_top_y = top_tang_end[1] - 1.5   # 1.5mm margin from top edge
    text_bot_y = bot_tang_end[1] + 1.5   # 1.5mm margin from bottom edge

    text_width = text_right - text_left
    text_height = text_top_y - text_bot_y

    # Avoid the string hole. The hole is a circle at (hole_x, hole_y).
    # Strategy: shift the text center Y away from the hole if needed,
    # keeping the full width. Only split horizontally as a last resort.
    hole_margin = hole_r + 1.5
    center_x = (text_left + text_right) / 2.0
    center_y = (text_top_y + text_bot_y) / 2.0

    # Check if hole is within the text rectangle
    if (text_left < hole_x + hole_margin and
            hole_x - hole_margin < text_right and
            text_bot_y < hole_y + hole_margin and
            hole_y - hole_margin < text_top_y):
        # Try shifting text center Y above or below the hole
        # The text only occupies a band of ~font_height centered on center_y.
        # Preferred text height is 6mm, so the band is about 6mm tall.
        text_band = PREFERRED_TEXT_HEIGHT + 2.0  # text height + margin

        # Option A: place text above hole
        above_y = hole_y + hole_margin + text_band / 2.0
        # Option B: place text below hole
        below_y = hole_y - hole_margin - text_band / 2.0

        if above_y + text_band / 2.0 <= text_top_y:
            center_y = above_y
        elif below_y - text_band / 2.0 >= text_bot_y:
            center_y = below_y
        else:
            # Cannot shift vertically; split horizontally
            zone_a_left = hole_x + hole_margin
            zone_a_width = text_right - zone_a_left
            zone_b_right = hole_x - hole_margin
            zone_b_width = zone_b_right - text_left

            if zone_a_width >= zone_b_width and zone_a_width > 0:
                text_left = zone_a_left
                text_width = zone_a_width
            elif zone_b_width > 0:
                text_right = zone_b_right
                text_width = zone_b_width
            center_x = (text_left + text_right) / 2.0

    return center_x, center_y, text_width, text_height, hole_x, hole_y, hole_r


def _fit_text_size(label: str, available_width: float, available_height: float,
                   preferred: float = PREFERRED_TEXT_HEIGHT,
                   minimum: float = MIN_TEXT_HEIGHT) -> float:
    """Determine font size that fits the available area.

    Uses an empirical width estimate: each character is roughly
    0.6x the font height for sans-serif bold.
    """
    # Approximate text width at a given font size
    def est_width(font_size):
        # Fraction characters like "/" are narrower
        char_width = font_size * 0.6
        return len(label) * char_width

    # Start at preferred, shrink until it fits
    size = preferred
    while size >= minimum:
        w = est_width(size)
        if w <= available_width and size <= available_height:
            return size
        size -= 0.5

    return minimum  # clamp to minimum even if tight


def build_leaf_with_text(
    radius_mm: float,
    system: str = "sae",
    form_key: str = None,
):
    """Build a leaf with debossed text, returning 3 named bodies.

    Returns:
        dict with keys 'leaf', 'text_top', 'text_bottom'
        Each value is a build123d Part/Solid.
    """
    if form_key is None:
        form_key = classify_ring(radius_mm)
    form = FORM_FACTORS[form_key]
    thickness = form["thickness"]

    # --- Step 1: Build the base leaf body ---
    leaf_body = build_leaf(radius_mm, form_key)

    # --- Step 2: Determine text content and placement ---
    if system == "sae":
        top_label = _fraction_label(radius_mm)
        bot_label = _decimal_label(radius_mm)
    else:
        top_label = _metric_label(radius_mm)
        bot_label = top_label  # same on both sides for metric

    # Check if secondary (decimal) label fits. If the text would overlap
    # the string hole significantly, fall back to primary on both faces.
    # "When space permits" per spec — small leaves don't permit it.

    if form_key == "small":
        cx, cy, aw, ah, hole_x, hole_y, hole_r = _compute_text_area_small(
            radius_mm, form
        )
    else:
        cx, cy, aw, ah, hole_x, hole_y, hole_r = _compute_text_area_talon(
            radius_mm, form
        )

    font_size = _fit_text_size(top_label, aw, ah)

    # Check if secondary label fits the available text area.
    # For small leaves, also check string hole clearance since the text area
    # may not account for hole overlap. For talon leaves, the text area
    # already avoids the hole.
    if system == "sae" and bot_label != top_label:
        bot_test_size = _fit_text_size(bot_label, aw, ah)
        est_bot_width = len(bot_label) * bot_test_size * 0.6
        if form_key == "small":
            # Small leaves: additional hole clearance check
            hole_clear = 2.0 * (hole_r + 1.0)
            max_width = aw - hole_clear
        else:
            # Talon leaves: text area already avoids hole
            max_width = aw
        if est_bot_width > max_width:
            print(f"  Secondary label '{bot_label}' too wide "
                  f"({est_bot_width:.1f}mm vs {max_width:.1f}mm). "
                  f"Using primary on both faces.")
            bot_label = top_label

    print(f"  Top: '{top_label}' at {font_size}mm, "
          f"Bot: '{bot_label}' on {aw:.1f}x{ah:.1f}mm area")

    # --- Step 3: Create debossed leaf (subtract text from body) ---
    # Top face is at Z = thickness
    top_z = thickness
    bot_z = 0.0

    # Create text sketch on top face, deboss into leaf
    with BuildPart() as debossed:
        add(leaf_body)

        # Deboss top text
        top_plane = Plane(origin=(cx, cy, top_z), z_dir=(0, 0, 1))
        with BuildSketch(top_plane) as top_sk:
            Text(top_label, font_size=font_size, font=TEXT_FONT,
                 font_style=FontStyle.BOLD)
        extrude(amount=-DEBOSS_DEPTH, mode=Mode.SUBTRACT)

        # Deboss bottom text (from bottom face, into the body).
        # Force x_dir=(1,0,0) so text reads correctly when part is flipped.
        bot_font_size = _fit_text_size(bot_label, aw, ah)
        bot_plane = Plane(origin=(cx, cy, bot_z), z_dir=(0, 0, -1),
                          x_dir=(1, 0, 0))
        with BuildSketch(bot_plane) as bot_sk:
            Text(bot_label, font_size=bot_font_size, font=TEXT_FONT,
                 font_style=FontStyle.BOLD)
        extrude(amount=-DEBOSS_DEPTH, mode=Mode.SUBTRACT)

    debossed_leaf = debossed.part

    # --- Step 4: Create text inlay bodies ---
    # Top text inlay: fills the debossed pocket on top face
    with BuildPart() as top_text:
        top_plane = Plane(origin=(cx, cy, top_z - DEBOSS_DEPTH), z_dir=(0, 0, 1))
        with BuildSketch(top_plane) as ts:
            Text(top_label, font_size=font_size, font=TEXT_FONT,
                 font_style=FontStyle.BOLD)
        extrude(amount=DEBOSS_DEPTH)

        # Subtract string hole so inlay doesn't float over the hole
        with Locations([(hole_x, hole_y)]):
            Hole(radius=hole_r, depth=DEBOSS_DEPTH)

    text_top_body = top_text.part

    # Bottom text inlay: fills the debossed pocket on bottom face.
    # Match x_dir=(1,0,0) so inlay aligns with deboss pocket.
    with BuildPart() as bot_text:
        bot_plane_inlay = Plane(
            origin=(cx, cy, bot_z + DEBOSS_DEPTH), z_dir=(0, 0, -1),
            x_dir=(1, 0, 0),
        )
        with BuildSketch(bot_plane_inlay) as bs:
            Text(bot_label, font_size=bot_font_size, font=TEXT_FONT,
                 font_style=FontStyle.BOLD)
        extrude(amount=DEBOSS_DEPTH)

        # Subtract string hole so inlay doesn't float over the hole
        with Locations([(hole_x, hole_y)]):
            Hole(radius=hole_r, depth=DEBOSS_DEPTH)

    text_bot_body = bot_text.part

    return {
        "leaf": debossed_leaf,
        "text_top": text_top_body,
        "text_bottom": text_bot_body,
    }


def export_multibody(bodies: dict, filepath: str, label: str = "radius_gauge"):
    """Export multi-body assembly as a single STEP file."""
    # Label each body
    bodies["leaf"].label = "leaf"
    bodies["text_top"].label = "text_top"
    bodies["text_bottom"].label = "text_bottom"

    assembly = Compound(
        label=label,
        children=[bodies["leaf"], bodies["text_top"], bodies["text_bottom"]],
    )
    export_step(assembly, filepath)
    return assembly


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    radius = 6.35  # default: 1/4" SAE
    system = "sae"

    if len(sys.argv) > 2 and sys.argv[1] == "--radius":
        radius = float(sys.argv[2])
    if len(sys.argv) > 3:
        system = sys.argv[3]

    form_key = classify_ring(radius)
    print(f"Phase 2: Building leaf R={radius}mm ({form_key}, {system})")

    bodies = build_leaf_with_text(radius, system=system, form_key=form_key)

    out = Path(__file__).parent / "phase2_output"
    out.mkdir(exist_ok=True)

    # Export individual bodies for inspection
    for name, body in bodies.items():
        path = out / f"leaf_R{radius:.2f}mm_{name}.step"
        export_step(body, str(path))
        bb = body.bounding_box()
        print(f"  {name}: {bb.size.X:.2f} x {bb.size.Y:.2f} x {bb.size.Z:.2f} mm, "
              f"vol={body.volume:.2f} mm^3")

    # Export multi-body assembly
    assembly_path = out / f"leaf_R{radius:.2f}mm_assembly.step"
    export_multibody(bodies, str(assembly_path),
                     label=f"radius_gauge_R{radius:.2f}mm")
    print(f"\n  Assembly: {assembly_path}")


if __name__ == "__main__":
    main()
