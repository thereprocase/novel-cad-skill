#!/usr/bin/env python3
"""
validate_manifold.py -- Mesh topology validator using manifold3d.

Checks whether a tessellated solid is manifold (watertight, no
self-intersections, no T-junctions). Non-manifold meshes cause slicer
failures, infill leaks, and unprintable geometry.

Sits between construction and export in the validation pipeline:
  BuildPart -> validate_geometry -> check_printability -> validate_manifold -> export_3mf

Usage:
    python validate_manifold.py part.step
    python validate_manifold.py part.stl
    python validate_manifold.py part.step --fix --output fixed.stl

Exit code 0 = manifold (or repaired successfully with --fix).
Exit code 1 = not manifold.
"""

import argparse
import sys
import os
from pathlib import Path

import numpy as np


def _load_mesh_from_step(step_path):
    """Tessellate a STEP file to vertices + faces arrays."""
    try:
        from build123d import import_step
        solid = import_step(step_path)
        tess = solid.tessellate(tolerance=0.01)
        verts = np.array([(v.X, v.Y, v.Z) for v in tess[0]], dtype=np.float64)
        faces = np.array(tess[1], dtype=np.int32)
        return verts, faces
    except ImportError:
        import cadquery as cq
        import tempfile
        import trimesh

        shape = cq.importers.importStep(step_path)
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            cq.exporters.export(shape, tmp_path, exportType="STL",
                                tolerance=0.01, angularTolerance=0.1)
            mesh = trimesh.load(tmp_path, force="mesh")
            return np.array(mesh.vertices, dtype=np.float64), np.array(mesh.faces, dtype=np.int32)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _load_mesh_from_file(input_path):
    """Load vertices + faces from STEP, STL, or 3MF."""
    ext = Path(input_path).suffix.lower()

    if ext in (".step", ".stp"):
        return _load_mesh_from_step(input_path)

    import trimesh
    mesh = trimesh.load(input_path, force="mesh")
    if isinstance(mesh, trimesh.Scene):
        parts = [g for g in mesh.geometry.values()
                 if isinstance(g, trimesh.Trimesh)]
        if not parts:
            raise ValueError(f"No mesh geometry found in {input_path}")
        mesh = trimesh.util.concatenate(parts)

    return np.array(mesh.vertices, dtype=np.float64), np.array(mesh.faces, dtype=np.int32)


def check_manifold(verts, faces):
    """Check manifoldness using manifold3d. Falls back to trimesh.

    Returns (is_manifold, detail_string).
    """
    try:
        import manifold3d

        mesh = manifold3d.Mesh(
            vert_properties=verts.astype(np.float32).reshape(-1, 3),
            tri_verts=faces.astype(np.uint32).reshape(-1, 3),
        )
        m = manifold3d.Manifold(mesh=mesh)
        status = m.status()
        if status == manifold3d.Manifold.Error.NoError:
            return True, (
                f"Manifold OK: {len(verts)} vertices, {len(faces)} triangles, "
                f"genus {m.genus()}"
            )
        else:
            return False, f"Manifold error: {status.name}"

    except ImportError:
        # Fallback: trimesh watertight + volume checks
        import trimesh
        tm = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
        issues = []
        if not tm.is_watertight:
            issues.append("not watertight (open edges)")
        if not tm.is_volume:
            issues.append("not a valid volume")

        if issues:
            return False, f"trimesh fallback: {'; '.join(issues)}"
        return True, (
            f"trimesh fallback PASS: {len(verts)} vertices, {len(faces)} triangles, "
            f"watertight=True, volume=True"
        )

    except Exception as e:
        return False, f"Manifold check raised: {e}"


def attempt_repair(verts, faces):
    """Try to repair non-manifold mesh via trimesh, then re-check.

    Returns (success, repaired_trimesh_or_None, detail_string).
    """
    import trimesh

    tm = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    trimesh.repair.fill_holes(tm)
    trimesh.repair.fix_normals(tm)
    trimesh.repair.fix_winding(tm)

    repaired_verts = np.array(tm.vertices, dtype=np.float64)
    repaired_faces = np.array(tm.faces, dtype=np.int32)

    ok, detail = check_manifold(repaired_verts, repaired_faces)
    if ok:
        delta_v = len(repaired_verts) - len(verts)
        delta_f = len(repaired_faces) - len(faces)
        return True, tm, (
            f"Repair succeeded: {detail} "
            f"(vertices delta: {delta_v:+d}, faces delta: {delta_f:+d})"
        )
    return False, None, f"Repair failed: {detail}"


def main():
    parser = argparse.ArgumentParser(
        description="Validate mesh manifoldness for 3D printing."
    )
    parser.add_argument("input_file", help="Path to STEP, STL, or 3MF file")
    parser.add_argument("--fix", action="store_true",
                        help="Attempt repair if non-manifold")
    parser.add_argument("--output", default=None,
                        help="Output path for repaired mesh (requires --fix)")
    args = parser.parse_args()

    if not os.path.exists(args.input_file):
        print(f"Error: file not found: {args.input_file}")
        sys.exit(1)

    print(f"Loading: {args.input_file}")
    verts, faces = _load_mesh_from_file(args.input_file)
    print(f"Mesh: {len(verts)} vertices, {len(faces)} triangles")

    ok, detail = check_manifold(verts, faces)
    print(f"[manifold] {detail}")

    if ok:
        print("[PASS] Mesh is manifold")
        sys.exit(0)

    if not args.fix:
        print("[FAIL] Mesh is NOT manifold")
        sys.exit(1)

    print("[manifold] Attempting repair...")
    repaired, mesh, repair_detail = attempt_repair(verts, faces)
    print(f"[manifold] {repair_detail}")

    if not repaired:
        print("[FAIL] Repair unsuccessful")
        sys.exit(1)

    output_path = args.output
    if output_path is None:
        stem = Path(args.input_file).stem
        output_path = str(Path(args.input_file).parent / f"{stem}_repaired.stl")

    mesh.export(output_path)
    print(f"[PASS] Repaired mesh exported: {output_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
