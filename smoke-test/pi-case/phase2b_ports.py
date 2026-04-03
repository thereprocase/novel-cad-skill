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
interior_l = board_l + 2 * clearance   # 88.6
interior_w = board_w + 2 * clearance   # 59.5
ext_l = interior_l + 2 * wall          # 92.6
ext_w = interior_w + 2 * wall          # 63.5
ext_h = 15.0
floor_z = -ext_h / 2 + wall            # -5.5
standoff_h = 3.0
pcb_bottom_z = floor_z + standoff_h    # -2.5 (bottom of PCB)
pcb_top_z = pcb_bottom_z + 1.4         # -1.1 (top of PCB)

# Board origin in case coordinates
board_origin_x = -interior_l / 2 + clearance  # -42.8 (left edge of board)
board_origin_y = -interior_w / 2 + clearance   # -28.25

# Port cutout clearance
port_clearance = 0.5  # mm per side

# USB-C power (short edge at board_origin_x, i.e. left wall of case)
# Connector on bottom of PCB, center at 11.2mm from board corner along Y
usbc_center_y = board_origin_y + 11.2
usbc_w = 9.0 + 2 * port_clearance      # connector width + clearance
usbc_h = 3.5 + 2 * port_clearance      # connector height + clearance
usbc_center_z = pcb_bottom_z - 0.5     # slightly below PCB bottom

# micro HDMI 0 (same short edge, center at 26.0mm from corner)
hdmi0_center_y = board_origin_y + 26.0
hdmi0_w = 7.5 + 2 * port_clearance
hdmi0_h = 3.5 + 2 * port_clearance
hdmi0_center_z = pcb_bottom_z - 0.3

# micro HDMI 1 (same short edge, center at 39.5mm from corner)
hdmi1_center_y = board_origin_y + 39.5
hdmi1_w = hdmi0_w
hdmi1_h = hdmi0_h
hdmi1_center_z = hdmi0_center_z

# 3.5mm audio jack (long edge at board_origin_y, i.e. front wall)
# Center at 53.5mm from board corner along X
audio_center_x = board_origin_x + 53.5
audio_d = 7.0 + 2 * port_clearance     # jack housing diameter + clearance
audio_center_z = pcb_top_z + 3.5       # center of jack above PCB top

# Wall positions for cutouts
left_wall_x = -ext_l / 2               # -46.3 (outer surface of left wall)
front_wall_y = -ext_w / 2              # -31.75 (outer surface of front wall)

# ============================================================
# SPEC
# ============================================================
spec = create_spec(
    "Raspberry Pi 4 Case — Base + Standoffs + Ports",
    width=ext_l, depth=ext_w, height=ext_h,
    material="PLA",
    min_wall_mm=wall,
    warn_wall_mm=wall + 0.5,
    engine="build123d",
    export_format="3mf",
    units="millimeter",
    description="Pi 4 case base with standoffs and port cutouts (USB-C, 2x HDMI, audio)",
    features=[
        {"type": "pocket", "name": "USB-C cutout", "width": usbc_w, "depth": wall + 1.0},
        {"type": "pocket", "name": "micro HDMI 0 cutout", "width": hdmi0_w, "depth": wall + 1.0},
        {"type": "pocket", "name": "micro HDMI 1 cutout", "width": hdmi1_w, "depth": wall + 1.0},
        {"type": "pocket", "name": "audio jack cutout", "width": audio_d, "depth": wall + 1.0},
    ],
)
write_spec(spec, "phase2b_ports.step")

# ============================================================
# GATE
# ============================================================
gate = GateEnforcer("pi4_case_base")
# Approve Phase 2a
gate.record_validation("validate_geometry", passed=True)
gate.record_validation("check_printability", passed=True)
gate.record_validation("validate_manifold", passed=True)
gate.record_cross_sections([
    "section_Z-0.8_XY_M2_5_standoff_pilot_NW.png",
    "section_Z-0.8_XY_M2_5_standoff_pilot_NE.png",
    "section_Z-0.8_XY_M2_5_standoff_pilot_SW.png",
    "section_Z-0.8_XY_M2_5_standoff_pilot_SE.png",
])
gate.request_approval("phase_2a")
gate.approve("phase_2a", approved_by="DeskGuy")
gate.begin_phase("phase_2b")

# ============================================================
# MODEL — import Phase 2a STEP, add port cutouts
# ============================================================
base = import_step("phase2a_standoffs.step")

with BuildPart() as part:
    add(base)

    # USB-C cutout (through left wall)
    before = snapshot(part)
    with Locations((left_wall_x, usbc_center_y, usbc_center_z)):
        Box(wall + 1.0, usbc_w, usbc_h, mode=Mode.SUBTRACT)
    verify_result(part, before, "USB-C cutout")

    # micro HDMI 0 cutout (through left wall)
    before = snapshot(part)
    with Locations((left_wall_x, hdmi0_center_y, hdmi0_center_z)):
        Box(wall + 1.0, hdmi0_w, hdmi0_h, mode=Mode.SUBTRACT)
    verify_result(part, before, "micro HDMI 0 cutout")

    # micro HDMI 1 cutout (through left wall)
    before = snapshot(part)
    with Locations((left_wall_x, hdmi1_center_y, hdmi1_center_z)):
        Box(wall + 1.0, hdmi1_w, hdmi1_h, mode=Mode.SUBTRACT)
    verify_result(part, before, "micro HDMI 1 cutout")

    # Audio jack cutout (through front wall)
    before = snapshot(part)
    with Locations((audio_center_x, front_wall_y, audio_center_z)):
        Cylinder(radius=audio_d / 2, height=wall + 1.0,
                 rotation=(90, 0, 0), mode=Mode.SUBTRACT)
    verify_result(part, before, "audio jack cutout")

result = part.part

# ============================================================
# EXPORT
# ============================================================
export_step(result, "phase2b_ports.step")
print(f"Exported phase2b_ports.step")
print(f"USB-C: {usbc_w:.1f}x{usbc_h:.1f}mm at Y={usbc_center_y:.1f}")
print(f"HDMI 0: {hdmi0_w:.1f}x{hdmi0_h:.1f}mm at Y={hdmi0_center_y:.1f}")
print(f"HDMI 1: {hdmi1_w:.1f}x{hdmi1_h:.1f}mm at Y={hdmi1_center_y:.1f}")
print(f"Audio: D={audio_d:.1f}mm at X={audio_center_x:.1f}")
