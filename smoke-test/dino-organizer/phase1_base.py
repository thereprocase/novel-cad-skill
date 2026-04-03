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
base_h = 15.0           # mm — base slab height

# Irregular hexagon vertices — perturbed regular hex (~120x80mm footprint)
# Start with regular hex inscribed in ~60mm radius, then perturb ±5-8mm
# and scale X vs Y to get 120x80 footprint
hex_vertices = [
    (55.0, 5.0),        # right (perturbed from 60, 0)
    (32.0, 38.0),       # upper-right (perturbed from 30, 35)
    (-28.0, 42.0),      # upper-left (perturbed from -30, 35)
    (-58.0, -3.0),      # left (perturbed from -60, 0)
    (-35.0, -36.0),     # lower-left (perturbed from -30, -35)
    (25.0, -40.0),      # lower-right (perturbed from 30, -35)
]

# Bounding box for spec
xs = [v[0] for v in hex_vertices]
ys = [v[1] for v in hex_vertices]
bb_w = max(xs) - min(xs)  # ~113mm
bb_d = max(ys) - min(ys)  # ~82mm

# ============================================================
# SPEC
# ============================================================
spec = create_spec(
    "Dino Desk Organizer — Base",
    width=bb_w, depth=bb_d, height=base_h,
    material="PLA",
    min_wall_mm=2.0,
    warn_wall_mm=2.5,
    engine="build123d",
    export_format="3mf",
    units="millimeter",
    description="Irregular hexagonal base slab for dinosaur-themed desk organizer",
)
write_spec(spec, "phase1_base.step")

# ============================================================
# GATE
# ============================================================
gate = GateEnforcer("dino_organizer")
gate.begin_phase("phase_1")

# ============================================================
# MODEL — irregular hexagonal base
# ============================================================
with BuildPart() as part:
    with BuildSketch() as sk:
        with BuildLine() as ln:
            for i in range(len(hex_vertices)):
                x1, y1 = hex_vertices[i]
                x2, y2 = hex_vertices[(i + 1) % len(hex_vertices)]
                Line((x1, y1), (x2, y2))
        make_face()
    extrude(amount=base_h)

result = part.part

# ============================================================
# EXPORT
# ============================================================
export_step(result, "phase1_base.step")
print(f"Exported phase1_base.step")
print(f"Bounding box: {bb_w:.1f} x {bb_d:.1f} x {base_h:.1f} mm")
print(f"Hex vertices: {hex_vertices}")
