"""Tests for lib/mesh_utils.py — shared tessellation module.

These tests verify the module structure and API. STEP-loading tests
require build123d or CadQuery + a fixture file. Tests that need
fixtures are marked and will skip if fixtures aren't available.
"""

import sys
import pytest
import importlib
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SKILL_DIR / "lib"))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class TestModuleStructure:
    """Verify mesh_utils exports the expected API."""

    def test_imports(self):
        import mesh_utils
        assert hasattr(mesh_utils, "load_mesh_from_step")
        assert hasattr(mesh_utils, "load_mesh_auto")
        assert hasattr(mesh_utils, "load_face_groups_from_step")
        assert hasattr(mesh_utils, "tessellate_occ_solid")
        assert hasattr(mesh_utils, "TESSELLATION_TOLERANCE")

    def test_tolerance_is_005(self):
        from mesh_utils import TESSELLATION_TOLERANCE
        assert TESSELLATION_TOLERANCE == 0.05

    def test_functions_are_callable(self):
        from mesh_utils import load_mesh_from_step, load_mesh_auto, load_face_groups_from_step
        assert callable(load_mesh_from_step)
        assert callable(load_mesh_auto)
        assert callable(load_face_groups_from_step)


class TestLoadMeshFromStep:
    """Tests that require a STEP fixture file."""

    @pytest.fixture
    def good_box_step(self):
        path = FIXTURES_DIR / "good_box.step"
        if not path.exists():
            pytest.skip("good_box.step fixture not available yet")
        return str(path)

    def test_loads_trimesh(self, good_box_step):
        from mesh_utils import load_mesh_from_step
        import trimesh
        mesh = load_mesh_from_step(good_box_step)
        assert isinstance(mesh, trimesh.Trimesh)
        assert len(mesh.vertices) > 0
        assert len(mesh.faces) > 0

    def test_bounding_box_reasonable(self, good_box_step):
        from mesh_utils import load_mesh_from_step
        mesh = load_mesh_from_step(good_box_step)
        extents = mesh.bounding_box.extents
        # good_box should be 10x10x10
        for dim in extents:
            assert dim > 0.1, "Bounding box dimension too small"
            assert dim < 1000, "Bounding box dimension too large"


class TestLoadMeshAuto:
    """Test the auto-detection path."""

    def test_nonexistent_file_raises(self):
        from mesh_utils import load_mesh_auto
        with pytest.raises(Exception):
            load_mesh_auto("/nonexistent/file.step")

    @pytest.fixture
    def stl_fixture(self):
        path = FIXTURES_DIR / "non_manifold.stl"
        if not path.exists():
            pytest.skip("non_manifold.stl fixture not available yet")
        return str(path)

    def test_loads_stl(self, stl_fixture):
        from mesh_utils import load_mesh_auto
        import trimesh
        mesh = load_mesh_auto(stl_fixture)
        assert isinstance(mesh, trimesh.Trimesh)


class TestConsistentTessellation:
    """Verify all consumers get the same tessellation."""

    def test_validate_manifold_uses_mesh_utils(self):
        """validate_manifold.py should import from mesh_utils, not do its own tessellation."""
        script_path = _SKILL_DIR / "scripts" / "validate_manifold.py"
        source = script_path.read_text()
        assert "mesh_utils" in source, "validate_manifold.py should use mesh_utils"
        assert "solid.tessellate" not in source, "validate_manifold.py should not use build123d tessellate"

    def test_check_printability_uses_mesh_utils(self):
        script_path = _SKILL_DIR / "scripts" / "check_printability.py"
        source = script_path.read_text()
        assert "mesh_utils" in source or "load_mesh_auto" in source

    def test_export_3mf_uses_mesh_utils(self):
        script_path = _SKILL_DIR / "scripts" / "export_3mf.py"
        source = script_path.read_text()
        assert "mesh_utils" in source or "load_mesh_from_step" in source

    def test_render_preview_uses_mesh_utils(self):
        script_path = _SKILL_DIR / "scripts" / "render_preview.py"
        source = script_path.read_text()
        assert "mesh_utils" in source or "load_face_groups_from_step" in source

    def test_render_cross_sections_uses_mesh_utils(self):
        script_path = _SKILL_DIR / "scripts" / "render_cross_sections.py"
        source = script_path.read_text()
        assert "mesh_utils" in source or "load_mesh_auto" in source
