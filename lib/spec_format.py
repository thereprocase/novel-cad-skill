"""
spec_format.py — Intent capture format for novel-cad-skill validation.

Claude fills in a spec dict immediately after the parameters block, before
any geometry is generated. The spec is the contract between design intent
and post-export validation. Both validate_geometry.py and
check_printability.py read this file to know what to check against.

Evolved from cad-skill spec_format.py. Additions:
  - "pattern" feature type for ventilation grids and hole arrays
  - "assembly" field for multi-part specs (base + lid)
  - "engine" field to track which CAD engine generated geometry
  - "warn_wall_mm" for soft warning threshold
  - "export_format" / "color" / "units" / "description" for 3MF metadata
  - "sub_phases" for complex part decomposition
  - "manifold_check" to control mesh topology validation

Usage in a build123d script:
    from pathlib import Path
    import sys
    sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/lib"))
    from spec_format import create_spec, write_spec

    spec = create_spec(
        "DDR4 DIMM tray",
        width=60.0, depth=40.0, height=25.0,
        material="PLA", min_wall_mm=2.0,
        engine="build123d",
        features=[
            {"type": "slot", "name": "DIMM slot", "width": 5.0,
             "probe_z": 5.0, "tolerance": 0.3},
            {"type": "pattern", "name": "vent grid",
             "element": {"type": "slot", "width": 2.0, "length": 15.0},
             "arrangement": "linear", "count": 20, "pitch": 3.0,
             "position": [10.0, 20.0, 0.0], "direction": [1.0, 0.0, 0.0]},
        ],
    )
    write_spec(spec, "dimm_tray.step")
"""

import json
import os
from pathlib import Path

# ── Defaults ──────────────────────────────────────────────────────────────────

# Minimum acceptable wall thickness per material. FDM extrusion width is
# typically 0.4-0.45mm; two walls = ~0.9mm. 1.2mm is the hard floor,
# 2.0mm is the structural target.
_MIN_WALL_DEFAULTS = {
    "PLA":  1.2,
    "PETG": 1.2,
    "TPU":  3.0,   # TPU needs more wall for structure; flex absorbs compression
    "ABS":  1.2,
}

# Extra clearance added per material on top of what the design specifies.
# PLA is the baseline. PETG strings slightly. TPU swells under compression.
_EXTRA_CLEARANCE = {
    "PLA":  0.0,
    "PETG": 0.1,
    "TPU":  0.2,
    "ABS":  0.0,
}

_VALID_MATERIALS = set(_MIN_WALL_DEFAULTS.keys())

_VALID_FEATURE_TYPES = {"slot", "hole", "pocket", "rail", "channel", "pattern",
                        "boss", "standoff", "rib", "sweep", "loft", "revolve"}

_VALID_ENGINES = {"build123d", "cadquery", "openscad"}

_VALID_ARRANGEMENTS = {"linear", "grid", "radial", "polar"}

_VALID_EXPORT_FORMATS = {"step", "stl", "3mf"}

_DEFAULT_TOLERANCE_MM = 0.3   # +/-mm on nominal dimension checks
_DEFAULT_BRIDGE_SPAN_MM = 20.0
_DEFAULT_OVERHANG_ANGLE_DEG = 45.0


# ── Public API ────────────────────────────────────────────────────────────────

def validate_spec(spec: dict) -> dict:
    """Validate spec dict and fill in defaults for optional fields.

    Raises ValueError with a specific message if required fields are missing
    or values are out of range. Returns a new dict with defaults applied so
    downstream validators never have to handle missing keys.

    Required fields: part_name, overall_dimensions (with width/depth/height).
    All other fields are optional and get sensible defaults.
    """
    if not isinstance(spec, dict):
        raise ValueError("spec must be a dict")

    out = dict(spec)  # shallow copy

    # ── part_name ──
    if "part_name" not in out or not out["part_name"]:
        raise ValueError("spec requires 'part_name' (non-empty string)")
    out["part_name"] = str(out["part_name"])

    # ── overall_dimensions ──
    dims = out.get("overall_dimensions")
    if not dims:
        raise ValueError("spec requires 'overall_dimensions' with width, depth, height")
    for axis in ("width", "depth", "height"):
        if axis not in dims:
            raise ValueError(f"spec.overall_dimensions missing '{axis}'")
        val = float(dims[axis])
        if val <= 0:
            raise ValueError(f"spec.overall_dimensions.{axis} must be > 0, got {val}")
    out["overall_dimensions"] = {
        "width":     float(dims["width"]),
        "depth":     float(dims["depth"]),
        "height":    float(dims["height"]),
        "tolerance": float(dims.get("tolerance", _DEFAULT_TOLERANCE_MM)),
    }

    # ── material ──
    material = out.get("material", "PLA").upper()
    if material not in _VALID_MATERIALS:
        raise ValueError(
            f"spec.material '{material}' not recognized. "
            f"Valid values: {sorted(_VALID_MATERIALS)}"
        )
    out["material"] = material

    # ── min_wall_mm ──
    if "min_wall_mm" not in out:
        out["min_wall_mm"] = _MIN_WALL_DEFAULTS[material]
    else:
        out["min_wall_mm"] = float(out["min_wall_mm"])
        if out["min_wall_mm"] <= 0:
            raise ValueError(f"spec.min_wall_mm must be > 0, got {out['min_wall_mm']}")

    # ── warn_wall_mm (soft threshold) ──
    if "warn_wall_mm" in out:
        out["warn_wall_mm"] = float(out["warn_wall_mm"])
        if out["warn_wall_mm"] <= out["min_wall_mm"]:
            raise ValueError(
                f"spec.warn_wall_mm ({out['warn_wall_mm']}) must be > "
                f"min_wall_mm ({out['min_wall_mm']})"
            )
    else:
        # Default warn band: 125% of min_wall
        out["warn_wall_mm"] = round(out["min_wall_mm"] * 1.25, 2)

    # ── engine ──
    engine = out.get("engine", "build123d").lower()
    if engine not in _VALID_ENGINES:
        raise ValueError(
            f"spec.engine '{engine}' not recognized. "
            f"Valid values: {sorted(_VALID_ENGINES)}"
        )
    out["engine"] = engine

    # ── export_format ──
    export_fmt = out.get("export_format", "3mf").lower()
    if export_fmt not in _VALID_EXPORT_FORMATS:
        raise ValueError(
            f"spec.export_format '{export_fmt}' not recognized. "
            f"Valid values: {sorted(_VALID_EXPORT_FORMATS)}"
        )
    out["export_format"] = export_fmt

    # ── 3MF metadata ──
    if "color" in out:
        color = out["color"]
        if not isinstance(color, (list, tuple)) or len(color) not in (3, 4):
            raise ValueError("spec.color must be [R, G, B] or [R, G, B, A] (0.0-1.0)")
        out["color"] = [float(c) for c in color]
    else:
        out["color"] = [0.7, 0.7, 0.7, 1.0]  # default PLA grey

    out["units"] = out.get("units", "millimeter")
    out["description"] = str(out.get("description", ""))

    # ── manifold_check ──
    out["manifold_check"] = bool(out.get("manifold_check", True))

    # ── components ──
    components = out.get("components", [])
    if not isinstance(components, list):
        raise ValueError("spec.components must be a list")
    validated_components = []
    for i, comp in enumerate(components):
        c = _validate_component(comp, i)
        c["effective_clearance_mm"] = (
            c["clearance_mm"] + _EXTRA_CLEARANCE[material]
        )
        validated_components.append(c)
    out["components"] = validated_components

    # ── features ──
    features = out.get("features", [])
    if not isinstance(features, list):
        raise ValueError("spec.features must be a list")
    out["features"] = [_validate_feature(f, i) for i, f in enumerate(features)]

    # ── sub_phases ──
    if "sub_phases" in out:
        sp = out["sub_phases"]
        if not isinstance(sp, dict):
            raise ValueError("spec.sub_phases must be a dict mapping phase names to feature lists")
        feature_names = {f["name"] for f in out["features"]}
        for phase_name, phase_features in sp.items():
            if not isinstance(phase_features, list):
                raise ValueError(f"spec.sub_phases['{phase_name}'] must be a list of feature names")
            for fname in phase_features:
                if fname not in feature_names:
                    raise ValueError(
                        f"spec.sub_phases['{phase_name}'] references unknown feature '{fname}'. "
                        f"Known features: {sorted(feature_names)}"
                    )

    # ── assembly ──
    if "assembly" in out:
        assembly = out["assembly"]
        if not isinstance(assembly, list):
            raise ValueError("spec.assembly must be a list of part dicts")
        validated_assembly = []
        for i, apart in enumerate(assembly):
            if not isinstance(apart, dict):
                raise ValueError(f"spec.assembly[{i}] must be a dict")
            if "name" not in apart:
                raise ValueError(f"spec.assembly[{i}] missing 'name'")
            if "role" not in apart:
                raise ValueError(
                    f"spec.assembly[{i}] missing 'role' "
                    f"(e.g., 'base', 'lid', 'bracket')"
                )
            ap = dict(apart)
            ap["name"] = str(ap["name"])
            ap["role"] = str(ap["role"])
            ap["clearance_mm"] = float(ap.get("clearance_mm", 0.3))
            validated_assembly.append(ap)
        out["assembly"] = validated_assembly

    # ── printability thresholds ──
    out["overhangs_ok"] = bool(out.get("overhangs_ok", False))
    out["max_overhang_angle_deg"] = float(
        out.get("max_overhang_angle_deg", _DEFAULT_OVERHANG_ANGLE_DEG)
    )
    out["max_bridge_span_mm"] = float(
        out.get("max_bridge_span_mm", _DEFAULT_BRIDGE_SPAN_MM)
    )

    return out


def create_spec(name: str, width: float = 0, depth: float = 0,
                height: float = 0, **kwargs) -> dict:
    """Build a spec dict with required fields pre-filled, then validate it.

    Positional shorthand for the common case where you know the outer dims
    and just need to tack on components/features:

        spec = create_spec(
            "DDR4 DIMM tray",
            width=60.0, depth=40.0, height=25.0,
            material="PLA", min_wall_mm=2.0,
            engine="build123d",
            features=[...],
        )

    Returns a validated spec dict ready for write_spec().
    """
    raw = {
        "part_name": name,
        "overall_dimensions": {
            "width": width,
            "depth": depth,
            "height": height,
        },
    }
    raw.update(kwargs)

    # Let tolerance pass through to overall_dimensions if given as a kwarg.
    # Pop from raw (not kwargs) to remove the phantom top-level key
    # that raw.update(kwargs) created.
    if "tolerance" in raw and "tolerance" not in raw.get("overall_dimensions", {}):
        raw["overall_dimensions"]["tolerance"] = raw.pop("tolerance")
    elif "tolerance" in raw and "tolerance" in raw.get("overall_dimensions", {}):
        raw.pop("tolerance", None)

    return validate_spec(raw)


def write_spec(spec: dict, output_path: str) -> str:
    """Validate spec and write it as JSON alongside the output file.

    output_path can be:
    - A STEP/STL/3MF file path: "part.step" -> writes "part.spec.json"
    - An explicit .spec.json path: written as-is

    Returns the path of the written .spec.json file.
    """
    validated = validate_spec(spec)

    p = Path(output_path)
    if p.suffix.lower() in (".step", ".stp", ".stl", ".3mf"):
        spec_path = p.with_suffix(".spec.json")
    elif p.suffix.lower() == ".json":
        spec_path = p
    else:
        spec_path = Path(str(p) + ".spec.json")

    spec_path.parent.mkdir(parents=True, exist_ok=True)
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(validated, f, indent=2)

    print(f"[spec] Written: {spec_path}")
    return str(spec_path)


def load_spec(spec_path: str) -> dict:
    """Load and validate a spec from a .spec.json file.

    Accepts:
    - Direct path to a .spec.json file
    - Path to a STEP/STL/3MF file — looks for the sibling .spec.json

    Raises FileNotFoundError if the spec file doesn't exist.
    Raises ValueError if the spec is malformed.
    """
    p = Path(spec_path)
    if p.suffix.lower() in (".step", ".stp", ".stl", ".3mf"):
        p = p.with_suffix(".spec.json")

    if not p.exists():
        raise FileNotFoundError(
            f"Spec file not found: {p}\n"
            f"Write a spec in your build123d script using write_spec() before exporting."
        )

    with open(p, "r", encoding="utf-8") as f:
        raw = json.load(f)

    return validate_spec(raw)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _validate_component(comp: dict, idx: int) -> dict:
    """Validate a single component spec dict. Returns normalized copy."""
    if not isinstance(comp, dict):
        raise ValueError(f"spec.components[{idx}] must be a dict")

    c = dict(comp)
    name = c.get("name", f"component_{idx}")
    c["name"] = str(name)

    for dim in ("length", "width", "height"):
        if dim not in c:
            raise ValueError(
                f"spec.components[{idx}] ('{name}') missing '{dim}'"
            )
        val = float(c[dim])
        if val <= 0:
            raise ValueError(
                f"spec.components[{idx}].{dim} must be > 0, got {val}"
            )
        c[dim] = val

    c["clearance_mm"] = float(c.get("clearance_mm", 0.3))
    if c["clearance_mm"] < 0:
        raise ValueError(
            f"spec.components[{idx}].clearance_mm must be >= 0, got {c['clearance_mm']}"
        )

    return c


def _validate_feature(feat: dict, idx: int) -> dict:
    """Validate a single feature spec dict. Returns normalized copy."""
    if not isinstance(feat, dict):
        raise ValueError(f"spec.features[{idx}] must be a dict")

    f = dict(feat)
    feat_type = f.get("type", "").lower()
    if feat_type not in _VALID_FEATURE_TYPES:
        raise ValueError(
            f"spec.features[{idx}].type '{feat_type}' not recognized. "
            f"Valid values: {sorted(_VALID_FEATURE_TYPES)}"
        )
    f["type"] = feat_type
    f["name"] = str(f.get("name", f"{feat_type}_{idx}"))
    f["tolerance"] = float(f.get("tolerance", _DEFAULT_TOLERANCE_MM))

    if feat_type == "slot":
        if "width" not in f:
            raise ValueError(f"spec.features[{idx}] (slot '{f['name']}') missing 'width'")
        f["width"] = float(f["width"])
        if f["width"] <= 0:
            raise ValueError(f"spec.features[{idx}].width must be > 0")
        f["probe_z"] = float(f.get("probe_z", 0.0))
        if "probe_axis" in f:
            axis = f["probe_axis"].lower()
            if axis not in ("x", "y", "z"):
                raise ValueError(f"spec.features[{idx}].probe_axis must be 'x', 'y', or 'z'")
            f["probe_axis"] = axis

    elif feat_type == "hole":
        if "diameter" not in f:
            raise ValueError(f"spec.features[{idx}] (hole '{f['name']}') missing 'diameter'")
        f["diameter"] = float(f["diameter"])
        if f["diameter"] <= 0:
            raise ValueError(f"spec.features[{idx}].diameter must be > 0")
        if "position" in f:
            pos = f["position"]
            if not isinstance(pos, (list, tuple)) or len(pos) < 2:
                raise ValueError(
                    f"spec.features[{idx}].position must be [x, y] or [x, y, z]"
                )
            f["position"] = [float(v) for v in pos]

    elif feat_type == "pattern":
        _validate_pattern_feature(f, idx)

    elif feat_type in ("pocket", "rail", "channel", "rib"):
        for dim in ("width", "depth"):
            if dim in f:
                f[dim] = float(f[dim])

    elif feat_type in ("boss", "standoff"):
        if "diameter" not in f:
            raise ValueError(f"spec.features[{idx}] ({feat_type} '{f['name']}') missing 'diameter'")
        f["diameter"] = float(f["diameter"])
        if f["diameter"] <= 0:
            raise ValueError(f"spec.features[{idx}].diameter must be > 0")
        if "position" in f:
            pos = f["position"]
            if not isinstance(pos, (list, tuple)) or len(pos) < 2:
                raise ValueError(
                    f"spec.features[{idx}].position must be [x, y] or [x, y, z]"
                )
            f["position"] = [float(v) for v in pos]

    elif feat_type in ("sweep", "loft", "revolve"):
        pass  # generic features — name validation is sufficient

    return f


def _validate_pattern_feature(f: dict, idx: int) -> None:
    """Validate a pattern feature in-place. Patterns describe arrays of
    identical sub-features (ventilation grids, screw hole arrays)."""

    # element: the repeated sub-feature
    if "element" not in f:
        raise ValueError(
            f"spec.features[{idx}] (pattern '{f.get('name', '')}') "
            f"missing 'element' dict describing the repeated feature"
        )
    elem = f["element"]
    if not isinstance(elem, dict):
        raise ValueError(f"spec.features[{idx}].element must be a dict")
    elem_type = elem.get("type", "").lower()
    if elem_type not in ("slot", "hole", "pocket"):
        raise ValueError(
            f"spec.features[{idx}].element.type '{elem_type}' not recognized. "
            f"Pattern elements must be 'slot', 'hole', or 'pocket'."
        )
    f["element"] = dict(elem)
    f["element"]["type"] = elem_type

    # arrangement
    arrangement = f.get("arrangement", "linear").lower()
    if arrangement not in _VALID_ARRANGEMENTS:
        raise ValueError(
            f"spec.features[{idx}].arrangement '{arrangement}' not recognized. "
            f"Valid values: {sorted(_VALID_ARRANGEMENTS)}"
        )
    if arrangement == "polar":
        arrangement = "radial"
    f["arrangement"] = arrangement

    # count
    if "count" not in f:
        raise ValueError(
            f"spec.features[{idx}] (pattern '{f.get('name', '')}') missing 'count'"
        )
    f["count"] = int(f["count"])
    if f["count"] < 1:
        raise ValueError(f"spec.features[{idx}].count must be >= 1")

    # pitch (spacing between elements; for radial, this is degrees)
    if "pitch" in f:
        f["pitch"] = float(f["pitch"])
        if arrangement == "radial":
            if f["pitch"] < 0:
                raise ValueError(f"spec.features[{idx}].pitch must be >= 0 for radial patterns")
        else:
            if f["pitch"] <= 0:
                raise ValueError(f"spec.features[{idx}].pitch must be > 0")

    # For grid arrangement, also accept count_x/count_y
    if arrangement == "grid":
        if "count_x" in f:
            f["count_x"] = int(f["count_x"])
        if "count_y" in f:
            f["count_y"] = int(f["count_y"])
        if "pitch_x" in f:
            f["pitch_x"] = float(f["pitch_x"])
        if "pitch_y" in f:
            f["pitch_y"] = float(f["pitch_y"])

    # position and direction are optional
    if "position" in f:
        pos = f["position"]
        if not isinstance(pos, (list, tuple)) or len(pos) < 2:
            raise ValueError(
                f"spec.features[{idx}].position must be [x, y] or [x, y, z]"
            )
        f["position"] = [float(v) for v in pos]

    if "direction" in f:
        d = f["direction"]
        if not isinstance(d, (list, tuple)) or len(d) != 3:
            raise ValueError(
                f"spec.features[{idx}].direction must be [dx, dy, dz]"
            )
        f["direction"] = [float(v) for v in d]
