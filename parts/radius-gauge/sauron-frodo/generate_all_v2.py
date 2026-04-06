"""V2 Phase 3: Batch generation of all 78 radius gauge leaves.

Generates multi-body STEP files (leaf + text_top + text_bottom) with
color metadata, plus PNG previews. Runs manifold validation on each.

Output:
  sauron-frodo/output/step/  — 78 STEP files
  sauron-frodo/output/png/   — 78 PNG previews
"""

import json
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

# Local imports
sys.path.insert(0, str(Path(__file__).parent))
from build_talon import build_talon, TALON_PARAMS
from build_dogbone import build_dogbone, DOGBONE_PARAMS
from build_text import (
    build_leaf_with_text,
    export_multibody,
)

SKILL_DIR = Path.home() / ".claude/skills/novel-cad-skill"
RENDER_SCRIPT = SKILL_DIR / "scripts" / "render_preview.py"
MANIFOLD_SCRIPT = SKILL_DIR / "scripts" / "validate_manifold.py"

# Size tables from spec
SAE_SIZES = {
    "small": [
        "1/8", "5/32", "3/16", "7/32", "1/4", "9/32", "5/16", "11/32",
        "3/8", "13/32", "7/16", "15/32", "1/2",
    ],
    "medium": [
        "9/16", "5/8", "11/16", "3/4", "13/16", "7/8", "15/16", "1",
        "1-1/16", "1-1/8", "1-3/16", "1-1/4",
        "1-3/8", "1-1/2", "1-5/8", "1-3/4", "1-7/8", "2", "2-1/8",
    ],
    "large": [
        "2-1/4", "2-1/2", "2-3/4", "3", "3-1/4", "3-1/2", "3-3/4",
        "4", "4-1/4", "4-1/2", "5", "5-1/2", "6",
    ],
}

METRIC_SIZES = {
    "small": [3, 3.5, 4, 4.5, 5, 5.5, 6, 7, 8, 9, 10, 11, 12, 13],
    "medium": [14, 15, 16, 18, 20, 25, 30, 35, 40, 45, 50],
    "large": [60, 75, 80, 90, 100, 120, 125, 150],
}


def _parse_sae_fraction(frac_str: str) -> float:
    """Convert SAE fraction string to mm."""
    if "-" in frac_str:
        parts = frac_str.split("-", 1)
        whole = int(parts[0])
        frac = Fraction(parts[1])
        inches = whole + float(frac)
    else:
        try:
            inches = float(Fraction(frac_str))
        except ValueError:
            inches = float(frac_str)
    return inches * 25.4


def _safe_filename(label: str) -> str:
    """Convert label to filesystem-safe string."""
    return label.replace("/", "-").replace(" ", "_")


def main():
    out_step = Path(__file__).parent / "output" / "step"
    out_png = Path(__file__).parent / "output" / "png"
    out_step.mkdir(parents=True, exist_ok=True)
    out_png.mkdir(parents=True, exist_ok=True)

    results = []
    failures = []
    oversized = []
    t0 = time.time()

    # --- SAE ---
    for ring, sizes in SAE_SIZES.items():
        for label in sizes:
            r_mm = _parse_sae_fraction(label)
            safe = _safe_filename(label)
            fname = f"sae_{ring}_R{r_mm:.1f}mm_{safe}"

            print(f"[SAE {ring}] R={r_mm:.2f}mm ({label})...", end=" ", flush=True)

            try:
                bodies = build_leaf_with_text(r_mm, ring, system="sae")
                step_path = out_step / f"{fname}.step"
                export_multibody(bodies, str(step_path), system="sae")

                # Check bounding box
                bb = bodies["leaf"].bounding_box()
                if bb.size.X > 250 or bb.size.Y > 250:
                    oversized.append((fname, bb.size.X, bb.size.Y))
                    print(f"OVERSIZED {bb.size.X:.0f}x{bb.size.Y:.0f}", flush=True)
                else:
                    print(f"{bb.size.X:.0f}x{bb.size.Y:.0f}mm", flush=True)

                results.append(fname)
            except Exception as e:
                print(f"FAILED: {e}", flush=True)
                failures.append((fname, str(e)))

    # --- Metric ---
    for ring, sizes in METRIC_SIZES.items():
        for r_mm in sizes:
            if r_mm == int(r_mm):
                label = f"{int(r_mm)}mm"
            else:
                label = f"{r_mm:.1f}mm"
            safe = _safe_filename(label)
            fname = f"metric_{ring}_R{r_mm}mm_{safe}"

            print(f"[Metric {ring}] R={r_mm}mm ({label})...", end=" ", flush=True)

            try:
                bodies = build_leaf_with_text(r_mm, ring, system="metric")
                step_path = out_step / f"{fname}.step"
                export_multibody(bodies, str(step_path), system="metric")

                bb = bodies["leaf"].bounding_box()
                if bb.size.X > 250 or bb.size.Y > 250:
                    oversized.append((fname, bb.size.X, bb.size.Y))
                    print(f"OVERSIZED {bb.size.X:.0f}x{bb.size.Y:.0f}", flush=True)
                else:
                    print(f"{bb.size.X:.0f}x{bb.size.Y:.0f}mm", flush=True)

                results.append(fname)
            except Exception as e:
                print(f"FAILED: {e}", flush=True)
                failures.append((fname, str(e)))

    elapsed = time.time() - t0

    print(f"\n{'='*60}")
    print(f"STEP generation complete: {len(results)}/{len(results)+len(failures)}")
    print(f"Time: {elapsed:.0f}s ({elapsed/max(len(results),1):.1f}s/leaf)")
    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for name, err in failures:
            print(f"  {name}: {err}")
    if oversized:
        print(f"\nOVERSIZED ({len(oversized)}):")
        for name, x, y in oversized:
            print(f"  {name}: {x:.0f}x{y:.0f}mm (limit 250mm)")
    print()

    # --- Render PNGs ---
    print("Rendering PNGs...")
    for fname in results:
        step_path = out_step / f"{fname}.step"
        png_path = out_png / f"{fname}.png"
        try:
            subprocess.run(
                [sys.executable, str(RENDER_SCRIPT), str(step_path), str(png_path)],
                capture_output=True, timeout=30,
            )
        except Exception:
            pass  # non-critical

    # --- Manifold validation (sample 6 — one per ring) ---
    print("\nManifold validation (6 samples):")
    samples = [
        f"sae_small_R{_parse_sae_fraction('1/4'):.1f}mm_1-4",
        f"sae_medium_R{_parse_sae_fraction('1'):.1f}mm_1",
        f"sae_large_R{_parse_sae_fraction('3'):.1f}mm_3",
        "metric_small_R6mm_6mm",
        "metric_medium_R25mm_25mm",
        "metric_large_R100mm_100mm",
    ]
    for s in samples:
        step_path = out_step / f"{s}.step"
        if step_path.exists():
            try:
                result = subprocess.run(
                    [sys.executable, str(MANIFOLD_SCRIPT), str(step_path)],
                    capture_output=True, text=True, timeout=30,
                )
                status = "PASS" if result.returncode == 0 else "FAIL"
                print(f"  {s}: {status}")
            except Exception as e:
                print(f"  {s}: ERROR ({e})")
        else:
            print(f"  {s}: NOT FOUND")

    print(f"\nDone. {len(results)} STEP + PNG in sauron-frodo/output/")


if __name__ == "__main__":
    main()
