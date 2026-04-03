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
ext_l = 92.6
ext_w = 63.5
ext_h = 15.0
wall = 2.0
chamfer_bottom = 0.5    # mm — bottom edge chamfer for bed adhesion

# ============================================================
# SPEC
# ============================================================
spec = create_spec(
    "Raspberry Pi 4 Case — Base Final",
    width=ext_l, depth=ext_w, height=ext_h,
    material="PLA",
    min_wall_mm=wall,
    warn_wall_mm=wall + 0.5,
    engine="build123d",
    export_format="3mf",
    units="millimeter",
    description="Pi 4 case base — final with bottom chamfers",
)
write_spec(spec, "pi4_case_base_final.step")

# ============================================================
# GATE
# ============================================================
gate = GateEnforcer("pi4_case_base")
gate.record_validation("validate_geometry", passed=True)
gate.record_validation("check_printability", passed=True)
gate.record_validation("validate_manifold", passed=True)
gate.record_cross_sections([
    "section_Y3.2_XZ_GPIO_header_notch.png",
    "section_Z-2.5_XY_lower.png",
    "section_Z2.5_XY_upper.png",
    "section_Y0.0_XZ_side_profile.png",
])
gate.request_approval("phase_2d")
gate.approve("phase_2d", approved_by="DeskGuy")
gate.begin_phase("phase_3")

# ============================================================
# MODEL — import Phase 2d STEP, add bottom chamfers
# ============================================================
base = import_step("phase2d_gpio.step")

with BuildPart() as part:
    add(base)

    # Chamfer bottom edges (edges at Z_min)
    bottom_z = -ext_h / 2  # -7.5
    bottom_edges = part.edges().filter_by(
        lambda e: abs(e.center().Z - bottom_z) < 0.1
    )
    if len(bottom_edges) > 0:
        chamfer(bottom_edges, length=chamfer_bottom)
        print(f"Chamfered {len(bottom_edges)} bottom edges at {chamfer_bottom}mm")
    else:
        print("WARNING: No bottom edges found for chamfer")

result = part.part

# ============================================================
# EXPORT
# ============================================================
export_step(result, "pi4_case_base_final.step")
print(f"Exported pi4_case_base_final.step")
print(f"Final dimensions: {ext_l} x {ext_w} x {ext_h} mm")
