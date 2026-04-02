"""
build123d Debug Helpers -- catch silent booleans, feature overflow, context drift.

Replaces cq_debug_helpers.py for the build123d-based CAD skill. Uses a
snapshot-then-verify pattern because build123d's BuildPart mutates in place
(no before/after objects like CadQuery's fluent API).

Usage:
    from bd_debug_helpers import snapshot, verify_result, verify_bounds, debug_context
"""


def snapshot(builder) -> dict:
    """Capture builder state for later comparison.

    Call this BEFORE the operation you want to verify. Pass the returned
    dict to verify_result() or verify_bounds() after the operation.
    """
    solid = builder.part
    bb = solid.bounding_box()
    return {
        "volume": solid.volume,
        "face_count": len(solid.faces()),
        "bbox_min": (bb.min.X, bb.min.Y, bb.min.Z),
        "bbox_max": (bb.max.X, bb.max.Y, bb.max.Z),
        "bbox_size": (bb.size.X, bb.size.Y, bb.size.Z),
        "centroid": (
            (bb.min.X + bb.max.X) / 2.0,
            (bb.min.Y + bb.max.Y) / 2.0,
            (bb.min.Z + bb.max.Z) / 2.0,
        ),
    }


def verify_result(builder, before: dict, label: str = ""):
    """Check that the most recent operation actually changed the geometry.

    Compares volume, face count, and centroid shift against the snapshot.
    Raises RuntimeError if nothing changed -- indicates a silent boolean
    failure (tool missed the body, or degenerate intersection).
    """
    solid = builder.part
    vol_after = solid.volume
    faces_after = len(solid.faces())
    bb = solid.bounding_box()
    centroid_after = (
        (bb.min.X + bb.max.X) / 2.0,
        (bb.min.Y + bb.max.Y) / 2.0,
        (bb.min.Z + bb.max.Z) / 2.0,
    )

    vol_changed = abs(vol_after - before["volume"]) > 0.001
    faces_changed = faces_after != before["face_count"]
    centroid_shift = sum(
        abs(a - b) for a, b in zip(centroid_after, before["centroid"])
    )
    centroid_moved = centroid_shift > 0.01

    if not vol_changed and not faces_changed and not centroid_moved:
        raise RuntimeError(
            f"[Boolean {label}] Operation produced NO change! "
            f"Volume: {before['volume']:.2f} -> {vol_after:.2f}, "
            f"Faces: {before['face_count']} -> {faces_after}"
        )


def verify_bounds(builder, before: dict, label: str = "", tolerance: float = 0.1):
    """Check that new geometry stays within the prior bounding box.

    Use after additive operations (union, extrude) to catch features that
    extend past the body's footprint. Raises RuntimeError on overflow.
    """
    bb = builder.part.bounding_box()

    x_overflow = max(
        0,
        bb.max.X - before["bbox_max"][0] - tolerance,
        before["bbox_min"][0] - bb.min.X - tolerance,
    )
    y_overflow = max(
        0,
        bb.max.Y - before["bbox_max"][1] - tolerance,
        before["bbox_min"][1] - bb.min.Y - tolerance,
    )
    z_overflow = max(
        0,
        bb.max.Z - before["bbox_max"][2] - tolerance,
        before["bbox_min"][2] - bb.min.Z - tolerance,
    )

    if x_overflow > 0 or y_overflow > 0 or z_overflow > 0:
        raise RuntimeError(
            f"[Bounds {label}] Feature extends past body! "
            f"X overflow: {x_overflow:.2f}mm, "
            f"Y overflow: {y_overflow:.2f}mm, "
            f"Z overflow: {z_overflow:.2f}mm"
        )


def debug_context(builder, label: str = "", expected_origin=None, tolerance: float = 0.1):
    """Print builder context plane origin and normal. Raise on drift.

    build123d doesn't have CadQuery's mutable workplane origin, but
    BuildPart tracks exit_workplanes for nested contexts. This helper
    prints the current state and optionally asserts expected values.
    """
    from build123d import Plane

    plane = Plane.XY
    if hasattr(builder, "exit_workplanes") and builder.exit_workplanes:
        plane = builder.exit_workplanes[-1]

    origin = (plane.origin.X, plane.origin.Y, plane.origin.Z)
    normal = (plane.z_dir.X, plane.z_dir.Y, plane.z_dir.Z)

    print(
        f"[CTX {label}] origin=({origin[0]:.2f}, {origin[1]:.2f}, {origin[2]:.2f}) "
        f"normal=({normal[0]:.2f}, {normal[1]:.2f}, {normal[2]:.2f})"
    )

    if expected_origin is not None:
        dist = sum((a - b) ** 2 for a, b in zip(origin, expected_origin)) ** 0.5
        if dist > tolerance:
            raise ValueError(
                f"[CTX {label}] Origin drift: "
                f"expected {expected_origin}, got {origin} (delta={dist:.3f}mm)"
            )


class StepExporter:
    """Export intermediate geometry snapshots at each construction step.

    Disabled by default. Enable with `enabled=True` for debugging
    multi-step builds where you need to see exactly when geometry breaks.
    """

    def __init__(self, prefix="step", output_dir=".", enabled=False):
        self.prefix = prefix
        self.output_dir = output_dir
        self.enabled = enabled
        self.step_num = 0

    def export(self, builder, label=""):
        if not self.enabled:
            return
        self.step_num += 1
        import os
        from build123d import export_stl

        name = f"{self.prefix}_{self.step_num:02d}_{label}.stl"
        path = os.path.join(self.output_dir, name)
        export_stl(builder.part, path)
        print(f"[Step {self.step_num}] Exported: {path}")
