#!/usr/bin/env python3
"""
export_3mf.py -- Export a STEP file to 3MF format with spec metadata.

Reads the sibling .spec.json (same stem as input STEP) for part name, material,
color, and description. Falls back to STL if 3MF export fails.

Units in the 3MF file are always millimeters.

Usage:
    python export_3mf.py part.step output.3mf
    python export_3mf.py part.step output.3mf --spec custom.spec.json
    python export_3mf.py part.step output.3mf --color 0.2 0.6 0.8 1.0
"""

import sys
import os
import json
import argparse
from pathlib import Path


def _load_spec(step_path: str, spec_path: str = None) -> dict:
    """Load spec JSON if available; return empty dict on failure."""
    if spec_path is None:
        candidate = Path(step_path).with_suffix(".spec.json")
        if candidate.exists():
            spec_path = str(candidate)

    if spec_path and os.path.exists(spec_path):
        try:
            with open(spec_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _step_to_trimesh(step_path: str):
    """
    Load a STEP file and return a trimesh.Trimesh via OCC tessellation.

    Tries build123d first; falls back to CadQuery. Tessellation tolerance
    is 0.05mm to match the rest of the pipeline.
    """
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    import numpy as np
    import trimesh

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

    BRepMesh_IncrementalMesh(solid, 0.05, False, 0.1)

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
        raise ValueError(f"No geometry extracted from STEP: {step_path}")

    verts = np.array(verts_list, dtype=np.float64)
    faces = np.array(tris_list, dtype=np.int32)
    return trimesh.Trimesh(vertices=verts, faces=faces, process=False)


def _build_3mf_xml(mesh, part_name: str, material: str, color_rgba: list,
                    description: str) -> bytes:
    """
    Build a minimal 3MF XML document. Units are millimeters.

    Returns the XML as UTF-8 bytes. This is the inner 3dmodel.model content
    that goes into the 3MF ZIP archive.
    """
    import xml.etree.ElementTree as ET

    NS_3MF = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    NS_MATERIAL = "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"

    ET.register_namespace("", NS_3MF)
    ET.register_namespace("m", NS_MATERIAL)

    model = ET.Element(f"{{{NS_3MF}}}model")
    model.set("unit", "millimeter")
    model.set("xml:lang", "en-US")

    # Metadata
    def add_meta(name, value):
        m = ET.SubElement(model, f"{{{NS_3MF}}}metadata")
        m.set("name", name)
        m.text = str(value)

    add_meta("Title", part_name)
    add_meta("Description", description or part_name)
    if material:
        add_meta("Designer", "novel-cad-skill")
        add_meta("Application", material)

    resources = ET.SubElement(model, f"{{{NS_3MF}}}resources")

    # Color resource (sRGB hex)
    r, g, b, a = [max(0.0, min(1.0, float(c))) for c in color_rgba]
    hex_color = "#{:02X}{:02X}{:02X}{:02X}".format(
        int(r * 255), int(g * 255), int(b * 255), int(a * 255)
    )
    color_group = ET.SubElement(resources, f"{{{NS_MATERIAL}}}colorgroup")
    color_group.set("id", "1")
    color_item = ET.SubElement(color_group, f"{{{NS_MATERIAL}}}color")
    color_item.set("color", hex_color)

    # Object resource
    obj = ET.SubElement(resources, f"{{{NS_3MF}}}object")
    obj.set("id", "2")
    obj.set("type", "model")
    obj.set("name", part_name)
    obj.set(f"{{{NS_MATERIAL}}}colorid", "1")

    mesh_el = ET.SubElement(obj, f"{{{NS_3MF}}}mesh")

    vertices_el = ET.SubElement(mesh_el, f"{{{NS_3MF}}}vertices")
    for v in mesh.vertices:
        vert = ET.SubElement(vertices_el, f"{{{NS_3MF}}}vertex")
        vert.set("x", f"{v[0]:.6f}")
        vert.set("y", f"{v[1]:.6f}")
        vert.set("z", f"{v[2]:.6f}")

    triangles_el = ET.SubElement(mesh_el, f"{{{NS_3MF}}}triangles")
    for tri in mesh.faces:
        t = ET.SubElement(triangles_el, f"{{{NS_3MF}}}triangle")
        t.set("v1", str(tri[0]))
        t.set("v2", str(tri[1]))
        t.set("v3", str(tri[2]))

    build = ET.SubElement(model, f"{{{NS_3MF}}}build")
    item = ET.SubElement(build, f"{{{NS_3MF}}}item")
    item.set("objectid", "2")

    return ET.tostring(model, encoding="utf-8", xml_declaration=True)


def export_3mf_trimesh(mesh, output_path: str, part_name: str, material: str,
                        color_rgba: list, description: str) -> bool:
    """
    Write a 3MF archive using Python's zipfile. Builds the XML manually
    to avoid trimesh version-specific API differences.

    Returns True on success, False on failure.
    """
    import zipfile

    try:
        xml_bytes = _build_3mf_xml(mesh, part_name, material, color_rgba, description)

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Required content types
            content_types = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
                '</Types>'
            )
            zf.writestr("[Content_Types].xml", content_types)

            # Required relationships
            rels = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
                'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
                '</Relationships>'
            )
            zf.writestr("_rels/.rels", rels)

            # 3D model content
            zf.writestr("3D/3dmodel.model", xml_bytes)

        return True
    except Exception as e:
        print(f"[WARN] 3MF export failed: {e}", file=sys.stderr)
        return False


def export_stl_fallback(mesh, output_path: str) -> bool:
    """Write STL as fallback when 3MF export fails."""
    try:
        import trimesh
        stl_path = Path(output_path).with_suffix(".stl")
        mesh.export(str(stl_path))
        print(f"[WARN] 3MF failed -- exported STL fallback: {stl_path}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"[ERROR] STL fallback also failed: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Export STEP to 3MF with spec metadata.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input",  help="Input .step or .stp file")
    parser.add_argument("output", help="Output .3mf file")
    parser.add_argument("--spec", default=None,
                        help="Spec JSON path (default: auto-detect sibling .spec.json)")
    parser.add_argument("--color", nargs=4, type=float, metavar=("R", "G", "B", "A"),
                        default=None,
                        help="RGBA color override (0.0-1.0 each, overrides spec)")
    args = parser.parse_args()

    input_path  = os.path.realpath(args.input)
    output_path = os.path.realpath(args.output)

    if not os.path.exists(input_path):
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        sys.exit(2)

    spec = _load_spec(input_path, args.spec)

    part_name   = spec.get("part_name", Path(input_path).stem)
    material    = spec.get("material", "")
    description = spec.get("description", part_name)

    # Color: CLI flag overrides spec; spec overrides default PLA grey
    if args.color:
        color_rgba = args.color
    elif "color" in spec:
        color_rgba = spec["color"]
    else:
        color_rgba = [0.75, 0.75, 0.75, 1.0]  # default PLA grey

    print(f"Loading STEP: {input_path}")
    try:
        mesh = _step_to_trimesh(input_path)
    except Exception as e:
        print(f"Error loading geometry: {e}", file=sys.stderr)
        sys.exit(2)

    print(f"Mesh: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
    print(f"Part: {part_name} | Material: {material or '(none)'}")
    print(f"Color RGBA: {color_rgba}")

    success = export_3mf_trimesh(mesh, output_path, part_name, material,
                                  color_rgba, description)

    if success:
        size_kb = os.path.getsize(output_path) / 1024
        print(f"3MF exported: {output_path} ({size_kb:.1f} KB)")
        sys.exit(0)
    else:
        export_stl_fallback(mesh, output_path)
        sys.exit(1)


if __name__ == "__main__":
    main()
