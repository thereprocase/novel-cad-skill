# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Claude Code skill for designing 3D-printable parts using **build123d** (Python, OCCT kernel) with a three-layer validation pipeline and phased checkpoint gates. Triggered by keywords: STL, STEP, 3MF, 3D printing, enclosure, bracket, mount, case, holder, stand, or physical object requests.

## Commands

```bash
# Environment setup (one-time)
bash scripts/setup_env.sh

# Run all tests
pytest -v tests/

# Run a single test file
pytest -v tests/test_spec_format.py

# Run a single test
pytest -v tests/test_spec_format.py::TestCreateSpec::test_minimal_spec

# Validate a part (run from project root)
python scripts/validate_geometry.py <part>.step
python scripts/check_printability.py <part>.step
python scripts/validate_manifold.py <part>.step
python scripts/render_cross_sections.py <part>.step
python scripts/render_preview.py <part>.step <output>.png

# Export to 3MF
python scripts/export_3mf.py <part>.step <output>.3mf
```

No linter or formatter is configured. Python 3.10+ required.

## Architecture

### Data Flow

User description → **spec** (`.spec.json`) → **build123d script** → **STEP file** → **validators** → **renders** → user approval gate → next phase.

### Core Libraries (`lib/`)

- **`spec_format.py`** — Creates, validates, and round-trips intent specs (dimensions, features, material, tolerances). Specs are the contract between design intent and validation. `create_spec()` / `validate_spec()` / `write_spec()` / `load_spec()`.
- **`gate_enforcer.py`** — State machine enforcing phased checkpoints. Persists to `<part>.gates.json`. Prevents skipping validation or phases. `begin_phase()` requires prior phase approved; `request_approval()` requires all validators passed + ≥3 cross-section PNGs.
- **`context_budget.py`** — Estimates token cost per phase, recommends sub-phase splits for complex parts (>10 features → split Phase 2 into 2a/2b/2c with ~4 features each).
- **`mesh_utils.py`** — Shared OCC tessellation pipeline (0.05mm tolerance). All validators use `load_mesh_from_step()` for consistent mesh representation.

### Validation Scripts (`scripts/`)

Three-layer validation, each catching different failure modes:

1. **Construction-time** (`bd_debug_helpers.py`) — `snapshot()` → operation → `verify_result()` catches silent booleans and feature overflow inline during geometry building.
2. **Manifold** (`validate_manifold.py`) — Mesh topology check via manifold3d (trimesh fallback). Catches self-intersections, open edges, T-junctions.
3. **Post-export** — `validate_geometry.py` (spec vs. measured dimensions), `check_printability.py` (FDM structural: wall thickness, overhangs, bridges, material-specific thresholds).

### Rendering (`scripts/`)

- `render_preview.py` — 2×2 orthographic + perspective grid from STEP.
- `render_cross_sections.py` — Annotated dimension slices at spec feature heights. Minimum 3 per phase (gate-enforced).

### Fallback (`scripts/fallback_router.py`)

Diagnosis tool, not automatic. Classifies build123d failures and recommends CadQuery (same OCCT kernel, different API) or OpenSCAD (different kernel for crashes/CSG-only parts).

## Key Patterns

**Phased workflow with hard gates:** Phase 0 (requirements) → Phase 1 (base shape) → Phase 2 (features, may sub-split) → Phase 3 (print optimization + delivery). Each phase: build → validate all 3 layers → render → gate approval → next. Never skip a gate.

**Spec-driven validation:** Every validator reads the `.spec.json` sidecar. The spec declares intent; validators compare against measured geometry.

**Snapshot-then-verify:** build123d's `BuildPart` mutates in place. Use `snapshot(part)` before critical operations, then `verify_result(part, before, "label")` to catch silent failures.

**Builder vs. Algebra modes:** Builder (context managers) for >3 features; Algebra (stateless expressions) for simple parts. Both produce identical geometry.

**Import STEP between phases, not script text.** Each phase imports the prior phase's STEP file. This prevents context accumulation and ensures geometry is the source of truth.

## Tests

pytest with fixtures in `tests/fixtures/` (STEP, STL, spec.json files). `conftest.py` adds `lib/` and `scripts/` to `sys.path`. Regenerate fixtures with `tests/fixtures/generate_fixtures.py`.

## Reference Docs

`SKILL.md`, `ARCHITECTURE.md`, `BUILD123D_REFERENCE.md`, and `VALIDATION_PIPELINE.md` are detailed reference documents — load on demand, not by default.
