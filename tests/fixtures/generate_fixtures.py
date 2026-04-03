#!/usr/bin/env python3
"""Generate test fixture files for novel-cad-skill test suite."""

import sys
import json
import os
from pathlib import Path

# Add lib to path for spec_format
SKILL_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SKILL_DIR / "lib"))

from spec_format import create_spec, write_spec

FIXTURE_DIR = Path(__file__).resolve().parent


def generate_good_box():
    """Simple 30x20x15mm box with 2mm walls and a 4.3mm hole."""
    from build123d import (
        BuildPart, Box, Hole, fillet, Axis, export_step, export_stl
    )

    width, depth, height = 30.0, 20.0, 15.0
    wall = 2.0
    hole_d = 4.3  # M4 + 0.3mm clearance

    with BuildPart() as part:
        Box(width, depth, height)
        fillet(part.edges().filter_by(Axis.Z), radius=2.0)
        # Hole in center, through
        Hole(radius=hole_d / 2.0, depth=height)

    step_path = str(FIXTURE_DIR / "good_box.step")
    stl_path = str(FIXTURE_DIR / "good_box.stl")
    export_step(part.part, step_path)
    export_stl(part.part, stl_path)
    print(f"Exported: {step_path}")
    print(f"Exported: {stl_path}")

    # Spec
    spec = create_spec(
        "Test box",
        width=width, depth=depth, height=height,
        material="PLA", min_wall_mm=wall,
        engine="build123d",
        features=[
            {"type": "hole", "name": "center hole", "diameter": hole_d,
             "position": [0, 0]},
        ],
    )
    write_spec(spec, step_path)


def generate_box_with_slots():
    """40x30x20mm box with 2 parallel slots — tests pattern/slot validation."""
    from build123d import Box, Pos, export_step

    width, depth, height = 40.0, 30.0, 20.0
    slot_w, slot_d, slot_h = 5.0, 20.0, 15.0

    # Algebra mode — more reliable for positioned subtractions
    body = Box(width, depth, height)
    slot1 = Pos(-8, 0, 0) * Box(slot_w, slot_d, slot_h)
    slot2 = Pos(8, 0, 0) * Box(slot_w, slot_d, slot_h)
    result = body - slot1 - slot2

    step_path = str(FIXTURE_DIR / "box_with_slots.step")
    export_step(result, step_path)
    print(f"Exported: {step_path}")

    spec = create_spec(
        "Slotted box",
        width=width, depth=depth, height=height,
        material="PLA", min_wall_mm=2.0,
        engine="build123d",
        features=[
            {"type": "slot", "name": "left slot", "width": slot_w,
             "probe_z": height / 2.0, "tolerance": 0.5},
            {"type": "slot", "name": "right slot", "width": slot_w,
             "probe_z": height / 2.0, "tolerance": 0.5},
        ],
    )
    write_spec(spec, step_path)


def generate_non_manifold():
    """Create an intentionally non-manifold STL (two boxes sharing an edge)."""
    import numpy as np
    import trimesh

    # Two cubes sharing a single edge — non-manifold topology
    box1 = trimesh.creation.box(extents=[10, 10, 10])
    box2 = trimesh.creation.box(extents=[10, 10, 10])
    box2.apply_translation([10, 0, 0])

    # Concatenate without boolean union — shared edge is non-manifold
    combined = trimesh.util.concatenate([box1, box2])

    # Corrupt: duplicate a face to create a non-manifold condition
    verts = np.array(combined.vertices)
    faces = np.array(combined.faces)
    # Add a degenerate face that shares an edge with two different faces
    extra_face = np.array([[0, 1, faces.shape[0] % len(verts)]])
    faces = np.vstack([faces, extra_face])

    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    stl_path = str(FIXTURE_DIR / "non_manifold.stl")
    mesh.export(stl_path)
    print(f"Exported: {stl_path}")


def generate_spec_only():
    """Generate a spec with no geometry — for testing spec_format in isolation."""
    spec = create_spec(
        "Spec-only test",
        width=50.0, depth=30.0, height=25.0,
        material="PETG", min_wall_mm=1.5,
        engine="build123d",
        features=[
            {"type": "hole", "name": "M3 mount", "diameter": 3.3,
             "position": [10, 10]},
            {"type": "pocket", "name": "battery bay", "width": 15.0,
             "depth": 50.0},
            {"type": "pattern", "name": "vent grid",
             "element": {"type": "slot", "width": 2.0, "length": 12.0},
             "arrangement": "linear", "count": 8, "pitch": 3.0,
             "position": [0, 0, 0], "direction": [1, 0, 0]},
        ],
        components=[
            {"name": "AA battery", "length": 50.5, "width": 14.5,
             "height": 14.5, "clearance_mm": 0.3},
        ],
    )
    spec_path = str(FIXTURE_DIR / "spec_only.spec.json")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    print(f"Written: {spec_path}")


if __name__ == "__main__":
    print("Generating test fixtures...")
    print()

    print("1. good_box (STEP + STL + spec)")
    generate_good_box()
    print()

    print("2. box_with_slots (STEP + spec)")
    generate_box_with_slots()
    print()

    print("3. non_manifold (STL)")
    generate_non_manifold()
    print()

    print("4. spec_only (spec.json)")
    generate_spec_only()
    print()

    print("Done. Fixtures in:", FIXTURE_DIR)
