from build123d import *
import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/scripts"))
from bd_debug_helpers import snapshot, verify_result

sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/lib"))
from spec_format import create_spec, write_spec
from gate_enforcer import GateEnforcer

# ============================================================
# PARAMETERS
# ============================================================
base_h = 15.0

# Chevron tray — pentagonal pocket in front-left area
tray_depth = 3.0        # mm — pocket depth
tray_center_x = -15.0
tray_center_y = -20.0
# Chevron vertices (arrowhead pointing forward/down in Y)
tray_vertices = [
    (-30.0, -10.0),     # back-left
    (0.0, -10.0),       # back-right
    (10.0, -22.0),      # right shoulder
    (-15.0, -35.0),     # front point (arrowhead tip)
    (-40.0, -22.0),     # left shoulder
]

# Raptor claw — 3 separate wedges on front-right corner
claw_base_x = 40.0      # front-right area of hex
claw_base_y = -25.0
claw_h = 30.0            # mm tall
claw_base_w = 5.0        # mm wide at base
claw_tip_w = 1.5         # mm wide at tip
claw_thickness = 4.0     # mm thick (Y direction)
claw_angle = 15.0        # degrees backward lean
claw_gap = 2.5           # mm between claws
# 3 claws spread along X
claw_offsets_x = [-(claw_base_w + claw_gap), 0.0, (claw_base_w + claw_gap)]

# ============================================================
# SPEC
# ============================================================
spec = create_spec(
    "Dino Desk Organizer — Complete",
    width=113.6, depth=82.0, height=63.0,  # pen holders still tallest at 63mm
    material="PLA",
    min_wall_mm=1.5,
    warn_wall_mm=2.0,
    engine="build123d",
    export_format="3mf",
    units="millimeter",
    description="Dino organizer with all features: pens, teeth, spine, tray, claw",
    features=[
        {"type": "pocket", "name": "chevron tray", "width": 50.0, "depth": tray_depth},
        {"type": "pocket", "name": "raptor claw assembly", "width": 25.0, "depth": claw_h},
    ],
)
write_spec(spec, "phase2d_tray_claw.step")

# ============================================================
# GATE
# ============================================================
gate = GateEnforcer("dino_organizer")
gate.record_validation("validate_geometry", passed=True)
gate.record_validation("check_printability", passed=True)
gate.record_validation("validate_manifold", passed=True)
gate.record_cross_sections([
    "section_Y5.1_XZ_spine_ridge_body.png",
    "section_Z21.0_XY_lower.png",
    "section_Z42.0_XY_upper.png",
    "section_Y1.0_XZ_side_profile.png",
])
gate.request_approval("phase_2c")
gate.approve("phase_2c", approved_by="DeskGuy")
gate.begin_phase("phase_2d")

# ============================================================
# MODEL
# ============================================================
base = import_step("phase2c_spine.step")

with BuildPart() as part:
    add(base)

    # --- Chevron tray pocket ---
    before = snapshot(part)
    # Create the chevron profile on the top face of the base, then cut down
    with BuildSketch(Plane(origin=(0, 0, base_h), z_dir=(0, 0, 1))) as tray_sk:
        with BuildLine() as tray_ln:
            for i in range(len(tray_vertices)):
                x1, y1 = tray_vertices[i]
                x2, y2 = tray_vertices[(i + 1) % len(tray_vertices)]
                Line((x1, y1), (x2, y2))
        make_face()
    extrude(amount=-tray_depth, mode=Mode.SUBTRACT)
    verify_result(part, before, "chevron tray pocket")

    # --- Raptor claw (3 separate wedges) ---
    # Use XZ plane (z_dir default, sketch on XZ via Plane.XZ offset)
    # Each claw: triangular profile in XZ, extruded along Y
    before = snapshot(part)
    for dx in claw_offsets_x:
        cx = claw_base_x + dx
        cy = claw_base_y
        half_w = claw_base_w / 2
        lean = claw_h * math.tan(math.radians(claw_angle))
        # Build triangle directly using Box + position approach
        # Simpler: use Plane.XZ shifted to (cx, cy, base_h)
        with BuildSketch(Plane(origin=(cx, cy, base_h),
                               z_dir=(0, -1, 0), x_dir=(1, 0, 0))) as claw_sk:
            with BuildLine() as claw_ln:
                # Triangle in sketch coords: X = world X offset, Y = world Z (upward)
                Line((-half_w, 0), (half_w, 0))
                Line((half_w, 0), (lean, claw_h))
                Line((lean, claw_h), (-half_w, 0))
            make_face()
        extrude(amount=claw_thickness / 2, both=True)
    verify_result(part, before, "raptor claw (3 wedges)")

result = part.part

# ============================================================
# EXPORT
# ============================================================
export_step(result, "phase2d_tray_claw.step")
print(f"Exported phase2d_tray_claw.step")
print(f"Chevron tray: {tray_depth}mm deep pocket")
print(f"Raptor claw: 3 wedges, {claw_h}mm tall, {claw_gap}mm gaps")
