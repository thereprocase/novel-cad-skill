#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# setup_env.sh — Set up the build123d + Manifold environment
# Run once: bash ~/.claude/skills/novel-cad-skill/scripts/setup_env.sh
# Uses pip + system Python — no conda required.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================================"
echo "  Novel CAD Skill — Environment Setup"
echo "========================================================"
echo ""

# ---- Step 1: Check Python >= 3.10 ----
if ! command -v python &>/dev/null && ! command -v python3 &>/dev/null; then
    echo "ERROR: Python not found. Install Python 3.10+ and ensure it is on your PATH."
    exit 1
fi

PYTHON=$(command -v python || command -v python3)
PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[1/5] Using Python $PY_VERSION at $PYTHON"
"$PYTHON" -c "
import sys
if sys.version_info < (3, 10):
    print(f'ERROR: Python 3.10+ required, got {sys.version_info.major}.{sys.version_info.minor}')
    sys.exit(1)
"

# ---- Step 2: Install packages ----
echo "[2/5] Installing packages via pip..."
"$PYTHON" -m pip install --quiet --upgrade \
    "build123d>=0.7,<1.0" \
    "cadquery>=2.4,<3.0" \
    "trimesh>=4.0,<5.0" \
    "numpy>=1.26,<3.0" \
    "matplotlib>=3.8,<4.0" \
    "pillow>=10.0,<11.0" \
    "scipy>=1.12,<2.0" \
    "shapely>=2.0,<3.0"
echo "    Packages installed"

# ---- Step 3: Install manifold3d (may fail on some platforms) ----
echo "[3/5] Installing manifold3d..."
if "$PYTHON" -m pip install --quiet "manifold3d>=2.5,<3.0" 2>/dev/null; then
    echo "    manifold3d installed"
    HAS_MANIFOLD=1
else
    echo "    WARN: manifold3d failed to install. Mesh validation will fall back to trimesh."
    echo "          This is OK — trimesh provides basic watertight/volume checks."
    HAS_MANIFOLD=0
fi

# ---- Step 4: Verify imports ----
echo "[4/5] Verifying installation..."
"$PYTHON" -c "
import build123d
print(f'    build123d:   OK')

import cadquery as cq
print(f'    cadquery:    OK')

import trimesh
print(f'    trimesh:     {trimesh.__version__}')

import numpy
print(f'    numpy:       {numpy.__version__}')

import matplotlib
print(f'    matplotlib:  {matplotlib.__version__}')

import PIL
print(f'    pillow:      {PIL.__version__}')

import scipy
print(f'    scipy:       {scipy.__version__}')

import shapely
print(f'    shapely:     {shapely.__version__}')

try:
    import manifold3d
    print(f'    manifold3d:  OK')
except ImportError:
    print(f'    manifold3d:  NOT AVAILABLE (trimesh fallback active)')
"

# ---- Step 5: Smoke test ----
echo "[5/5] Running smoke test..."
"$PYTHON" -c "
from build123d import *
import tempfile, os

# Build a simple box
with BuildPart() as p:
    Box(10, 10, 10)
result = p.part

# Verify it has volume
vol = result.volume
assert vol > 0, f'Smoke test box has zero volume: {vol}'

# Export and load with trimesh
tmp = tempfile.mktemp(suffix='.stl')
export_stl(result, tmp)
import trimesh
mesh = trimesh.load(tmp)
assert mesh.is_watertight, 'Smoke test mesh is not watertight'
print(f'    Smoke test: OK (volume={vol:.1f}mm^3, watertight={mesh.is_watertight})')
os.remove(tmp)
"

echo ""
echo "========================================================"
echo "  Ready to use!"
echo ""
echo "  Run build123d scripts with:"
echo "    python script.py"
echo ""
echo "  Render preview with:"
echo "    python $SKILL_DIR/scripts/render_preview.py part.stl preview.png"
echo ""
echo "  Skill files:"
echo "    $SKILL_DIR/SKILL.md"
echo "    $SKILL_DIR/BUILD123D_REFERENCE.md"
echo "========================================================"
