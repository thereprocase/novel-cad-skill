"""Phase 3: Batch generation of all 78 radius gauge leaves.

Generates STEP files and optional PNG previews for all SAE and metric
leaves across small/medium/large rings.

Usage:
    python generate_all.py                    # full 78-leaf run
    python generate_all.py --test             # 6-leaf test batch
    python generate_all.py --png              # also render PNG previews
    python generate_all.py --test --png       # test batch with PNGs
"""

import os
import sys
import time
import traceback
from fractions import Fraction
from pathlib import Path

# Ensure project modules are importable
sys.path.insert(0, str(Path(__file__).parent))

from phase1_leaf_body import classify_ring
from phase2_text import build_leaf_with_text, export_multibody

# Render preview lives in scripts/
SKILL_DIR = Path(__file__).parent.parent.parent
RENDER_SCRIPT = SKILL_DIR / "scripts" / "render_preview.py"
sys.path.insert(0, str(RENDER_SCRIPT.parent))
from render_preview import render_preview


# ---------------------------------------------------------------------------
# SAE size definitions
# ---------------------------------------------------------------------------

def _parse_sae_fraction(label: str) -> float:
    """Parse an SAE fraction label like '1/8', '1-1/4', '2' to mm."""
    label = label.strip()
    if "-" in label:
        # Mixed number: "2-1/4" -> 2 + 1/4
        parts = label.split("-", 1)
        whole = int(parts[0])
        frac = Fraction(parts[1])
        inches = whole + float(frac)
    elif "/" in label:
        inches = float(Fraction(label))
    else:
        inches = float(label)
    return inches * 25.4


def _sae_file_label(label: str) -> str:
    """Convert SAE label to filename-safe string. '1/4' -> '1-4', '2-1/4' -> '2-1_4'."""
    # First replace the mixed-number dash with underscore to distinguish it
    # from fraction slash replacement.
    # "2-1/4" -> we want "2-1_4"
    # "1/4" -> "1-4"
    # "1" -> "1"
    result = label.replace("/", "-")
    # For mixed numbers like "2-1-4", we need the whole-fraction separator
    # to be underscore. The original "2-1/4" becomes "2-1-4" after slash replace.
    # We want "2-1_4". The pattern is: the last dash before digits is the
    # fraction separator.
    # Simpler: replace "/" first with "_", then the existing "-" stays.
    # "2-1/4" -> "2-1_4" (dash stays, slash becomes underscore)
    # "1/4" -> "1_4"
    # Hmm, the spec says "1-4" for "1/4" and "2-1_4" for "2-1/4".
    # So: slash -> dash for simple fractions, but for mixed numbers
    # the existing dash stays and slash -> underscore.
    if "-" in label and "/" in label:
        # Mixed number: keep dash, replace slash with underscore
        return label.replace("/", "_")
    else:
        # Simple fraction or whole: replace slash with dash
        return label.replace("/", "-")


SAE_SMALL = [
    "1/8", "5/32", "3/16", "7/32", "1/4", "9/32", "5/16", "11/32",
    "3/8", "13/32", "7/16", "15/32", "1/2",
]

SAE_MEDIUM = [
    "9/16", "5/8", "11/16", "3/4", "13/16", "7/8", "15/16", "1",
    "1-1/16", "1-1/8", "1-3/16", "1-1/4", "1-3/8", "1-1/2",
    "1-5/8", "1-3/4", "1-7/8", "2", "2-1/8",
]

SAE_LARGE = [
    "2-1/4", "2-1/2", "2-3/4", "3", "3-1/4", "3-1/2", "3-3/4",
    "4", "4-1/4", "4-1/2", "5", "5-1/2", "6",
]

METRIC_SMALL = [3, 3.5, 4, 4.5, 5, 5.5, 6, 7, 8, 9, 10, 11, 12, 13]
METRIC_MEDIUM = [14, 15, 16, 18, 20, 25, 30, 35, 40, 45, 50]
METRIC_LARGE = [60, 75, 80, 90, 100, 120, 125, 150]


def _metric_file_label(radius_mm: float) -> str:
    """Convert metric radius to filename label. 3.5 -> '3.5mm', 10 -> '10mm'."""
    if radius_mm == int(radius_mm):
        return f"{int(radius_mm)}mm"
    return f"{radius_mm}mm"


# ---------------------------------------------------------------------------
# Leaf descriptor: everything needed to build and name one leaf
# ---------------------------------------------------------------------------

def _build_leaf_list(test_mode: bool = False):
    """Build the full list of leaf descriptors.

    Each descriptor is a dict with:
        system, ring, radius_mm, label, file_label, form_key
    """
    leaves = []

    # SAE leaves
    for ring_name, size_list in [("small", SAE_SMALL),
                                  ("medium", SAE_MEDIUM),
                                  ("large", SAE_LARGE)]:
        for label in size_list:
            radius_mm = _parse_sae_fraction(label)
            leaves.append({
                "system": "sae",
                "ring": ring_name,
                "radius_mm": radius_mm,
                "label": label,
                "file_label": _sae_file_label(label),
                "form_key": ring_name,
            })

    # Metric leaves
    for ring_name, size_list in [("small", METRIC_SMALL),
                                  ("medium", METRIC_MEDIUM),
                                  ("large", METRIC_LARGE)]:
        for radius_mm in size_list:
            leaves.append({
                "system": "metric",
                "ring": ring_name,
                "radius_mm": float(radius_mm),
                "label": _metric_file_label(radius_mm),
                "file_label": _metric_file_label(radius_mm),
                "form_key": ring_name,
            })

    if test_mode:
        # 3 SAE small + 3 metric small
        sae_test = [l for l in leaves if l["system"] == "sae" and l["ring"] == "small"][:3]
        metric_test = [l for l in leaves if l["system"] == "metric" and l["ring"] == "small"][:3]
        return sae_test + metric_test

    return leaves


def _step_filename(leaf: dict) -> str:
    """Generate STEP filename for a leaf descriptor."""
    return (f"{leaf['system']}_{leaf['ring']}_"
            f"R{leaf['radius_mm']:.4g}mm_{leaf['file_label']}.step")


def _png_filename(leaf: dict) -> str:
    """Generate PNG filename for a leaf descriptor."""
    return (f"{leaf['system']}_{leaf['ring']}_"
            f"R{leaf['radius_mm']:.4g}mm_{leaf['file_label']}.png")


# ---------------------------------------------------------------------------
# Main generation loop
# ---------------------------------------------------------------------------

def generate_all(test_mode: bool = False, render_pngs: bool = False):
    """Generate all leaves, exporting STEP and optionally PNG."""
    base_dir = Path(__file__).parent / "output"
    step_dir = base_dir / "step"
    png_dir = base_dir / "png"
    step_dir.mkdir(parents=True, exist_ok=True)
    png_dir.mkdir(parents=True, exist_ok=True)

    leaves = _build_leaf_list(test_mode)
    total = len(leaves)

    print(f"{'='*60}")
    print(f"Radius Gauge Batch Generation")
    print(f"  Mode: {'TEST (6 leaves)' if test_mode else f'FULL ({total} leaves)'}")
    print(f"  PNG rendering: {'ON' if render_pngs else 'OFF'}")
    print(f"  Output: {base_dir}")
    print(f"{'='*60}\n")

    # Build-plate limit: Bambu P1S is 256x256mm, use 250mm with 6mm margin
    BED_LIMIT_MM = 250.0

    successes = 0
    failures = []
    oversized = []
    t_start = time.time()

    for i, leaf in enumerate(leaves, 1):
        step_name = _step_filename(leaf)
        step_path = step_dir / step_name

        print(f"[{i}/{total}] {leaf['system'].upper()} {leaf['ring']} "
              f"R={leaf['radius_mm']:.4g}mm ({leaf['label']})")

        try:
            bodies = build_leaf_with_text(
                leaf["radius_mm"],
                system=leaf["system"],
                form_key=leaf["form_key"],
            )

            # Build-plate size check
            bb = bodies["leaf"].bounding_box()
            x_dim, y_dim = bb.size.X, bb.size.Y
            if x_dim > BED_LIMIT_MM or y_dim > BED_LIMIT_MM:
                print(f"  WARNING: {x_dim:.1f} x {y_dim:.1f}mm exceeds "
                      f"{BED_LIMIT_MM}mm bed limit!")
                oversized.append((leaf, x_dim, y_dim))

            assembly_label = (f"radius_gauge_{leaf['system']}_"
                              f"R{leaf['radius_mm']:.4g}mm")
            export_multibody(bodies, str(step_path), label=assembly_label,
                             system=leaf["system"])
            print(f"  -> {step_name}")

            if render_pngs:
                png_name = _png_filename(leaf)
                png_path = png_dir / png_name
                try:
                    render_preview(str(step_path), str(png_path), size=1600)
                    print(f"  -> {png_name}")
                except Exception as e:
                    print(f"  PNG FAILED: {e}")

            successes += 1

        except Exception as e:
            print(f"  FAILED: {e}")
            traceback.print_exc()
            failures.append((leaf, str(e)))

    elapsed = time.time() - t_start

    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"  Total:     {total}")
    print(f"  Success:   {successes}")
    print(f"  Failed:    {len(failures)}")
    print(f"  Oversized: {len(oversized)}")
    print(f"  Time:      {elapsed:.1f}s ({elapsed/total:.1f}s/leaf)")
    print(f"  STEP dir:  {step_dir}")
    if render_pngs:
        print(f"  PNG dir:   {png_dir}")
    print(f"{'='*60}")

    if oversized:
        print(f"\nOversized leaves (exceed {BED_LIMIT_MM}mm bed limit):")
        for leaf, x, y in oversized:
            print(f"  {leaf['system']} {leaf['ring']} "
                  f"R={leaf['radius_mm']:.4g}mm: {x:.1f} x {y:.1f}mm")

    if failures:
        print(f"\nFailed leaves:")
        for leaf, err in failures:
            print(f"  {leaf['system']} {leaf['ring']} "
                  f"R={leaf['radius_mm']:.4g}mm: {err}")

    return successes, failures


if __name__ == "__main__":
    test_mode = "--test" in sys.argv
    render_pngs = "--png" in sys.argv
    generate_all(test_mode=test_mode, render_pngs=render_pngs)
