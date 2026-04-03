"""Phase 2 — Pen Organizer features.

Imports phase1_base.step and adds:
- 8 pen holes (2 rows of 4, 12mm dia, 50mm deep)
- Sticky note pocket (78x78x40mm, open top, thumb scoop on front)
- Phone stand slot (angled 70deg from horizontal, 10mm wide)
"""
from build123d import *
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/scripts"))
from bd_debug_helpers import snapshot, verify_result

sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/lib"))
from spec_format import create_spec, write_spec
from gate_enforcer import GateEnforcer

# ============================================================
# PARAMETERS
# ============================================================
# Overall dims (must match phase 1)
W = 200.0
D = 100.0
H_pen = 55.0
H_phone = 80.0
wall = 2.0

W_left = 140.0
W_right = W - W_left  # 60mm

# Pen holes
pen_dia = 12.0          # mm — hole diameter
pen_depth = 50.0        # mm — hole depth (floor at 5mm from bottom)
pen_rows = 2
pen_cols = 4
pen_pitch_x = 22.0      # mm — center-to-center spacing X
pen_pitch_y = 22.0      # mm — center-to-center spacing Y

# Pen hole grid center: positioned in upper-left quadrant of left section
# Left section spans X from -W/2 to -W/2 + W_left = -100 to +40
# Center the pen grid in the upper portion of the left section
pen_grid_cx = -W/2 + W_left/2    # X center of left section = -30
pen_grid_cy = D/2 - wall - (pen_rows * pen_pitch_y)/2  # near rear

# Sticky note pocket
sticky_w = 78.0         # mm — internal width (76mm pad + 1mm clearance each side)
sticky_d = 78.0         # mm — internal depth
sticky_h = 40.0         # mm — internal height
# Position: lower-left area of left section, near front
sticky_cx = -W/2 + wall + sticky_w/2 + 5  # 5mm inset from left wall
sticky_cy = -D/2 + wall + sticky_d/2      # near front edge

# Phone stand slot
phone_slot_width = 10.0  # mm — slot width (phone thickness + clearance)
phone_angle = 70.0       # degrees from horizontal
phone_lip = 8.0          # mm — bottom lip to catch phone
# Phone slot is in the right section, centered on Y
# The slot cuts through the top of the phone stand section

# ============================================================
# SPEC — declare all Phase 2 features
# ============================================================
spec = create_spec(
    "Pen Organizer",
    width=W, depth=D, height=H_phone,
    material="PLA",
    min_wall_mm=wall,
    warn_wall_mm=wall + 0.5,
    engine="build123d",
    export_format="3mf",
    units="millimeter",
    description="Desktop pen organizer with pen slots, sticky note pocket, phone stand",
    features=[
        {"type": "pattern", "name": "pen holes",
         "element": {"type": "hole", "diameter": pen_dia},
         "arrangement": "grid", "count": pen_rows * pen_cols,
         "count_x": pen_cols, "count_y": pen_rows,
         "pitch_x": pen_pitch_x, "pitch_y": pen_pitch_y,
         "position": [pen_grid_cx, pen_grid_cy, 0]},
        {"type": "pocket", "name": "sticky note pocket",
         "width": sticky_w, "depth": sticky_d},
        {"type": "slot", "name": "phone slot",
         "width": phone_slot_width, "probe_z": H_phone/2},
    ],
)
write_spec(spec, "phase2_features.step")

# ============================================================
# GATE
# ============================================================
gate = GateEnforcer.resume_from("pen_organizer", "phase_1")
gate.begin_phase("phase_2")

# ============================================================
# MODEL
# ============================================================
base = import_step("phase1_base.step")

with BuildPart() as part:
    add(base)

    # --- Pen holes: 2 rows x 4 cols, blind holes from top ---
    before = snapshot(part)
    pen_locs = []
    for row in range(pen_rows):
        for col in range(pen_cols):
            x = pen_grid_cx + (col - (pen_cols - 1) / 2) * pen_pitch_x
            y = pen_grid_cy + (row - (pen_rows - 1) / 2) * pen_pitch_y
            pen_locs.append((x, y))

    # Holes cut from the top face of the pen section (Z = H_pen)
    # We need to position at the top of the pen section
    pen_top_z = H_pen  # top of the shorter section
    with BuildSketch(Plane(origin=(0, 0, pen_top_z), z_dir=(0, 0, 1))):
        for (px, py) in pen_locs:
            with Locations([(px, py)]):
                Circle(pen_dia / 2)
    extrude(amount=-pen_depth, mode=Mode.SUBTRACT)
    verify_result(part, before, "pen holes")

    # --- Sticky note pocket: rectangular pocket from top ---
    before = snapshot(part)
    with BuildSketch(Plane(origin=(0, 0, pen_top_z), z_dir=(0, 0, 1))):
        with Locations([(sticky_cx, sticky_cy)]):
            Rectangle(sticky_w, sticky_d)
    extrude(amount=-sticky_h, mode=Mode.SUBTRACT)
    verify_result(part, before, "sticky note pocket")

    # --- Phone stand slot ---
    # Angled slot in the right section for leaning a phone.
    # 70deg from horizontal = 20deg tilt back from vertical.
    # Cut a tilted rectangular channel through the phone stand top.
    before = snapshot(part)

    phone_cx = -W/2 + W_left + W_right/2  # X center of phone section = +70

    tilt_angle = 90.0 - phone_angle  # 20 degrees from vertical
    slot_length = D - 2 * wall  # runs most of the depth
    # Slot height sized to cut from lip to top of phone section
    slot_cut_height = (H_phone - phone_lip) / math.cos(math.radians(tilt_angle)) + phone_slot_width

    # Build slot cutter on a tilted workplane
    slot_plane = Plane(
        origin=(phone_cx, 0, phone_lip + (H_phone - phone_lip) / 2),
        z_dir=(math.sin(math.radians(tilt_angle)), 0, math.cos(math.radians(tilt_angle))),
        x_dir=(0, 1, 0),
    )
    with BuildSketch(slot_plane):
        Rectangle(slot_length, phone_slot_width)
    extrude(amount=slot_cut_height / 2, both=True, mode=Mode.SUBTRACT)
    verify_result(part, before, "phone slot")

result = part.part

# ============================================================
# EXPORT
# ============================================================
export_step(result, "phase2_features.step")

bb = result.bounding_box()
print(f"Exported phase2_features.step")
print(f"Bounding box: {bb.max.X - bb.min.X:.1f} x {bb.max.Y - bb.min.Y:.1f} x {bb.max.Z - bb.min.Z:.1f} mm")
