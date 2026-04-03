from build123d import *
import sys
from pathlib import Path

# Construction-time checks
sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/scripts"))
from bd_debug_helpers import snapshot, verify_result

# Spec capture + gate enforcement
sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/lib"))
from spec_format import create_spec, write_spec
from gate_enforcer import GateEnforcer

# ============================================================
# PARAMETERS
# ============================================================
# Board dimensions (Pi 4 Model B datasheet)
board_l = 85.6       # mm — board length
board_w = 56.5       # mm — board width
clearance = 1.5      # mm — clearance per side

# Case dimensions
wall = 2.0           # mm — wall thickness
interior_l = board_l + 2 * clearance   # 88.6mm
interior_w = board_w + 2 * clearance   # 59.5mm
interior_h = 20.0    # mm — interior height (tallest component ~16mm + margin)
base_h = 15.0        # mm — base height (lid adds the rest)

ext_l = interior_l + 2 * wall   # 92.6mm
ext_w = interior_w + 2 * wall   # 63.5mm
ext_h = base_h                  # 15.0mm

r_ext = 3.0          # mm — exterior corner radius
r_int = r_ext - wall  # mm — interior radius (concentric)

# ============================================================
# SPEC — Phase 1: overall dimensions only
# ============================================================
spec = create_spec(
    "Raspberry Pi 4 Case — Base",
    width=ext_l, depth=ext_w, height=ext_h,
    material="PLA",
    min_wall_mm=wall,
    warn_wall_mm=wall + 0.5,
    engine="build123d",
    export_format="3mf",
    units="millimeter",
    description="Two-piece snap-fit case for Raspberry Pi 4 Model B — base shell",
)
write_spec(spec, "phase1_base.step")

# ============================================================
# GATE — begin Phase 1
# ============================================================
gate = GateEnforcer("pi4_case_base")
gate.begin_phase("phase_1")

# ============================================================
# MODEL — base shell only
# ============================================================
with BuildPart() as part:
    # Exterior box
    Box(ext_l, ext_w, ext_h)

    # Fillet vertical edges
    z_edges = part.edges().filter_by(Axis.Z)
    fillet(z_edges, radius=r_ext)

    # Shell — remove top face to create open-top box
    top_face = part.faces().sort_by(Axis.Z)[-1]
    offset(amount=-wall, openings=top_face)

result = part.part

# ============================================================
# EXPORT
# ============================================================
export_step(result, "phase1_base.step")
print(f"Exported phase1_base.step: {ext_l:.1f} x {ext_w:.1f} x {ext_h:.1f} mm")
print(f"Interior: {interior_l:.1f} x {interior_w:.1f} x {interior_h:.1f} mm")
print(f"Wall: {wall:.1f}mm, Corner radius: {r_ext:.1f}mm ext / {r_int:.1f}mm int")
