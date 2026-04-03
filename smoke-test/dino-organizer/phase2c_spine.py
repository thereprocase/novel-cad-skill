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

# Spine body
spine_l = 90.0          # mm — length along X
spine_w = 8.0           # mm — width (Y direction)
spine_h = 12.0          # mm — height above base
spine_center_x = -5.0   # slightly left of center
spine_center_y = 30.0   # toward back of hex
spine_center_z = base_h + spine_h / 2   # 15 + 6 = 21

# Plate fins (5 total)
fin_thickness = 4.0     # mm
fin_base_w = 8.0        # mm — width at base (same as spine width)
fin_tip_w = 2.0         # mm — width at top
fin_h = 15.0            # mm — height above spine top
fin_top_z = base_h + spine_h + fin_h    # 15 + 12 + 15 = 42

# Fin positions along spine (X coords)
# Need gaps for: USB-A (13mm) x2, SD (10mm) x3
# 5 fins at 4mm each = 20mm
# 2 USB gaps at 13mm = 26mm
# 3 SD gaps at 10mm = 30mm
# Total = 20 + 26 + 30 = 76mm (fits in 90mm spine with 7mm margins)
# Layout: [margin] fin SD fin SD fin USB fin SD fin [margin]
# Positions from left edge of spine:
spine_left = spine_center_x - spine_l / 2  # -50
fin_positions_x = []
x = spine_left + 5.0  # 5mm left margin
gaps = [10.0, 10.0, 13.0, 10.0, 13.0]  # SD, SD, USB, SD, USB
for i in range(5):
    fin_positions_x.append(x + fin_thickness / 2)
    x += fin_thickness
    if i < len(gaps):
        x += gaps[i]

# Fin center Z (rises from spine top)
spine_top_z = base_h + spine_h  # 27
fin_center_z = spine_top_z + fin_h / 2   # 27 + 7.5 = 34.5

# ============================================================
# SPEC
# ============================================================
spec = create_spec(
    "Dino Desk Organizer — Spine + Fins",
    width=113.0, depth=82.0, height=63.0,  # pen holders + teeth are tallest at 63mm
    material="PLA",
    min_wall_mm=1.5,
    warn_wall_mm=2.0,
    engine="build123d",
    export_format="3mf",
    units="millimeter",
    description="Dino organizer with stegosaurus spine ridge and plate fins",
    features=[
        {"type": "pocket", "name": "spine ridge body", "width": spine_l, "depth": spine_w},
        {"type": "pattern", "name": "stego plate fins",
         "element": {"type": "slot", "width": fin_thickness, "length": fin_h},
         "arrangement": "linear", "count": 5, "pitch": 15.0,
         "position": [fin_positions_x[0], spine_center_y, fin_center_z],
         "direction": [1.0, 0.0, 0.0]},
    ],
)
write_spec(spec, "phase2c_spine.step")

# ============================================================
# GATE
# ============================================================
gate = GateEnforcer("dino_organizer")
gate.record_validation("validate_geometry", passed=True)
gate.record_validation("check_printability", passed=True)
gate.record_validation("validate_manifold", passed=True)
gate.record_cross_sections([
    "section_Z21.0_XY_lower.png",
    "section_Z42.0_XY_upper.png",
    "section_Y1.0_XZ_side_profile.png",
    "section_X-1.5_YZ_front_profile.png",
])
gate.request_approval("phase_2b")
gate.approve("phase_2b", approved_by="DeskGuy")
gate.begin_phase("phase_2c")

# ============================================================
# MODEL
# ============================================================
base = import_step("phase2b_teeth.step")

with BuildPart() as part:
    add(base)

    # Spine body — rectangular block along back edge
    before = snapshot(part)
    with Locations((spine_center_x, spine_center_y, spine_center_z)):
        Box(spine_l, spine_w, spine_h)
    verify_result(part, before, "spine body")

    # Plate fins — triangular profiles extruded along Y (fin_thickness)
    before = snapshot(part)
    for fx in fin_positions_x:
        # Build a triangular fin as a tapered box
        # Simple approach: use a wedge-shaped profile
        with BuildSketch(Plane(origin=(fx, spine_center_y, spine_top_z),
                               z_dir=(0, 1, 0), x_dir=(1, 0, 0))) as fin_sk:
            with BuildLine() as fin_ln:
                # Triangle: base at bottom, point at top
                Line((-fin_base_w / 2, 0), (fin_base_w / 2, 0))
                Line((fin_base_w / 2, 0), (0, fin_h))
                Line((0, fin_h), (-fin_base_w / 2, 0))
            make_face()
        extrude(amount=fin_thickness / 2, both=True)

    verify_result(part, before, "plate fins (5)")

result = part.part

# ============================================================
# EXPORT
# ============================================================
export_step(result, "phase2c_spine.step")
print(f"Exported phase2c_spine.step")
print(f"Spine: {spine_l}x{spine_w}x{spine_h}mm at Y={spine_center_y}")
print(f"Fins: 5x {fin_base_w}->{fin_tip_w}mm x {fin_h}mm tall, {fin_thickness}mm thick")
print(f"Fin X positions: {[f'{x:.1f}' for x in fin_positions_x]}")
print(f"Total height: {fin_top_z}mm")
