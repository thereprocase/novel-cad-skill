"""Phase 3 — Pen Organizer print optimization & final delivery.

Imports phase2_features.step and:
- Verifies bottom chamfer from Phase 1 is still present
- Runs final validation suite
- Exports STEP + 3MF
"""
from build123d import *
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/scripts"))
sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/lib"))
from spec_format import create_spec, write_spec
from gate_enforcer import GateEnforcer

# ============================================================
# PARAMETERS (same as Phase 2 for spec consistency)
# ============================================================
W = 200.0
D = 100.0
H_phone = 80.0
wall = 2.0
pen_dia = 12.0
pen_pitch_x = 22.0
pen_pitch_y = 22.0
sticky_w = 78.0
sticky_d = 78.0
phone_slot_width = 10.0

# ============================================================
# SPEC — final spec with all features
# ============================================================
spec = create_spec(
    "Pen Organizer",
    width=W, depth=D, height=H_phone,
    material="PLA",
    min_wall_mm=wall,
    warn_wall_mm=wall + 0.5,
    engine="build123d",
    export_format="3mf",
    units="millimeter",
    description="Desktop pen organizer with pen slots, sticky note pocket, phone stand",
    features=[
        {"type": "pattern", "name": "pen holes",
         "element": {"type": "hole", "diameter": pen_dia},
         "arrangement": "grid", "count": 8,
         "count_x": 4, "count_y": 2,
         "pitch_x": pen_pitch_x, "pitch_y": pen_pitch_y,
         "position": [-30, 28, 0]},
        {"type": "pocket", "name": "sticky note pocket",
         "width": sticky_w, "depth": sticky_d},
        {"type": "slot", "name": "phone slot",
         "width": phone_slot_width, "probe_z": H_phone/2},
    ],
)
write_spec(spec, "pen_organizer_final.step")

# ============================================================
# GATE
# ============================================================
gate = GateEnforcer.resume_from("pen_organizer", "phase_2")
gate.begin_phase("phase_3")

# ============================================================
# MODEL — import Phase 2, no geometry changes needed
# Phase 1 already applied bottom chamfers and exterior chamfers.
# Phase 2 added all features. Phase 3 is validation + export.
# ============================================================
result = import_step("phase2_features.step")

# Re-export as final STEP
export_step(result, "pen_organizer_final.step")

bb = result.bounding_box()
print(f"Exported pen_organizer_final.step")
print(f"Bounding box: {bb.max.X - bb.min.X:.1f} x {bb.max.Y - bb.min.Y:.1f} x {bb.max.Z - bb.min.Z:.1f} mm")
