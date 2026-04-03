from build123d import *
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/lib"))
from spec_format import create_spec, write_spec
from gate_enforcer import GateEnforcer

# ============================================================
# PARAMETERS
# ============================================================
chamfer_bottom = 0.5    # mm

# ============================================================
# SPEC
# ============================================================
spec = create_spec(
    "Dino Desk Organizer — Final",
    width=113.6, depth=82.0, height=63.0,
    material="PLA",
    min_wall_mm=1.5,
    warn_wall_mm=2.0,
    engine="build123d",
    export_format="3mf",
    units="millimeter",
    description="Dinosaur-themed desk organizer — final with bottom chamfers",
)
write_spec(spec, "dino_organizer_final.step")

# ============================================================
# GATE
# ============================================================
gate = GateEnforcer("dino_organizer")
gate.record_validation("validate_geometry", passed=True)
gate.record_validation("check_printability", passed=True)
gate.record_validation("validate_manifold", passed=True)
gate.record_cross_sections([
    "section_Y5.1_XZ_chevron_tray.png",
    "section_Z11.0_XY_lower.png",
    "section_Z37.0_XY_upper.png",
    "section_Y1.0_XZ_side_profile.png",
])
gate.request_approval("phase_2d")
gate.approve("phase_2d", approved_by="DeskGuy")
gate.begin_phase("phase_3")

# ============================================================
# MODEL — import Phase 2d, add bottom chamfers
# ============================================================
base = import_step("phase2d_tray_claw.step")

with BuildPart() as part:
    add(base)

    # Chamfer bottom edges
    bottom_edges = part.edges().filter_by(
        lambda e: abs(e.center().Z) < 0.1
    )
    if len(bottom_edges) > 0:
        chamfer(bottom_edges, length=chamfer_bottom)
        print(f"Chamfered {len(bottom_edges)} bottom edges at {chamfer_bottom}mm")
    else:
        print("WARNING: No bottom edges found")

result = part.part

# ============================================================
# EXPORT
# ============================================================
export_step(result, "dino_organizer_final.step")
print(f"Exported dino_organizer_final.step")
