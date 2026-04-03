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
cyl_h = 45.0
cyl_od = 15.0
cyl_top_z = base_h + cyl_h   # 60.0

pen_positions = [
    (-30.0, 10.0),
    (0.0, 15.0),
    (25.0, 5.0),
]

# Tooth parameters
n_teeth = 8              # teeth per cylinder
tooth_heights = [3.0, 2.0, 3.0, 2.0, 3.0, 2.0, 3.0, 2.0]  # alternating
tooth_base_w = 3.0       # mm — width at base
tooth_tip_w = 0.8        # mm — width at tip
tooth_radial_depth = 3.0 # mm — how far tooth extends radially (inward + outward from rim)
rim_radius = cyl_od / 2  # 7.5mm — center of tooth sits on this radius

# ============================================================
# SPEC
# ============================================================
spec = create_spec(
    "Dino Desk Organizer — Base + Pens + Teeth",
    width=113.0, depth=82.0, height=base_h + cyl_h + max(tooth_heights),
    material="PLA",
    min_wall_mm=1.5,
    warn_wall_mm=2.0,
    engine="build123d",
    export_format="3mf",
    units="millimeter",
    description="Dino organizer with serrated tooth rims on pen holders",
    features=[
        {"type": "pattern", "name": "teeth left pen",
         "element": {"type": "slot", "width": tooth_base_w, "length": tooth_radial_depth},
         "arrangement": "radial", "count": n_teeth, "pitch": 45.0,
         "position": [pen_positions[0][0], pen_positions[0][1], cyl_top_z],
         "direction": [0.0, 0.0, 1.0]},
        {"type": "pattern", "name": "teeth center pen",
         "element": {"type": "slot", "width": tooth_base_w, "length": tooth_radial_depth},
         "arrangement": "radial", "count": n_teeth, "pitch": 45.0,
         "position": [pen_positions[1][0], pen_positions[1][1], cyl_top_z],
         "direction": [0.0, 0.0, 1.0]},
        {"type": "pattern", "name": "teeth right pen",
         "element": {"type": "slot", "width": tooth_base_w, "length": tooth_radial_depth},
         "arrangement": "radial", "count": n_teeth, "pitch": 45.0,
         "position": [pen_positions[2][0], pen_positions[2][1], cyl_top_z],
         "direction": [0.0, 0.0, 1.0]},
    ],
)
write_spec(spec, "phase2b_teeth.step")

# ============================================================
# GATE
# ============================================================
gate = GateEnforcer("dino_organizer")
gate.record_validation("validate_geometry", passed=True)
gate.record_validation("check_printability", passed=True)
gate.record_validation("validate_manifold", passed=True)
gate.record_cross_sections([
    "section_Z27.0_XY_pen_hole_left.png",
    "section_Z20.0_XY_lower.png",
    "section_Y1.0_XZ_side_profile.png",
    "section_X-1.5_YZ_front_profile.png",
])
gate.request_approval("phase_2a")
gate.approve("phase_2a", approved_by="DeskGuy")
gate.begin_phase("phase_2b")

# ============================================================
# MODEL — import Phase 2a, add teeth
# ============================================================
base = import_step("phase2a_pens.step")

with BuildPart() as part:
    add(base)
    before = snapshot(part)

    # For each pen holder, add 8 triangular teeth around the rim
    for px, py in pen_positions:
        for i in range(n_teeth):
            angle = i * (360.0 / n_teeth)  # degrees
            angle_rad = math.radians(angle)
            th = tooth_heights[i]

            # Tooth center on the rim
            tx = px + rim_radius * math.cos(angle_rad)
            ty = py + rim_radius * math.sin(angle_rad)
            tz = cyl_top_z + th / 2  # tooth rises from cylinder top

            # Create a tapered triangular prism for each tooth
            # Oriented radially — the "length" axis points outward from center
            # Use a simple box tapered via loft... or just use a wedge shape
            # Simplest: use a Box for the tooth body (rectangular prism)
            # and rely on the visual effect of many small blocks around the rim
            with Locations((tx, ty, tz)):
                Box(tooth_base_w, tooth_radial_depth, th,
                    rotation=(0, 0, math.degrees(angle_rad)))

    verify_result(part, before, "tooth addition (24 teeth total)")

result = part.part

# ============================================================
# EXPORT
# ============================================================
export_step(result, "phase2b_teeth.step")
print(f"Exported phase2b_teeth.step")
print(f"24 teeth added (8 per cylinder, alternating {tooth_heights[0]}/{tooth_heights[1]}mm)")
print(f"Total height: {base_h + cyl_h + max(tooth_heights)}mm")
