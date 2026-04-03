"""
mesh_utils.py -- Shared OCC tessellation for the novel-cad-skill pipeline.

All scripts that need to load STEP files and convert to trimesh should use
load_mesh_from_step() from this module. This ensures consistent tessellation
tolerance (0.05mm) across validate_manifold, check_printability, export_3mf,
render_preview, and render_cross_sections.

Usage:
    from mesh_utils import load_mesh_from_step, load_mesh_auto
"""

import os
import numpy as np
from pathlib import Path


# Tessellation tolerance in mm. 0.05mm gives accurate normals and
# reasonable triangle counts for FDM-scale parts (50-200mm).
TESSELLATION_TOLERANCE = 0.05
TESSELLATION_ANGULAR = 0.1


def _get_occ_solid(step_path: str):
    """Load a STEP file and return the raw OCC TopoDS_Shape.

    Tries build123d first; falls back to CadQuery.
    """
    solid = None
    try:
        from build123d import import_step
        shape = import_step(step_path)
        solid = shape.wrapped
    except (ImportError, Exception):
        pass

    if solid is None:
        try:
            import cadquery as cq
            shape = cq.importers.importStep(step_path)
            solid = shape.val().wrapped
        except Exception as e:
            raise ValueError(f"Could not load STEP with build123d or CadQuery: {e}")

    return solid


def tessellate_occ_solid(solid, tolerance=TESSELLATION_TOLERANCE,
                         angular_tolerance=TESSELLATION_ANGULAR):
    """Tessellate an OCC solid and return (vertices, faces) as numpy arrays.

    Returns:
        verts: np.ndarray shape (N, 3) float64
        faces: np.ndarray shape (M, 3) int32
    """
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    BRepMesh_IncrementalMesh(solid, tolerance, False, angular_tolerance)

    verts_list, tris_list = [], []
    offset = 0
    exp = TopExp_Explorer(solid, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        loc = TopLoc_Location()
        poly = BRep_Tool.Triangulation_s(face, loc)
        if poly is not None:
            trsf = loc.Transformation()
            is_id = loc.IsIdentity()
            nodes = []
            for i in range(1, poly.NbNodes() + 1):
                p = poly.Node(i)
                if not is_id:
                    p = p.Transformed(trsf)
                nodes.append([p.X(), p.Y(), p.Z()])
            for i in range(1, poly.NbTriangles() + 1):
                t = poly.Triangle(i)
                i1, i2, i3 = t.Get()
                tris_list.append([i1 - 1 + offset, i2 - 1 + offset, i3 - 1 + offset])
            verts_list.extend(nodes)
            offset += len(nodes)
        exp.Next()

    if not verts_list:
        raise ValueError("No geometry extracted from STEP solid")

    verts = np.array(verts_list, dtype=np.float64)
    faces = np.array(tris_list, dtype=np.int32)
    return verts, faces


def load_mesh_from_step(step_path: str):
    """Load a STEP file and return a trimesh.Trimesh.

    Uses OCC tessellation at TESSELLATION_TOLERANCE (0.05mm).
    This is the canonical STEP-to-mesh path for the entire pipeline.
    """
    import trimesh

    solid = _get_occ_solid(step_path)
    verts, faces = tessellate_occ_solid(solid)
    # process=True merges duplicate vertices at shared edges.
    # fix_normals + fix_winding ensure consistent face orientation —
    # required for manifold3d which rejects inconsistent winding.
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    trimesh.repair.fix_normals(mesh)
    trimesh.repair.fix_winding(mesh)
    return mesh


def load_mesh_auto(input_path: str):
    """Load STEP, STL, or 3MF and return a trimesh.Trimesh.

    STEP files go through OCC tessellation. Everything else uses trimesh
    directly.
    """
    import trimesh

    ext = Path(input_path).suffix.lower()

    if ext in (".step", ".stp"):
        return load_mesh_from_step(input_path)

    mesh = trimesh.load(input_path, force="mesh")
    if isinstance(mesh, trimesh.Scene):
        parts = [g for g in mesh.geometry.values()
                 if isinstance(g, trimesh.Trimesh)]
        if not parts:
            raise ValueError(f"No mesh geometry found in {input_path}")
        mesh = trimesh.util.concatenate(parts)
    return mesh


def load_face_groups_from_step(step_path: str, tolerance=TESSELLATION_TOLERANCE):
    """Load STEP and return per-B-rep-face triangle groups for rendering.

    Returns list of (vertices_array, faces_array) per OCC face.
    Used by render_preview.py for per-face shading.
    """
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopoDS import TopoDS

    solid = _get_occ_solid(step_path)
    BRepMesh_IncrementalMesh(solid, tolerance, False, TESSELLATION_ANGULAR)

    groups = []
    exp = TopExp_Explorer(solid, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        loc = TopLoc_Location()
        poly = BRep_Tool.Triangulation_s(face, loc)
        if poly is not None:
            trsf = loc.Transformation()
            is_identity = loc.IsIdentity()
            nodes = []
            for i in range(1, poly.NbNodes() + 1):
                p = poly.Node(i)
                if not is_identity:
                    p = p.Transformed(trsf)
                nodes.append([p.X(), p.Y(), p.Z()])
            tris = []
            for i in range(1, poly.NbTriangles() + 1):
                t = poly.Triangle(i)
                i1, i2, i3 = t.Get()
                tris.append([i1 - 1, i2 - 1, i3 - 1])
            if nodes and tris:
                groups.append((np.array(nodes), np.array(tris)))
        exp.Next()
    return groups
