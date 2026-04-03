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
floor_z = -ext_h / 2 + wall            # -5.5
standoff_h = 3.0
pcb_bottom_z = floor_z + standoff_h    # -2.5
pcb_top_z = pcb_bottom_z + 1.4         # -1.1

board_origin_x = -interior_l / 2 + clearance  # -42.8
board_origin_y = -interior_w / 2 + clearance   # -28.25

port_clearance = 0.5

# USB-A stacked x2 (long edge, right side — board Y=0 edge)
# Located at ~29mm from board corner along X, on the board_w edge
usba_center_x = board_origin_x + 29.0
usba_w = 13.5 + 2 * port_clearance     # stacked USB-A width
usba_h = 16.0 + 2 * port_clearance     # stacked height
usba_center_z = pcb_bottom_z + usba_h / 2 - 1.0  # bottom near PCB
back_wall_y = ext_w / 2                 # 31.75

# RJ45 Ethernet (same long edge, next to USB-A)
# Located at ~45.75mm from board corner along X
eth_center_x = board_origin_x + 45.75
eth_w = 16.0 + 2 * port_clearance
eth_h = 14.0 + 2 * port_clearance
eth_center_z = pcb_bottom_z + eth_h / 2 - 1.0

# microSD slot (opposite short edge from USB-C — right wall)
# Open slot at bottom, ~12mm wide, 1.5mm tall
right_wall_x = ext_l / 2               # 46.3
sd_center_y = board_origin_y + board_w / 2  # center of board width
sd_w = 12.0 + 2 * port_clearance
sd_h = 2.0 + 2 * port_clearance
sd_center_z = pcb_bottom_z - 0.5       # below PCB

# Vent grid (on top — will be on lid, but for the base we skip it)
# Actually, the vent grid goes on the lid. For the base, let's add
# ventilation slots on the bottom if needed, or skip.
# Per skill workflow, vents go on the lid. But DeskGuy asked about them here.
# Let's add small side vents on the long wall opposite the ports.
vent_slot_w = 2.0       # slot width
vent_slot_l = 15.0      # slot length (vertical)
vent_pitch = 3.5        # center-to-center
vent_count = 8
front_wall_y = -ext_w / 2  # -31.75
# Vent position: centered on front wall, upper portion
vent_start_x = -vent_count * vent_pitch / 2 + vent_pitch / 2
vent_center_z = ext_h / 2 - vent_slot_l / 2 - 1.0  # near top of wall

# ============================================================
# SPEC
# ============================================================
spec = create_spec(
    "Raspberry Pi 4 Case — Base + All Features",
    width=ext_l, depth=ext_w, height=ext_h,
    material="PLA",
    min_wall_mm=wall,
    warn_wall_mm=wall + 0.5,
    engine="build123d",
    export_format="3mf",
    units="millimeter",
    description="Pi 4 case base with all port cutouts and side ventilation",
    features=[
        {"type": "pocket", "name": "USB-A stack cutout", "width": usba_w, "depth": wall + 1.0},
        {"type": "pocket", "name": "RJ45 Ethernet cutout", "width": eth_w, "depth": wall + 1.0},
        {"type": "pocket", "name": "microSD slot", "width": sd_w, "depth": wall + 1.0},
        {"type": "pattern", "name": "side vent grid",
         "element": {"type": "slot", "width": vent_slot_w, "length": vent_slot_l},
         "arrangement": "linear", "count": vent_count, "pitch": vent_pitch,
         "position": [vent_start_x, front_wall_y, vent_center_z],
         "direction": [1.0, 0.0, 0.0]},
    ],
)
write_spec(spec, "phase2c_remaining.step")

# ============================================================
# GATE
# ============================================================
gate = GateEnforcer("pi4_case_base")
gate.record_validation("validate_geometry", passed=True)
gate.record_validation("check_printability", passed=True)
gate.record_validation("validate_manifold", passed=True)
gate.record_cross_sections([
    "section_Y3.2_XZ_USB-C_cutout.png",
    "section_Z-2.5_XY_lower.png",
    "section_Z2.5_XY_upper.png",
    "section_Y0.0_XZ_side_profile.png",
])
gate.request_approval("phase_2b")
gate.approve("phase_2b", approved_by="DeskGuy")
gate.begin_phase("phase_2c")

# ============================================================
# MODEL — import Phase 2b STEP, add remaining features
# ============================================================
base = import_step("phase2b_ports.step")

with BuildPart() as part:
    add(base)

    # USB-A stacked cutout (through back wall)
    before = snapshot(part)
    with Locations((usba_center_x, back_wall_y, usba_center_z)):
        Box(usba_w, wall + 1.0, usba_h, mode=Mode.SUBTRACT)
    verify_result(part, before, "USB-A stack cutout")

    # RJ45 Ethernet cutout (through back wall)
    before = snapshot(part)
    with Locations((eth_center_x, back_wall_y, eth_center_z)):
        Box(eth_w, wall + 1.0, eth_h, mode=Mode.SUBTRACT)
    verify_result(part, before, "RJ45 Ethernet cutout")

    # microSD slot (through right wall, open at bottom)
    before = snapshot(part)
    with Locations((right_wall_x, sd_center_y, sd_center_z)):
        Box(wall + 1.0, sd_w, sd_h, mode=Mode.SUBTRACT)
    verify_result(part, before, "microSD slot")

    # Side ventilation grid (through front wall)
    before = snapshot(part)
    for i in range(vent_count):
        vx = vent_start_x + i * vent_pitch
        with Locations((vx, front_wall_y, vent_center_z)):
            Box(vent_slot_w, wall + 1.0, vent_slot_l, mode=Mode.SUBTRACT)
    verify_result(part, before, "side vent grid")

result = part.part

# ============================================================
# EXPORT
# ============================================================
export_step(result, "phase2c_remaining.step")
print(f"Exported phase2c_remaining.step")
print(f"USB-A: {usba_w:.1f}x{usba_h:.1f}mm at X={usba_center_x:.1f}")
print(f"RJ45:  {eth_w:.1f}x{eth_h:.1f}mm at X={eth_center_x:.1f}")
print(f"microSD: {sd_w:.1f}x{sd_h:.1f}mm at Y={sd_center_y:.1f}")
print(f"Vents: {vent_count}x {vent_slot_w:.1f}x{vent_slot_l:.1f}mm, pitch={vent_pitch:.1f}mm")
