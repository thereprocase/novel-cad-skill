"""Shared pytest configuration for novel-cad-skill tests."""

import sys
from pathlib import Path

# Ensure lib/ and scripts/ are importable
_SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SKILL_DIR / "lib"))
sys.path.insert(0, str(_SKILL_DIR / "scripts"))
