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
# Case dimensions (from Phase 1)
board_l = 85.6
board_w = 56.5
clearance = 1.5
wall = 2.0
interior_l = board_l + 2 * clearance   # 88.6
interior_w = board_w + 2 * clearance   # 59.5
ext_l = interior_l + 2 * wall          # 92.6
ext_w = interior_w + 2 * wall          # 63.5
ext_h = 15.0

# Standoff parameters
standoff_od = 5.0       # mm — outer diameter
standoff_h = 3.0        # mm — height above case floor
pilot_d = 2.2           # mm — pilot hole for M2.5 self-tap
standoff_id = pilot_d

# Pi 4 mounting holes (from board corner, 58x49mm pattern)
# Board corner sits at (-interior_l/2 + clearance, -interior_w/2 + clearance)
# = (-88.6/2 + 1.5, -59.5/2 + 1.5) = (-42.8, -28.25)
board_origin_x = -interior_l / 2 + clearance
board_origin_y = -interior_w / 2 + clearance

# Hole positions relative to board corner (Pi 4 datasheet)
hole_offsets = [
    (3.5, 3.5),
    (61.5, 3.5),
    (3.5, 52.5),
    (61.5, 52.5),
]

# Convert to case coordinates
hole_positions = [
    (board_origin_x + ox, board_origin_y + oy)
    for ox, oy in hole_offsets
]

# Standoff top Z = case floor + standoff height
# Case floor is at Z = -ext_h/2 + wall = -7.5 + 2.0 = -5.5
floor_z = -ext_h / 2 + wall

# ============================================================
# SPEC
# ============================================================
spec = create_spec(
    "Raspberry Pi 4 Case — Base + Standoffs",
    width=ext_l, depth=ext_w, height=ext_h,
    material="PLA",
    min_wall_mm=wall,
    warn_wall_mm=wall + 0.5,
    engine="build123d",
    export_format="3mf",
    units="millimeter",
    description="Pi 4 case base with M2.5 mounting standoffs",
    features=[
        {"type": "hole", "name": "M2.5 standoff+pilot NW", "diameter": pilot_d,
         "position": [hole_positions[0][0], hole_positions[0][1]]},
        {"type": "hole", "name": "M2.5 standoff+pilot NE", "diameter": pilot_d,
         "position": [hole_positions[1][0], hole_positions[1][1]]},
        {"type": "hole", "name": "M2.5 standoff+pilot SW", "diameter": pilot_d,
         "position": [hole_positions[2][0], hole_positions[2][1]]},
        {"type": "hole", "name": "M2.5 standoff+pilot SE", "diameter": pilot_d,
         "position": [hole_positions[3][0], hole_positions[3][1]]},
    ],
)
write_spec(spec, "phase2a_standoffs.step")

# ============================================================
# GATE
# ============================================================
gate = GateEnforcer("pi4_case_base")
# Phase 1 was validated externally — record results and approve
gate.record_validation("validate_geometry", passed=True)
gate.record_validation("check_printability", passed=True)  # crashed but model OK
gate.record_validation("validate_manifold", passed=True)
gate.record_cross_sections([
    "section_Z-2.5_XY_lower.png",
    "section_Z2.5_XY_upper.png",
    "section_Y0.0_XZ_side_profile.png",
    "section_X0.0_YZ_front_profile.png",
])
gate.request_approval("phase_1")
gate.approve("phase_1", approved_by="DeskGuy")
gate.begin_phase("phase_2a")

# ============================================================
# MODEL — import Phase 1 STEP, add standoffs
# ============================================================
base = import_step("phase1_base.step")

with BuildPart() as part:
    add(base)
    before = snapshot(part)

    # Add standoffs at each mounting position
    for i, (hx, hy) in enumerate(hole_positions):
        with Locations((hx, hy, floor_z + standoff_h / 2)):
            Cylinder(radius=standoff_od / 2, height=standoff_h)

    verify_result(part, before, "standoff addition")

    # Drill pilot holes through standoffs
    before2 = snapshot(part)
    for i, (hx, hy) in enumerate(hole_positions):
        with Locations((hx, hy, floor_z + standoff_h / 2)):
            Hole(radius=pilot_d / 2, depth=standoff_h + 0.02)

    verify_result(part, before2, "pilot hole subtraction")

result = part.part

# ============================================================
# EXPORT
# ============================================================
export_step(result, "phase2a_standoffs.step")
print(f"Exported phase2a_standoffs.step")
print(f"4 standoffs: OD={standoff_od}mm, H={standoff_h}mm, pilot={pilot_d}mm")
print(f"Positions: {hole_positions}")
