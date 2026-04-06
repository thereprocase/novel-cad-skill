"""V2 Phase 2: Multi-body text labels for radius gauge leaves.

Adds debossed text inlays for MMU printing. Imports label formatting
from v1, computes text area from v2 geometry.

Each leaf produces 3 bodies:
  - leaf: main body with debossed pockets
  - text_top: text inlay filling top-face pockets (white)
  - text_bottom: text inlay filling bottom-face pockets (white)
"""

import math
import sys
from pathlib import Path

from build123d import (
    BuildPart,
    BuildSketch,
    Color,
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

# Import v1 label formatting (proven correct)
sys.path.insert(0, str(Path(__file__).parent.parent))
from phase2_text import (
    _fraction_label,
    _decimal_label,
    _metric_label,
    _fit_text_size,
    DEBOSS_DEPTH,
    MIN_TEXT_HEIGHT,
    PREFERRED_TEXT_HEIGHT,
    TEXT_FONT,
)

# Import v2 builders
sys.path.insert(0, str(Path(__file__).parent))
from build_talon import build_talon, TALON_PARAMS, _pt
from build_dogbone import build_dogbone, DOGBONE_PARAMS


def _text_area_dogbone(r: float, params: dict):
    """Text area for small dual-ended dogbone."""
    half_cvx = params["convex_sweep"] / 2.0
    total_len = max(25.0, 3.0 * r + 10.0)
    body_left_x = -(total_len - r)
    cvx_top = _pt(0, 0, r, half_cvx)
    hw = cvx_top[1]

    hole_x = body_left_x + 0.35 * (cvx_top[0] - body_left_x)
    hole_r = params["hole_dia"] / 2.0

    text_left = hole_x + hole_r + 1.5
    text_right = cvx_top[0] - 3.0
    text_width = text_right - text_left
    text_height = 2.0 * hw - 2.0

    if text_width < 6.0:
        alt_left = body_left_x + 3.0
        alt_right = hole_x - hole_r - 1.5
        if alt_right - alt_left > text_width:
            text_left = alt_left
            text_right = alt_right
            text_width = alt_right - alt_left

    cx = (text_left + text_right) / 2.0
    return cx, 0.0, text_width, text_height, hole_x, 0.0, hole_r


def _text_area_talon(r: float, params: dict):
    """Text area for talon leaf (straight-back geometry).

    Text goes on the flat body area between the tangent departures
    and the back line, avoiding the hole boss.
    """
    jaw_angle = params["jaw_angle"]
    cvx_sweep = params["convex_sweep"]
    ccv_sweep = params["concave_corner_sweep"]
    half_jaw = jaw_angle / 2.0
    hole_dia = params["hole_dia"]

    cvx_cx = -r * math.cos(math.radians(90 - half_jaw))
    cvx_cy = -r * math.sin(math.radians(90 - half_jaw))
    ccv_cx = cvx_cx
    ccv_cy = -cvx_cy

    tip_angle_cvx = math.degrees(math.atan2(-cvx_cy, -cvx_cx))
    cvx_end_angle = tip_angle_cvx + cvx_sweep
    cvx_end = _pt(cvx_cx, cvx_cy, r, cvx_end_angle)
    cvx_tan_angle = cvx_end_angle + 90

    tip_angle_ccv = math.degrees(math.atan2(-ccv_cy, -ccv_cx))
    ccv_end_angle = tip_angle_ccv - ccv_sweep
    ccv_end = _pt(ccv_cx, ccv_cy, r, ccv_end_angle)
    ccv_tan_angle = ccv_end_angle - 90

    tang_len = max(3.0, 0.06 * r)
    cvx_depart = (cvx_end[0] + tang_len * math.cos(math.radians(cvx_tan_angle)),
                  cvx_end[1] + tang_len * math.sin(math.radians(cvx_tan_angle)))
    ccv_depart = (ccv_end[0] + tang_len * math.cos(math.radians(ccv_tan_angle)),
                  ccv_end[1] + tang_len * math.sin(math.radians(ccv_tan_angle)))

    # Back line midpoint (hole location)
    hole_center = (0.55 * cvx_depart[0] + 0.45 * ccv_depart[0],
                   0.55 * cvx_depart[1] + 0.45 * ccv_depart[1])
    hole_r = hole_dia / 2.0

    # Text area: on the body strip between the two tangent departure lines.
    # The body is thin — text goes along the convex tangent line (wider jaw).
    # Place text midway along the convex tangent, between the arc endpoint
    # and the departure point.
    cvx_mid = ((cvx_end[0] + cvx_depart[0]) / 2.0,
               (cvx_end[1] + cvx_depart[1]) / 2.0)

    # Available width: roughly along the back line direction
    text_width = max(tang_len * 2, 8.0)  # at least 8mm
    text_height = max(tang_len, 6.0)

    cx = cvx_mid[0]
    cy = cvx_mid[1]

    # If the convex tangent is too short for text, use the back line midpoint
    back_mid = ((cvx_depart[0] + ccv_depart[0]) / 2.0,
                (cvx_depart[1] + ccv_depart[1]) / 2.0)
    back_len = math.hypot(ccv_depart[0] - cvx_depart[0],
                          ccv_depart[1] - cvx_depart[1])
    if back_len > text_width:
        cx = back_mid[0]
        cy = back_mid[1]
        text_width = back_len * 0.6
        text_height = max(tang_len * 2, 6.0)

    return cx, cy, text_width, text_height, hole_center[0], hole_center[1], hole_r


def build_leaf_with_text(r: float, form_key: str, system: str = "sae"):
    """Build a labeled leaf. Returns dict with 'leaf', 'text_top', 'text_bottom'."""
    if form_key == "small":
        leaf_body = build_dogbone(r)
        params = DOGBONE_PARAMS
        cx, cy, aw, ah, hole_x, hole_y, hole_r = _text_area_dogbone(r, params)
        thickness = params["thickness"]
    else:
        params = TALON_PARAMS[form_key]
        leaf_body = build_talon(r, params)
        cx, cy, aw, ah, hole_x, hole_y, hole_r = _text_area_talon(r, params)
        thickness = params["thickness"]

    # Labels
    if system == "sae":
        top_label = _fraction_label(r)
        bot_label = _decimal_label(r)
    else:
        top_label = _metric_label(r)
        bot_label = top_label

    font_size = _fit_text_size(top_label, aw, ah)

    # Check if secondary label fits
    if system == "sae" and bot_label != top_label:
        bot_test_size = _fit_text_size(bot_label, aw, ah)
        est_bot_width = len(bot_label) * bot_test_size * 0.6
        if est_bot_width > aw:
            bot_label = top_label

    print(f"  Text: '{top_label}' / '{bot_label}' at {font_size}mm on {aw:.1f}x{ah:.1f}mm")

    top_z = thickness
    bot_z = 0.0

    # Deboss text from leaf
    with BuildPart() as debossed:
        add(leaf_body)
        top_plane = Plane(origin=(cx, cy, top_z), z_dir=(0, 0, 1))
        with BuildSketch(top_plane):
            Text(top_label, font_size=font_size, font=TEXT_FONT,
                 font_style=FontStyle.BOLD)
        extrude(amount=-DEBOSS_DEPTH, mode=Mode.SUBTRACT)

        bot_font_size = _fit_text_size(bot_label, aw, ah)
        bot_plane = Plane(origin=(cx, cy, bot_z), z_dir=(0, 0, -1),
                          x_dir=(1, 0, 0))
        with BuildSketch(bot_plane):
            Text(bot_label, font_size=bot_font_size, font=TEXT_FONT,
                 font_style=FontStyle.BOLD)
        extrude(amount=-DEBOSS_DEPTH, mode=Mode.SUBTRACT)

    # Text inlay bodies
    with BuildPart() as top_text:
        top_plane = Plane(origin=(cx, cy, top_z - DEBOSS_DEPTH), z_dir=(0, 0, 1))
        with BuildSketch(top_plane):
            Text(top_label, font_size=font_size, font=TEXT_FONT,
                 font_style=FontStyle.BOLD)
        extrude(amount=DEBOSS_DEPTH)
        with Locations([(hole_x, hole_y)]):
            Hole(radius=hole_r, depth=DEBOSS_DEPTH)

    with BuildPart() as bot_text:
        bot_plane = Plane(origin=(cx, cy, bot_z + DEBOSS_DEPTH), z_dir=(0, 0, -1),
                          x_dir=(1, 0, 0))
        with BuildSketch(bot_plane):
            Text(bot_label, font_size=bot_font_size, font=TEXT_FONT,
                 font_style=FontStyle.BOLD)
        extrude(amount=DEBOSS_DEPTH)
        with Locations([(hole_x, hole_y)]):
            Hole(radius=hole_r, depth=DEBOSS_DEPTH)

    return {
        "leaf": debossed.part,
        "text_top": top_text.part,
        "text_bottom": bot_text.part,
    }


def export_multibody(bodies: dict, filepath: str, system: str = "sae"):
    """Export multi-body STEP with color metadata."""
    bodies["leaf"].label = "leaf"
    bodies["text_top"].label = "text_top"
    bodies["text_bottom"].label = "text_bottom"

    leaf_color = Color("blue") if system == "sae" else Color("red")
    bodies["leaf"].color = leaf_color
    bodies["text_top"].color = Color("white")
    bodies["text_bottom"].color = Color("white")

    assembly = Compound(
        label="radius_gauge",
        children=[bodies["leaf"], bodies["text_top"], bodies["text_bottom"]],
    )
    export_step(assembly, filepath)
    return assembly


if __name__ == "__main__":
    out = Path(__file__).parent / "output"
    out.mkdir(exist_ok=True)

    tests = [
        ("small", 6.35, "sae", "1/4\" SAE"),
        ("medium", 25.4, "sae", "1\" SAE"),
        ("large", 76.2, "sae", "3\" SAE"),
        ("medium", 25.0, "metric", "25mm metric"),
    ]

    for form_key, r, system, desc in tests:
        print(f"Building {desc} (R={r}mm)...")
        bodies = build_leaf_with_text(r, form_key, system)
        path = out / f"labeled_{system}_{form_key}_R{r:.1f}mm.step"
        export_multibody(bodies, str(path), system)
        print(f"  Exported: {path}")
        print()
