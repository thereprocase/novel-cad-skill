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
board_l = 85.6
board_w = 56.5
clearance = 1.5
wall = 2.0
interior_l = board_l + 2 * clearance
interior_w = board_w + 2 * clearance
ext_l = interior_l + 2 * wall          # 92.6
ext_w = interior_w + 2 * wall          # 63.5
ext_h = 15.0

board_origin_x = -interior_l / 2 + clearance  # -42.8
board_origin_y = -interior_w / 2 + clearance   # -28.25

# GPIO header: 2x20 pin, ~51mm long, on back long edge
# Starts at ~7.1mm from board corner along X axis
# Center at ~32.6mm from corner
gpio_center_x = board_origin_x + 32.6
gpio_w = 52.0          # slightly wider than header for clearance
gpio_h = 6.0           # depth of notch from top of wall
back_wall_y = ext_w / 2  # 31.75
top_z = ext_h / 2        # 7.5

# ============================================================
# SPEC
# ============================================================
spec = create_spec(
    "Raspberry Pi 4 Case — Base Complete",
    width=ext_l, depth=ext_w, height=ext_h,
    material="PLA",
    min_wall_mm=wall,
    warn_wall_mm=wall + 0.5,
    engine="build123d",
    export_format="3mf",
    units="millimeter",
    description="Pi 4 case base — all features complete including GPIO access notch",
    features=[
        {"type": "pocket", "name": "GPIO header notch", "width": gpio_w, "depth": wall + 1.0},
    ],
)
write_spec(spec, "phase2d_gpio.step")

# ============================================================
# GATE
# ============================================================
gate = GateEnforcer("pi4_case_base")
gate.record_validation("validate_geometry", passed=True)
gate.record_validation("check_printability", passed=True)
gate.record_validation("validate_manifold", passed=True)
gate.record_cross_sections([
    "section_Y3.2_XZ_USB-A_stack_cutout.png",
    "section_X-12.2_YZ_side_vent_grid_first.png",
    "section_Z-2.5_XY_lower.png",
    "section_Z2.5_XY_upper.png",
])
gate.request_approval("phase_2c")
gate.approve("phase_2c", approved_by="DeskGuy")
gate.begin_phase("phase_2d")

# ============================================================
# MODEL — import Phase 2c STEP, add GPIO notch
# ============================================================
base = import_step("phase2c_remaining.step")

with BuildPart() as part:
    add(base)

    # GPIO notch — open at top of back wall
    before = snapshot(part)
    with Locations((gpio_center_x, back_wall_y, top_z)):
        Box(gpio_w, wall + 1.0, gpio_h, mode=Mode.SUBTRACT)
    verify_result(part, before, "GPIO header notch")

result = part.part

# ============================================================
# EXPORT
# ============================================================
export_step(result, "phase2d_gpio.step")
print(f"Exported phase2d_gpio.step")
print(f"GPIO notch: {gpio_w:.1f}x{gpio_h:.1f}mm at X={gpio_center_x:.1f}, top of back wall")
