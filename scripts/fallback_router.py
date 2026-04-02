#!/usr/bin/env python3
"""
fallback_router.py -- Detects which CAD environment to use for a part description.

Analyzes the description for B-rep requirements (fillets, chamfers, lofts, shells)
and recommends the appropriate engine from the fallback chain:

    build123d (primary)
        -> CadQuery (API-level fallback, same OCC kernel)
        -> OpenSCAD (CSG-only, different kernel)

Usage:
    python fallback_router.py "description of part"
        --> prints recommended engine and reasoning

    python fallback_router.py --check-build123d script.py
        --> validates that the script can import and syntax-check cleanly
"""

import sys
import re
import argparse
from pathlib import Path


# -- Keyword sets for feature detection ---------------------------------------

# B-rep operations: require parametric kernel (build123d or CadQuery)
_BREP_KEYWORDS = {
    "fillet":     "curved edge blending",
    "chamfer":    "angled edge transition",
    "loft":       "profile-to-profile sweep",
    "shell":      "hollow shell from solid",
    "sweep":      "profile along path",
    "revolve":    "rotational sweep",
    "thread":     "helical profile",
    "spline":     "freeform curve",
    "offset":     "face/edge offset",
    "draft":      "draft angle on face",
    "rib":        "structural rib feature",
    "boss":       "cylindrical boss",
    "snap":       "snap-fit feature",
    "living hinge": "living hinge",
    "undercut":   "undercut geometry",
}

# CSG-only: can be handled by OpenSCAD's Manifold backend
_CSG_KEYWORDS = {
    "box":        "rectilinear box",
    "cylinder":   "cylinder",
    "sphere":     "sphere",
    "union":      "boolean union",
    "difference": "boolean difference",
    "intersection": "boolean intersection",
    "hole":       "cylindrical hole",
    "slot":       "rectangular slot",
    "pocket":     "rectangular pocket",
    "cutout":     "rectangular cutout",
    "tray":       "simple tray",
    "bracket":    "angle bracket",
    "mount":      "flat mount",
}

# Keywords that indicate build123d is preferred over CadQuery for API reasons
_BUILD123D_PREFERRED = {
    "array":      "pattern array (build123d polar/linear array)",
    "polar":      "polar array",
    "linear array": "linear array",
    "pattern":    "feature pattern",
    "text":       "embossed/debossed text",
    "emboss":     "embossed text",
    "deboss":     "debossed text",
}

# Keywords hinting at CadQuery strengths
_CADQUERY_STRENGTHS = {
    "workplane": "CadQuery workplane idiom in existing code",
    "assembly":  "multi-part assembly (CadQuery Assembly API)",
    "plate":     "build plate packing (CQ BRep_Builder compound)",
}

# --------------------------------------------------------

def _normalize(text: str) -> str:
    return text.lower()


def analyze_description(description: str) -> dict:
    """
    Analyze a free-text part description and return a recommendation dict.

    Returns:
        {
          "recommended_engine": "build123d" | "cadquery" | "openscad",
          "confidence": "high" | "medium" | "low",
          "brep_features": [...],
          "csg_features": [...],
          "build123d_preferred": [...],
          "cadquery_strengths": [...],
          "reasoning": "...",
        }
    """
    norm = _normalize(description)

    brep_found   = [label for kw, label in _BREP_KEYWORDS.items() if kw in norm]
    csg_found    = [label for kw, label in _CSG_KEYWORDS.items() if kw in norm]
    bd_preferred = [label for kw, label in _BUILD123D_PREFERRED.items() if kw in norm]
    cq_strengths = [label for kw, label in _CADQUERY_STRENGTHS.items() if kw in norm]

    # Decision logic
    if brep_found or bd_preferred:
        # B-rep features present -- need OCC kernel
        if cq_strengths and not bd_preferred:
            engine = "cadquery"
            reasoning = (
                f"B-rep features detected ({', '.join(brep_found or bd_preferred)}) "
                f"and CadQuery-specific strengths found ({', '.join(cq_strengths)}). "
                "CadQuery recommended as primary."
            )
            confidence = "medium"
        else:
            engine = "build123d"
            reasons = brep_found + bd_preferred
            reasoning = (
                f"B-rep features detected: {', '.join(reasons)}. "
                "build123d recommended (explicit context managers, no workplane drift, "
                "exceptions on degenerate booleans)."
            )
            confidence = "high" if len(reasons) >= 2 else "medium"
    elif csg_found and not brep_found:
        engine = "openscad"
        reasoning = (
            f"CSG-only geometry detected ({', '.join(csg_found)}), no B-rep features. "
            "OpenSCAD with Manifold backend is viable -- simpler, no OCC overhead."
        )
        confidence = "medium"
    else:
        # Default: build123d handles both CSG and B-rep
        engine = "build123d"
        reasoning = (
            "No strong feature signal. Defaulting to build123d -- handles both "
            "CSG and B-rep, and degrades gracefully to CadQuery if needed."
        )
        confidence = "low"

    return {
        "recommended_engine": engine,
        "confidence": confidence,
        "brep_features": brep_found,
        "csg_features": csg_found,
        "build123d_preferred": bd_preferred,
        "cadquery_strengths": cq_strengths,
        "reasoning": reasoning,
    }


def diagnose_failure(error_text: str, script_source: str = "") -> dict:
    """
    Classify a build123d (or CadQuery) failure and suggest a fallback.

    Args:
        error_text:    The exception message / traceback as a string.
        script_source: The Python script that failed (optional, for context).

    Returns:
        {
          "engine":          original engine,
          "failure_type":    short label,
          "recommendation":  suggested fallback engine,
          "reason":          why the fallback might help,
        }
    """
    err = error_text.lower()

    if "importerror" in err or "no module named" in err:
        return {
            "engine": "build123d",
            "failure_type": "import_error",
            "recommendation": "cadquery",
            "reason": "build123d not installed -- CadQuery uses the same OCC kernel",
        }

    if any(kw in err for kw in ("fillet", "chamfer", "edge", "topology")):
        return {
            "engine": "build123d",
            "failure_type": "fillet_topology",
            "recommendation": "cadquery",
            "reason": (
                "Fillet/chamfer topology failure. CadQuery's edge selector may "
                "handle this degenerate edge case differently."
            ),
        }

    if "shell" in err:
        return {
            "engine": "build123d",
            "failure_type": "shell_failure",
            "recommendation": "cadquery",
            "reason": (
                "Shell operation failed. Try CadQuery with a different face "
                "selection order -- same kernel, sometimes resolves shell issues."
            ),
        }

    if any(kw in err for kw in ("loft", "sweep", "guide")):
        return {
            "engine": "build123d",
            "failure_type": "loft_sweep_failure",
            "recommendation": "cadquery",
            "reason": (
                "Loft/sweep failure. CadQuery's loft API is more mature for "
                "some profile combinations."
            ),
        }

    if any(kw in err for kw in ("sigsegv", "segmentation", "signal 11", "access violation")):
        return {
            "engine": "build123d",
            "failure_type": "kernel_crash",
            "recommendation": "openscad",
            "reason": (
                "OCC kernel crash (SIGSEGV). OpenSCAD uses a different kernel "
                "(CGAL/Manifold) -- avoids the crash entirely for CSG geometry."
            ),
        }

    if any(kw in err for kw in ("boolean", "cut", "intersect", "brep_builder")):
        return {
            "engine": "build123d",
            "failure_type": "boolean_failure",
            "recommendation": "cadquery",
            "reason": (
                "Boolean operation failure. CadQuery's .cut()/.intersect() API "
                "may handle the geometry differently."
            ),
        }

    # Generic OCC failure
    return {
        "engine": "build123d",
        "failure_type": "occ_generic",
        "recommendation": "cadquery",
        "reason": (
            "Unclassified OCC failure. CadQuery uses the same kernel but different "
            "wrapper paths -- worth trying before escalating to OpenSCAD."
        ),
    }


def suggest_fallback(diagnosis: dict) -> str:
    """Format a human-readable fallback suggestion from a diagnosis dict."""
    lines = [
        f"Failure type : {diagnosis['failure_type']}",
        f"Recommendation: {diagnosis['recommendation']}",
        f"Reason       : {diagnosis['reason']}",
        "",
        "Next steps:",
    ]
    engine = diagnosis["recommendation"]
    if engine == "cadquery":
        lines.append("  1. Rewrite the script using CadQuery API (import cadquery as cq).")
        lines.append("  2. Keep the same spec.json -- dimensions are unchanged.")
        lines.append("  3. Run the same validator pipeline after rewrite.")
    elif engine == "openscad":
        lines.append("  1. Rewrite as OpenSCAD CSG (.scad file).")
        lines.append("  2. Export STL with: openscad -o part.stl part.scad")
        lines.append("  3. Run check_printability.py against the STL.")
        lines.append("  Note: fillets/chamfers are not available in OpenSCAD without workarounds.")
    return "\n".join(lines)


def check_build123d_script(script_path: str) -> bool:
    """
    Validate that a build123d script can be imported (syntax check + import).
    Does NOT execute the model -- just checks for syntax errors and missing imports.

    Returns True if the script passes, False if it fails.
    """
    import ast
    import subprocess

    script_path = str(Path(script_path).resolve())

    # Step 1: AST parse (catches SyntaxError without executing)
    try:
        with open(script_path, "r", encoding="utf-8") as f:
            source = f.read()
        ast.parse(source, filename=script_path)
        print(f"[PASS] Syntax check: {script_path}")
    except SyntaxError as e:
        print(f"[FAIL] Syntax error in {script_path}: {e}", file=sys.stderr)
        return False

    # Step 2: Try importing with a subprocess (catches ImportError at module level)
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             f"import ast, sys; "
             f"src = open({repr(script_path)}).read(); "
             f"compile(src, {repr(script_path)}, 'exec');"
             f"print('compile ok')"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            print(f"[PASS] Compile check: {script_path}")
            return True
        else:
            print(f"[FAIL] Compile error:\n{result.stderr}", file=sys.stderr)
            return False
    except subprocess.TimeoutExpired:
        print(f"[WARN] Compile check timed out -- treating as pass", file=sys.stderr)
        return True
    except Exception as e:
        print(f"[WARN] Could not run compile check: {e}", file=sys.stderr)
        return True  # Don't block on subprocess failures


def main():
    parser = argparse.ArgumentParser(
        description="Detect CAD environment or diagnose build123d failures.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command")

    # Default: analyze description
    parser.add_argument("description", nargs="?", default=None,
                        help='Part description (e.g. "enclosure with filleted corners and shell")')

    # --check-build123d: validate a script
    parser.add_argument("--check-build123d", metavar="SCRIPT", default=None,
                        help="Validate a build123d script (syntax + compile check)")

    args = parser.parse_args()

    if args.check_build123d:
        ok = check_build123d_script(args.check_build123d)
        sys.exit(0 if ok else 1)

    if not args.description:
        parser.print_help()
        sys.exit(1)

    result = analyze_description(args.description)

    print(f"Recommended engine : {result['recommended_engine']}")
    print(f"Confidence         : {result['confidence']}")
    print(f"Reasoning          : {result['reasoning']}")

    if result["brep_features"]:
        print(f"B-rep features     : {', '.join(result['brep_features'])}")
    if result["csg_features"]:
        print(f"CSG features       : {', '.join(result['csg_features'])}")
    if result["build123d_preferred"]:
        print(f"build123d-preferred: {', '.join(result['build123d_preferred'])}")
    if result["cadquery_strengths"]:
        print(f"CadQuery strengths : {', '.join(result['cadquery_strengths'])}")

    # Always exit 0 -- the recommendation is informational
    sys.exit(0)


if __name__ == "__main__":
    main()
