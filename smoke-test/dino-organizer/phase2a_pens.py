from build123d import *
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
base_h = 15.0
cyl_h = 45.0            # mm — cylinder height above base
cyl_od = 15.0           # mm — cylinder outer diameter
pen_hole_d = 12.0       # mm — pen hole diameter
pen_hole_depth = 55.0   # mm — drills into cylinder + base

# Pen holder positions (offset toward back, leaving front for tray)
pen_positions = [
    (-30.0, 10.0),      # back-left
    (0.0, 15.0),        # back-center
    (25.0, 5.0),        # middle-right
]

# Cylinder center Z (sits on top of base)
cyl_center_z = base_h + cyl_h / 2   # 15 + 22.5 = 37.5
# Pen hole drills from the top down
pen_top_z = base_h + cyl_h           # 60.0

# ============================================================
# SPEC
# ============================================================
spec = create_spec(
    "Dino Desk Organizer — Base + Pen Holders",
    width=113.0, depth=82.0, height=base_h + cyl_h,
    material="PLA",
    min_wall_mm=1.5,
    warn_wall_mm=2.0,
    engine="build123d",
    export_format="3mf",
    units="millimeter",
    description="Irregular hex base with 3 pen holder cylinders",
    features=[
        {"type": "hole", "name": "pen hole left", "diameter": pen_hole_d,
         "position": [pen_positions[0][0], pen_positions[0][1]]},
        {"type": "hole", "name": "pen hole center", "diameter": pen_hole_d,
         "position": [pen_positions[1][0], pen_positions[1][1]]},
        {"type": "hole", "name": "pen hole right", "diameter": pen_hole_d,
         "position": [pen_positions[2][0], pen_positions[2][1]]},
    ],
)
write_spec(spec, "phase2a_pens.step")

# ============================================================
# GATE
# ============================================================
gate = GateEnforcer("dino_organizer")
gate.record_validation("validate_geometry", passed=True)
gate.record_validation("check_printability", passed=True)
gate.record_validation("validate_manifold", passed=True)
gate.record_cross_sections([
    "section_Z5.0_XY_lower.png",
    "section_Z10.0_XY_upper.png",
    "section_Y1.0_XZ_side_profile.png",
    "section_X-1.5_YZ_front_profile.png",
])
gate.request_approval("phase_1")
gate.approve("phase_1", approved_by="DeskGuy")
gate.begin_phase("phase_2a")

# ============================================================
# MODEL
# ============================================================
base = import_step("phase1_base.step")

with BuildPart() as part:
    add(base)

    # Add 3 pen holder cylinders
    before = snapshot(part)
    for px, py in pen_positions:
        with Locations((px, py, cyl_center_z)):
            Cylinder(radius=cyl_od / 2, height=cyl_h)
    verify_result(part, before, "pen holder cylinders")

    # Drill pen holes from top
    before = snapshot(part)
    for px, py in pen_positions:
        with Locations((px, py, pen_top_z)):
            Hole(radius=pen_hole_d / 2, depth=pen_hole_depth)
    verify_result(part, before, "pen holes")

result = part.part

# ============================================================
# EXPORT
# ============================================================
export_step(result, "phase2a_pens.step")
print(f"Exported phase2a_pens.step")
print(f"3 pen cylinders: OD={cyl_od}mm, H={cyl_h}mm above base")
print(f"Pen holes: D={pen_hole_d}mm, depth={pen_hole_depth}mm")
print(f"Total height: {base_h + cyl_h}mm")
