#!/usr/bin/env python3
"""
context_budget.py -- Estimates context budget for a part build.

Given a spec (or raw feature/component/phase counts), estimates token usage
and whether Phase 2 should be split into sub-phases.

Usage (CLI):
    python context_budget.py part.spec.json

Usage (library):
    from context_budget import estimate_complexity
    est = estimate_complexity(spec)
    print(est["recommendation"])
"""

import sys
import os
import json
import math
from pathlib import Path


# -- Token cost heuristics ----------------------------------------------------
# Empirical estimates from Rounds 1-6 of cad-skill.

# Base overhead: imports, spec, gate setup, export
_BASE_TOKENS = 400

# Per-phase overhead: bounding box, export calls, validator invocations
_PHASE_TOKENS = 200

# Per-feature costs by type (tokens to describe and implement the feature)
_FEATURE_COSTS = {
    "pocket":       180,
    "slot":         160,
    "hole":         120,
    "cutout":       220,  # port cutouts are verbose: position, rotation, size
    "port":         240,
    "fillet":        80,
    "chamfer":       80,
    "shell":        100,
    "text":         150,
    "pattern":      120,  # compact: one element + array params
    "standoff":     160,
    "boss":         140,
    "rib":          130,
    "sweep":        250,
    "loft":         300,
    "revolve":      200,
    "default":      150,
}

# Port cutout premium: these are especially verbose (Round 6 lesson)
_PORT_CUTOUT_PREMIUM = 80

# Pattern feature discount vs. N individual features
_PATTERN_DISCOUNT = 0.6   # a pattern of 20 costs ~60% of 20 individual features

# Tokens per component (sub-body import, bounding box check)
_COMPONENT_TOKENS = 100

# Context window budget (conservative -- leaves room for conversation history)
_CONTEXT_BUDGET_TOKENS = 6000

# Sub-phase target: max features per sub-phase
_MAX_FEATURES_PER_SUBPHASE = 4

# Risk thresholds
_RISK_LOW_MAX    = 5
_RISK_MEDIUM_MAX = 10


def _feature_cost(feature: dict) -> int:
    """Estimate token cost for a single feature dict."""
    ftype = feature.get("type", "default").lower()

    # Pattern features: compact representation
    if ftype == "pattern":
        elem = feature.get("element", {})
        elem_type = elem.get("type", "default").lower()
        elem_cost = _FEATURE_COSTS.get(elem_type, _FEATURE_COSTS["default"])
        count = feature.get("count", 1)
        # Pattern costs: element cost + array param overhead, discounted vs. N copies
        return int(elem_cost * _PATTERN_DISCOUNT + 40)

    base = _FEATURE_COSTS.get(ftype, _FEATURE_COSTS["default"])

    # Port/cutout premium
    if ftype in ("port", "cutout") or "port" in feature.get("name", "").lower():
        base += _PORT_CUTOUT_PREMIUM

    return base


def _group_features_into_subphases(features: list, max_per: int) -> dict:
    """
    Split a flat feature list into sub-phases with at most max_per features each.

    Returns dict: {"2a": [name, ...], "2b": [name, ...], ...}
    """
    if not features:
        return {}

    subphases = {}
    labels = "abcdefghijklmnopqrstuvwxyz"

    for i, chunk_start in enumerate(range(0, len(features), max_per)):
        chunk = features[chunk_start:chunk_start + max_per]
        label = f"2{labels[i]}"
        subphases[label] = [f.get("name", f.get("type", f"feature_{chunk_start + j}"))
                            for j, f in enumerate(chunk)]

    return subphases


def estimate_complexity(spec: dict) -> dict:
    """
    Estimate token budget and sub-phase split recommendation for a part spec.

    Args:
        spec: A spec dict as produced by spec_format.create_spec().

    Returns:
        {
          "feature_count": int,
          "component_count": int,
          "estimated_script_tokens": int,
          "estimated_phases": int,
          "sub_phase_split": dict or None,
          "risk": "low" | "medium" | "high",
          "recommendation": str,
        }
    """
    features   = spec.get("features", [])
    components = spec.get("components", [])

    feature_count   = len(features)
    component_count = len(components)

    # Token estimate
    feature_tokens   = sum(_feature_cost(f) for f in features)
    component_tokens = component_count * _COMPONENT_TOKENS
    estimated_tokens = _BASE_TOKENS + _PHASE_TOKENS + feature_tokens + component_tokens

    # Risk classification
    if feature_count <= _RISK_LOW_MAX:
        risk = "low"
    elif feature_count <= _RISK_MEDIUM_MAX:
        risk = "medium"
    else:
        risk = "high"

    # Sub-phase split recommendation
    sub_phase_split = None
    if risk == "low":
        estimated_phases = 3
        recommendation = (
            f"{feature_count} features, estimated {estimated_tokens} tokens. "
            "Standard 3-phase workflow. No sub-phases needed."
        )
    elif risk == "medium":
        # Split Phase 2 into 2 sub-phases
        max_per = math.ceil(feature_count / 2)
        sub_phase_split = _group_features_into_subphases(features, max_per)
        estimated_phases = 2 + len(sub_phase_split)
        recommendation = (
            f"{feature_count} features, estimated {estimated_tokens} tokens (medium risk). "
            f"Split Phase 2 into {len(sub_phase_split)} sub-phases. "
            "Import STEP between sub-phases -- do not carry forward script text."
        )
    else:
        # High risk: ceil(N / max_per) sub-phases
        sub_phase_split = _group_features_into_subphases(features, _MAX_FEATURES_PER_SUBPHASE)
        estimated_phases = 2 + len(sub_phase_split)
        recommendation = (
            f"{feature_count} features, estimated {estimated_tokens} tokens (HIGH RISK). "
            f"Split Phase 2 into {len(sub_phase_split)} sub-phases "
            f"({_MAX_FEATURES_PER_SUBPHASE} features each). "
            "Present sub-phase plan to user before starting. "
            "Import STEP between sub-phases -- do not carry forward script text."
        )

    return {
        "feature_count":            feature_count,
        "component_count":          component_count,
        "estimated_script_tokens":  estimated_tokens,
        "estimated_phases":         estimated_phases,
        "sub_phase_split":          sub_phase_split,
        "risk":                     risk,
        "recommendation":           recommendation,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: context_budget.py <part.spec.json>")
        sys.exit(1)

    spec_path = os.path.realpath(sys.argv[1])
    if not os.path.exists(spec_path):
        print(f"Error: file not found: {spec_path}", file=sys.stderr)
        sys.exit(2)

    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    result = estimate_complexity(spec)

    print(f"Feature count      : {result['feature_count']}")
    print(f"Component count    : {result['component_count']}")
    print(f"Est. script tokens : {result['estimated_script_tokens']}")
    print(f"Est. phases        : {result['estimated_phases']}")
    print(f"Risk               : {result['risk'].upper()}")
    print(f"Recommendation     : {result['recommendation']}")

    if result["sub_phase_split"]:
        print("\nSub-phase split:")
        for label, names in result["sub_phase_split"].items():
            print(f"  Phase {label}: {', '.join(names)}")


if __name__ == "__main__":
    main()
